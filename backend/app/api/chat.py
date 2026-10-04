from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote
from uuid import UUID

from anyio import CancelScope
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send
from urllib3.exceptions import HTTPError

from app.api.router import translate_errors
from app.core.object_storage import CHUNK_SIZE, get_storage
from app.db.session import get_session
from app.dependencies.auth import current_user_id
from app.schemas.chat import CommentCreate, CommentPage, CommentResponse
from app.services.attachment_files import SAFE_IMAGES
from app.services.chat import ChatService

router = APIRouter()


@router.get("/tasks/{task_id}/comments", response_model=CommentPage)
async def comments(
    task_id: UUID,
    limit: int = Query(50, ge=1, le=50),
    before: int | None = Query(None, ge=1, le=2147483647),
    after: int | None = Query(None, ge=0, le=2147483647),
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(ChatService(session).page)(user_id, task_id, limit, before, after)


@router.get("/tasks/{task_id}/comments/{comment_id}", response_model=CommentResponse)
async def comment(
    task_id: UUID,
    comment_id: UUID,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    return await translate_errors(ChatService(session).get)(user_id, task_id, comment_id)


@router.post(
    "/tasks/{task_id}/comments",
    response_model=CommentResponse,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["metadata"],
                        "properties": {
                            "metadata": {"type": "string", "maxLength": 20000},
                            "files": {
                                "type": "array",
                                "maxItems": 5,
                                "items": {"type": "string", "format": "binary"},
                            },
                        },
                    }
                }
            },
        }
    },
)
async def post_comment(
    task_id: UUID,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    service = ChatService(session)
    await translate_errors(service.authorize)(user_id, task_id)
    try:
        async with request.form(max_files=5, max_fields=1, max_part_size=20000) as form:
            metadata = form.get("metadata")
            files = form.getlist("files")
            if (
                not isinstance(metadata, str)
                or len(metadata) > 20000
                or any(not isinstance(file, UploadFile) for file in files)
                or any(key not in {"metadata", "files"} for key in form)
            ):
                raise HTTPException(422, "Invalid message metadata or files")
            try:
                data = CommentCreate.model_validate_json(metadata)
            except ValidationError:
                raise HTTPException(422, "Invalid message metadata") from None
            uploads = await translate_errors(service.prepare)(files)
            return await translate_errors(service.create)(user_id, task_id, data, uploads)
    except StarletteHTTPException as exc:
        if exc.status_code == 400:
            raise HTTPException(422, "Invalid multipart message or too many files") from None
        raise
    except OSError:
        raise HTTPException(503, "Temporary upload storage unavailable") from None


@router.get("/attachments/{attachment_id}/content")
async def attachment(
    attachment_id: UUID,
    preview: bool = False,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    file = await translate_errors(ChatService(session).attachment)(user_id, attachment_id)
    disposition = "inline" if preview and file.media_type in SAFE_IMAGES.values() else "attachment"
    filename = quote(file.filename, safe="")

    async def open_object() -> Any:
        assert file.object_key is not None
        return await run_in_threadpool(get_storage().open, file.object_key)

    response = await translate_errors(open_object)()

    async def chunks() -> AsyncIterator[bytes]:
        try:
            while chunk := await run_in_threadpool(response.read, CHUNK_SIZE):
                yield chunk
        except (HTTPError, OSError):
            # Headers already sent: fail the stream rather than returning partial success.
            raise RuntimeError("Attachment transfer interrupted") from None

    class ProtectedResponse(StreamingResponse):
        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            try:
                await super().__call__(scope, receive, send)
            finally:
                with CancelScope(shield=True):
                    await run_in_threadpool(response.close)
                    await run_in_threadpool(response.release_conn)

    return ProtectedResponse(
        chunks(),
        media_type=file.media_type,
        headers={
            "Content-Length": str(file.size),
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{filename}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
