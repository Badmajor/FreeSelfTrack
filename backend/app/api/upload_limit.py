import asyncio
import time

from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings

MAX_REQUEST = 130 * 1024 * 1024


class ChatUploadLimit:
    """Reject excess transfers before parsing; slots cover the entire response lifetime."""

    def __init__(self, app: ASGIApp):
        self.app = app
        self.uploads = 0
        self.downloads = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        upload = scope["method"] == "POST" and scope["path"].endswith("/comments")
        download = "/attachments/" in scope["path"] and scope["path"].endswith("/content")
        if not upload and not download:
            await self.app(scope, receive, send)
            return
        settings = get_settings()
        counter = "uploads" if upload else "downloads"
        limit = settings.attachment_upload_slots if upload else settings.attachment_download_slots
        if getattr(self, counter) >= limit:
            await JSONResponse(
                {"detail": "Attachment transfer capacity exceeded"},
                429,
                headers={"Retry-After": "5"},
            )(scope, receive, send)
            return
        length = dict(scope["headers"]).get(b"content-length", b"0")
        if upload and length.isdigit() and int(length) > MAX_REQUEST:
            await JSONResponse({"detail": "Upload request exceeds 130 MB"}, 413)(
                scope, receive, send
            )
            return
        setattr(self, counter, getattr(self, counter) + 1)
        received = 0
        started = False
        deadline = time.monotonic() + settings.attachment_request_seconds

        def timeout() -> float:
            return max(0, min(settings.attachment_idle_seconds, deadline - time.monotonic()))

        async def limited_receive() -> Message:
            nonlocal received
            if not upload:
                # StreamingResponse listens for disconnects while sending. A quiet
                # receive channel is normal for downloads, not an idle upload.
                return await receive()
            try:
                message = await asyncio.wait_for(receive(), timeout())
            except TimeoutError:
                raise HTTPException(408, "Attachment transfer timed out") from None
            received += len(message.get("body", b""))
            if upload and received > MAX_REQUEST:
                raise HTTPException(413, "Upload request exceeds 130 MB")
            return message

        async def limited_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await asyncio.wait_for(send(message), timeout())

        try:
            await self.app(scope, limited_receive, limited_send)
        except TimeoutError:
            if started:
                raise  # Disconnect after headers; never append a JSON error to file bytes.
            await JSONResponse({"detail": "Attachment transfer timed out"}, 408)(
                scope, receive, send
            )
        finally:
            setattr(self, counter, getattr(self, counter) - 1)
