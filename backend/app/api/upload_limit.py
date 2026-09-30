from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_REQUEST = 130 * 1024 * 1024


class ChatUploadLimit:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not scope["path"].endswith("/comments")
        ):
            await self.app(scope, receive, send)
            return
        length = dict(scope["headers"]).get(b"content-length", b"0")
        if length.isdigit() and int(length) > MAX_REQUEST:
            await JSONResponse({"detail": "Upload request exceeds 130 MB"}, status_code=413)(
                scope, receive, send
            )
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > MAX_REQUEST:
                raise HTTPException(413, "Upload request exceeds 130 MB")
            return message

        await self.app(scope, limited_receive, send)
