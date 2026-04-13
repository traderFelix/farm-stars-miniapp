import logging
from typing import Optional

import aiosqlite

from shared.config import REFERRAL_PERCENT, SYSTEM_REASONS, GOOD_ACTIVITY_REASONS

from shared.db.users import get_referrer_id

logger = logging.getLogger(__name__)


async def add_referral_bonus_for_paid_withdrawal(
        db: aiosqlite.Connection,
        referred_user_id: int,
        withdrawal_id: int,
        withdraw_amount: float,
) -> tuple[bool, Optional[int], float]:
    logger.info(
        "REF CHECK | referred_user=%s withdrawal=%s amount=%s",
        referred_user_id, withdrawal_id, withdraw_amount
    )

    referred_user_id = int(referred_user_id)
    withdrawal_id = int(withdrawal_id)
    withdraw_amount = float(withdraw_amount)

    referrer_id = await get_referrer_id(db, referred_user_id)
    if not referrer_id:
        return False, None, 0.0

    async with db.execute(
            """
        SELECT 1
        FROM ledger
        WHERE withdrawal_id = ? AND reason = 'referral_bonus'
        LIMIT 1
        """,
            (withdrawal_id,),
    ) as cur:
        exists = await cur.fetchone()

    if exists:
        return False, referrer_id, 0.0

    bonus = round(withdraw_amount * REFERRAL_PERCENT, 2)
    if bonus <= 0:
        return False, referrer_id, 0.0

    await apply_balance_delta(
        db,
        user_id=referrer_id,
        delta=bonus,
        reason="referral_bonus",
        withdrawal_id=withdrawal_id,
        meta=f"from_user_id={referred_user_id};percent={REFERRAL_PERCENT}",
    )

    logger.info(
        "REF RESULT | bonus_added=%s referrer=%s amount=%s",
        True, referrer_id, bonus
    )

    return True, referrer_id, bonus


async def ledger_add(
        db: aiosqlite.Connection,
        user_id: int,
        delta: float,
        reason: str,
        campaign_key: Optional[str] = None,
        withdrawal_id: Optional[int] = None,
        meta: Optional[str] = None,
) -> None:
    await db.execute(
        """
        INSERT INTO ledger (user_id, delta, reason, campaign_key, withdrawal_id, meta, created_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (int(user_id), float(delta), reason, campaign_key, withdrawal_id, meta),
    )


async def ledger_last(db: aiosqlite.Connection, user_id: int, limit: int = 20):
    async with db.execute(
            """
        SELECT created_at, delta, reason, campaign_key, meta
        FROM ledger
        WHERE user_id = ?
        ORDER BY datetime(created_at) DESC
        LIMIT ?
        """,
            (int(user_id), int(limit)),
    ) as cur:
        return await cur.fetchall()


async def list_global_ledger_page(
        db: aiosqlite.Connection,
        *,
        limit: int,
        offset: int,
):
    async with db.execute(
            """
        SELECT l.created_at, u.username, l.delta, l.reason, l.campaign_key
        FROM ledger l
        LEFT JOIN users u ON u.user_id = l.user_id
        ORDER BY l.created_at DESC, l.id DESC
        LIMIT ? OFFSET ?
        """,
            (int(limit), int(offset)),
    ) as cur:
        return await cur.fetchall()


async def list_user_ledger_page(
        db: aiosqlite.Connection,
        user_id: int,
        *,
        limit: int,
        offset: int,
):
    async with db.execute(
            """
        SELECT created_at, delta, reason, campaign_key
        FROM ledger
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
            (int(user_id), int(limit), int(offset)),
    ) as cur:
        return await cur.fetchall()


async def ledger_sum(db: aiosqlite.Connection, user_id: int) -> float:
    async with db.execute(
            "SELECT COALESCE(SUM(delta), 0) AS s FROM ledger WHERE user_id = ?",
            (int(user_id),),
    ) as cur:
        row = await cur.fetchone()
    return float(row["s"] or 0.0)


async def get_balance_adjusts_by_admin(db: aiosqlite.Connection) -> tuple[int, int]:
    query = """
    SELECT
        COALESCE(SUM(CASE WHEN delta > 0 THEN delta END), 0) AS added,
        COALESCE(SUM(CASE WHEN delta < 0 THEN -delta END), 0) AS removed
    FROM ledger
    WHERE reason = 'admin_adjust'
    """

    async with db.execute(query) as cur:
        row = await cur.fetchone()
        added = int(row[0] or 0)
        removed = int(row[1] or 0)

    return added, removed


async def ledger_sum_by_reason(db: aiosqlite.Connection, reason: str) -> float:
    query = """
    SELECT COALESCE(SUM(delta), 0)
    FROM ledger
    WHERE reason = ?
    """
    async with db.execute(query, (reason,)) as cur:
        row = await cur.fetchone()
        return float(row[0] or 0)


async def apply_balance_delta(
        db: aiosqlite.Connection,
        user_id: int,
        delta: float,
        reason: str,
        campaign_key: Optional[str] = None,
        withdrawal_id: Optional[int] = None,
        meta: Optional[str] = None,
) -> None:
    await db.execute(
        """
        INSERT INTO ledger (user_id, delta, reason, campaign_key, withdrawal_id, meta, created_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (int(user_id), float(delta), reason, campaign_key, withdrawal_id, meta),
    )

    logger.info(
        "LEDGER | user_id=%s delta=%s reason=%s withdrawal_id=%s campaign=%s meta=%s",
        user_id, delta, reason, withdrawal_id, campaign_key, meta
    )

    await db.execute(
        "UPDATE users SET balance = balance + ? WHERE user_id = ?",
        (float(delta), int(user_id)),
    )


async def apply_balance_debit_if_enough(
        db: aiosqlite.Connection,
        user_id: int,
        amount: float,
        reason: str,
        campaign_key: Optional[str] = None,
        withdrawal_id: Optional[int] = None,
        meta: Optional[str] = None,
) -> bool:
    amount = float(amount)

    cur = await db.execute(
        "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
        (amount, int(user_id), amount),
    )
    if cur.rowcount != 1:
        return False

    await db.execute(
        """
        INSERT INTO ledger (user_id, delta, reason, campaign_key, withdrawal_id, meta, created_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (int(user_id), -amount, reason, campaign_key, withdrawal_id, meta),
    )
    return True

async def get_user_earnings_breakdown(db: aiosqlite.Connection, user_id: int) -> dict[str, float]:
    system_placeholders = ",".join("?" for _ in SYSTEM_REASONS)

    query = f"""
        SELECT
            COALESCE(SUM(CASE WHEN reason = 'view_post_bonus' THEN delta ELSE 0 END), 0) AS view_post_bonus,
            COALESCE(SUM(CASE WHEN reason = 'daily_bonus' THEN delta ELSE 0 END), 0) AS daily_bonus,
            COALESCE(SUM(CASE WHEN reason = 'contest_bonus' THEN delta ELSE 0 END), 0) AS contest_bonus,
            COALESCE(SUM(CASE WHEN reason = 'promo_bonus' THEN delta ELSE 0 END), 0) AS promo_bonus,
            COALESCE(SUM(CASE WHEN reason = 'referral_bonus' THEN delta ELSE 0 END), 0) AS referral_bonus,
            COALESCE(SUM(CASE WHEN reason = 'admin_adjust' THEN delta ELSE 0 END), 0) AS admin_adjust,
            COALESCE(
                SUM(
                    CASE
                        WHEN reason NOT IN ({system_placeholders})
                        THEN delta ELSE 0
                    END
                ),
                0
            ) AS total_earned
        FROM ledger
        WHERE user_id = ?
    """

    params = (*SYSTEM_REASONS, int(user_id))
    async with db.execute(query, params) as cursor:
        row = await cursor.fetchone()

    view_post_bonus = float(row["view_post_bonus"] or 0)
    daily_bonus = float(row["daily_bonus"] or 0)
    contest_bonus = float(row["contest_bonus"] or 0)
    promo_bonus = float(row["promo_bonus"] or 0)
    referral_bonus = float(row["referral_bonus"] or 0)
    admin_adjust = float(row["admin_adjust"] or 0)
    total = float(row["total_earned"] or 0)

    def pct(value: float, total_value: float) -> float:
        if total_value == 0:
            return 0.0
        return value * 100 / total_value

    return {
        "total": total,
        "view_post_bonus": view_post_bonus,
        "view_post_bonus_pct": pct(view_post_bonus, total),
        "daily_bonus": daily_bonus,
        "daily_bonus_pct": pct(daily_bonus, total),
        "contest_bonus": contest_bonus,
        "contest_bonus_pct": pct(contest_bonus, total),
        "promo_bonus": promo_bonus,
        "promo_bonus_pct": pct(promo_bonus, total),
        "referral_bonus": referral_bonus,
        "referral_bonus_pct": pct(referral_bonus, total),
        "admin_adjust": admin_adjust,
        "admin_adjust_pct": pct(admin_adjust, total),
    }

async def get_activity_index(db, user_id: int) -> float:
    system_placeholders = ",".join("?" for _ in SYSTEM_REASONS)
    good_placeholders = ",".join("?" for _ in GOOD_ACTIVITY_REASONS)

    sql = f"""
    SELECT
        COALESCE(SUM(CASE
            WHEN reason IN ({good_placeholders}) THEN delta
            ELSE 0
        END), 0) AS good_total,
        COALESCE(SUM(delta), 0) AS total_earned
    FROM ledger
    WHERE user_id = ?
      AND reason NOT IN ({system_placeholders})
    """

    params = [*GOOD_ACTIVITY_REASONS, int(user_id), *SYSTEM_REASONS]

    async with db.execute(sql, params) as cur:
        row = await cur.fetchone()

    good_total = float(row["good_total"] or 0)
    total_earned = float(row["total_earned"] or 0)

    if total_earned <= 0:
        return 0.0

    return (good_total / total_earned) * 100.0


async def balances_audit(db: aiosqlite.Connection, limit: int = 10):
    async with db.execute(
            """
        SELECT
          u.user_id,
          u.username,
          COALESCE(u.balance, 0) AS users_balance,
          COALESCE(SUM(l.delta), 0) AS ledger_sum,
          (COALESCE(u.balance, 0) - COALESCE(SUM(l.delta), 0)) AS diff
        FROM users u
        LEFT JOIN ledger l ON l.user_id = u.user_id
        GROUP BY u.user_id
        HAVING ABS(diff) > 1e-9
        ORDER BY ABS(diff) DESC
        LIMIT ?
        """,
            (int(limit),),
    ) as cur:
        return await cur.fetchall()
