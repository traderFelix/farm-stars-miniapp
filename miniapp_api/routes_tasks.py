import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from .auth_session import get_bearer_token
from .db import add_balance_to_user
from .routes_auth import SESSIONS
from .schemas import (
    MiniAppNextTaskResponse,
    MiniAppTask,
    MiniAppTaskActionRequest,
    MiniAppTaskCheckResponse,
    MiniAppTaskOpenResponse,
)

router = APIRouter()

# Временное хранилище открытий/зачетов.
# Потом вынесем в нормальную таблицу БД.
TASK_OPENS: dict[tuple[int, int], dict] = {}


def get_demo_next_task_for_user(user_id: int):
    channel_username = "telegram"
    message_id = 1

    return {
        "id": 101,
        "type": "view_post",
        "title": "Просмотреть пост",
        "reward": 0.03,
        "hold_seconds": 3,
        "telegram_url": f"https://t.me/{channel_username}/{message_id}",
        "channel_name": f"@{channel_username}",
        "message_id": message_id,
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


@router.post("/api/tasks/open", response_model=MiniAppTaskOpenResponse)
async def open_task(
        payload: MiniAppTaskActionRequest,
        authorization: Optional[str] = Header(default=None),
):
    token = get_bearer_token(authorization)

    session_data = SESSIONS.get(token)
    if not session_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    task_data = get_demo_next_task_for_user(session_data["user_id"])
    if not task_data or int(task_data["id"]) != int(payload.task_id):
        raise HTTPException(status_code=404, detail="Task not found")

    now_ts = int(time.time())
    key = (int(session_data["user_id"]), int(payload.task_id))

    existing = TASK_OPENS.get(key)
    if existing and existing.get("completed"):
        raise HTTPException(status_code=400, detail="Task already completed")

    TASK_OPENS[key] = {
        "opened_at": now_ts,
        "completed": False,
        "reward": float(task_data["reward"]),
        "hold_seconds": int(task_data["hold_seconds"]),
    }

    return MiniAppTaskOpenResponse(
        ok=True,
        opened_at=now_ts,
    )


@router.post("/api/tasks/check", response_model=MiniAppTaskCheckResponse)
async def check_task(
        payload: MiniAppTaskActionRequest,
        authorization: Optional[str] = Header(default=None),
):
    token = get_bearer_token(authorization)

    session_data = SESSIONS.get(token)
    if not session_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    user_id = int(session_data["user_id"])
    task_data = get_demo_next_task_for_user(user_id)

    if not task_data or int(task_data["id"]) != int(payload.task_id):
        raise HTTPException(status_code=404, detail="Task not found")

    key = (user_id, int(payload.task_id))
    open_data = TASK_OPENS.get(key)

    if not open_data:
        raise HTTPException(status_code=400, detail="Task was not opened")

    if open_data.get("completed"):
        raise HTTPException(status_code=400, detail="Task already completed")

    now_ts = int(time.time())
    opened_at = int(open_data["opened_at"])
    hold_seconds = int(open_data["hold_seconds"])

    if now_ts - opened_at < hold_seconds:
        left = hold_seconds - (now_ts - opened_at)
        raise HTTPException(
            status_code=400,
            detail=f"Hold time not reached. Wait {left} more sec",
        )

    reward = float(open_data["reward"])
    new_balance = add_balance_to_user(user_id, reward)

    open_data["completed"] = True
    TASK_OPENS[key] = open_data

    return MiniAppTaskCheckResponse(
        ok=True,
        reward=reward,
        new_balance=new_balance,
        message="Просмотр засчитан",
    )
