import json
import logging
import time
from html import escape
from typing import Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

from api.db.connection import get_db
from api.schemas.tasks import (
    TaskCheckResponse,
    TaskListItem,
    TaskOpenResponse,
)
from shared.db.tasks import (
    add_task_post_view,
    allocate_task_post_from_channel_post,
    get_task_channel_by_chat_id,
    get_next_view_post_task_for_user,
    get_view_post_task_for_user,
    increment_task_post_views,
)
from shared.db.abuse import count_recent_abuse_events, log_abuse_event
from shared.db.common import tx
from shared.config import TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)


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


def _telegram_api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def _build_client_mention(
        *,
        username: Optional[str],
 ) -> Optional[str]:
    normalized_username = (username or "").strip().lstrip("@")
    if normalized_username:
        return f"@{escape(normalized_username)}"

    return None


def _build_channel_alert_heading(client_mention: Optional[str]) -> str:
    if client_mention:
        return f"⚠️ {client_mention}, внимание по каналу просмотров"
    return "⚠️ Внимание по каналу просмотров"


def _build_low_posts_alert_text(
        *,
        client_mention: Optional[str],
        channel_title: str,
        remaining_post_slots: int,
        remaining_views: int,
) -> str:
    title = escape((channel_title or "").strip() or "твоего канала")
    return (
        f"{_build_channel_alert_heading(client_mention)}\n\n"
        f"Для {title} осталось просмотров примерно на {remaining_post_slots} поста\n"
        f"Остаток: {remaining_views} просмотров\n\n"
        "Если хочешь, чтобы новые посты продолжали попадать в задания без остановки, пополни лимит заранее"
    )


def _build_exhausted_posts_alert_text(
        *,
        client_mention: Optional[str],
        channel_title: str,
) -> str:
    title = escape((channel_title or "").strip() or "твоего канала")
    return (
        f"{_build_channel_alert_heading(client_mention)}\n\n"
        f"Для {title} просмотры закончились\n"
        "Новые посты больше не будут попадать в задания\n\n"
        "Пополни лимит, чтобы канал снова начал участвовать в просмотрах"
    )


def _send_low_posts_alert(*, user_id: int, text: str) -> None:
    if not TELEGRAM_BOT_TOKEN:
        return

    payload = json.dumps(
        {
            "chat_id": int(user_id),
            "text": text,
            "parse_mode": "HTML",
        },
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib_request.Request(
        _telegram_api_url("sendMessage"),
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    with urllib_request.urlopen(request, timeout=15) as response:
        response_payload = json.loads(response.read().decode("utf-8"))

    if not response_payload.get("ok"):
        raise RuntimeError(response_payload.get("description") or "Telegram API request failed")


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


async def _is_task_already_completed(db, user_id: int, task_post_id: int) -> bool:
    async with db.execute(
            """
        SELECT 1
        FROM task_post_views
        WHERE user_id = ? AND task_post_id = ?
        LIMIT 1
        """,
            (int(user_id), int(task_post_id)),
    ) as cur:
        row = await cur.fetchone()
        return row is not None


async def _apply_task_reward(
        db,
        *,
        user_id: int,
        reward: float,
        reason: str,
        meta: dict,
) -> float:
    updated_user = await db.execute(
        """
        UPDATE users
        SET balance = COALESCE(balance, 0) + ?
        WHERE user_id = ?
        """,
        (float(reward), int(user_id)),
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
            float(reward),
            reason,
            json.dumps(meta, ensure_ascii=False),
        ),
    )

    return await _get_user_balance_safe(db, user_id)


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


async def open_view_post_task(db, user_id: int, row) -> TaskOpenResponse:
    hold_seconds = int(row["view_seconds"] or 0)

    recent_clicks = await count_recent_abuse_events(db, user_id, "task_view_click", 1)
    if hold_seconds > 0 and recent_clicks >= 60 / hold_seconds:
        return TaskOpenResponse(
            ok=False,
            task_id=int(row["id"]),
            message="⏳ Слишком часто.\nПопробуй через минуту.",
            opened_at=0,
            hold_seconds=hold_seconds,
            can_check_at=0,
            chat_id=row["chat_id"],
            channel_post_id=int(row["channel_post_id"]),
            post_url=build_task_post_url(
                row["chat_id"],
                row["channel_post_id"],
            ),
            session_id=None,
        )

    already_completed = await _is_task_already_completed(db, user_id, int(row["id"]))
    if already_completed:
        return TaskOpenResponse(
            ok=False,
            task_id=int(row["id"]),
            message="Задание уже засчитано",
            opened_at=0,
            hold_seconds=hold_seconds,
            can_check_at=0,
            chat_id=row["chat_id"],
            channel_post_id=int(row["channel_post_id"]),
            post_url=build_task_post_url(
                row["chat_id"],
                row["channel_post_id"],
            ),
            session_id=None,
        )

    await log_abuse_event(db, user_id, "task_view_click")

    opened_at = int(time.time())
    can_check_at = opened_at + hold_seconds

    return TaskOpenResponse(
        ok=True,
        task_id=int(row["id"]),
        message="Показываю пост...",
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
    task_post_id = int(row["id"])
    reward = float(row["reward"] or 0)

    already_completed = await _is_task_already_completed(db, user_id, task_post_id)
    if already_completed:
        current_balance = await _get_user_balance_safe(db, user_id)
        await db.rollback()
        return TaskCheckResponse(
            ok=True,
            task_id=task_post_id,
            status="already_completed",
            message="Задание уже засчитано",
            reward_granted=0,
            new_balance=current_balance,
            task_completed=True,
        )

    inserted = await add_task_post_view(db, user_id, task_post_id, reward)
    if not inserted:
        current_balance = await _get_user_balance_safe(db, user_id)
        await db.rollback()
        return TaskCheckResponse(
            ok=True,
            task_id=task_post_id,
            status="already_completed",
            message="Задание уже засчитано",
            reward_granted=0,
            new_balance=current_balance,
            task_completed=True,
        )

    updated_post = await increment_task_post_views(db, task_post_id)
    if not updated_post:
        current_balance = await _get_user_balance_safe(db, user_id)
        await db.rollback()
        return TaskCheckResponse(
            ok=True,
            task_id=task_post_id,
            status="rejected",
            message="Лимит просмотров достигнут или задание уже недоступно",
            reward_granted=0,
            new_balance=current_balance,
            task_completed=False,
        )

    new_balance = await _apply_task_reward(
        db,
        user_id=int(user_id),
        reward=reward,
        reason="view_post_bonus",
        meta={
            "task_post_id": task_post_id,
            "channel_id": int(row["channel_id"]),
            "channel_post_id": int(row["channel_post_id"]),
        },
    )

    await db.commit()

    return TaskCheckResponse(
        ok=True,
        task_id=task_post_id,
        status="completed",
        message="Просмотр засчитан",
        reward_granted=reward,
        new_balance=new_balance,
        task_completed=True,
    )


async def open_task_by_type(db, user_id: int, row) -> TaskOpenResponse:
    task_type = get_task_type_from_row(row)

    if task_type == "view_post":
        return await open_view_post_task(db, user_id, row)

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
        if not row:
            return None

        item = map_task_row_to_item(row)
        item.already_completed = await _is_task_already_completed(db, user_id, item.id)
        item.status = "completed" if item.already_completed else "available"
        item.can_claim = not item.already_completed
        return item
    finally:
        await db.close()


async def ingest_task_channel_post_message(
        *,
        chat_id: str,
        channel_post_id: int,
        title: Optional[str],
        reward: float = 0.01,
) -> dict[str, bool]:
    db = await get_db()
    try:
        async with tx(db, immediate=True):
            allocated = await allocate_task_post_from_channel_post(
                db=db,
                chat_id=str(chat_id),
                channel_post_id=int(channel_post_id),
                title=title,
                reward=float(reward),
            )

            channel = None
            if allocated:
                channel = await get_task_channel_by_chat_id(db, str(chat_id))

        if allocated and channel:
            client_user_id = channel["client_user_id"]
            remaining_views = int(channel["remaining_views"] or 0)
            views_per_post = int(channel["views_per_post"] or 0)
            remaining_post_slots = remaining_views // views_per_post if views_per_post > 0 else 0
            client_mention = _build_client_mention(
                username=channel["client_username"],
            )

            if client_user_id is not None and remaining_post_slots in {0, 3}:
                try:
                    _send_low_posts_alert(
                        user_id=int(client_user_id),
                        text=(
                            _build_exhausted_posts_alert_text(
                                client_mention=client_mention,
                                channel_title=channel["title"] or title or str(chat_id),
                            )
                            if remaining_post_slots == 0
                            else _build_low_posts_alert_text(
                                client_mention=client_mention,
                                channel_title=channel["title"] or title or str(chat_id),
                                remaining_post_slots=remaining_post_slots,
                                remaining_views=remaining_views,
                            )
                        ),
                    )
                except (urllib_error.HTTPError, urllib_error.URLError, RuntimeError) as exc:
                    logger.warning(
                        "Failed to notify client about task channel stock state channel_id=%s client_user_id=%s detail=%s",
                        channel["id"],
                        client_user_id,
                        exc,
                    )

        return {
            "allocated": bool(allocated),
        }
    finally:
        await db.close()


async def open_task_for_user(user_id: int, task_id: int) -> TaskOpenResponse:
    db = await get_db()
    try:
        row = await get_view_post_task_for_user(db, user_id, task_id)
        if not row:
            return TaskOpenResponse(
                ok=False,
                task_id=task_id,
                message="Task not found",
                opened_at=0,
                hold_seconds=0,
                can_check_at=0,
                chat_id=None,
                channel_post_id=None,
                post_url=None,
                session_id=None,
            )

        response = await open_task_by_type(db, user_id, row)
        await db.commit()
        return response
    finally:
        await db.close()


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

        return await check_task_by_type(db, user_id, row)

    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()
