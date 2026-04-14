from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from .auth_session import get_bearer_token
from .db import fetch_user_by_id
from .schemas import MiniAppMeResponse, MiniAppMeUser
from .routes_auth import MiniAppSessionData, SESSIONS

router = APIRouter()


@router.get("/api/me", response_model=MiniAppMeResponse)
async def get_me(authorization: Optional[str] = Header(default=None)):
    token = get_bearer_token(authorization)

    session_data: Optional[MiniAppSessionData] = SESSIONS.get(token)
    if not session_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    row = fetch_user_by_id(session_data["user_id"])
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    return MiniAppMeResponse(
        ok=True,
        user=MiniAppMeUser(
            id=int(row["user_id"]),
            balance=float(row["balance"] or 0),
            role="user",
            withdrawal_ability=0.0,
        ),
    )
