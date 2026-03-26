from __future__ import annotations

import aiosqlite


async def cleanup_abuse_events(db: aiosqlite.Connection) -> None:
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
) -> None:
    await cleanup_abuse_events(db)
    await db.execute(
        """
        INSERT INTO abuse_events (user_id, action, amount)
        VALUES (?, ?, ?)
        """,
        (int(user_id), action, float(amount)),
    )


async def count_recent_abuse_events(
        db: aiosqlite.Connection,
        user_id: int,
        action: str,
        minutes: int,
) -> int:
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