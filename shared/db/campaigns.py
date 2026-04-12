from typing import List, Optional, Tuple

import aiosqlite

from shared.db.users import get_user_id_by_username


async def upsert_campaign(
        db: aiosqlite.Connection,
        campaign_key: str,
        title: str,
        reward_amount: float,
        status: str = "draft",
        post_url: Optional[str] = None,
) -> None:
    await db.execute(
        """
        INSERT INTO campaigns (campaign_key, title, reward_amount, status, description)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(campaign_key) DO UPDATE SET
            title=excluded.title,
            reward_amount=excluded.reward_amount,
            status=excluded.status,
            description=excluded.description
        """,
        (campaign_key, title, float(reward_amount), status, post_url),
    )


async def set_campaign_status(
        db: aiosqlite.Connection,
        campaign_key: str,
        status: str,
) -> None:
    await db.execute(
        "UPDATE campaigns SET status = ? WHERE campaign_key = ?",
        (status, campaign_key),
    )


async def delete_campaign(
        db: aiosqlite.Connection,
        campaign_key: str,
) -> None:
    await db.execute("DELETE FROM claims WHERE campaign_key = ?", (campaign_key,))
    await db.execute("DELETE FROM campaign_winners WHERE campaign_key = ?", (campaign_key,))
    await db.execute("DELETE FROM campaigns WHERE campaign_key = ?", (campaign_key,))


async def get_campaign(
        db: aiosqlite.Connection,
        campaign_key: str,
):
    async with db.execute(
            """
            SELECT campaign_key, title, reward_amount, status, description AS post_url, created_at
            FROM campaigns
            WHERE campaign_key = ?
            """,
            (campaign_key,),
    ) as cur:
        return await cur.fetchone()


async def list_campaigns(db: aiosqlite.Connection):
    async with db.execute(
            """
            SELECT campaign_key, title, reward_amount, status, description AS post_url, created_at
            FROM campaigns
            ORDER BY datetime(created_at) DESC
            """
    ) as cur:
        return await cur.fetchall()


async def list_campaigns_latest(
        db: aiosqlite.Connection,
        limit: int = 5,
):
    async with db.execute(
            """
            SELECT campaign_key, title, reward_amount, status, description AS post_url, created_at
            FROM campaigns
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (int(limit),),
    ) as cur:
        return await cur.fetchall()


async def campaigns_status_counts(db: aiosqlite.Connection) -> Tuple[int, int, int]:
    async with db.execute("SELECT status, COUNT(*) AS cnt FROM campaigns GROUP BY status") as cur:
        rows = await cur.fetchall()

    counts = {"active": 0, "ended": 0, "draft": 0}
    for row in rows:
        counts[str(row["status"])] = int(row["cnt"])

    return counts["active"], counts["ended"], counts["draft"]


async def add_winners(
        db: aiosqlite.Connection,
        campaign_key: str,
        usernames: List[str],
) -> int:
    count = 0
    for username in usernames:
        normalized_username = (username or "").strip().lstrip("@")
        if not normalized_username:
            continue
        await db.execute(
            "INSERT OR IGNORE INTO campaign_winners (campaign_key, username) VALUES (?, ?)",
            (campaign_key, normalized_username),
        )
        count += 1
    return count


async def list_winners(
        db: aiosqlite.Connection,
        campaign_key: str,
) -> List[str]:
    async with db.execute(
            """
            SELECT username
            FROM campaign_winners
            WHERE campaign_key = ?
            ORDER BY added_at ASC
            """,
            (campaign_key,),
    ) as cur:
        rows = await cur.fetchall()
    return [row["username"] for row in rows]


async def claimed_usernames(
        db: aiosqlite.Connection,
        campaign_key: str,
) -> List[str]:
    async with db.execute(
            """
            SELECT u.username
            FROM claims c
            JOIN users u ON u.user_id = c.user_id
            WHERE c.campaign_key = ?
              AND u.username IS NOT NULL
              AND u.username != ''
            ORDER BY datetime(c.claimed_at) ASC
            """,
            (campaign_key,),
    ) as cur:
        rows = await cur.fetchall()
    return [row["username"] for row in rows]


async def campaign_stats(
        db: aiosqlite.Connection,
        campaign_key: str,
) -> tuple[int, int, float]:
    async with db.execute(
            """
            SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total
            FROM claims
            WHERE campaign_key = ?
            """,
            (campaign_key,),
    ) as cur:
        row = await cur.fetchone()

    claims_count = int(row["cnt"] or 0)
    total_paid = float(row["total"] or 0.0)

    async with db.execute(
            "SELECT COUNT(*) AS c FROM campaign_winners WHERE campaign_key = ?",
            (campaign_key,),
    ) as cur:
        winners_row = await cur.fetchone()

    winners_count = int(winners_row["c"] or 0)
    return claims_count, winners_count, total_paid


async def global_claims_stats(db: aiosqlite.Connection) -> tuple[int, float]:
    async with db.execute("SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total FROM claims") as cur:
        row = await cur.fetchone()
    return int(row["cnt"] or 0), float(row["total"] or 0.0)


async def delete_winner_if_not_claimed(
        db: aiosqlite.Connection,
        campaign_key: str,
        username: str,
) -> tuple[bool, str]:
    normalized_username = (username or "").strip().lstrip("@")
    if not normalized_username:
        return False, "Пустой username"

    async with db.execute(
            """
            SELECT user_id
            FROM campaign_winners
            WHERE campaign_key = ?
              AND username = ?
            """,
            (campaign_key, normalized_username),
    ) as cur:
        row = await cur.fetchone()

    if row is None:
        return False, "Этого username нет в списке победителей"

    winner_user_id = row["user_id"]
    user_id_by_username = None
    if winner_user_id is None:
        user_id_by_username = await get_user_id_by_username(db, normalized_username)

    async with db.execute(
            """
            SELECT 1
            FROM claims cl
            WHERE cl.campaign_key = ?
              AND (
                (? IS NOT NULL AND cl.user_id = ?)
                OR (? IS NOT NULL AND cl.user_id = ?)
              )
            LIMIT 1
            """,
            (
                campaign_key,
                winner_user_id,
                winner_user_id,
                user_id_by_username,
                user_id_by_username,
            ),
    ) as cur:
        if await cur.fetchone() is not None:
            return False, "Нельзя удалить: этот победитель уже заклеймил"

    await db.execute(
        "DELETE FROM campaign_winners WHERE campaign_key = ? AND username = ?",
        (campaign_key, normalized_username),
    )
    return True, "Удалено"


async def total_assigned_amount(db: aiosqlite.Connection) -> float:
    async with db.execute(
            """
            SELECT COALESCE(SUM(c.reward_amount), 0) AS total
            FROM campaign_winners w
            JOIN campaigns c ON c.campaign_key = w.campaign_key
            """
    ) as cur:
        row = await cur.fetchone()
    return float(row["total"] or 0.0)


async def unclaimed_total_amount(db: aiosqlite.Connection) -> float:
    async with db.execute(
            """
            SELECT COALESCE(SUM(c.reward_amount), 0) AS total
            FROM campaign_winners w
            JOIN campaigns c ON c.campaign_key = w.campaign_key
            LEFT JOIN users u ON u.username = w.username
            WHERE NOT EXISTS (
                SELECT 1
                FROM claims cl
                WHERE cl.campaign_key = w.campaign_key
                  AND (
                    (w.user_id IS NOT NULL AND cl.user_id = w.user_id)
                    OR (w.user_id IS NULL AND u.user_id IS NOT NULL AND cl.user_id = u.user_id)
                  )
            )
            """
    ) as cur:
        row = await cur.fetchone()
    return float(row["total"] or 0.0)
