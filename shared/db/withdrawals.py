import aiosqlite, logging

from typing import Optional

logger = logging.getLogger(__name__)


async def create_withdrawal(
        db: aiosqlite.Connection,
        user_id: int,
        amount: float,
        method: str,
        wallet: Optional[str] = None,
) -> int:
    cur = await db.execute(
        """
        INSERT INTO withdrawals (user_id, amount, method, wallet, status)
        VALUES (?, ?, ?, ?, 'pending')
        """,
        (int(user_id), float(amount), method, wallet),
    )

    logger.info(
        "WITHDRAW CREATE | user_id=%s amount=%s wallet=%s",
        user_id, amount, wallet
    )

    return int(cur.lastrowid)


async def list_withdrawals(db: aiosqlite.Connection, status: str = "pending", limit: int = 20):
    async with db.execute(
            """
        SELECT
            w.id,
            w.user_id,
            u.username,
            w.amount,
            w.method,
            w.wallet,
            w.status,
            w.created_at,
            w.processed_at,
            w.fee_xtr,
            w.fee_paid,
            w.fee_refunded,
            w.fee_telegram_charge_id,
            w.fee_invoice_payload
        FROM withdrawals w
        LEFT JOIN users u ON u.user_id = w.user_id
        WHERE w.status = ?
        ORDER BY datetime(w.created_at) DESC
        LIMIT ?
        """,
            (status, int(limit)),
    ) as cur:
        return await cur.fetchall()


async def get_withdrawal(db: aiosqlite.Connection, withdrawal_id: int):
    async with db.execute(
            """
        SELECT
            w.id,
            w.user_id,
            u.username,
            w.amount,
            w.method,
            w.wallet,
            w.status,
            w.created_at,
            w.processed_at,
            w.fee_xtr,
            w.fee_paid,
            w.fee_refunded,
            w.fee_telegram_charge_id,
            w.fee_invoice_payload
        FROM withdrawals w
        LEFT JOIN users u ON u.user_id = w.user_id
        WHERE w.id = ?
        """,
            (int(withdrawal_id),),
    ) as cur:
        return await cur.fetchone()


async def set_withdrawal_status(
        db: aiosqlite.Connection,
        withdrawal_id: int,
        status: str,
        processed_by: Optional[int] = None,
) -> None:
    await db.execute(
        """
        UPDATE withdrawals
        SET status = ?,
            processed_at = datetime('now'),
            processed_by = ?
        WHERE id = ?
        """,
        (status, processed_by, int(withdrawal_id)),
    )


async def user_withdrawals(db: aiosqlite.Connection, user_id: int, limit: int = 20):
    async with db.execute(
            """
        SELECT
            id,
            amount,
            method,
            wallet,
            status,
            created_at,
            processed_at,
            fee_xtr,
            fee_paid,
            fee_refunded,
            fee_telegram_charge_id,
            fee_invoice_payload
        FROM withdrawals
        WHERE user_id = ?
        ORDER BY datetime(created_at) DESC
        LIMIT ?
        """,
            (int(user_id), int(limit)),
    ) as cur:
        return await cur.fetchall()


async def total_withdrawn_amount(db: aiosqlite.Connection) -> int:
    query = """
    SELECT COALESCE(SUM(amount), 0)
    FROM withdrawals
    WHERE status = 'paid'
    """

    async with db.execute(query) as cur:
        row = await cur.fetchone()
        return int(row[0] or 0)


async def pending_withdrawn_amount(db: aiosqlite.Connection) -> int:
    query = """
    SELECT COALESCE(SUM(amount), 0)
    FROM withdrawals
    WHERE status = 'pending'
    """
    async with db.execute(query) as cur:
        row = await cur.fetchone()
        return int(row[0] or 0)


async def has_pending_withdrawal(db: aiosqlite.Connection, user_id: int) -> bool:
    async with db.execute(
            """
        SELECT 1
        FROM withdrawals
        WHERE user_id = ?
          AND status = 'pending'
        LIMIT 1
        """,
            (int(user_id),),
    ) as cur:
        return await cur.fetchone() is not None


async def wallet_used_by_another_user(
        db: aiosqlite.Connection,
        user_id: int,
        wallet: str,
) -> bool:
    async with db.execute(
            """
        SELECT 1
        FROM withdrawals
        WHERE method = 'ton'
          AND wallet = ?
          AND user_id != ?
        LIMIT 1
        """,
            (wallet.strip(), int(user_id)),
    ) as cur:
        return await cur.fetchone() is not None


async def wallet_users(db, wallet: str) -> list[str]:
    async with db.execute(
            """
        SELECT DISTINCT w.user_id, u.username
        FROM withdrawals w
        LEFT JOIN users u ON u.user_id = w.user_id
        WHERE w.wallet = ?
        ORDER BY w.user_id ASC
        """,
            (wallet.strip(),)
    ) as cur:
        rows = await cur.fetchall()

    result = []
    for user_id, username in rows:
        if username:
            result.append(f"@{username}")
        else:
            result.append(f"user_id={user_id}")

    return result


async def mark_withdraw_fee_refunded(db, withdrawal_id: int):
    await db.execute(
        """
        UPDATE withdrawals
        SET fee_refunded = 1
        WHERE id = ?
        """,
        (withdrawal_id,),
    )
    await db.commit()


async def list_recent_fee_payments(db, limit: int = 10):
    cur = await db.execute(
        """
        SELECT
            w.id AS withdrawal_id,
            w.user_id,
            u.username AS username,
            w.fee_xtr,
            w.fee_paid,
            w.fee_refunded,
            w.fee_telegram_charge_id,
            w.created_at
        FROM withdrawals w
        LEFT JOIN users u ON u.user_id = w.user_id
        WHERE w.fee_paid = 1
          AND w.fee_telegram_charge_id IS NOT NULL
          AND w.fee_telegram_charge_id != ''
        ORDER BY w.id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = await cur.fetchall()
    await cur.close()
    return rows


async def find_withdraw_by_fee_charge_id(db, charge_id: str):
    cur = await db.execute(
        """
        SELECT
            w.id AS withdrawal_id,
            w.user_id,
            w.fee_xtr,
            w.fee_paid,
            w.fee_refunded,
            w.fee_telegram_charge_id,
            w.created_at
        FROM withdrawals w
        WHERE w.fee_telegram_charge_id = ?
        LIMIT 1
        """,
        (charge_id,),
    )
    row = await cur.fetchone()
    await cur.close()
    return row


async def is_first_withdraw(db: aiosqlite.Connection, user_id: int) -> bool:
    async with db.execute(
            """
        SELECT 1
        FROM withdrawals
        WHERE user_id = ?
        LIMIT 1
        """,
            (int(user_id),),
    ) as cur:
        row = await cur.fetchone()
    return row is None


async def set_withdrawal_fee_info(
        db: aiosqlite.Connection,
        withdrawal_id: int,
        fee_xtr: int,
        fee_paid: bool,
        fee_payment_charge_id: Optional[str] = None,
        fee_invoice_payload: Optional[str] = None,
) -> None:
    await db.execute(
        """
        UPDATE withdrawals
        SET fee_xtr = ?,
            fee_paid = ?,
            fee_refunded = 0,
            fee_telegram_charge_id = ?,
            fee_invoice_payload = ?
        WHERE id = ?
        """,
        (
            int(fee_xtr),
            1 if fee_paid else 0,
            fee_payment_charge_id,
            fee_invoice_payload,
            int(withdrawal_id),
        ),
    )