from __future__ import annotations

from typing import Any, Optional

import aiosqlite


async def ensure_subscription_tasks_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS subscription_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            channel_url TEXT NOT NULL,
            instant_reward REAL NOT NULL DEFAULT 0,
            daily_reward_total REAL NOT NULL DEFAULT 0,
            daily_claim_days INTEGER NOT NULL DEFAULT 0,
            max_subscribers INTEGER NOT NULL,
            participants_count INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS subscription_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            title_snapshot TEXT NOT NULL DEFAULT '',
            channel_url_snapshot TEXT NOT NULL DEFAULT '',
            instant_reward REAL NOT NULL DEFAULT 0,
            daily_reward_total REAL NOT NULL DEFAULT 0,
            daily_claim_days INTEGER NOT NULL DEFAULT 0,
            instant_claimed_at TEXT,
            daily_claims_done INTEGER NOT NULL DEFAULT 0,
            daily_reward_claimed REAL NOT NULL DEFAULT 0,
            last_daily_claim_day TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT,
            abandoned_at TEXT,
            UNIQUE(task_id, user_id),
            FOREIGN KEY(task_id) REFERENCES subscription_tasks(id) ON DELETE CASCADE
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS subscription_abandon_cooldowns (
            user_id INTEGER PRIMARY KEY,
            available_at TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_subscription_tasks_active_limit
        ON subscription_tasks(is_active, participants_count, max_subscribers)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_subscription_assignments_user_status
        ON subscription_assignments(user_id, status, created_at DESC)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_subscription_assignments_task_status
        ON subscription_assignments(task_id, status)
        """
    )


async def current_utc_day(db: aiosqlite.Connection) -> str:
    async with db.execute("SELECT date('now')") as cur:
        row = await cur.fetchone()
    return str(row[0])


async def create_subscription_task(
        db: aiosqlite.Connection,
        *,
        chat_id: str,
        title: str,
        channel_url: str,
        instant_reward: float,
        daily_reward_total: float,
        daily_claim_days: int,
        max_subscribers: int,
) -> int:
    await ensure_subscription_tasks_schema(db)
    cur = await db.execute(
        """
        INSERT INTO subscription_tasks (
            chat_id, title, channel_url, instant_reward, daily_reward_total,
            daily_claim_days, max_subscribers, is_active, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, datetime('now'))
        """,
        (
            str(chat_id),
            str(title or ""),
            str(channel_url),
            float(instant_reward),
            float(daily_reward_total),
            int(daily_claim_days),
            int(max_subscribers),
        ),
    )
    return int(cur.lastrowid)


async def get_subscription_task(db: aiosqlite.Connection, task_id: int) -> Optional[Any]:
    await ensure_subscription_tasks_schema(db)
    async with db.execute(
        """
        SELECT *
        FROM subscription_tasks
        WHERE id = ?
        """,
        (int(task_id),),
    ) as cur:
        return await cur.fetchone()


async def list_subscription_tasks(db: aiosqlite.Connection) -> list[Any]:
    await ensure_subscription_tasks_schema(db)
    async with db.execute(
        """
        SELECT
            t.*,
            COUNT(a.id) AS assignment_count,
            COALESCE(SUM(CASE WHEN a.status = 'active' THEN 1 ELSE 0 END), 0) AS active_count,
            COALESCE(SUM(CASE WHEN a.status = 'completed' THEN 1 ELSE 0 END), 0) AS completed_count,
            COALESCE(SUM(CASE WHEN a.status = 'abandoned' THEN 1 ELSE 0 END), 0) AS abandoned_count
        FROM subscription_tasks t
        LEFT JOIN subscription_assignments a ON a.task_id = t.id
        GROUP BY t.id
        ORDER BY t.id DESC
        """
    ) as cur:
        return await cur.fetchall()


async def set_subscription_task_active(
        db: aiosqlite.Connection,
        *,
        task_id: int,
        is_active: bool,
) -> None:
    await ensure_subscription_tasks_schema(db)
    await db.execute(
        """
        UPDATE subscription_tasks
        SET is_active = ?, updated_at = datetime('now')
        WHERE id = ?
        """,
        (1 if is_active else 0, int(task_id)),
    )


async def list_available_subscription_tasks_for_user(
        db: aiosqlite.Connection,
        user_id: int,
) -> list[Any]:
    await ensure_subscription_tasks_schema(db)
    async with db.execute(
        """
        SELECT t.*
        FROM subscription_tasks t
        LEFT JOIN subscription_assignments a
          ON a.task_id = t.id AND a.user_id = ?
        WHERE t.is_active = 1
          AND t.participants_count < t.max_subscribers
          AND a.id IS NULL
        ORDER BY t.id DESC
        """,
        (int(user_id),),
    ) as cur:
        return await cur.fetchall()


async def get_user_subscription_assignment_for_task(
        db: aiosqlite.Connection,
        *,
        user_id: int,
        task_id: int,
) -> Optional[Any]:
    await ensure_subscription_tasks_schema(db)
    async with db.execute(
        """
        SELECT *
        FROM subscription_assignments
        WHERE user_id = ? AND task_id = ?
        """,
        (int(user_id), int(task_id)),
    ) as cur:
        return await cur.fetchone()


async def get_subscription_assignment_with_task(
        db: aiosqlite.Connection,
        assignment_id: int,
        *,
        user_id: Optional[int] = None,
) -> Optional[Any]:
    await ensure_subscription_tasks_schema(db)
    params: list[Any] = [int(assignment_id)]
    user_filter = ""
    if user_id is not None:
        user_filter = "AND a.user_id = ?"
        params.append(int(user_id))

    async with db.execute(
        f"""
        SELECT
            a.*,
            t.chat_id,
            t.title AS task_title,
            t.channel_url AS task_channel_url,
            t.is_active AS task_is_active,
            t.participants_count,
            t.max_subscribers
        FROM subscription_assignments a
        JOIN subscription_tasks t ON t.id = a.task_id
        WHERE a.id = ?
        {user_filter}
        """,
        tuple(params),
    ) as cur:
        return await cur.fetchone()


async def list_user_active_subscription_assignments(
        db: aiosqlite.Connection,
        user_id: int,
) -> list[Any]:
    await ensure_subscription_tasks_schema(db)
    async with db.execute(
        """
        SELECT
            a.*,
            t.chat_id,
            t.title AS task_title,
            t.channel_url AS task_channel_url,
            t.is_active AS task_is_active,
            t.participants_count,
            t.max_subscribers
        FROM subscription_assignments a
        JOIN subscription_tasks t ON t.id = a.task_id
        WHERE a.user_id = ?
          AND a.status = 'active'
        ORDER BY datetime(a.created_at) DESC, a.id DESC
        """,
        (int(user_id),),
    ) as cur:
        return await cur.fetchall()


async def count_user_active_subscription_slots(
        db: aiosqlite.Connection,
        user_id: int,
) -> int:
    await ensure_subscription_tasks_schema(db)
    async with db.execute(
        """
        SELECT COUNT(*)
        FROM subscription_assignments
        WHERE user_id = ?
          AND status = 'active'
          AND daily_reward_total > 0
          AND daily_claim_days > 0
          AND daily_claims_done < daily_claim_days
        """,
        (int(user_id),),
    ) as cur:
        row = await cur.fetchone()
    return int(row[0] or 0)


async def create_subscription_assignment(
        db: aiosqlite.Connection,
        *,
        task: Any,
        user_id: int,
        status: str,
        instant_claimed_at: bool,
) -> int:
    await ensure_subscription_tasks_schema(db)
    cur = await db.execute(
        """
        INSERT INTO subscription_assignments (
            task_id, user_id, status, title_snapshot, channel_url_snapshot,
            instant_reward, daily_reward_total, daily_claim_days,
            instant_claimed_at, created_at, completed_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?,
            CASE WHEN ? THEN datetime('now') ELSE NULL END,
            datetime('now'),
            CASE WHEN ? THEN datetime('now') ELSE NULL END
        )
        """,
        (
            int(task["id"]),
            int(user_id),
            status,
            str(task["title"] or ""),
            str(task["channel_url"]),
            float(task["instant_reward"] or 0),
            float(task["daily_reward_total"] or 0),
            int(task["daily_claim_days"] or 0),
            1 if instant_claimed_at else 0,
            1 if status == "completed" else 0,
        ),
    )
    return int(cur.lastrowid)


async def increment_subscription_task_participants(
        db: aiosqlite.Connection,
        task_id: int,
) -> None:
    await ensure_subscription_tasks_schema(db)
    await db.execute(
        """
        UPDATE subscription_tasks
        SET participants_count = participants_count + 1,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (int(task_id),),
    )


async def mark_subscription_daily_claimed(
        db: aiosqlite.Connection,
        *,
        assignment_id: int,
        amount: float,
        claim_day: str,
        completed: bool,
) -> None:
    await ensure_subscription_tasks_schema(db)
    await db.execute(
        """
        UPDATE subscription_assignments
        SET
            daily_claims_done = daily_claims_done + 1,
            daily_reward_claimed = daily_reward_claimed + ?,
            last_daily_claim_day = ?,
            status = CASE WHEN ? THEN 'completed' ELSE status END,
            completed_at = CASE WHEN ? THEN datetime('now') ELSE completed_at END
        WHERE id = ?
        """,
        (
            float(amount),
            str(claim_day),
            1 if completed else 0,
            1 if completed else 0,
            int(assignment_id),
        ),
    )


async def get_subscription_abandon_available_at(
        db: aiosqlite.Connection,
        user_id: int,
) -> Optional[str]:
    await ensure_subscription_tasks_schema(db)
    async with db.execute(
        """
        SELECT available_at
        FROM subscription_abandon_cooldowns
        WHERE user_id = ?
        """,
        (int(user_id),),
    ) as cur:
        row = await cur.fetchone()
    return str(row["available_at"]) if row else None


async def set_subscription_abandon_cooldown(
        db: aiosqlite.Connection,
        *,
        user_id: int,
        days: int,
) -> None:
    await ensure_subscription_tasks_schema(db)
    await db.execute(
        """
        INSERT INTO subscription_abandon_cooldowns (user_id, available_at, updated_at)
        VALUES (?, datetime('now', ?), datetime('now'))
        ON CONFLICT(user_id) DO UPDATE SET
            available_at = excluded.available_at,
            updated_at = datetime('now')
        """,
        (int(user_id), f"+{int(days)} days"),
    )


async def abandon_subscription_assignment(
        db: aiosqlite.Connection,
        *,
        assignment_id: int,
) -> None:
    await ensure_subscription_tasks_schema(db)
    await db.execute(
        """
        UPDATE subscription_assignments
        SET status = 'abandoned',
            abandoned_at = datetime('now')
        WHERE id = ?
          AND status = 'active'
        """,
        (int(assignment_id),),
    )
