import time
from typing import Optional

from api.db.connection import get_db
from api.schemas.tasks import (
    TaskCheckResponse,
    TaskListItem,
    TaskListResponse,
    TaskOpenResponse,
)
from shared.db.tasks import (
    get_next_view_post_task_for_user,
    get_view_post_task_for_user,
)


def build_task_post_url(chat_id: Optional[str], channel_post_id: Optional[str]) -> Optional[str]:
    if not chat_id or not channel_post_id:
        return None

    chat = str(chat_id).strip()

    if chat.startswith("@"):
        return f"https://t.me/{chat[1:]}/{channel_post_id}"

    return None


def map_task_row_to_item(row) -> TaskListItem:
    return TaskListItem(
        id=int(row["id"]),
        type="view_post",
        title="Посмотреть пост",
        description="Открой пост и подержи нужное время",
        reward=float(row["reward"] or 0),
        status="available",
        chat_id=row["chat_id"],
        channel_post_id=int(row["channel_post_id"]),
        post_url=build_task_post_url(row["chat_id"], row["channel_post_id"]),
        already_completed=False,
        can_claim=False,
        hold_seconds=int(row["view_seconds"] or 0),
    )


async def list_tasks_for_user(user_id: int) -> TaskListResponse:
    db = await get_db()
    try:
        row = await get_next_view_post_task_for_user(db, user_id)
    finally:
        await db.close()

    if not row:
        return TaskListResponse(items=[])

    return TaskListResponse(items=[map_task_row_to_item(row)])


async def open_task_for_user(user_id: int, task_id: int) -> TaskOpenResponse:
    db = await get_db()
    try:
        row = await get_view_post_task_for_user(db, user_id, task_id)
    finally:
        await db.close()

    if not row:
        return TaskOpenResponse(
            ok=False,
            task_id=task_id,
            opened_at=0,
            hold_seconds=0,
            chat_id=None,
            channel_post_id=None,
            post_url=None,
            session_id=None,
        )

    return TaskOpenResponse(
        ok=True,
        task_id=int(row["id"]),
        opened_at=int(time.time()),
        hold_seconds=int(row["view_seconds"] or 0),
        chat_id=row["chat_id"],
        channel_post_id=int(row["channel_post_id"]),
        post_url=build_task_post_url(row["chat_id"], row["channel_post_id"]),
        session_id=None,
    )


async def check_task_for_user(user_id: int, task_id: int) -> TaskCheckResponse:
    db = await get_db()
    try:
        row = await get_view_post_task_for_user(db, user_id, task_id)
    finally:
        await db.close()

    if not row:
        return TaskCheckResponse(
            ok=False,
            task_id=task_id,
            status="rejected",
            message="Task not found",
            reward_granted=0,
            new_balance=0,
            task_completed=False,
        )

    return TaskCheckResponse(
        ok=True,
        task_id=int(row["id"]),
        status="completed",
        message="Просмотр засчитан",
        reward_granted=float(row["reward"] or 0),
        new_balance=0,
        task_completed=True,
    )