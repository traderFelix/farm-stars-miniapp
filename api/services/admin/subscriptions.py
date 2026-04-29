from __future__ import annotations

from typing import Any, Optional
from urllib import parse as urllib_parse

import aiosqlite
from fastapi import HTTPException

from api.services.admin.client_roles import ensure_client_role, sync_client_role_after_rebind
from shared.db.common import tx
from shared.db.subscriptions import (
    archive_subscription_task,
    create_subscription_task,
    get_subscription_task,
    list_subscription_tasks,
    reset_subscription_task_unavailable_notification,
    set_subscription_task_client,
    set_subscription_task_active,
    set_subscription_task_title,
)
from shared.db.users import get_user_by_id
from api.services.admin.telegram_channels import (
    try_fetch_telegram_channel_title,
    verified_telegram_channel_title,
)


def _serialize_task(row: Any) -> dict[str, Any]:
    instant_reward = round(float(row["instant_reward"] or 0), 2)
    daily_reward_total = round(float(row["daily_reward_total"] or 0), 2)
    return {
        "id": int(row["id"]),
        "chat_id": str(row["chat_id"]),
        "title": str(row["title"] or ""),
        "client_user_id": int(row["client_user_id"]) if row["client_user_id"] is not None else None,
        "client_username": (row["client_username"] or None) if "client_username" in row.keys() else None,
        "client_first_name": (row["client_first_name"] or None) if "client_first_name" in row.keys() else None,
        "channel_url": normalize_subscription_channel_url(str(row["channel_url"])),
        "instant_reward": instant_reward,
        "daily_reward_total": daily_reward_total,
        "daily_claim_days": int(row["daily_claim_days"] or 0),
        "total_reward": round(instant_reward + daily_reward_total, 2),
        "max_subscribers": int(row["max_subscribers"] or 0),
        "participants_count": int(row["participants_count"] or 0),
        "is_active": bool(row["is_active"] or 0),
        "is_archived": bool(row["is_archived"] or 0) if "is_archived" in row.keys() else False,
        "assignment_count": int(row["assignment_count"] or 0) if "assignment_count" in row.keys() else 0,
        "active_count": int(row["active_count"] or 0) if "active_count" in row.keys() else 0,
        "completed_count": int(row["completed_count"] or 0) if "completed_count" in row.keys() else 0,
        "abandoned_count": int(row["abandoned_count"] or 0) if "abandoned_count" in row.keys() else 0,
        "created_at": row["created_at"],
    }


def _normalize_text(value: Optional[str], *, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail=f"{field_name} не может быть пустым.")
    return normalized


def normalize_subscription_channel_url(value: Optional[str]) -> str:
    raw = _normalize_text(value, field_name="channel_url")

    if raw.startswith("@"):
        username = raw.lstrip("@").strip("/")
        if not username:
            raise HTTPException(status_code=400, detail="channel_url не может быть пустым.")
        return f"https://t.me/{username}"

    if raw.startswith("t.me/") or raw.startswith("telegram.me/") or raw.startswith("telegram.dog/"):
        raw = f"https://{raw}"

    if raw.startswith("tg://"):
        return raw

    try:
        parsed = urllib_parse.urlparse(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректная ссылка на канал.") from exc

    if parsed.scheme in {"http", "https"} and parsed.netloc:
        host = parsed.netloc.lower()
        if host in {"t.me", "www.t.me", "telegram.me", "telegram.dog"}:
            path = parsed.path.rstrip("/")
            if path.startswith("/s/"):
                path = path[2:]
            query = f"?{parsed.query}" if parsed.query else ""
            return f"https://t.me{path}{query}"
        return raw

    username = raw.strip().strip("/")
    if username:
        return f"https://t.me/{username.lstrip('@')}"

    raise HTTPException(status_code=400, detail="Некорректная ссылка на канал.")


def _normalize_reward(value: float, *, field_name: str) -> float:
    normalized = round(float(value), 2)
    if normalized < 0:
        raise HTTPException(status_code=400, detail=f"{field_name} не может быть меньше 0.")
    return normalized


def _normalize_non_negative_int(value: int, *, field_name: str) -> int:
    normalized = int(value)
    if normalized < 0:
        raise HTTPException(status_code=400, detail=f"{field_name} не может быть меньше 0.")
    return normalized


def _normalize_positive_int(value: int, *, field_name: str) -> int:
    normalized = int(value)
    if normalized <= 0:
        raise HTTPException(status_code=400, detail=f"{field_name} должно быть больше 0.")
    return normalized


async def list_admin_subscription_tasks(db: aiosqlite.Connection) -> dict[str, Any]:
    rows = await list_subscription_tasks(db)
    return {"items": [_serialize_task(row) for row in rows]}


async def build_admin_subscription_task_detail(
        db: aiosqlite.Connection,
        task_id: int,
) -> dict[str, Any]:
    rows = await list_subscription_tasks(db)
    for row in rows:
        if int(row["id"]) == int(task_id):
            return {"task": _serialize_task(row)}

    if not await get_subscription_task(db, int(task_id)):
        raise HTTPException(status_code=404, detail="Задание подписки не найдено.")
    raise HTTPException(status_code=404, detail="Задание подписки не найдено.")


async def create_admin_subscription_task(
        db: aiosqlite.Connection,
        *,
        chat_id: str,
        title: Optional[str],
        client_user_id: Optional[int],
        channel_url: str,
        instant_reward: float,
        daily_reward_total: float,
        daily_claim_days: int,
        max_subscribers: int,
) -> dict[str, Any]:
    normalized_chat_id = _normalize_text(chat_id, field_name="chat_id")
    normalized_title = (title or "").strip()
    normalized_client_user_id = int(client_user_id) if client_user_id is not None else None
    normalized_channel_url = normalize_subscription_channel_url(channel_url)
    if not normalized_title:
        normalized_title = await try_fetch_telegram_channel_title(normalized_chat_id) or ""
    normalized_instant_reward = _normalize_reward(instant_reward, field_name="instant_reward")
    normalized_daily_reward_total = _normalize_reward(daily_reward_total, field_name="daily_reward_total")
    normalized_daily_claim_days = _normalize_non_negative_int(daily_claim_days, field_name="daily_claim_days")
    normalized_max_subscribers = _normalize_positive_int(max_subscribers, field_name="max_subscribers")

    if normalized_daily_reward_total > 0 and normalized_daily_claim_days <= 0:
        raise HTTPException(
            status_code=400,
            detail="Если есть ежедневная награда, количество дней должно быть больше 0.",
        )
    if normalized_daily_reward_total == 0 and normalized_daily_claim_days != 0:
        normalized_daily_claim_days = 0
    if normalized_instant_reward == 0 and normalized_daily_reward_total == 0:
        raise HTTPException(status_code=400, detail="Награда не может быть 0.")
    if normalized_client_user_id is not None and not await get_user_by_id(db, normalized_client_user_id):
        raise HTTPException(status_code=404, detail="Клиент не найден")

    async with tx(db, immediate=True):
        task_id = await create_subscription_task(
            db,
            chat_id=normalized_chat_id,
            title=normalized_title,
            client_user_id=normalized_client_user_id,
            channel_url=normalized_channel_url,
            instant_reward=normalized_instant_reward,
            daily_reward_total=normalized_daily_reward_total,
            daily_claim_days=normalized_daily_claim_days,
            max_subscribers=normalized_max_subscribers,
            is_active=False,
        )
        if normalized_client_user_id is not None:
            await ensure_client_role(db, normalized_client_user_id)

    return await build_admin_subscription_task_detail(db, int(task_id))


async def bind_admin_subscription_task_client(
        db: aiosqlite.Connection,
        *,
        task_id: int,
        client_user_id: int,
) -> dict[str, Any]:
    row = await get_subscription_task(db, int(task_id))
    if not row:
        raise HTTPException(status_code=404, detail="Задание подписки не найдено.")
    if int(row["is_archived"] or 0) == 1:
        raise HTTPException(status_code=404, detail="Задание подписки уже в архиве.")
    if not await get_user_by_id(db, int(client_user_id)):
        raise HTTPException(status_code=404, detail="Клиент не найден")

    previous_client_user_id = (
        int(row["client_user_id"])
        if row["client_user_id"] is not None
        else None
    )
    async with tx(db, immediate=True):
        await set_subscription_task_client(
            db,
            task_id=int(task_id),
            client_user_id=int(client_user_id),
        )
        await sync_client_role_after_rebind(
            db,
            previous_user_id=previous_client_user_id,
            next_user_id=int(client_user_id),
        )

    return await build_admin_subscription_task_detail(db, int(task_id))


async def set_admin_subscription_task_status(
        db: aiosqlite.Connection,
        *,
        task_id: int,
        is_active: bool,
) -> dict[str, Any]:
    row = await get_subscription_task(db, int(task_id))
    if not row:
        raise HTTPException(status_code=404, detail="Задание подписки не найдено.")
    if int(row["is_archived"] or 0) == 1:
        raise HTTPException(status_code=404, detail="Задание подписки уже в архиве.")

    verified_title: Optional[str] = None
    if is_active:
        if int(row["participants_count"] or 0) >= int(row["max_subscribers"] or 0):
            raise HTTPException(
                status_code=400,
                detail="Нельзя включить задание: лимит подписчиков уже заполнен.",
            )
        verified_title = await verified_telegram_channel_title(
            str(row["chat_id"]),
            activation_subject="задание",
        )

    async with tx(db, immediate=True):
        if verified_title:
            await reset_subscription_task_unavailable_notification(
                db,
                task_id=int(task_id),
            )
            await set_subscription_task_title(
                db,
                task_id=int(task_id),
                title=verified_title,
            )
        await set_subscription_task_active(
            db,
            task_id=int(task_id),
            is_active=bool(is_active),
        )

    return await build_admin_subscription_task_detail(db, int(task_id))


async def archive_admin_subscription_task(
        db: aiosqlite.Connection,
        *,
        task_id: int,
) -> dict[str, Any]:
    row = await get_subscription_task(db, int(task_id))
    if not row:
        raise HTTPException(status_code=404, detail="Задание подписки не найдено.")
    if int(row["is_archived"] or 0) == 1:
        return {
            "ok": True,
            "task_id": int(task_id),
        }

    async with tx(db, immediate=True):
        await archive_subscription_task(db, task_id=int(task_id))

    return {
        "ok": True,
        "task_id": int(task_id),
    }
