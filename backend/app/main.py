import logging

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.chat import router as chat_router
from app.api.router import router
from app.api.upload_limit import ChatUploadLimit
from app.core.config import get_settings

settings = get_settings()
# Uvicorn configures its own loggers, not the root logger. Enable sanitized auth
# outcomes explicitly so successful/failed attempts are visible in normal deployments.
security_logger = logging.getLogger("security.auth")
security_logger.setLevel(logging.INFO)
if not security_logger.handlers:
    security_handler = logging.StreamHandler()
    security_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    security_logger.addHandler(security_handler)
app = FastAPI(title="FreeSelfTrack API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ChatUploadLimit)
app.include_router(router, prefix=settings.api_prefix)
app.include_router(chat_router, prefix=settings.api_prefix)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    if not request.url.path.startswith(settings.api_prefix + "/auth/"):
        return await request_validation_exception_handler(request, exc)
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
                for error in exc.errors()
            ]
        },
    )
