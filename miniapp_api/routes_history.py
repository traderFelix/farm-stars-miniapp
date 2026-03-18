from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from .auth_session import get_bearer_token
from .db import list_completed_tasks_for_user
from .routes_auth import SESSIONS
from .schemas import MiniAppHistoryItem, MiniAppHistoryResponse

router = APIRouter()


@router.get("/api/history", response_model=MiniAppHistoryResponse)
async def get_history(authorization: Optional[str] = Header(default=None)):
    token = get_bearer_token(authorization)
    session_data = SESSIONS.get(token)

    if not session_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    rows = list_completed_tasks_for_user(int(session_data["user_id"]), limit=20)

    items = [
        MiniAppHistoryItem(
            task_id=int(row["task_id"]),
            title=str(row["title"]),
            reward=float(row["reward"] or 0),
            completed_at=int(row["completed_at"] or 0),
        )
        for row in rows
    ]

    return MiniAppHistoryResponse(ok=True, items=items)