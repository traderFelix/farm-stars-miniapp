from __future__ import annotations

from typing import Any

import aiosqlite
from fastapi import HTTPException

from shared.config import ROLE_CLIENT
from shared.db.subscriptions import ensure_subscription_tasks_schema
from shared.db.tasks import ensure_task_channels_client_schema, list_task_posts_by_channel, task_channel_stats
from shared.db.users import get_balance, get_user_by_id, user_has_role


def _serialize_channel(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "chat_id": str(row["chat_id"]),
        "title": str(row["title"] or ""),
        "is_active": bool(row["is_active"] or 0),
        "has_views": bool(row.get("has_views", True) if isinstance(row, dict) else row["has_views"] if "has_views" in row.keys() else True),
        "has_subscriptions": bool(
            row.get("has_subscriptions", False)
            if isinstance(row, dict)
            else row["has_subscriptions"] if "has_subscriptions" in row.keys() else False
        ),
        "total_bought_views": int(row["total_bought_views"] or 0),
        "views_per_post": int(row["views_per_post"] or 0),
        "view_seconds": int(row["view_seconds"] or 0),
        "allocated_views": int(row["allocated_views"] or 0),
        "remaining_views": int(row["remaining_views"] or 0),
        "created_at": row["created_at"],
    }


def _serialize_view_stats(row: Any) -> dict[str, Any]:
    return {
        "total_posts": int(row["total_posts"] or 0),
        "total_required": int(row["total_required"] or 0),
        "total_current": int(row["total_current"] or 0),
        "active_posts": int(row["active_posts"] or 0),
    }


def _serialize_subscription_stats(row: Any) -> dict[str, Any]:
    return {
        "tasks_count": int(row["tasks_count"] or 0),
        "active_tasks_count": int(row["active_tasks_count"] or 0),
        "total_subscribers_bought": int(row["total_subscribers_bought"] or 0),
        "total_participants": int(row["total_participants"] or 0),
        "total_assignments": int(row["total_assignments"] or 0),
        "active_assignments": int(row["active_assignments"] or 0),
        "completed_assignments": int(row["completed_assignments"] or 0),
        "abandoned_assignments": int(row["abandoned_assignments"] or 0),
    }


def _serialize_post(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "channel_post_id": int(row["channel_post_id"]),
        "required_views": int(row["required_views"] or 0),
        "current_views": int(row["current_views"] or 0),
        "is_active": bool(row["is_active"] or 0),
        "source": row["source"] if "source" in row.keys() else "auto",
        "added_by_admin_id": (
            int(row["added_by_admin_id"])
            if "added_by_admin_id" in row.keys() and row["added_by_admin_id"] is not None
            else None
        ),
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
    }


def _serialize_subscription_campaign(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "created_at": row["created_at"],
        "is_active": bool(row["is_active"] or 0),
        "participants_count": int(row["participants_count"] or 0),
        "max_subscribers": int(row["max_subscribers"] or 0),
    }


def _serialize_view_order(row: Any) -> dict[str, Any]:
    return {
        "kind": "views",
        "chat_id": str(row["chat_id"]),
        "title": str(row["title"] or row["chat_id"]),
        "created_at": row["created_at"],
        "price_stars": None,
        "price_note": None,
        "total_bought_views": int(row["total_bought_views"] or 0),
        "views_per_post": int(row["views_per_post"] or 0),
        "view_seconds": int(row["view_seconds"] or 0),
        "max_subscribers": None,
        "daily_claim_days": None,
    }


def _serialize_subscription_order(row: Any) -> dict[str, Any]:
    return {
        "kind": "subscriptions",
        "chat_id": str(row["chat_id"]),
        "title": str(row["title"] or row["chat_id"]),
        "created_at": row["created_at"],
        "price_stars": None,
        "price_note": None,
        "total_bought_views": None,
        "views_per_post": None,
        "view_seconds": None,
        "max_subscribers": int(row["max_subscribers"] or 0),
        "daily_claim_days": int(row["daily_claim_days"] or 0),
    }


async def _ensure_client_access(
        db: aiosqlite.Connection,
        user_id: int,
) -> None:
    if not await get_user_by_id(db, int(user_id)):
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if not await user_has_role(db, int(user_id), ROLE_CLIENT):
        raise HTTPException(status_code=403, detail="Раздел клиента тебе пока недоступен.")


def _build_client_channel_row(
        *,
        channel_id: int,
        chat_id: str,
        title: str,
        is_active: bool,
        has_views: bool,
        has_subscriptions: bool,
        total_bought_views: int = 0,
        views_per_post: int = 0,
        view_seconds: int = 0,
        allocated_views: int = 0,
        remaining_views: int = 0,
        created_at: Any = None,
) -> dict[str, Any]:
    return {
        "id": int(channel_id),
        "chat_id": str(chat_id),
        "title": str(title or ""),
        "is_active": 1 if is_active else 0,
        "has_views": bool(has_views),
        "has_subscriptions": bool(has_subscriptions),
        "total_bought_views": int(total_bought_views or 0),
        "views_per_post": int(views_per_post or 0),
        "view_seconds": int(view_seconds or 0),
        "allocated_views": int(allocated_views or 0),
        "remaining_views": int(remaining_views or 0),
        "created_at": created_at,
    }


async def _list_client_view_channel_rows(
        db: aiosqlite.Connection,
        user_id: int,
) -> list[Any]:
    await ensure_task_channels_client_schema(db)
    async with db.execute(
        """
        SELECT
            id,
            chat_id,
            COALESCE(title, '') AS title,
            is_active,
            total_bought_views,
            views_per_post,
            view_seconds,
            allocated_views,
            (total_bought_views - allocated_views) AS remaining_views,
            created_at
        FROM task_channels
        WHERE client_user_id = ?
        ORDER BY id DESC
        """,
        (int(user_id),),
    ) as cur:
        return await cur.fetchall()


async def _list_client_subscription_channel_rows(
        db: aiosqlite.Connection,
        user_id: int,
) -> list[Any]:
    await ensure_subscription_tasks_schema(db)
    view_rows = await _list_client_view_channel_rows(db, int(user_id))
    view_chat_ids = [str(row["chat_id"]) for row in view_rows]
    conditions = ["client_user_id = ?"]
    params: list[Any] = [int(user_id)]
    if view_chat_ids:
        placeholders = ", ".join("?" for _ in view_chat_ids)
        conditions.append(f"chat_id IN ({placeholders})")
        params.extend(view_chat_ids)
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


async def _list_client_channel_rows(
        db: aiosqlite.Connection,
        user_id: int,
) -> list[dict[str, Any]]:
    view_rows = await _list_client_view_channel_rows(db, int(user_id))
    subscription_rows = await _list_client_subscription_channel_rows(db, int(user_id))

    merged_by_chat_id: dict[str, dict[str, Any]] = {}
    for row in view_rows:
        chat_id = str(row["chat_id"])
        merged_by_chat_id[chat_id] = _build_client_channel_row(
            channel_id=int(row["id"]),
            chat_id=chat_id,
            title=str(row["title"] or ""),
            is_active=bool(row["is_active"] or 0),
            has_views=True,
            has_subscriptions=False,
            total_bought_views=int(row["total_bought_views"] or 0),
            views_per_post=int(row["views_per_post"] or 0),
            view_seconds=int(row["view_seconds"] or 0),
            allocated_views=int(row["allocated_views"] or 0),
            remaining_views=int(row["remaining_views"] or 0),
            created_at=row["created_at"],
        )

    for row in subscription_rows:
        chat_id = str(row["chat_id"])
        existing = merged_by_chat_id.get(chat_id)
        if existing is not None:
            existing["has_subscriptions"] = True
            if not existing.get("title"):
                existing["title"] = str(row["title"] or "")
            if not existing.get("created_at"):
                existing["created_at"] = row["created_at"]
            continue

        merged_by_chat_id[chat_id] = _build_client_channel_row(
            channel_id=int(chat_id),
            chat_id=chat_id,
            title=str(row["title"] or ""),
            is_active=bool(row["is_active"] or 0),
            has_views=False,
            has_subscriptions=True,
            created_at=row["created_at"],
        )

    return sorted(
        merged_by_chat_id.values(),
        key=lambda item: (str(item.get("created_at") or ""), int(item["id"])),
        reverse=True,
    )


async def _get_client_channel_row(
        db: aiosqlite.Connection,
        user_id: int,
        channel_id: int,
) -> Any:
    rows = await _list_client_channel_rows(db, int(user_id))
    for row in rows:
        if int(row["id"]) == int(channel_id):
            return row

    if int(channel_id) >= 0:
        raise HTTPException(status_code=404, detail="Канал клиента не найден.")
    raise HTTPException(status_code=404, detail="Канал клиента не найден.")


async def _list_client_subscription_rows(
        db: aiosqlite.Connection,
        user_id: int,
        *,
        limit: int = 20,
) -> list[Any]:
    await ensure_subscription_tasks_schema(db)
    channel_rows = await _list_client_view_channel_rows(db, int(user_id))
    channel_chat_ids = [str(row["chat_id"]) for row in channel_rows]

    conditions = ["client_user_id = ?"]
    params: list[Any] = [int(user_id)]
    if channel_chat_ids:
        placeholders = ", ".join("?" for _ in channel_chat_ids)
        conditions.append(f"chat_id IN ({placeholders})")
        params.extend(channel_chat_ids)

    where_clause = " OR ".join(conditions)
    params.append(int(limit))

    async with db.execute(
        f"""
        SELECT
            id,
            chat_id,
            COALESCE(title, '') AS title,
            max_subscribers,
            daily_claim_days,
            created_at
        FROM subscription_tasks
        WHERE {where_clause}
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT ?
        """,
        tuple(params),
    ) as cur:
        return await cur.fetchall()


async def get_client_cabinet_summary(
        db: aiosqlite.Connection,
        user_id: int,
) -> dict[str, Any]:
    await _ensure_client_access(db, int(user_id))
    view_channel_rows = await _list_client_view_channel_rows(db, int(user_id))
    channel_rows = await _list_client_channel_rows(db, int(user_id))
    subscription_rows = await _list_client_subscription_rows(db, int(user_id), limit=1000)
    balance = await get_balance(db, int(user_id))
    return {
        "user_id": int(user_id),
        "balance": float(balance or 0),
        "channels_count": len(channel_rows),
        "orders_count": len(view_channel_rows) + len(subscription_rows),
    }


async def list_client_channels(
        db: aiosqlite.Connection,
        user_id: int,
) -> dict[str, Any]:
    await _ensure_client_access(db, int(user_id))
    rows = await _list_client_channel_rows(db, int(user_id))
    return {
        "items": [_serialize_channel(row) for row in rows],
    }


async def get_client_channel_detail(
        db: aiosqlite.Connection,
        user_id: int,
        channel_id: int,
) -> dict[str, Any]:
    await _ensure_client_access(db, int(user_id))
    row = await _get_client_channel_row(db, int(user_id), int(channel_id))
    return {
        "channel": _serialize_channel(row),
    }


async def get_client_channel_view_stats(
        db: aiosqlite.Connection,
        user_id: int,
        channel_id: int,
) -> dict[str, Any]:
    await _ensure_client_access(db, int(user_id))
    row = await _get_client_channel_row(db, int(user_id), int(channel_id))
    if bool(row.get("has_views")):
        stats = await task_channel_stats(db, int(channel_id))
    else:
        stats = {
            "total_posts": 0,
            "total_required": 0,
            "total_current": 0,
            "active_posts": 0,
        }
    return {
        "channel": _serialize_channel(row),
        "stats": _serialize_view_stats(stats),
    }


async def get_client_channel_subscription_stats(
        db: aiosqlite.Connection,
        user_id: int,
        channel_id: int,
) -> dict[str, Any]:
    await _ensure_client_access(db, int(user_id))
    row = await _get_client_channel_row(db, int(user_id), int(channel_id))
    await ensure_subscription_tasks_schema(db)

    async with db.execute(
        """
        SELECT
            id,
            is_active,
            COALESCE(is_archived, 0) AS is_archived,
            max_subscribers,
            participants_count
        FROM subscription_tasks
        WHERE chat_id = ?
        """,
        (str(row["chat_id"]),),
    ) as cur:
        campaign_rows = await cur.fetchall()

    campaign_ids = [int(campaign["id"]) for campaign in campaign_rows]
    stats = {
        "tasks_count": len(campaign_rows),
        "active_tasks_count": sum(
            1
            for campaign in campaign_rows
            if int(campaign["is_active"] or 0) == 1 and int(campaign["is_archived"] or 0) == 0
        ),
        "total_subscribers_bought": sum(int(campaign["max_subscribers"] or 0) for campaign in campaign_rows),
        "total_participants": sum(int(campaign["participants_count"] or 0) for campaign in campaign_rows),
        "total_assignments": 0,
        "active_assignments": 0,
        "completed_assignments": 0,
        "abandoned_assignments": 0,
    }

    if campaign_ids:
        placeholders = ", ".join("?" for _ in campaign_ids)
        async with db.execute(
            f"""
            SELECT
                COUNT(*) AS total_assignments,
                COALESCE(SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END), 0) AS active_assignments,
                COALESCE(SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END), 0) AS completed_assignments,
                COALESCE(SUM(CASE WHEN status = 'abandoned' THEN 1 ELSE 0 END), 0) AS abandoned_assignments
            FROM subscription_assignments
            WHERE task_id IN ({placeholders})
            """,
            tuple(campaign_ids),
        ) as cur:
            assignment_stats = await cur.fetchone()

        stats.update(
            {
                "total_assignments": int(assignment_stats["total_assignments"] or 0),
                "active_assignments": int(assignment_stats["active_assignments"] or 0),
                "completed_assignments": int(assignment_stats["completed_assignments"] or 0),
                "abandoned_assignments": int(assignment_stats["abandoned_assignments"] or 0),
            }
        )

    return {
        "channel": _serialize_channel(row),
        "stats": _serialize_subscription_stats(stats),
    }


async def list_client_channel_posts(
        db: aiosqlite.Connection,
        user_id: int,
        channel_id: int,
        *,
        limit: int = 5,
        page: int = 0,
) -> dict[str, Any]:
    await _ensure_client_access(db, int(user_id))
    row = await _get_client_channel_row(db, int(user_id), int(channel_id))
    normalized_limit = max(int(limit), 1)
    normalized_page = max(int(page), 0)
    offset = normalized_page * normalized_limit
    if bool(row.get("has_views")):
        posts = await list_task_posts_by_channel(
            db,
            int(channel_id),
            limit=normalized_limit + 1,
            offset=offset,
        )
    else:
        posts = []
    has_next = len(posts) > normalized_limit
    return {
        "channel": _serialize_channel(row),
        "items": [_serialize_post(post) for post in posts[:normalized_limit]],
        "page": normalized_page,
        "has_next": has_next,
    }


async def list_client_channel_subscription_campaigns(
        db: aiosqlite.Connection,
        user_id: int,
        channel_id: int,
) -> dict[str, Any]:
    await _ensure_client_access(db, int(user_id))
    row = await _get_client_channel_row(db, int(user_id), int(channel_id))
    await ensure_subscription_tasks_schema(db)
    async with db.execute(
        """
        SELECT
            id,
            created_at,
            is_active,
            participants_count,
            max_subscribers
        FROM subscription_tasks
        WHERE chat_id = ?
        ORDER BY datetime(created_at) DESC, id DESC
        """,
        (str(row["chat_id"]),),
    ) as cur:
        campaigns = await cur.fetchall()

    return {
        "channel": _serialize_channel(row),
        "items": [_serialize_subscription_campaign(item) for item in campaigns],
    }


async def list_client_orders(
        db: aiosqlite.Connection,
        user_id: int,
        *,
        limit: int = 20,
) -> dict[str, Any]:
    await _ensure_client_access(db, int(user_id))

    channel_rows = await _list_client_view_channel_rows(db, int(user_id))
    subscription_rows = await _list_client_subscription_rows(db, int(user_id), limit=max(int(limit), 1) * 2)

    items = [
        *[_serialize_view_order(row) for row in channel_rows],
        *[_serialize_subscription_order(row) for row in subscription_rows],
    ]
    items.sort(
        key=lambda item: (
            str(item.get("created_at") or ""),
            1 if item["kind"] == "subscriptions" else 0,
        ),
        reverse=True,
    )

    return {
        "items": items[: max(int(limit), 1)],
    }
