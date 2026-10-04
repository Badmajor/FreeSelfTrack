from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Header, HTTPException, Response

from app.core.config import get_settings

REFRESH_COOKIE = "__Secure-fst-refresh"


def csrf_protection(
    origin: Annotated[str | None, Header()] = None,
    x_csrf_protection: Annotated[str | None, Header()] = None,
) -> None:
    url = urlsplit(get_settings().public_app_url)
    expected_origin = f"{url.scheme}://{url.netloc}"
    if origin != expected_origin or x_csrf_protection != "1":
        raise HTTPException(403, "Invalid request origin")


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        secure=True,
        httponly=True,
        samesite="strict",
        path=get_settings().api_prefix + "/auth",
        max_age=get_settings().refresh_expire_days * 86400,
    )
    response.headers["Cache-Control"] = "no-store"


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        secure=True,
        httponly=True,
        samesite="strict",
        path=get_settings().api_prefix + "/auth",
    )
    response.headers["Cache-Control"] = "no-store"
