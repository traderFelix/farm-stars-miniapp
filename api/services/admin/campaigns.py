import sqlite3
from typing import Any

import aiosqlite
from fastapi import HTTPException

from shared.db.campaigns import (
    add_winners,
    campaign_stats,
    campaigns_status_counts,
    claimed_usernames,
    delete_campaign,
    delete_winner_if_not_claimed,
    get_campaign,
    global_claims_stats,
    list_campaigns,
    list_campaigns_latest,
    list_winners,
    set_campaign_status,
    total_assigned_amount,
    unclaimed_total_amount,
    upsert_campaign,
)
from shared.db.common import tx


def _serialize_campaign(row: Any) -> dict[str, Any]:
    return {
        "campaign_key": row["campaign_key"],
        "title": row["title"] or "",
        "reward_amount": float(row["reward_amount"] or 0),
        "status": row["status"] or "draft",
        "created_at": row["created_at"],
    }


async def _get_campaign_or_404(
        db: aiosqlite.Connection,
        campaign_key: str,
) -> Any:
    row = await get_campaign(db, campaign_key)
    if not row:
        raise HTTPException(status_code=404, detail="Конкурс не найден")
    return row


def _normalize_campaign_key(value: str) -> str:
    normalized = (value or "").strip()
    if " " in normalized or len(normalized) < 3:
        raise HTTPException(
            status_code=400,
            detail="KEY без пробелов, минимум 3 символа.",
        )
    return normalized


def _normalize_campaign_title(value: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Название конкурса не может быть пустым.")
    return normalized


def _normalize_campaign_amount(value: float) -> float:
    normalized = float(value)
    if normalized <= 0:
        raise HTTPException(status_code=400, detail="Нужна награда числом > 0.")
    return normalized


def _normalize_status(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in {"draft", "active", "ended"}:
        raise HTTPException(status_code=400, detail="Некорректный статус конкурса.")
    return normalized


async def list_all_campaigns(db: aiosqlite.Connection) -> dict[str, Any]:
    rows = await list_campaigns(db)
    return {
        "items": [_serialize_campaign(row) for row in rows],
    }


async def get_campaign_detail(
        db: aiosqlite.Connection,
        campaign_key: str,
) -> dict[str, Any]:
    row = await _get_campaign_or_404(db, campaign_key)
    return _serialize_campaign(row)


async def create_campaign_entry(
        db: aiosqlite.Connection,
        *,
        campaign_key: str,
        title: str,
        amount: float,
) -> dict[str, Any]:
    normalized_key = _normalize_campaign_key(campaign_key)
    normalized_title = _normalize_campaign_title(title)
    normalized_amount = _normalize_campaign_amount(amount)

    async with tx(db):
        await upsert_campaign(
            db,
            normalized_key,
            normalized_title,
            normalized_amount,
            "draft",
        )

    return await get_campaign_detail(db, normalized_key)


async def update_campaign_status(
        db: aiosqlite.Connection,
        campaign_key: str,
        *,
        status: str,
) -> dict[str, Any]:
    normalized_status = _normalize_status(status)
    await _get_campaign_or_404(db, campaign_key)

    async with tx(db, immediate=False):
        await set_campaign_status(db, campaign_key, normalized_status)

    return await get_campaign_detail(db, campaign_key)


async def delete_campaign_entry(
        db: aiosqlite.Connection,
        campaign_key: str,
) -> dict[str, Any]:
    async with tx(db):
        await delete_campaign(db, campaign_key)

    return {
        "ok": True,
        "campaign_key": campaign_key,
    }


async def add_campaign_winners(
        db: aiosqlite.Connection,
        campaign_key: str,
        usernames: list[str],
) -> dict[str, Any]:
    try:
        async with tx(db):
            count = await add_winners(db, campaign_key, usernames)
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=404, detail="Конкурс не найден") from e

    return {
        "campaign_key": campaign_key,
        "added_count": int(count),
    }


async def get_campaign_summary(
        db: aiosqlite.Connection,
        *,
        latest_limit: int = 5,
) -> dict[str, Any]:
    latest_rows = await list_campaigns_latest(db, limit=latest_limit)
    assigned_amount = await total_assigned_amount(db)
    claims_count, total_claimed = await global_claims_stats(db)
    active_count, ended_count, draft_count = await campaigns_status_counts(db)
    unclaimed_amount = await unclaimed_total_amount(db)

    return {
        "total_assigned_amount": float(assigned_amount),
        "unclaimed_amount": float(unclaimed_amount),
        "total_claimed_amount": float(total_claimed),
        "claims_count": int(claims_count),
        "active_count": int(active_count),
        "ended_count": int(ended_count),
        "draft_count": int(draft_count),
        "latest_items": [_serialize_campaign(row) for row in latest_rows],
    }


async def get_campaign_stats_detail(
        db: aiosqlite.Connection,
        campaign_key: str,
) -> dict[str, Any]:
    claims_count, winners_count, total_paid = await campaign_stats(db, campaign_key)
    claimed = await claimed_usernames(db, campaign_key)

    return {
        "campaign_key": campaign_key,
        "claims_count": int(claims_count),
        "winners_count": int(winners_count),
        "total_paid": float(total_paid),
        "claimed_usernames": claimed,
    }


async def get_campaign_winners_detail(
        db: aiosqlite.Connection,
        campaign_key: str,
) -> dict[str, Any]:
    winners = await list_winners(db, campaign_key)
    claimed = await claimed_usernames(db, campaign_key)

    return {
        "campaign_key": campaign_key,
        "winners": winners,
        "claimed_usernames": claimed,
    }


async def delete_campaign_winner(
        db: aiosqlite.Connection,
        campaign_key: str,
        *,
        username: str,
) -> dict[str, Any]:
    async with tx(db):
        ok, message = await delete_winner_if_not_claimed(db, campaign_key, username)

    return {
        "ok": bool(ok),
        "message": message,
    }
