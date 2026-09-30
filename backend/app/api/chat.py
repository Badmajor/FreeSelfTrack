from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.router import translate_errors
from app.db.session import get_session
from app.dependencies.auth import current_user_id
from app.schemas.chat import CommentCreate, CommentPage, CommentResponse
from app.services.chat import MAX_FILE_SIZE, MAX_FILES, ChatService, Uploaded

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


@router.post("/tasks/{task_id}/comments", response_model=CommentResponse, status_code=201)
async def post_comment(
    task_id: UUID,
    metadata: Annotated[str, Form(max_length=20000)],
    files: Annotated[list[UploadFile] | None, File()] = None,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    files = files or []
    service = ChatService(session)
    await translate_errors(service.authorize)(user_id, task_id)
    try:
        data = CommentCreate.model_validate_json(metadata)
    except ValidationError as exc:
        raise HTTPException(422, "Invalid message metadata") from exc
    if len(files) > MAX_FILES:
        raise HTTPException(422, "At most 5 files per message")
    uploads = []
    for upload in files:
        content = bytearray()
        while chunk := await upload.read(1024 * 1024):
            content.extend(chunk)
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(413, "File exceeds 25 MB")
        uploads.append(Uploaded(upload.filename or "file", bytes(content)))
    return await translate_errors(service.create)(user_id, task_id, data, uploads)


@router.get("/attachments/{attachment_id}/content")
async def attachment(
    attachment_id: UUID,
    preview: bool = False,
    user_id: UUID = Depends(current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Any:
    file = await translate_errors(ChatService(session).attachment)(user_id, attachment_id)
    disposition = "inline" if preview and file.media_type.startswith("image/") else "attachment"
    filename = quote(file.filename, safe="")
    return Response(
        file.content,
        media_type=file.media_type,
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{filename}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
