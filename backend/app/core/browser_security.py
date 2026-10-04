"""Response policy outside the error handler, including streaming/error responses."""

from fastapi import FastAPI
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

API_CSP = "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
HEADERS = {
    "Content-Security-Policy": API_CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "X-Frame-Options": "DENY",
}


class BrowserSecurity:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def secure_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in HEADERS.items():
                    # Attachments retain their stricter sandbox policy.
                    if name not in headers:
                        headers[name] = value
                # Uvicorn must run with --no-proxy-headers. TLS proxies add HSTS
                # themselves; untrusted forwarded scheme headers have no effect.
                if scope["scheme"] == "https":
                    headers["Strict-Transport-Security"] = "max-age=31536000"
            await send(message)

        await self.app(scope, receive, secure_send)


class SecureFastAPI(FastAPI):
    def build_middleware_stack(self) -> ASGIApp:
        return BrowserSecurity(super().build_middleware_stack())
