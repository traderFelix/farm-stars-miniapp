import logging
from typing import Optional

import aiosqlite

from shared.config import REFERRAL_PERCENT
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