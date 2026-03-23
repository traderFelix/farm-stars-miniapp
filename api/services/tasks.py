import json
import time
from typing import Optional

from api.db.connection import get_db
from api.schemas.tasks import (
    TaskCheckResponse,
    TaskListItem,
    TaskOpenResponse,
)
from shared.db.tasks import (
    add_task_post_view,
    get_next_view_post_task_for_user,
    get_view_post_task_for_user,
    increment_task_post_views,
)


def build_task_post_url(
        chat_id: Optional[str],
        channel_post_id: Optional[int],
) -> Optional[str]:
    if not chat_id or not channel_post_id:
        return None

    chat = str(chat_id).strip()

    if chat.startswith("@"):
        return f"https://t.me/{chat[1:]}/{channel_post_id}"

    return None


def build_task_title(row) -> str:
    channel_title = (row["channel_title"] or "").strip()
    if channel_title:
        return f"Посмотреть пост — {channel_title}"
    return "Посмотреть пост"


async def _get_user_balance_safe(db, user_id: int) -> float:
    async with db.execute(
            """
        SELECT COALESCE(balance, 0) AS balance
        FROM users
        WHERE user_id = ?
        LIMIT 1
        """,
            (int(user_id),),
    ) as cur:
        row = await cur.fetchone()
        if not row:
            return 0.0
        return float(row["balance"] or 0)


def get_task_type_from_row(row) -> str:
    return "view_post"


def map_view_post_task_row_to_item(row) -> TaskListItem:
    return TaskListItem(
        id=int(row["id"]),
        type="view_post",
        title=build_task_title(row),
        description="Открой пост и подержи нужное время",
        reward=float(row["reward"] or 0),
        status="available",
        chat_id=row["chat_id"],
        channel_post_id=int(row["channel_post_id"]),
        post_url=build_task_post_url(
            row["chat_id"],
            row["channel_post_id"],
        ),
        already_completed=False,
        can_claim=False,
        hold_seconds=int(row["view_seconds"] or 0),
    )


def map_task_row_to_item(row) -> TaskListItem:
    task_type = get_task_type_from_row(row)

    if task_type == "view_post":
        return map_view_post_task_row_to_item(row)

    raise ValueError(f"Unsupported task type: {task_type}")


async def open_view_post_task(row) -> TaskOpenResponse:
    opened_at = int(time.time())
    hold_seconds = int(row["view_seconds"] or 0)
    can_check_at = opened_at + hold_seconds

    return TaskOpenResponse(
        ok=True,
        task_id=int(row["id"]),
        opened_at=opened_at,
        hold_seconds=hold_seconds,
        can_check_at=can_check_at,
        chat_id=row["chat_id"],
        channel_post_id=int(row["channel_post_id"]),
        post_url=build_task_post_url(
            row["chat_id"],
            row["channel_post_id"],
        ),
        session_id=None,
    )


async def check_view_post_task(db, user_id: int, row) -> TaskCheckResponse:
    reward = float(row["reward"] or 0)

    inserted = await add_task_post_view(db, user_id, int(row["id"]), reward)
    if not inserted:
        current_balance = await _get_user_balance_safe(db, user_id)
        await db.rollback()
        return TaskCheckResponse(
            ok=True,
            task_id=int(row["id"]),
            status="already_completed",
            message="Задание уже засчитано",
            reward_granted=0,
            new_balance=current_balance,
            task_completed=True,
        )

    updated_post = await increment_task_post_views(db, int(row["id"]))
    if not updated_post:
        current_balance = await _get_user_balance_safe(db, user_id)
        await db.rollback()
        return TaskCheckResponse(
            ok=True,
            task_id=int(row["id"]),
            status="rejected",
            message="Лимит просмотров достигнут или задание уже недоступно",
            reward_granted=0,
            new_balance=current_balance,
            task_completed=False,
        )

    updated_user = await db.execute(
        """
        UPDATE users
        SET balance = COALESCE(balance, 0) + ?
        WHERE user_id = ?
        """,
        (reward, int(user_id)),
    )
    if updated_user.rowcount != 1:
        raise RuntimeError(f"User {user_id} not found while crediting reward")

    await db.execute(
        """
        INSERT INTO ledger (user_id, delta, reason, meta)
        VALUES (?, ?, ?, ?)
        """,
        (
            int(user_id),
            reward,
            "view_post_bonus",
            json.dumps(
                {
                    "task_post_id": int(row["id"]),
                    "channel_id": int(row["channel_id"]),
                    "channel_post_id": int(row["channel_post_id"]),
                },
                ensure_ascii=False,
            ),
        ),
    )

    new_balance = await _get_user_balance_safe(db, user_id)

    await db.commit()

    return TaskCheckResponse(
        ok=True,
        task_id=int(row["id"]),
        status="completed",
        message="Просмотр засчитан",
        reward_granted=reward,
        new_balance=new_balance,
        task_completed=True,
    )


async def open_task_by_type(row) -> TaskOpenResponse:
    task_type = get_task_type_from_row(row)

    if task_type == "view_post":
        return await open_view_post_task(row)

    return TaskOpenResponse(
        ok=False,
        task_id=int(row["id"]),
        opened_at=0,
        hold_seconds=0,
        can_check_at=0,
        chat_id=None,
        channel_post_id=None,
        post_url=None,
        session_id=None,
    )


async def check_task_by_type(db, user_id: int, row) -> TaskCheckResponse:
    task_type = get_task_type_from_row(row)

    if task_type == "view_post":
        return await check_view_post_task(db, user_id, row)

    current_balance = await _get_user_balance_safe(db, user_id)
    await db.rollback()
    return TaskCheckResponse(
        ok=False,
        task_id=int(row["id"]),
        status="rejected",
        message=f"Unsupported task type: {task_type}",
        reward_granted=0,
        new_balance=current_balance,
        task_completed=False,
    )


async def get_next_task_for_user(user_id: int) -> Optional[TaskListItem]:
    db = await get_db()
    try:
        row = await get_next_view_post_task_for_user(db, user_id)
    finally:
        await db.close()

    if not row:
        return None

    return map_task_row_to_item(row)


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
            can_check_at=0,
            chat_id=None,
            channel_post_id=None,
            post_url=None,
            session_id=None,
        )

    response: TaskOpenResponse = await open_task_by_type(row)
    return response


async def check_task_for_user(user_id: int, task_id: int) -> TaskCheckResponse:
    db = await get_db()
    try:
        await db.execute("BEGIN IMMEDIATE")

        row = await get_view_post_task_for_user(db, user_id, task_id)
        if not row:
            current_balance = await _get_user_balance_safe(db, user_id)
            await db.rollback()
            return TaskCheckResponse(
                ok=False,
                task_id=task_id,
                status="rejected",
                message="Task not found",
                reward_granted=0,
                new_balance=current_balance,
                task_completed=False,
            )

        response: TaskCheckResponse = await check_task_by_type(db, user_id, row)
        return response

    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()