from __future__ import annotations

from typing import Any, Optional

import aiosqlite


async def ensure_partner_traffic_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS partner_traffic_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partner_user_id INTEGER NOT NULL,
            channel_chat_id TEXT NOT NULL,
            channel_title TEXT NOT NULL DEFAULT '',
            subscribers_promised INTEGER NOT NULL DEFAULT 0,
            subscribers_delivered INTEGER NOT NULL DEFAULT 0,
            views_promised INTEGER NOT NULL DEFAULT 0,
            views_delivered INTEGER NOT NULL DEFAULT 0,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_partner_traffic_partner_channel_created
        ON partner_traffic_events(partner_user_id, channel_chat_id, created_at DESC)
        """
    )


async def list_partner_traffic_channels(
        db: aiosqlite.Connection,
        partner_user_id: int,
) -> list[Any]:
    await ensure_partner_traffic_schema(db)
    async with db.execute(
        """
        SELECT
            channel_chat_id,
            COALESCE(MAX(NULLIF(channel_title, '')), '') AS channel_title,
            MAX(created_at) AS created_at
        FROM partner_traffic_events
        WHERE partner_user_id = ?
        GROUP BY channel_chat_id
        ORDER BY datetime(MAX(created_at)) DESC, channel_chat_id DESC
        """,
        (int(partner_user_id),),
    ) as cur:
        return await cur.fetchall()


async def get_partner_traffic_event(
        db: aiosqlite.Connection,
        event_id: int,
) -> Any:
    await ensure_partner_traffic_schema(db)
    async with db.execute(
        """
        SELECT
            id,
            partner_user_id,
            channel_chat_id,
            channel_title,
            subscribers_promised,
            subscribers_delivered,
            views_promised,
            views_delivered,
            note,
            created_at
        FROM partner_traffic_events
        WHERE id = ?
        """,
        (int(event_id),),
    ) as cur:
        return await cur.fetchone()


async def get_partner_traffic_totals(
        db: aiosqlite.Connection,
        partner_user_id: int,
        channel_chat_id: str,
) -> Any:
    await ensure_partner_traffic_schema(db)
    async with db.execute(
        """
        SELECT
            COALESCE(SUM(subscribers_promised), 0) AS subscribers_promised,
            COALESCE(SUM(subscribers_delivered), 0) AS subscribers_delivered,
            COALESCE(SUM(views_promised), 0) AS views_promised,
            COALESCE(SUM(views_delivered), 0) AS views_delivered
        FROM partner_traffic_events
        WHERE partner_user_id = ?
          AND channel_chat_id = ?
        """,
        (int(partner_user_id), str(channel_chat_id)),
    ) as cur:
        return await cur.fetchone()


async def get_partner_remaining_views(
        db: aiosqlite.Connection,
        partner_user_id: int,
        channel_chat_id: str,
) -> int:
    totals = await get_partner_traffic_totals(db, int(partner_user_id), str(channel_chat_id))
    promised = int(totals["views_promised"] or 0) if totals is not None else 0
    delivered = int(totals["views_delivered"] or 0) if totals is not None else 0
    return max(promised - delivered, 0)


async def list_partner_traffic_history(
        db: aiosqlite.Connection,
        partner_user_id: int,
        channel_chat_id: str,
        *,
        limit: int = 50,
) -> list[Any]:
    await ensure_partner_traffic_schema(db)
    async with db.execute(
        """
        SELECT
            id,
            channel_chat_id,
            channel_title,
            subscribers_promised,
            subscribers_delivered,
            views_promised,
            views_delivered,
            note,
            created_at
        FROM partner_traffic_events
        WHERE partner_user_id = ?
          AND channel_chat_id = ?
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT ?
        """,
        (int(partner_user_id), str(channel_chat_id), int(limit)),
    ) as cur:
        return await cur.fetchall()


async def add_partner_traffic_event(
        db: aiosqlite.Connection,
        *,
        partner_user_id: int,
        channel_chat_id: str,
        channel_title: Optional[str] = None,
        subscribers_promised: int = 0,
        subscribers_delivered: int = 0,
        views_promised: int = 0,
        views_delivered: int = 0,
        note: Optional[str] = None,
) -> int:
    await ensure_partner_traffic_schema(db)
    cur = await db.execute(
        """
        INSERT INTO partner_traffic_events (
            partner_user_id,
            channel_chat_id,
            channel_title,
            subscribers_promised,
            subscribers_delivered,
            views_promised,
            views_delivered,
            note,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            int(partner_user_id),
            str(channel_chat_id),
            str(channel_title or ""),
            int(subscribers_promised),
            int(subscribers_delivered),
            int(views_promised),
            int(views_delivered),
            note,
        ),
    )
    return int(cur.lastrowid)


async def allocate_partner_views(
        db: aiosqlite.Connection,
        *,
        partner_user_id: int,
        channel_chat_id: str,
        amount: int,
) -> int:
    await ensure_partner_traffic_schema(db)
    remaining_to_allocate = max(int(amount), 0)
    if remaining_to_allocate <= 0:
        return 0

    async with db.execute(
        """
        SELECT
            id,
            views_promised,
            views_delivered
        FROM partner_traffic_events
        WHERE partner_user_id = ?
          AND channel_chat_id = ?
          AND views_delivered < views_promised
        ORDER BY datetime(created_at) ASC, id ASC
        """,
        (int(partner_user_id), str(channel_chat_id)),
    ) as cur:
        rows = await cur.fetchall()

    allocated_total = 0
    for row in rows:
        available = max(int(row["views_promised"] or 0) - int(row["views_delivered"] or 0), 0)
        if available <= 0:
            continue

        chunk = min(available, remaining_to_allocate)
        if chunk <= 0:
            continue

        await db.execute(
            """
            UPDATE partner_traffic_events
            SET views_delivered = views_delivered + ?
            WHERE id = ?
            """,
            (int(chunk), int(row["id"])),
        )
        allocated_total += int(chunk)
        remaining_to_allocate -= int(chunk)
        if remaining_to_allocate <= 0:
            break

    return allocated_total
