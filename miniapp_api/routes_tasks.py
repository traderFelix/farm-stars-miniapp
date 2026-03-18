import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from .auth_session import get_bearer_token
from .db import (
    add_balance_to_user,
    complete_task_for_user,
    fetch_next_task_for_user,
    fetch_task_by_id,
    fetch_task_event,
)
from .routes_auth import SESSIONS
from .schemas import (
    MiniAppNextTaskResponse,
    MiniAppTask,
    MiniAppTaskActionRequest,
    MiniAppTaskCheckResponse,
    MiniAppTaskOpenResponse,
)
from .db import open_task_for_user

router = APIRouter()


@router.get("/api/tasks/next", response_model=MiniAppNextTaskResponse)
async def get_next_task(authorization: Optional[str] = Header(default=None)):
    token = get_bearer_token(authorization)
    session_data = SESSIONS.get(token)

    if not session_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    row = fetch_next_task_for_user(int(session_data["user_id"]))
    if not row:
        return MiniAppNextTaskResponse(ok=True, task=None)

    return MiniAppNextTaskResponse(
        ok=True,
        task=MiniAppTask(
            id=int(row["id"]),
            type=str(row["type"]),
            title=str(row["title"]),
            reward=float(row["reward"]),
            hold_seconds=int(row["hold_seconds"]),
            telegram_url=str(row["telegram_url"]),
            channel_name=row["channel_name"],
            message_id=row["message_id"],
        ),
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

    task_row = fetch_task_by_id(int(payload.task_id))
    if not task_row or int(task_row["is_active"]) != 1:
        raise HTTPException(status_code=404, detail="Task not found")

    result = open_task_for_user(
        user_id=int(session_data["user_id"]),
        task_id=int(payload.task_id),
        reward=float(task_row["reward"]),
    )

    if result.get("error") == "Task already completed":
        raise HTTPException(status_code=400, detail="Task already completed")

    return MiniAppTaskOpenResponse(
        ok=True,
        opened_at=int(result["opened_at"]),
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
    task_row = fetch_task_by_id(int(payload.task_id))

    if not task_row or int(task_row["is_active"]) != 1:
        raise HTTPException(status_code=404, detail="Task not found")

    event_row = fetch_task_event(user_id, int(payload.task_id))
    if not event_row:
        raise HTTPException(status_code=400, detail="Task was not opened")

    if str(event_row["status"]) == "completed":
        raise HTTPException(status_code=400, detail="Task already completed")

    now_ts = int(time.time())
    opened_at = int(event_row["opened_at"] or 0)
    hold_seconds = int(task_row["hold_seconds"])

    if now_ts - opened_at < hold_seconds:
        left = hold_seconds - (now_ts - opened_at)
        raise HTTPException(
            status_code=400,
            detail=f"Hold time not reached. Wait {left} more sec",
        )

    reward = float(task_row["reward"])
    complete_task_for_user(user_id, int(payload.task_id), reward)
    new_balance = add_balance_to_user(user_id, reward)

    return MiniAppTaskCheckResponse(
        ok=True,
        reward=reward,
        new_balance=new_balance,
        message="Просмотр засчитан",
    )