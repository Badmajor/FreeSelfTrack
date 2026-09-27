from uuid import UUID

from fastapi import Header, HTTPException, status


async def current_user_id(x_user_id: str | None = Header(default=None)) -> UUID:
    if x_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    try:
        return UUID(x_user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity"
        ) from exc
