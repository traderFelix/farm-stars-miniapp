from typing import Optional

from fastapi import Header, HTTPException

from api.services.telegram_auth import decode_access_token


async def get_current_user_id(authorization: Optional[str] = Header(default=None)) -> int:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    payload = decode_access_token(token)

    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token payload")