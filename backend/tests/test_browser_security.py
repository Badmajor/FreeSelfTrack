import secrets

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from starlette.responses import Response

from app.core.browser_security import HEADERS, SecureFastAPI
from app.core.config import Settings
from app.main import app
from tests.test_sessions import account, bearer


@pytest.mark.parametrize(
    "origin",
    [
        "https://example..com",
        "https://example,com",
        "https://-example.com",
        "*",
        "https://*.example.com",
        "null",
        "ftp://example.com",
        "https://example.com/",
        "https://example.com/path",
        "https://user@example.com",
        "https://example.com?x=1",
        "https://example.com#x",
        "https://example.com:bad",
        "https://example.com:0",
        "https://example.com:",
        "https://example.com\\evil",
        " https://example.com",
    ],
)
def test_unsafe_origins_fail_startup(origin):
    for field in ("cors_origins", "public_app_url"):
        with pytest.raises(ValidationError):
            Settings(
                database_url="sqlite://",
                auth_secret_key=secrets.token_urlsafe(48),
                **{field: [origin] if field == "cors_origins" else origin},
            )


@pytest.mark.parametrize(
    "hosts", [["*"], ["*.example.com"], [], ["https://example.com"], ["host/path"]]
)
def test_unsafe_hosts_fail_startup(hosts):
    with pytest.raises(ValidationError):
        Settings(
            database_url="sqlite://", auth_secret_key=secrets.token_urlsafe(48), trusted_hosts=hosts
        )


async def test_cors_contract(client):
    headers = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type,x-csrf-protection",
    }
    response = await client.options("/api/auth/refresh", headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"
    for override in (
        {"Origin": "https://evil.example"},
        {"Origin": "null"},
        {"Access-Control-Request-Method": "TRACE"},
        {"Access-Control-Request-Headers": "x-unapproved"},
    ):
        denied = await client.options("/api/auth/refresh", headers=headers | override)
        assert denied.status_code == 400
        if "Origin" in override:
            assert "access-control-allow-origin" not in denied.headers
    login = await account(client)
    denied_read = await client.get(
        "/api/organizations", headers=bearer(login) | {"Origin": "https://evil.example"}
    )
    # CORS prevents browser disclosure, not server-side bearer authorization.
    assert denied_read.status_code == 200
    assert "access-control-allow-origin" not in denied_read.headers
    assert (await client.get("/api/organizations")).status_code == 401


async def test_headers_hosts_and_untrusted_forwarding(client):
    for path in ("/health", "/missing", "/api/organizations"):
        response = await client.get(path)
        for name, value in HEADERS.items():
            assert response.headers[name] == value
        assert response.headers["strict-transport-security"] == "max-age=31536000"
    response = await client.get(
        "/health", headers={"Host": "evil.example", "X-Forwarded-Host": "localhost"}
    )
    assert response.status_code == 400
    assert response.headers["x-frame-options"] == "DENY"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as http:
        response = await http.get(
            "/health", headers={"X-Forwarded-Proto": "https", "Forwarded": "proto=https"}
        )
        assert response.status_code == 200
        assert "strict-transport-security" not in response.headers


async def test_unhandled_errors_and_attachment_headers():
    application = SecureFastAPI()

    @application.get("/error")
    async def error():
        raise RuntimeError("test")

    @application.get("/attachment")
    async def attachment():
        return Response(
            b"test",
            headers={
                "Content-Security-Policy": "default-src 'none'; sandbox",
                "Content-Disposition": "attachment; filename=test.txt",
                "Cache-Control": "private, no-store",
            },
        )

    async with AsyncClient(
        transport=ASGITransport(app=application, raise_app_exceptions=False),
        base_url="https://test",
    ) as client:
        error_response = await client.get("/error")
        assert error_response.status_code == 500
        for name, value in HEADERS.items():
            assert error_response.headers[name] == value
        response = await client.get("/attachment")
        assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"
        assert response.headers["content-disposition"] == "attachment; filename=test.txt"
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
