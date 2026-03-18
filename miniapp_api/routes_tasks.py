from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from .auth_session import get_bearer_token
from .routes_auth import SESSIONS
from .schemas import MiniAppNextTaskResponse, MiniAppTask

router = APIRouter()


def get_demo_next_task_for_user(user_id: int):
    # Временная заглушка для ШАГА 4.
    # На следующем шаге заменим на реальную выборку из БД.
    return {
        "id": 101,
        "type": "view_post",
        "title": "Просмотреть пост в канале",
        "reward": 0.03,
        "hold_seconds": 3,
        "telegram_url": "https://t.me/telegram/1",
        "channel_name": "@telegram",
        "message_id": 1,
    }


@router.get("/api/tasks/next", response_model=MiniAppNextTaskResponse)
async def get_next_task(authorization: Optional[str] = Header(default=None)):
    token = get_bearer_token(authorization)

    session_data = SESSIONS.get(token)
    if not session_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    task_data = get_demo_next_task_for_user(session_data["user_id"])

    if not task_data:
        return MiniAppNextTaskResponse(ok=True, task=None)

    return MiniAppNextTaskResponse(
        ok=True,
        task=MiniAppTask(**task_data),
    )
