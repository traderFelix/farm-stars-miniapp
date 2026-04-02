import hmac
from typing import Optional

from fastapi import Header, HTTPException, status

from shared.config import BOT_INTERNAL_TOKEN


async def require_internal_token(
        x_internal_token: Optional[str] = Header(default=None),
) -> None:
    if not BOT_INTERNAL_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="BOT_INTERNAL_TOKEN is not configured",
        )

    if not x_internal_token or not hmac.compare_digest(x_internal_token, BOT_INTERNAL_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal token",
        )
