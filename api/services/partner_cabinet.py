from __future__ import annotations

from typing import Any

import aiosqlite
from fastapi import HTTPException

from shared.config import OWNER_TYPE_PARTNER, ROLE_PARTNER
from shared.db.partners import (
    get_partner_traffic_totals,
    list_partner_traffic_channels,
    list_partner_traffic_history,
)
from shared.db.promos import ensure_promos_schema
from shared.db.subscriptions import ensure_subscription_tasks_schema
from shared.db.tasks import ensure_task_channels_client_schema
from shared.db.users import get_referrals_count, get_user_by_id, user_has_role


def _serialize_channel(row: Any) -> dict[str, Any]:
    return {
        "chat_id": str(row["chat_id"]),
        "title": str(row["title"] or ""),
        "is_active": bool(row["is_active"] or 0),
        "has_promos": bool(row["has_promos"] or 0) if "has_promos" in row.keys() else bool(row.get("has_promos") or False),
        "has_accruals": bool(row["has_accruals"] or 0) if "has_accruals" in row.keys() else bool(row.get("has_accruals") or False),
        "created_at": row["created_at"],
    }


def _serialize_promo(row: Any) -> dict[str, Any]:
    return {
        "promo_code": str(row["promo_code"]),
        "title": (row["title"] or None) if "title" in row.keys() else None,
        "status": str(row["status"] or "draft"),
        "claims_count": int(row["claims_count"] or 0),
        "total_uses": int(row["total_uses"] or 0),
        "new_referrals_count": int(row["new_referrals_count"] or 0),
        "created_at": row["created_at"],
    }


def _serialize_accrual_summary(row: Any) -> dict[str, Any]:
    return {
        "subscribers_delivered": int(row["subscribers_delivered"] or 0),
        "subscribers_promised": int(row["subscribers_promised"] or 0),
        "views_delivered": int(row["views_delivered"] or 0),
        "views_promised": int(row["views_promised"] or 0),
    }


def _serialize_accrual_history_item(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "created_at": row["created_at"],
        "subscribers_delivered": int(row["subscribers_delivered"] or 0),
        "subscribers_promised": int(row["subscribers_promised"] or 0),
        "views_delivered": int(row["views_delivered"] or 0),
        "views_promised": int(row["views_promised"] or 0),
        "note": (row["note"] or None) if "note" in row.keys() else None,
    }


def _build_channel_row(
        *,
        chat_id: str,
        title: str,
        is_active: bool,
        has_promos: bool,
        has_accruals: bool,
        created_at: Any = None,
) -> dict[str, Any]:
    return {
        "chat_id": str(chat_id),
        "title": str(title or ""),
        "is_active": 1 if is_active else 0,
        "has_promos": 1 if has_promos else 0,
        "has_accruals": 1 if has_accruals else 0,
        "created_at": created_at,
    }


async def _ensure_partner_access(
        db: aiosqlite.Connection,
        user_id: int,
) -> None:
    if not await get_user_by_id(db, int(user_id)):
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if not await user_has_role(db, int(user_id), ROLE_PARTNER):
        raise HTTPException(status_code=403, detail="Раздел партнера тебе пока недоступен.")


async def _list_partner_view_channel_rows(
        db: aiosqlite.Connection,
        user_id: int,
) -> list[Any]:
    await ensure_task_channels_client_schema(db)
    async with db.execute(
        """
        SELECT
            chat_id,
            COALESCE(title, '') AS title,
            is_active,
            created_at
        FROM task_channels
        WHERE client_user_id = ?
          AND owner_type = ?
        ORDER BY datetime(created_at) DESC, id DESC
        """,
        (int(user_id), OWNER_TYPE_PARTNER),
    ) as cur:
        return await cur.fetchall()


async def _list_partner_subscription_channel_rows(
        db: aiosqlite.Connection,
        user_id: int,
) -> list[Any]:
    await ensure_subscription_tasks_schema(db)
    view_rows = await _list_partner_view_channel_rows(db, int(user_id))
    view_chat_ids = [str(row["chat_id"]) for row in view_rows]

    conditions = ["(client_user_id = ? AND owner_type = ?)"]
    params: list[Any] = [int(user_id), OWNER_TYPE_PARTNER]
    if view_chat_ids:
        placeholders = ", ".join("?" for _ in view_chat_ids)
        conditions.append(f"(chat_id IN ({placeholders}) AND owner_type = ?)")
        params.extend(view_chat_ids)
        params.append(OWNER_TYPE_PARTNER)
    where_clause = " OR ".join(conditions)

    async with db.execute(
        f"""
        SELECT
            chat_id,
            COALESCE(MAX(NULLIF(title, '')), '') AS title,
            MAX(CASE WHEN is_active = 1 AND COALESCE(is_archived, 0) = 0 THEN 1 ELSE 0 END) AS is_active,
            MAX(created_at) AS created_at
        FROM subscription_tasks
        WHERE COALESCE(is_archived, 0) = 0
          AND ({where_clause})
        GROUP BY chat_id
        ORDER BY datetime(MAX(created_at)) DESC, chat_id DESC
        """,
        tuple(params),
    ) as cur:
        return await cur.fetchall()


async def _list_partner_promo_channel_rows(
        db: aiosqlite.Connection,
        user_id: int,
) -> list[Any]:
    await ensure_promos_schema(db)
    async with db.execute(
        """
        SELECT
            partner_channel_chat_id AS chat_id,
            COALESCE(MAX(NULLIF(partner_channel_title, '')), '') AS title,
            MAX(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS is_active,
            MAX(created_at) AS created_at
        FROM promo_codes
        WHERE partner_user_id = ?
          AND partner_channel_chat_id IS NOT NULL
          AND TRIM(partner_channel_chat_id) != ''
          AND status != 'archived'
        GROUP BY partner_channel_chat_id
        ORDER BY datetime(MAX(created_at)) DESC, partner_channel_chat_id DESC
        """,
        (int(user_id),),
    ) as cur:
        return await cur.fetchall()


async def _list_partner_channel_rows(
        db: aiosqlite.Connection,
        user_id: int,
) -> list[dict[str, Any]]:
    view_rows = await _list_partner_view_channel_rows(db, int(user_id))
    subscription_rows = await _list_partner_subscription_channel_rows(db, int(user_id))
    promo_rows = await _list_partner_promo_channel_rows(db, int(user_id))
    traffic_rows = await list_partner_traffic_channels(db, int(user_id))

    merged: dict[str, dict[str, Any]] = {}

    for row in view_rows:
        chat_id = str(row["chat_id"])
        merged[chat_id] = _build_channel_row(
            chat_id=chat_id,
            title=str(row["title"] or ""),
            is_active=bool(row["is_active"] or 0),
            has_promos=False,
            has_accruals=True,
            created_at=row["created_at"],
        )

    for row in subscription_rows:
        chat_id = str(row["chat_id"])
        existing = merged.get(chat_id)
        if existing is not None:
            existing["is_active"] = 1 if bool(existing["is_active"] or row["is_active"] or 0) else 0
            if not existing.get("title"):
                existing["title"] = str(row["title"] or "")
            if not existing.get("created_at"):
                existing["created_at"] = row["created_at"]
            continue

        merged[chat_id] = _build_channel_row(
            chat_id=chat_id,
            title=str(row["title"] or ""),
            is_active=bool(row["is_active"] or 0),
            has_promos=False,
            has_accruals=True,
            created_at=row["created_at"],
        )

    for row in promo_rows:
        chat_id = str(row["chat_id"])
        existing = merged.get(chat_id)
        if existing is not None:
            existing["has_promos"] = 1
            existing["is_active"] = 1 if bool(existing["is_active"] or row["is_active"] or 0) else 0
            if not existing.get("title"):
                existing["title"] = str(row["title"] or "")
            if not existing.get("created_at"):
                existing["created_at"] = row["created_at"]
            continue

        merged[chat_id] = _build_channel_row(
            chat_id=chat_id,
            title=str(row["title"] or ""),
            is_active=bool(row["is_active"] or 0),
            has_promos=True,
            has_accruals=False,
            created_at=row["created_at"],
        )

    for row in traffic_rows:
        chat_id = str(row["channel_chat_id"])
        existing = merged.get(chat_id)
        if existing is not None:
            existing["has_accruals"] = 1
            if not existing.get("title"):
                existing["title"] = str(row["channel_title"] or "")
            if not existing.get("created_at"):
                existing["created_at"] = row["created_at"]
            continue

        merged[chat_id] = _build_channel_row(
            chat_id=chat_id,
            title=str(row["channel_title"] or ""),
            is_active=False,
            has_promos=False,
            has_accruals=True,
            created_at=row["created_at"],
        )

    return sorted(
        merged.values(),
        key=lambda item: (str(item.get("created_at") or ""), str(item["chat_id"])),
        reverse=True,
    )


async def _get_partner_live_view_rows(
        db: aiosqlite.Connection,
        user_id: int,
        chat_id: str,
) -> list[Any]:
    await ensure_task_channels_client_schema(db)
    async with db.execute(
        """
        SELECT
            id,
            created_at,
            total_bought_views,
            allocated_views
        FROM task_channels
        WHERE client_user_id = ?
          AND chat_id = ?
          AND owner_type = ?
        ORDER BY datetime(created_at) DESC, id DESC
        """,
        (int(user_id), str(chat_id), OWNER_TYPE_PARTNER),
    ) as cur:
        return await cur.fetchall()


async def _get_partner_live_subscription_rows(
        db: aiosqlite.Connection,
        user_id: int,
        chat_id: str,
) -> list[Any]:
    await ensure_subscription_tasks_schema(db)
    owns_view_channel = False
    async with db.execute(
        """
        SELECT 1
        FROM task_channels
        WHERE client_user_id = ?
          AND chat_id = ?
          AND owner_type = ?
        LIMIT 1
        """,
        (int(user_id), str(chat_id), OWNER_TYPE_PARTNER),
    ) as cur:
        owns_view_channel = await cur.fetchone() is not None

    async with db.execute(
        """
        SELECT
            id,
            created_at,
            max_subscribers,
            participants_count
        FROM subscription_tasks
        WHERE COALESCE(is_archived, 0) = 0
          AND chat_id = ?
          AND owner_type = ?
          AND (client_user_id = ? OR ? = 1)
        ORDER BY datetime(created_at) DESC, id DESC
        """,
        (str(chat_id), OWNER_TYPE_PARTNER, int(user_id), 1 if owns_view_channel else 0),
    ) as cur:
        return await cur.fetchall()


async def _get_partner_live_accrual_summary(
        db: aiosqlite.Connection,
        user_id: int,
        chat_id: str,
) -> dict[str, int]:
    view_rows = await _get_partner_live_view_rows(db, int(user_id), str(chat_id))
    subscription_rows = await _get_partner_live_subscription_rows(db, int(user_id), str(chat_id))
    return {
        "subscribers_delivered": sum(int(row["participants_count"] or 0) for row in subscription_rows),
        "subscribers_promised": sum(int(row["max_subscribers"] or 0) for row in subscription_rows),
        "views_delivered": sum(int(row["allocated_views"] or 0) for row in view_rows),
        "views_promised": sum(int(row["total_bought_views"] or 0) for row in view_rows),
    }


async def _get_partner_live_accrual_history(
        db: aiosqlite.Connection,
        user_id: int,
        chat_id: str,
) -> list[dict[str, Any]]:
    view_rows = await _get_partner_live_view_rows(db, int(user_id), str(chat_id))
    subscription_rows = await _get_partner_live_subscription_rows(db, int(user_id), str(chat_id))

    items: list[dict[str, Any]] = []
    for row in view_rows:
        items.append({
            "id": f"views:{int(row['id'])}",
            "created_at": row["created_at"],
            "subscribers_delivered": 0,
            "subscribers_promised": 0,
            "views_delivered": int(row["allocated_views"] or 0),
            "views_promised": int(row["total_bought_views"] or 0),
            "note": "пакет просмотров",
        })

    for row in subscription_rows:
        items.append({
            "id": f"subs:{int(row['id'])}",
            "created_at": row["created_at"],
            "subscribers_delivered": int(row["participants_count"] or 0),
            "subscribers_promised": int(row["max_subscribers"] or 0),
            "views_delivered": 0,
            "views_promised": 0,
            "note": "кампания подписок",
        })

    items.sort(
        key=lambda item: (str(item.get("created_at") or ""), str(item["id"])),
        reverse=True,
    )
    return items


async def _get_partner_channel_row(
        db: aiosqlite.Connection,
        user_id: int,
        chat_id: str,
) -> dict[str, Any]:
    rows = await _list_partner_channel_rows(db, int(user_id))
    normalized_chat_id = str(chat_id)
    for row in rows:
        if str(row["chat_id"]) == normalized_chat_id:
            return row
    raise HTTPException(status_code=404, detail="Канал партнера не найден.")


async def get_partner_cabinet_summary(
        db: aiosqlite.Connection,
        user_id: int,
) -> dict[str, Any]:
    await _ensure_partner_access(db, int(user_id))
    rows = await _list_partner_channel_rows(db, int(user_id))
    referrals_count = await get_referrals_count(db, int(user_id))
    return {
        "user_id": int(user_id),
        "channels_count": len(rows),
        "referrals_count": int(referrals_count),
    }


async def list_partner_channels(
        db: aiosqlite.Connection,
        user_id: int,
) -> dict[str, Any]:
    await _ensure_partner_access(db, int(user_id))
    rows = await _list_partner_channel_rows(db, int(user_id))
    return {
        "items": [_serialize_channel(row) for row in rows],
    }


async def get_partner_channel_detail(
        db: aiosqlite.Connection,
        user_id: int,
        chat_id: str,
) -> dict[str, Any]:
    await _ensure_partner_access(db, int(user_id))
    row = await _get_partner_channel_row(db, int(user_id), str(chat_id))
    return {
        "channel": _serialize_channel(row),
    }


async def list_partner_channel_promos(
        db: aiosqlite.Connection,
        user_id: int,
        chat_id: str,
) -> dict[str, Any]:
    await _ensure_partner_access(db, int(user_id))
    row = await _get_partner_channel_row(db, int(user_id), str(chat_id))
    await ensure_promos_schema(db)

    async with db.execute(
        """
        SELECT
            p.promo_code,
            p.title,
            p.status,
            p.total_uses,
            p.created_at,
            COUNT(pc.id) AS claims_count,
            COALESCE(
                SUM(
                    CASE
                        WHEN u.referred_by = ?
                         AND datetime(u.created_at) > datetime(p.created_at)
                        THEN 1
                        ELSE 0
                    END
                ),
                0
            ) AS new_referrals_count
        FROM promo_codes p
        LEFT JOIN promo_claims pc ON pc.promo_code = p.promo_code
        LEFT JOIN users u ON u.user_id = pc.user_id
        WHERE p.partner_user_id = ?
          AND p.partner_channel_chat_id = ?
          AND p.status != 'archived'
        GROUP BY p.promo_code, p.title, p.status, p.total_uses, p.created_at
        ORDER BY datetime(p.created_at) DESC, p.promo_code DESC
        """,
        (int(user_id), int(user_id), str(chat_id)),
    ) as cur:
        promo_rows = await cur.fetchall()

    return {
        "channel": _serialize_channel(row),
        "items": [_serialize_promo(item) for item in promo_rows],
    }


async def get_partner_channel_accruals(
        db: aiosqlite.Connection,
        user_id: int,
        chat_id: str,
) -> dict[str, Any]:
    await _ensure_partner_access(db, int(user_id))
    row = await _get_partner_channel_row(db, int(user_id), str(chat_id))
    live_totals = await _get_partner_live_accrual_summary(db, int(user_id), str(chat_id))
    totals = await get_partner_traffic_totals(db, int(user_id), str(chat_id))
    return {
        "channel": _serialize_channel(row),
        "summary": {
            "subscribers_delivered": int(live_totals["subscribers_delivered"]) + int(totals["subscribers_delivered"] or 0),
            "subscribers_promised": int(live_totals["subscribers_promised"]) + int(totals["subscribers_promised"] or 0),
            "views_delivered": int(live_totals["views_delivered"]) + int(totals["views_delivered"] or 0),
            "views_promised": int(live_totals["views_promised"]) + int(totals["views_promised"] or 0),
        },
    }


async def list_partner_channel_accrual_history(
        db: aiosqlite.Connection,
        user_id: int,
        chat_id: str,
        *,
        limit: int = 50,
) -> dict[str, Any]:
    await _ensure_partner_access(db, int(user_id))
    row = await _get_partner_channel_row(db, int(user_id), str(chat_id))
    live_items = await _get_partner_live_accrual_history(db, int(user_id), str(chat_id))
    traffic_items = await list_partner_traffic_history(
        db,
        int(user_id),
        str(chat_id),
        limit=max(int(limit), 1),
    )
    items = [
        *live_items,
        *[_serialize_accrual_history_item(item) for item in traffic_items],
    ]
    items = sorted(
        items,
        key=lambda item: (str(item.get("created_at") or ""), str(item["id"])),
        reverse=True,
    )[: max(int(limit), 1)]
    return {
        "channel": _serialize_channel(row),
        "items": items,
    }
