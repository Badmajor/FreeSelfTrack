"""Server-generated correlation IDs; client headers are never trusted as audit identity."""

from contextvars import ContextVar
from uuid import UUID, uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id: ContextVar[UUID | None] = ContextVar("audit_request_id", default=None)


class AuditCorrelation:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        correlation = uuid4()
        token = request_id.set(correlation)

        async def correlated_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append(
                    (b"x-request-id", str(correlation).encode("ascii"))
                )
            await send(message)

        try:
            await self.app(scope, receive, correlated_send)
        finally:
            request_id.reset(token)
