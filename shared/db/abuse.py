from __future__ import annotations

from typing import Optional

import aiosqlite


async def _column_exists(db: aiosqlite.Connection, table_name: str, column_name: str) -> bool:
    async with db.execute(f"PRAGMA table_info({table_name})") as cur:
        rows = await cur.fetchall()

    for row in rows:
        name = row["name"] if isinstance(row, aiosqlite.Row) else row[1]
        if name == column_name:
            return True
    return False


async def ensure_abuse_events_schema(db: aiosqlite.Connection) -> None:
    required_columns = {
        "ip_hash": "TEXT",
        "ua_hash": "TEXT",
        "session_id": "TEXT",
        "entity_type": "TEXT",
        "entity_id": "TEXT",
        "meta": "TEXT",
    }

    for column_name, column_type in required_columns.items():
        if not await _column_exists(db, "abuse_events", column_name):
            await db.execute(
                f"ALTER TABLE abuse_events ADD COLUMN {column_name} {column_type}"
            )


async def cleanup_abuse_events(db: aiosqlite.Connection) -> None:
    await ensure_abuse_events_schema(db)
    await db.execute(
        """
        DELETE FROM abuse_events
        WHERE datetime(created_at) < datetime('now', '-1 day')
        """
    )


async def log_abuse_event(
        db: aiosqlite.Connection,
        user_id: int,
        action: str,
        amount: float = 0,
        *,
        ip_hash: Optional[str] = None,
        ua_hash: Optional[str] = None,
        session_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        meta: Optional[str] = None,
) -> None:
    await ensure_abuse_events_schema(db)
    await cleanup_abuse_events(db)
    await db.execute(
        """
        INSERT INTO abuse_events (
            user_id, action, amount, ip_hash, ua_hash, session_id, entity_type, entity_id, meta
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(user_id),
            action,
            float(amount),
            ip_hash,
            ua_hash,
            session_id,
            entity_type,
            entity_id,
            meta,
        ),
    )


async def count_recent_abuse_events(
        db: aiosqlite.Connection,
        user_id: int,
        action: str,
        minutes: int,
) -> int:
    await ensure_abuse_events_schema(db)
    async with db.execute(
            """
        SELECT COUNT(*)
        FROM abuse_events
        WHERE user_id = ?
          AND action = ?
          AND datetime(created_at) >= datetime('now', ?)
        """,
            (int(user_id), action, f"-{int(minutes)} minutes"),
    ) as cur:
        row = await cur.fetchone()
    return int(row[0] or 0)


async def sum_recent_abuse_amount(
        db: aiosqlite.Connection,
        user_id: int,
        action: str,
        hours: int,
) -> float:
    await ensure_abuse_events_schema(db)
    async with db.execute(
            """
        SELECT COALESCE(SUM(amount), 0)
        FROM abuse_events
        WHERE user_id = ?
          AND action = ?
          AND datetime(created_at) >= datetime('now', ?)
        """,
            (int(user_id), action, f"-{int(hours)} hours"),
    ) as cur:
        row = await cur.fetchone()
    return float(row[0] or 0.0)


async def count_distinct_users_for_session(
        db: aiosqlite.Connection,
        *,
        user_id: int,
        session_id: str,
        hours: int,
) -> int:
    await ensure_abuse_events_schema(db)
    async with db.execute(
            """
        SELECT COUNT(DISTINCT user_id)
        FROM abuse_events
        WHERE session_id = ?
          AND user_id != ?
          AND datetime(created_at) >= datetime('now', ?)
        """,
            (session_id, int(user_id), f"-{int(hours)} hours"),
    ) as cur:
        row = await cur.fetchone()
    return int(row[0] or 0)


async def count_distinct_users_for_fingerprint(
        db: aiosqlite.Connection,
        *,
        user_id: int,
        ip_hash: str,
        ua_hash: str,
        hours: int,
) -> int:
    await ensure_abuse_events_schema(db)
    async with db.execute(
            """
        SELECT COUNT(DISTINCT user_id)
        FROM abuse_events
        WHERE ip_hash = ?
          AND ua_hash = ?
          AND user_id != ?
          AND datetime(created_at) >= datetime('now', ?)
        """,
            (ip_hash, ua_hash, int(user_id), f"-{int(hours)} hours"),
    ) as cur:
        row = await cur.fetchone()
    return int(row[0] or 0)
