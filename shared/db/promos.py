from __future__ import annotations

from typing import Optional

import aiosqlite


async def ensure_promos_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS promo_codes (
            promo_code TEXT PRIMARY KEY,
            title TEXT,
            reward_amount REAL NOT NULL,
            total_uses INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS promo_claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promo_code TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            claimed_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(promo_code, user_id)
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_promo_codes_status_created_at
        ON promo_codes(status, created_at DESC)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_promo_claims_code
        ON promo_claims(promo_code, claimed_at DESC)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_promo_claims_user
        ON promo_claims(user_id, claimed_at DESC)
        """
    )


async def upsert_promo(
        db: aiosqlite.Connection,
        promo_code: str,
        title: Optional[str],
        reward_amount: float,
        total_uses: int,
        status: str = "draft",
) -> None:
    await ensure_promos_schema(db)
    await db.execute(
        """
        INSERT INTO promo_codes (promo_code, title, reward_amount, total_uses, status)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(promo_code) DO UPDATE SET
            title = excluded.title,
            reward_amount = excluded.reward_amount,
            total_uses = excluded.total_uses,
            status = excluded.status
        """,
        (
            promo_code,
            title,
            float(reward_amount),
            int(total_uses),
            status,
        ),
    )


async def set_promo_status(
        db: aiosqlite.Connection,
        promo_code: str,
        status: str,
) -> None:
    await ensure_promos_schema(db)
    await db.execute(
        "UPDATE promo_codes SET status = ? WHERE promo_code = ?",
        (status, promo_code),
    )


async def delete_promo(
        db: aiosqlite.Connection,
        promo_code: str,
) -> None:
    await archive_promo(db, promo_code)


async def archive_promo(
        db: aiosqlite.Connection,
        promo_code: str,
) -> None:
    await ensure_promos_schema(db)
    await db.execute(
        "UPDATE promo_codes SET status = ? WHERE promo_code = ?",
        ("archived", promo_code),
    )


async def get_promo(
        db: aiosqlite.Connection,
        promo_code: str,
):
    await ensure_promos_schema(db)
    async with db.execute(
            """
            SELECT promo_code, title, reward_amount, total_uses, status, created_at
            FROM promo_codes
            WHERE promo_code = ?
            """,
            (promo_code,),
    ) as cur:
        return await cur.fetchone()


async def list_promos(db: aiosqlite.Connection):
    await ensure_promos_schema(db)
    async with db.execute(
            """
            SELECT
                p.promo_code,
                p.title,
                p.reward_amount,
                p.total_uses,
                p.status,
                p.created_at,
                COUNT(pc.id) AS claims_count
            FROM promo_codes p
            LEFT JOIN promo_claims pc ON pc.promo_code = p.promo_code
            WHERE p.status != 'archived'
            GROUP BY p.promo_code, p.title, p.reward_amount, p.total_uses, p.status, p.created_at
            ORDER BY datetime(p.created_at) DESC
            """
    ) as cur:
        return await cur.fetchall()


async def list_promos_latest(
        db: aiosqlite.Connection,
        limit: int = 5,
):
    await ensure_promos_schema(db)
    async with db.execute(
            """
            SELECT
                p.promo_code,
                p.title,
                p.reward_amount,
                p.total_uses,
                p.status,
                p.created_at,
                COUNT(pc.id) AS claims_count
            FROM promo_codes p
            LEFT JOIN promo_claims pc ON pc.promo_code = p.promo_code
            WHERE p.status != 'archived'
            GROUP BY p.promo_code, p.title, p.reward_amount, p.total_uses, p.status, p.created_at
            ORDER BY datetime(p.created_at) DESC
            LIMIT ?
            """,
            (int(limit),),
    ) as cur:
        return await cur.fetchall()


async def promos_status_counts(db: aiosqlite.Connection) -> tuple[int, int, int]:
    await ensure_promos_schema(db)
    async with db.execute(
            "SELECT status, COUNT(*) AS cnt FROM promo_codes WHERE status != 'archived' GROUP BY status"
    ) as cur:
        rows = await cur.fetchall()

    counts = {"active": 0, "ended": 0, "draft": 0}
    for row in rows:
        counts[str(row["status"])] = int(row["cnt"])
    return counts["active"], counts["ended"], counts["draft"]


async def has_promo_claim(
        db: aiosqlite.Connection,
        promo_code: str,
        user_id: int,
) -> bool:
    await ensure_promos_schema(db)
    async with db.execute(
            """
            SELECT 1
            FROM promo_claims
            WHERE promo_code = ?
              AND user_id = ?
            LIMIT 1
            """,
            (promo_code, int(user_id)),
    ) as cur:
        return await cur.fetchone() is not None


async def add_promo_claim(
        db: aiosqlite.Connection,
        promo_code: str,
        user_id: int,
        amount: float,
) -> None:
    await ensure_promos_schema(db)
    await db.execute(
        """
        INSERT INTO promo_claims (promo_code, user_id, amount)
        VALUES (?, ?, ?)
        """,
        (promo_code, int(user_id), float(amount)),
    )


async def get_promo_claims_count(
        db: aiosqlite.Connection,
        promo_code: str,
) -> int:
    await ensure_promos_schema(db)
    async with db.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM promo_claims
            WHERE promo_code = ?
            """,
            (promo_code,),
    ) as cur:
        row = await cur.fetchone()
    return int(row["cnt"] or 0)


async def claimed_usernames(
        db: aiosqlite.Connection,
        promo_code: str,
) -> list[str]:
    await ensure_promos_schema(db)
    async with db.execute(
            """
            SELECT u.username
            FROM promo_claims pc
            JOIN users u ON u.user_id = pc.user_id
            WHERE pc.promo_code = ?
              AND u.username IS NOT NULL
              AND u.username != ''
            ORDER BY datetime(pc.claimed_at) ASC
            """,
            (promo_code,),
    ) as cur:
        rows = await cur.fetchall()
    return [row["username"] for row in rows]


async def promo_stats(
        db: aiosqlite.Connection,
        promo_code: str,
) -> tuple[int, int, int, float]:
    await ensure_promos_schema(db)
    async with db.execute(
            """
            SELECT
                p.total_uses,
                COUNT(pc.id) AS claims_count,
                COALESCE(SUM(pc.amount), 0) AS total_paid
            FROM promo_codes p
            LEFT JOIN promo_claims pc ON pc.promo_code = p.promo_code
            WHERE p.promo_code = ?
            GROUP BY p.total_uses
            """,
            (promo_code,),
    ) as cur:
        row = await cur.fetchone()

    if row is None:
        return 0, 0, 0, 0.0

    total_uses = int(row["total_uses"] or 0)
    claims_count = int(row["claims_count"] or 0)
    remaining_uses = max(total_uses - claims_count, 0)
    total_paid = float(row["total_paid"] or 0.0)
    return claims_count, total_uses, remaining_uses, total_paid


async def total_assigned_amount(db: aiosqlite.Connection) -> float:
    await ensure_promos_schema(db)
    async with db.execute(
            """
            SELECT COALESCE(SUM(reward_amount * total_uses), 0) AS total
            FROM promo_codes
            WHERE status != 'archived'
            """
    ) as cur:
        row = await cur.fetchone()
    return float(row["total"] or 0.0)


async def unclaimed_total_amount(db: aiosqlite.Connection) -> float:
    await ensure_promos_schema(db)
    async with db.execute(
            """
            SELECT COALESCE(
                SUM(
                    MAX(p.total_uses - COALESCE(pc.claims_count, 0), 0) * p.reward_amount
                ),
                0
            ) AS total
            FROM promo_codes p
            LEFT JOIN (
                SELECT promo_code, COUNT(*) AS claims_count
                FROM promo_claims
                GROUP BY promo_code
            ) pc ON pc.promo_code = p.promo_code
            WHERE p.status != 'archived'
            """
    ) as cur:
        row = await cur.fetchone()
    return float(row["total"] or 0.0)


async def global_claims_stats(db: aiosqlite.Connection) -> tuple[int, float]:
    await ensure_promos_schema(db)
    async with db.execute(
            """
            SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total
            FROM promo_claims
            """
    ) as cur:
        row = await cur.fetchone()
    return int(row["cnt"] or 0), float(row["total"] or 0.0)
