from __future__ import annotations

from typing import Any, Optional

import aiosqlite
from fastapi import HTTPException

from shared.db.common import tx
from shared.db.subscriptions import (
    create_subscription_task,
    get_subscription_task,
    list_subscription_tasks,
    set_subscription_task_active,
)


def _serialize_task(row: Any) -> dict[str, Any]:
    instant_reward = round(float(row["instant_reward"] or 0), 2)
    daily_reward_total = round(float(row["daily_reward_total"] or 0), 2)
    return {
        "id": int(row["id"]),
        "chat_id": str(row["chat_id"]),
        "title": str(row["title"] or ""),
        "channel_url": str(row["channel_url"]),
        "instant_reward": instant_reward,
        "daily_reward_total": daily_reward_total,
        "daily_claim_days": int(row["daily_claim_days"] or 0),
        "total_reward": round(instant_reward + daily_reward_total, 2),
        "max_subscribers": int(row["max_subscribers"] or 0),
        "participants_count": int(row["participants_count"] or 0),
        "is_active": bool(row["is_active"] or 0),
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
        channel_url: str,
        instant_reward: float,
        daily_reward_total: float,
        daily_claim_days: int,
        max_subscribers: int,
) -> dict[str, Any]:
    normalized_chat_id = _normalize_text(chat_id, field_name="chat_id")
    normalized_title = (title or "").strip()
    normalized_channel_url = _normalize_text(channel_url, field_name="channel_url")
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

    async with tx(db, immediate=True):
        task_id = await create_subscription_task(
            db,
            chat_id=normalized_chat_id,
            title=normalized_title,
            channel_url=normalized_channel_url,
            instant_reward=normalized_instant_reward,
            daily_reward_total=normalized_daily_reward_total,
            daily_claim_days=normalized_daily_claim_days,
            max_subscribers=normalized_max_subscribers,
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

    async with tx(db, immediate=True):
        await set_subscription_task_active(
            db,
            task_id=int(task_id),
            is_active=bool(is_active),
        )

    return await build_admin_subscription_task_detail(db, int(task_id))
