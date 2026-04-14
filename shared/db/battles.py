from __future__ import annotations

from typing import Optional

import aiosqlite

from shared.db.users import ensure_users_profile_schema


async def ensure_view_battles_schema(db: aiosqlite.Connection) -> None:
    await ensure_users_profile_schema(db)
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS view_battles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_user_id INTEGER NOT NULL,
            opponent_user_id INTEGER,
            state TEXT NOT NULL DEFAULT 'waiting',
            result TEXT,
            winner_user_id INTEGER,
            target_views INTEGER NOT NULL DEFAULT 20,
            stake_amount REAL NOT NULL DEFAULT 1.0,
            duration_seconds INTEGER NOT NULL DEFAULT 300,
            creator_views INTEGER NOT NULL DEFAULT 0,
            opponent_views INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            started_at TEXT,
            ends_at TEXT,
            resolved_at TEXT
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_view_battles_state_created_at
        ON view_battles(state, created_at DESC)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_view_battles_creator_state
        ON view_battles(creator_user_id, state, created_at DESC)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_view_battles_opponent_state
        ON view_battles(opponent_user_id, state, created_at DESC)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_view_battles_pair_finished
        ON view_battles(creator_user_id, opponent_user_id, state, resolved_at DESC)
        """
    )


async def expire_waiting_battles(
        db: aiosqlite.Connection,
        *,
        older_than_seconds: int,
) -> None:
    await ensure_view_battles_schema(db)
    await db.execute(
        """
        UPDATE view_battles
        SET
            state = 'cancelled',
            result = 'cancelled',
            resolved_at = datetime('now')
        WHERE state = 'waiting'
          AND datetime(created_at) <= datetime('now', ?)
        """,
        (f"-{int(older_than_seconds)} seconds",),
    )


async def list_expired_waiting_battles(
        db: aiosqlite.Connection,
        *,
        older_than_seconds: int,
):
    await ensure_view_battles_schema(db)
    async with db.execute(
            f"""
            {_battle_select()}
            WHERE b.state = 'waiting'
              AND datetime(b.created_at) <= datetime('now', ?)
            ORDER BY datetime(b.created_at) ASC, b.id ASC
            """,
            (f"-{int(older_than_seconds)} seconds",),
    ) as cur:
        return await cur.fetchall()


def _battle_select() -> str:
    return """
        SELECT
            b.*,
            cu.username AS creator_username,
            cu.tg_first_name AS creator_first_name,
            cu.game_nickname AS creator_game_nickname,
            ou.username AS opponent_username,
            ou.tg_first_name AS opponent_first_name,
            ou.game_nickname AS opponent_game_nickname
        FROM view_battles b
        LEFT JOIN users cu ON cu.user_id = b.creator_user_id
        LEFT JOIN users ou ON ou.user_id = b.opponent_user_id
    """


async def get_battle_by_id(
        db: aiosqlite.Connection,
        battle_id: int,
):
    await ensure_view_battles_schema(db)
    async with db.execute(
            f"""
            {_battle_select()}
            WHERE b.id = ?
            LIMIT 1
            """,
            (int(battle_id),),
    ) as cur:
        return await cur.fetchone()


async def get_user_open_battle(
        db: aiosqlite.Connection,
        user_id: int,
):
    await ensure_view_battles_schema(db)
    async with db.execute(
            f"""
            {_battle_select()}
            WHERE (b.creator_user_id = ? OR b.opponent_user_id = ?)
              AND b.state IN ('waiting', 'active')
            ORDER BY
                CASE WHEN b.state = 'active' THEN 0 ELSE 1 END,
                datetime(b.created_at) DESC,
                b.id DESC
            LIMIT 1
            """,
            (int(user_id), int(user_id)),
    ) as cur:
        return await cur.fetchone()


async def get_user_latest_finished_battle(
        db: aiosqlite.Connection,
        user_id: int,
):
    await ensure_view_battles_schema(db)
    async with db.execute(
            f"""
            {_battle_select()}
            WHERE (b.creator_user_id = ? OR b.opponent_user_id = ?)
              AND b.state = 'finished'
            ORDER BY datetime(COALESCE(b.resolved_at, b.created_at)) DESC, b.id DESC
            LIMIT 1
            """,
            (int(user_id), int(user_id)),
    ) as cur:
        return await cur.fetchone()


async def get_waiting_battle_for_match(
        db: aiosqlite.Connection,
        user_id: int,
):
    await ensure_view_battles_schema(db)
    async with db.execute(
            f"""
            {_battle_select()}
            WHERE b.state = 'waiting'
              AND b.creator_user_id != ?
            ORDER BY datetime(b.created_at) ASC, b.id ASC
            LIMIT 1
            """,
            (int(user_id),),
    ) as cur:
        return await cur.fetchone()


async def create_waiting_battle(
        db: aiosqlite.Connection,
        *,
        creator_user_id: int,
        target_views: int,
        stake_amount: float,
        duration_seconds: int,
) -> int:
    await ensure_view_battles_schema(db)
    cur = await db.execute(
        """
        INSERT INTO view_battles (
            creator_user_id,
            state,
            target_views,
            stake_amount,
            duration_seconds
        )
        VALUES (?, 'waiting', ?, ?, ?)
        """,
        (
            int(creator_user_id),
            int(target_views),
            float(stake_amount),
            int(duration_seconds),
        ),
    )
    return int(cur.lastrowid)


async def activate_battle(
        db: aiosqlite.Connection,
        *,
        battle_id: int,
        opponent_user_id: int,
) -> bool:
    await ensure_view_battles_schema(db)
    cur = await db.execute(
        """
        UPDATE view_battles
        SET
            opponent_user_id = ?,
            state = 'active',
            started_at = datetime('now'),
            ends_at = datetime('now', '+' || duration_seconds || ' seconds')
        WHERE id = ?
          AND state = 'waiting'
          AND opponent_user_id IS NULL
        """,
        (int(opponent_user_id), int(battle_id)),
    )
    return cur.rowcount == 1


async def cancel_waiting_battle(
        db: aiosqlite.Connection,
        *,
        battle_id: int,
        user_id: int,
) -> bool:
    await ensure_view_battles_schema(db)
    cur = await db.execute(
        """
        UPDATE view_battles
        SET
            state = 'cancelled',
            result = 'cancelled',
            resolved_at = datetime('now')
        WHERE id = ?
          AND state = 'waiting'
          AND creator_user_id = ?
        """,
        (int(battle_id), int(user_id)),
    )
    return cur.rowcount == 1


async def increment_battle_progress(
        db: aiosqlite.Connection,
        *,
        battle_id: int,
        user_id: int,
) -> bool:
    await ensure_view_battles_schema(db)

    battle = await get_battle_by_id(db, battle_id)
    if not battle or battle["state"] != "active":
        return False

    if int(battle["creator_user_id"]) == int(user_id):
        column_name = "creator_views"
    elif battle["opponent_user_id"] is not None and int(battle["opponent_user_id"]) == int(user_id):
        column_name = "opponent_views"
    else:
        return False

    cur = await db.execute(
        f"""
        UPDATE view_battles
        SET {column_name} = {column_name} + 1
        WHERE id = ?
          AND state = 'active'
          AND datetime(ends_at) > datetime('now')
        """,
        (int(battle_id),),
    )
    return cur.rowcount == 1


async def finish_battle(
        db: aiosqlite.Connection,
        *,
        battle_id: int,
        result: str,
        winner_user_id: Optional[int],
) -> bool:
    await ensure_view_battles_schema(db)
    cur = await db.execute(
        """
        UPDATE view_battles
        SET
            state = 'finished',
            result = ?,
            winner_user_id = ?,
            resolved_at = datetime('now')
        WHERE id = ?
          AND state = 'active'
        """,
        (
            result,
            int(winner_user_id) if winner_user_id is not None else None,
            int(battle_id),
        ),
    )
    return cur.rowcount == 1


async def count_finished_battles_between_users(
        db: aiosqlite.Connection,
        *,
        user_a: int,
        user_b: int,
        hours: int = 24,
) -> int:
    await ensure_view_battles_schema(db)
    async with db.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM view_battles
            WHERE state = 'finished'
              AND datetime(COALESCE(resolved_at, created_at)) >= datetime('now', ?)
              AND (
                    (creator_user_id = ? AND opponent_user_id = ?)
                 OR (creator_user_id = ? AND opponent_user_id = ?)
              )
            """,
            (
                f"-{int(hours)} hours",
                int(user_a),
                int(user_b),
                int(user_b),
                int(user_a),
            ),
    ) as cur:
        row = await cur.fetchone()
    return int(row["cnt"] or 0)


async def count_wins_over_opponent(
        db: aiosqlite.Connection,
        *,
        user_id: int,
        opponent_user_id: int,
        hours: int = 24,
) -> int:
    await ensure_view_battles_schema(db)
    async with db.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM view_battles
            WHERE state = 'finished'
              AND winner_user_id = ?
              AND datetime(COALESCE(resolved_at, created_at)) >= datetime('now', ?)
              AND (
                    (creator_user_id = ? AND opponent_user_id = ?)
                 OR (creator_user_id = ? AND opponent_user_id = ?)
              )
            """,
            (
                int(user_id),
                f"-{int(hours)} hours",
                int(user_id),
                int(opponent_user_id),
                int(opponent_user_id),
                int(user_id),
            ),
    ) as cur:
        row = await cur.fetchone()
    return int(row["cnt"] or 0)


async def list_battle_opponent_stats(
        db: aiosqlite.Connection,
        *,
        user_id: int,
        limit: int = 50,
):
    await ensure_view_battles_schema(db)
    async with db.execute(
            """
            WITH user_battles AS (
                SELECT
                    CASE
                        WHEN creator_user_id = ? THEN opponent_user_id
                        ELSE creator_user_id
                    END AS opponent_user_id,
                    winner_user_id,
                    result
                FROM view_battles
                WHERE state = 'finished'
                  AND (creator_user_id = ? OR opponent_user_id = ?)
                  AND opponent_user_id IS NOT NULL
            )
            SELECT
                ub.opponent_user_id,
                u.username AS opponent_username,
                u.tg_first_name AS opponent_first_name,
                SUM(CASE WHEN ub.winner_user_id = ? THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN ub.winner_user_id = ub.opponent_user_id THEN 1 ELSE 0 END) AS losses,
                SUM(CASE WHEN ub.result = 'draw' THEN 1 ELSE 0 END) AS draws,
                COUNT(*) AS total
            FROM user_battles ub
            LEFT JOIN users u ON u.user_id = ub.opponent_user_id
            WHERE ub.opponent_user_id IS NOT NULL
            GROUP BY ub.opponent_user_id, u.username, u.tg_first_name
            ORDER BY total DESC, wins DESC, losses ASC, ub.opponent_user_id ASC
            LIMIT ?
            """,
            (
                int(user_id),
                int(user_id),
                int(user_id),
                int(user_id),
                int(limit),
            ),
    ) as cur:
        return await cur.fetchall()
