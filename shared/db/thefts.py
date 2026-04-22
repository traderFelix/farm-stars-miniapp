from __future__ import annotations

from typing import Optional

import aiosqlite

from shared.db.battles import ensure_view_battles_schema
from shared.db.users import ensure_users_profile_schema


async def ensure_view_thefts_schema(db: aiosqlite.Connection) -> None:
    await ensure_users_profile_schema(db)
    await ensure_view_battles_schema(db)
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS view_thefts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attacker_user_id INTEGER NOT NULL,
            victim_user_id INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'active',
            result TEXT,
            winner_user_id INTEGER,
            amount REAL NOT NULL,
            attacker_target_views INTEGER NOT NULL DEFAULT 5,
            victim_target_views INTEGER NOT NULL DEFAULT 3,
            duration_seconds INTEGER NOT NULL DEFAULT 120,
            attacker_views INTEGER NOT NULL DEFAULT 0,
            victim_views INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            ends_at TEXT NOT NULL,
            resolved_at TEXT
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_view_thefts_state_ends_at
        ON view_thefts(state, ends_at)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_view_thefts_attacker_created_at
        ON view_thefts(attacker_user_id, created_at DESC)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_view_thefts_victim_created_at
        ON view_thefts(victim_user_id, created_at DESC)
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS view_theft_protection_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'active',
            result TEXT,
            target_views INTEGER NOT NULL DEFAULT 5,
            views INTEGER NOT NULL DEFAULT 0,
            duration_seconds INTEGER NOT NULL DEFAULT 120,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            ends_at TEXT NOT NULL,
            resolved_at TEXT,
            protected_until TEXT
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_view_theft_protection_attempts_user_state
        ON view_theft_protection_attempts(user_id, state, ends_at)
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS view_theft_protections (
            user_id INTEGER PRIMARY KEY,
            protected_until TEXT NOT NULL,
            activated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_view_theft_protections_until
        ON view_theft_protections(protected_until)
        """
    )


def _theft_select() -> str:
    return """
        SELECT
            t.*,
            au.username AS attacker_username,
            au.tg_first_name AS attacker_first_name,
            au.game_nickname AS attacker_game_nickname,
            vu.username AS victim_username,
            vu.tg_first_name AS victim_first_name,
            vu.game_nickname AS victim_game_nickname
        FROM view_thefts t
        LEFT JOIN users au ON au.user_id = t.attacker_user_id
        LEFT JOIN users vu ON vu.user_id = t.victim_user_id
    """


async def get_theft_by_id(db: aiosqlite.Connection, theft_id: int):
    await ensure_view_thefts_schema(db)
    async with db.execute(
        f"""
        {_theft_select()}
        WHERE t.id = ?
        LIMIT 1
        """,
        (int(theft_id),),
    ) as cur:
        return await cur.fetchone()


async def get_user_active_theft(db: aiosqlite.Connection, user_id: int):
    await ensure_view_thefts_schema(db)
    async with db.execute(
        f"""
        {_theft_select()}
        WHERE t.state = 'active'
          AND (t.attacker_user_id = ? OR t.victim_user_id = ?)
        ORDER BY datetime(t.created_at) DESC, t.id DESC
        LIMIT 1
        """,
        (int(user_id), int(user_id)),
    ) as cur:
        return await cur.fetchone()


async def get_user_active_protection_attempt(db: aiosqlite.Connection, user_id: int):
    await ensure_view_thefts_schema(db)
    async with db.execute(
        """
        SELECT *
        FROM view_theft_protection_attempts
        WHERE user_id = ?
          AND state = 'active'
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT 1
        """,
        (int(user_id),),
    ) as cur:
        return await cur.fetchone()


async def get_user_current_protection(db: aiosqlite.Connection, user_id: int):
    await ensure_view_thefts_schema(db)
    async with db.execute(
        """
        SELECT *
        FROM view_theft_protections
        WHERE user_id = ?
          AND datetime(protected_until) > datetime('now')
        LIMIT 1
        """,
        (int(user_id),),
    ) as cur:
        return await cur.fetchone()


async def get_user_latest_finished_theft(db: aiosqlite.Connection, user_id: int):
    await ensure_view_thefts_schema(db)
    async with db.execute(
        f"""
        {_theft_select()}
        WHERE t.state = 'finished'
          AND COALESCE(t.result, '') != 'cancelled'
          AND (t.attacker_user_id = ? OR t.victim_user_id = ?)
        ORDER BY datetime(COALESCE(t.resolved_at, t.created_at)) DESC, t.id DESC
        LIMIT 1
        """,
        (int(user_id), int(user_id)),
    ) as cur:
        return await cur.fetchone()


async def has_theft_attack_today(
        db: aiosqlite.Connection,
        *,
        attacker_user_id: int,
) -> bool:
    await ensure_view_thefts_schema(db)
    async with db.execute(
        """
        SELECT 1
        FROM view_thefts
        WHERE attacker_user_id = ?
          AND COALESCE(result, '') != 'cancelled'
          AND date(created_at) = date('now')
        LIMIT 1
        """,
        (int(attacker_user_id),),
    ) as cur:
        return await cur.fetchone() is not None


async def list_theft_victim_candidates(
        db: aiosqlite.Connection,
        *,
        attacker_user_id: int,
        limit: int = 100,
):
    await ensure_view_thefts_schema(db)
    async with db.execute(
        """
        SELECT
            u.user_id,
            u.username,
            u.tg_first_name,
            u.game_nickname,
            COALESCE(u.balance, 0) AS balance,
            u.last_seen_at
        FROM users u
        WHERE u.user_id != ?
          AND COALESCE(u.balance, 0) >= 0.1
          AND datetime(COALESCE(u.last_seen_at, u.created_at)) >= datetime('now', '-3 days')
          AND NOT EXISTS (
              SELECT 1
              FROM view_theft_protections p
              WHERE p.user_id = u.user_id
                AND datetime(p.protected_until) > datetime('now')
          )
          AND NOT EXISTS (
              SELECT 1
              FROM view_thefts t
              WHERE t.state = 'active'
                AND (t.attacker_user_id = u.user_id OR t.victim_user_id = u.user_id)
          )
          AND NOT EXISTS (
              SELECT 1
              FROM view_theft_protection_attempts pa
              WHERE pa.user_id = u.user_id
                AND pa.state = 'active'
          )
          AND NOT EXISTS (
              SELECT 1
              FROM view_battles b
              WHERE b.state IN ('waiting', 'active')
                AND (b.creator_user_id = u.user_id OR b.opponent_user_id = u.user_id)
          )
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (int(attacker_user_id), int(limit)),
    ) as cur:
        return await cur.fetchall()


async def create_theft_attempt(
        db: aiosqlite.Connection,
        *,
        attacker_user_id: int,
        victim_user_id: int,
        amount: float,
        attacker_target_views: int,
        victim_target_views: int,
        duration_seconds: int,
) -> int:
    await ensure_view_thefts_schema(db)
    cur = await db.execute(
        """
        INSERT INTO view_thefts (
            attacker_user_id,
            victim_user_id,
            amount,
            attacker_target_views,
            victim_target_views,
            duration_seconds,
            ends_at
        )
        VALUES (?, ?, ?, ?, ?, ?, datetime('now', '+' || ? || ' seconds'))
        """,
        (
            int(attacker_user_id),
            int(victim_user_id),
            float(amount),
            int(attacker_target_views),
            int(victim_target_views),
            int(duration_seconds),
            int(duration_seconds),
        ),
    )
    return int(cur.lastrowid)


async def increment_theft_progress(
        db: aiosqlite.Connection,
        *,
        theft_id: int,
        user_id: int,
) -> bool:
    await ensure_view_thefts_schema(db)
    theft = await get_theft_by_id(db, int(theft_id))
    if not theft or theft["state"] != "active":
        return False

    if int(theft["attacker_user_id"]) == int(user_id):
        column_name = "attacker_views"
    elif int(theft["victim_user_id"]) == int(user_id):
        column_name = "victim_views"
    else:
        return False

    cur = await db.execute(
        f"""
        UPDATE view_thefts
        SET {column_name} = {column_name} + 1
        WHERE id = ?
          AND state = 'active'
          AND datetime(ends_at) > datetime('now')
        """,
        (int(theft_id),),
    )
    return cur.rowcount == 1


async def finish_theft(
        db: aiosqlite.Connection,
        *,
        theft_id: int,
        result: str,
        winner_user_id: Optional[int],
) -> bool:
    await ensure_view_thefts_schema(db)
    cur = await db.execute(
        """
        UPDATE view_thefts
        SET
            state = 'finished',
            result = ?,
            winner_user_id = ?,
            resolved_at = datetime('now')
        WHERE id = ?
          AND state = 'active'
        """,
        (
            str(result),
            int(winner_user_id) if winner_user_id is not None else None,
            int(theft_id),
        ),
    )
    return cur.rowcount == 1


async def create_theft_protection_attempt(
        db: aiosqlite.Connection,
        *,
        user_id: int,
        target_views: int,
        duration_seconds: int,
) -> int:
    await ensure_view_thefts_schema(db)
    cur = await db.execute(
        """
        INSERT INTO view_theft_protection_attempts (
            user_id,
            target_views,
            duration_seconds,
            ends_at
        )
        VALUES (?, ?, ?, datetime('now', '+' || ? || ' seconds'))
        """,
        (int(user_id), int(target_views), int(duration_seconds), int(duration_seconds)),
    )
    return int(cur.lastrowid)


async def increment_theft_protection_progress(
        db: aiosqlite.Connection,
        *,
        attempt_id: int,
        user_id: int,
) -> bool:
    await ensure_view_thefts_schema(db)
    cur = await db.execute(
        """
        UPDATE view_theft_protection_attempts
        SET views = views + 1
        WHERE id = ?
          AND user_id = ?
          AND state = 'active'
          AND datetime(ends_at) > datetime('now')
        """,
        (int(attempt_id), int(user_id)),
    )
    return cur.rowcount == 1


async def finish_theft_protection_attempt(
        db: aiosqlite.Connection,
        *,
        attempt_id: int,
        result: str,
        protected_seconds: Optional[int] = None,
) -> bool:
    await ensure_view_thefts_schema(db)
    protected_until_expr = (
        "datetime('now', '+' || ? || ' seconds')"
        if protected_seconds is not None
        else "NULL"
    )
    params: tuple[object, ...]
    if protected_seconds is not None:
        params = (str(result), int(protected_seconds), int(attempt_id))
    else:
        params = (str(result), int(attempt_id))
    cur = await db.execute(
        f"""
        UPDATE view_theft_protection_attempts
        SET
            state = 'finished',
            result = ?,
            resolved_at = datetime('now'),
            protected_until = {protected_until_expr}
        WHERE id = ?
          AND state = 'active'
        """,
        params,
    )
    return cur.rowcount == 1


async def upsert_theft_protection(
        db: aiosqlite.Connection,
        *,
        user_id: int,
        protected_seconds: int,
) -> None:
    await ensure_view_thefts_schema(db)
    await db.execute(
        """
        INSERT INTO view_theft_protections (user_id, protected_until, activated_at)
        VALUES (?, datetime('now', '+' || ? || ' seconds'), datetime('now'))
        ON CONFLICT(user_id) DO UPDATE SET
            protected_until = excluded.protected_until,
            activated_at = excluded.activated_at
        """,
        (int(user_id), int(protected_seconds)),
    )


async def list_expired_active_thefts(db: aiosqlite.Connection):
    await ensure_view_thefts_schema(db)
    async with db.execute(
        f"""
        {_theft_select()}
        WHERE t.state = 'active'
          AND datetime(t.ends_at) <= datetime('now')
        ORDER BY datetime(t.ends_at) ASC, t.id ASC
        """
    ) as cur:
        return await cur.fetchall()


async def list_expired_theft_protection_attempts(db: aiosqlite.Connection):
    await ensure_view_thefts_schema(db)
    async with db.execute(
        """
        SELECT *
        FROM view_theft_protection_attempts
        WHERE state = 'active'
          AND datetime(ends_at) <= datetime('now')
        ORDER BY datetime(ends_at) ASC, id ASC
        """
    ) as cur:
        return await cur.fetchall()


async def list_theft_opponent_stats(
        db: aiosqlite.Connection,
        *,
        user_id: int,
        limit: int = 50,
):
    await ensure_view_thefts_schema(db)
    async with db.execute(
        """
        WITH user_thefts AS (
            SELECT
                CASE
                    WHEN attacker_user_id = ? THEN victim_user_id
                    ELSE attacker_user_id
                END AS opponent_user_id,
                attacker_user_id,
                victim_user_id,
                result,
                amount
            FROM view_thefts
            WHERE state = 'finished'
              AND (attacker_user_id = ? OR victim_user_id = ?)
        )
        SELECT
            ut.opponent_user_id,
            u.username AS opponent_username,
            u.tg_first_name AS opponent_first_name,
            u.game_nickname AS opponent_game_nickname,
            COALESCE(SUM(CASE
                WHEN ut.attacker_user_id = ? AND ut.result = 'stolen'
                THEN ut.amount ELSE 0 END), 0) AS stolen_amount,
            SUM(CASE
                WHEN ut.attacker_user_id = ? AND ut.result = 'stolen'
                THEN 1 ELSE 0 END) AS stolen_count,
            COALESCE(SUM(CASE
                WHEN ut.victim_user_id = ? AND ut.result = 'stolen'
                THEN ut.amount ELSE 0 END), 0) AS lost_amount,
            SUM(CASE
                WHEN ut.victim_user_id = ? AND ut.result = 'stolen'
                THEN 1 ELSE 0 END) AS lost_count,
            SUM(CASE
                WHEN ut.victim_user_id = ? AND ut.result = 'defended'
                THEN 1 ELSE 0 END) AS defended_count,
            SUM(CASE
                WHEN ut.victim_user_id = ? AND ut.result = 'expired'
                THEN 1 ELSE 0 END) AS survived_count,
            SUM(CASE
                WHEN ut.attacker_user_id = ? AND ut.result IN ('defended', 'expired')
                THEN 1 ELSE 0 END) AS failed_count,
            COUNT(*) AS total
        FROM user_thefts ut
        LEFT JOIN users u ON u.user_id = ut.opponent_user_id
        GROUP BY ut.opponent_user_id, u.username, u.tg_first_name, u.game_nickname
        ORDER BY (stolen_amount + lost_amount) DESC, total DESC, ut.opponent_user_id ASC
        LIMIT ?
        """,
        (
            int(user_id),
            int(user_id),
            int(user_id),
            int(user_id),
            int(user_id),
            int(user_id),
            int(user_id),
            int(user_id),
            int(user_id),
            int(user_id),
            int(limit),
        ),
    ) as cur:
        return await cur.fetchall()
