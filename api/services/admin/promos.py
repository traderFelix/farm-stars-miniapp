from typing import Any, Optional

import aiosqlite
from fastapi import HTTPException

from shared.db.common import tx
from shared.db.promos import (
    claimed_usernames,
    delete_promo,
    get_promo,
    global_claims_stats,
    list_promos,
    list_promos_latest,
    promo_stats,
    promos_status_counts,
    set_promo_status,
    total_assigned_amount,
    unclaimed_total_amount,
    upsert_promo,
)


def _serialize_promo(row: Any) -> dict[str, Any]:
    claims_count = int(row["claims_count"] or 0)
    total_uses = int(row["total_uses"] or 0)
    remaining_uses = max(total_uses - claims_count, 0)
    return {
        "promo_code": row["promo_code"],
        "title": row["title"] or None,
        "reward_amount": float(row["reward_amount"] or 0),
        "total_uses": total_uses,
        "claims_count": claims_count,
        "remaining_uses": remaining_uses,
        "status": row["status"] or "draft",
        "created_at": row["created_at"],
    }


async def _get_promo_or_404(
        db: aiosqlite.Connection,
        promo_code: str,
) -> Any:
    row = await get_promo(db, promo_code)
    if not row:
        raise HTTPException(status_code=404, detail="Промокод не найден")
    return row


def _normalize_promo_code(value: str) -> str:
    normalized = "".join((value or "").strip().upper().split())
    if len(normalized) < 3:
        raise HTTPException(status_code=400, detail="Код без пробелов, минимум 3 символа")
    return normalized


def _normalize_promo_title(value: Optional[str]) -> Optional[str]:
    normalized = (value or "").strip()
    return normalized or None


def _normalize_promo_amount(value: float) -> float:
    normalized = float(value)
    if normalized <= 0:
        raise HTTPException(status_code=400, detail="Нужна награда числом > 0")
    return normalized


def _normalize_total_uses(value: int) -> int:
    normalized = int(value)
    if normalized <= 0:
        raise HTTPException(status_code=400, detail="Количество активаций должно быть больше 0")
    return normalized


def _normalize_status(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in {"draft", "active", "ended"}:
        raise HTTPException(status_code=400, detail="Некорректный статус промокода")
    return normalized


async def list_all_promos(db: aiosqlite.Connection) -> dict[str, Any]:
    rows = await list_promos(db)
    return {
        "items": [_serialize_promo(row) for row in rows],
    }


async def get_promo_detail(
        db: aiosqlite.Connection,
        promo_code: str,
) -> dict[str, Any]:
    await _get_promo_or_404(db, promo_code)
    rows = await list_promos(db)
    for row in rows:
        if row["promo_code"] == promo_code:
            return _serialize_promo(row)
    raise HTTPException(status_code=404, detail="Промокод не найден")


async def create_promo_entry(
        db: aiosqlite.Connection,
        *,
        promo_code: str,
        title: Optional[str],
        amount: float,
        total_uses: int,
) -> dict[str, Any]:
    normalized_code = _normalize_promo_code(promo_code)
    normalized_title = _normalize_promo_title(title)
    normalized_amount = _normalize_promo_amount(amount)
    normalized_total_uses = _normalize_total_uses(total_uses)

    async with tx(db):
        await upsert_promo(
            db,
            normalized_code,
            normalized_title,
            normalized_amount,
            normalized_total_uses,
            "draft",
        )

    return await get_promo_detail(db, normalized_code)


async def update_promo_status(
        db: aiosqlite.Connection,
        promo_code: str,
        *,
        status: str,
) -> dict[str, Any]:
    await _get_promo_or_404(db, promo_code)
    normalized_status = _normalize_status(status)

    async with tx(db, immediate=False):
        await set_promo_status(db, promo_code, normalized_status)

    return await get_promo_detail(db, promo_code)


async def delete_promo_entry(
        db: aiosqlite.Connection,
        promo_code: str,
) -> dict[str, Any]:
    await _get_promo_or_404(db, promo_code)

    async with tx(db):
        await delete_promo(db, promo_code)

    return {
        "ok": True,
        "promo_code": promo_code,
    }


async def get_promo_summary(
        db: aiosqlite.Connection,
        *,
        latest_limit: int = 5,
) -> dict[str, Any]:
    latest_rows = await list_promos_latest(db, limit=latest_limit)
    assigned_amount = await total_assigned_amount(db)
    claims_count, total_claimed = await global_claims_stats(db)
    active_count, ended_count, draft_count = await promos_status_counts(db)
    unclaimed_amount = await unclaimed_total_amount(db)

    return {
        "total_assigned_amount": float(assigned_amount),
        "unclaimed_amount": float(unclaimed_amount),
        "total_claimed_amount": float(total_claimed),
        "claims_count": int(claims_count),
        "active_count": int(active_count),
        "ended_count": int(ended_count),
        "draft_count": int(draft_count),
        "latest_items": [_serialize_promo(row) for row in latest_rows],
    }


async def get_promo_stats_detail(
        db: aiosqlite.Connection,
        promo_code: str,
) -> dict[str, Any]:
    await _get_promo_or_404(db, promo_code)
    claims_count, total_uses, remaining_uses, total_paid = await promo_stats(db, promo_code)
    claimed = await claimed_usernames(db, promo_code)
    return {
        "promo_code": promo_code,
        "claims_count": int(claims_count),
        "total_uses": int(total_uses),
        "remaining_uses": int(remaining_uses),
        "total_paid": float(total_paid),
        "claimed_usernames": claimed,
    }
