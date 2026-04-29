from typing import Any, Optional

import aiosqlite
from fastapi import HTTPException

from shared.db.common import tx
from shared.db.ledger import add_referral_bonus_for_paid_withdrawal, apply_balance_delta, ledger_add
from shared.db.withdrawals import (
    find_withdraw_by_fee_charge_id,
    get_withdrawal,
    list_recent_fee_payments,
    list_withdrawals,
    mark_withdraw_fee_refunded,
    set_withdrawal_status,
)
from shared.db.xtr_ledger import xtr_ledger_add


def _serialize_withdrawal(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "user_id": int(row["user_id"]),
        "username": row["username"],
        "amount": float(row["amount"] or 0),
        "method": str(row["method"]),
        "wallet": row["wallet"],
        "status": str(row["status"]),
        "created_at": row["created_at"],
        "processed_at": row["processed_at"],
        "fee_xtr": int(row["fee_xtr"] or 0),
        "fee_paid": bool(row["fee_paid"] or 0),
        "fee_refunded": bool(row["fee_refunded"] or 0),
        "fee_telegram_charge_id": row["fee_telegram_charge_id"],
        "fee_invoice_payload": row["fee_invoice_payload"],
    }


def _serialize_recent_fee_payment(row: Any) -> dict[str, Any]:
    return {
        "withdrawal_id": int(row["withdrawal_id"]),
        "user_id": int(row["user_id"]),
        "username": row["username"],
        "fee_xtr": int(row["fee_xtr"] or 0),
        "fee_paid": bool(row["fee_paid"] or 0),
        "fee_refunded": bool(row["fee_refunded"] or 0),
        "fee_telegram_charge_id": row["fee_telegram_charge_id"],
        "created_at": row["created_at"],
    }


def _build_fee_refund_context(row: Any) -> dict[str, Any]:
    fee_xtr = int(row["fee_xtr"] or 0)
    fee_paid = bool(row["fee_paid"] or 0)
    fee_refunded = bool(row["fee_refunded"] or 0)
    charge_id = row["fee_telegram_charge_id"]

    if fee_xtr <= 0 or not fee_paid:
        status = "no_fee_paid"
    elif fee_refunded:
        status = "already_refunded"
    elif not charge_id:
        status = "missing_charge_id"
    else:
        status = "ready"

    return {
        "status": status,
        "user_id": int(row["user_id"]),
        "fee_xtr": fee_xtr,
        "charge_id": charge_id,
    }


async def _get_pending_withdrawal(db: aiosqlite.Connection, withdrawal_id: int) -> Any:
    row = await get_withdrawal(db, int(withdrawal_id))
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if str(row["status"]) != "pending":
        raise HTTPException(status_code=409, detail="Уже обработана")
    async with db.execute(
            """
        SELECT 1
        FROM ledger
        WHERE user_id = ?
          AND withdrawal_id = ?
          AND reason = 'withdraw_hold'
        LIMIT 1
        """,
            (int(row["user_id"]), int(withdrawal_id)),
    ) as cur:
        hold_row = await cur.fetchone()
    if not hold_row:
        raise HTTPException(
            status_code=409,
            detail="Заявка без удержания баланса, нужна ручная проверка",
        )
    return row


async def list_requests(
        db: aiosqlite.Connection,
        *,
        status: str = "pending",
        limit: int = 20,
) -> dict[str, Any]:
    rows = await list_withdrawals(db, status=status, limit=limit)
    return {
        "status": status,
        "limit": int(limit),
        "items": [_serialize_withdrawal(row) for row in rows],
    }


async def get_request(
        db: aiosqlite.Connection,
        withdrawal_id: int,
) -> dict[str, Any]:
    row = await get_withdrawal(db, int(withdrawal_id))
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return _serialize_withdrawal(row)


async def list_recent_fee_payment_requests(
        db: aiosqlite.Connection,
        *,
        limit: int = 10,
) -> dict[str, Any]:
    rows = await list_recent_fee_payments(db, limit=limit)
    return {
        "limit": int(limit),
        "items": [_serialize_recent_fee_payment(row) for row in rows],
    }


async def mark_paid(
        db: aiosqlite.Connection,
        withdrawal_id: int,
        *,
        admin_id: int,
) -> dict[str, Any]:
    async with tx(db):
        row = await _get_pending_withdrawal(db, withdrawal_id)

        await set_withdrawal_status(db, withdrawal_id, "paid", int(admin_id))
        await ledger_add(
            db,
            user_id=int(row["user_id"]),
            delta=0.0,
            reason="withdraw_paid",
            withdrawal_id=int(withdrawal_id),
            meta=f"method={row['method']}",
        )

        bonus_added, referrer_id, bonus_amount = await add_referral_bonus_for_paid_withdrawal(
            db,
            referred_user_id=int(row["user_id"]),
            withdrawal_id=int(withdrawal_id),
            withdraw_amount=float(row["amount"]),
        )

    updated = await get_request(db, withdrawal_id)
    return {
        "withdrawal": updated,
        "referral_bonus": {
            "added": bool(bonus_added),
            "referrer_id": int(referrer_id) if referrer_id else None,
            "amount": float(bonus_amount or 0),
        },
    }


async def reject(
        db: aiosqlite.Connection,
        withdrawal_id: int,
        *,
        admin_id: int,
) -> dict[str, Any]:
    async with tx(db):
        row = await _get_pending_withdrawal(db, withdrawal_id)

        await set_withdrawal_status(db, withdrawal_id, "rejected", int(admin_id))
        await apply_balance_delta(
            db,
            user_id=int(row["user_id"]),
            delta=float(row["amount"]),
            reason="withdraw_release",
            withdrawal_id=int(withdrawal_id),
            meta="rejected",
        )

    updated = await get_request(db, withdrawal_id)
    return {
        "withdrawal": updated,
        "fee_refund": _build_fee_refund_context(row),
    }


async def record_fee_refund(
        db: aiosqlite.Connection,
        withdrawal_id: int,
        *,
        meta: Optional[str],
) -> dict[str, Any]:
    row = await get_withdrawal(db, int(withdrawal_id))
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    context = _build_fee_refund_context(row)
    status = context["status"]
    if status != "ready":
        return {
            "status": status,
            "withdrawal_id": int(row["id"]),
            "user_id": int(row["user_id"]),
            "fee_xtr": int(row["fee_xtr"] or 0),
            "charge_id": row["fee_telegram_charge_id"],
        }

    async with tx(db):
        await mark_withdraw_fee_refunded(db, int(withdrawal_id))
        await xtr_ledger_add(
            db,
            user_id=int(row["user_id"]),
            withdrawal_id=int(withdrawal_id),
            delta_xtr=-int(row["fee_xtr"] or 0),
            reason="withdraw_fee_refunded",
            telegram_payment_charge_id=row["fee_telegram_charge_id"],
            meta=meta or "status=rejected",
        )

    return {
        "status": "refunded",
        "withdrawal_id": int(row["id"]),
        "user_id": int(row["user_id"]),
        "fee_xtr": int(row["fee_xtr"] or 0),
        "charge_id": row["fee_telegram_charge_id"],
    }


async def record_fee_refund_by_charge_id(
        db: aiosqlite.Connection,
        charge_id: str,
        *,
        meta: Optional[str],
) -> dict[str, Any]:
    row = await find_withdraw_by_fee_charge_id(db, charge_id)
    if not row:
        return {
            "status": "not_found",
            "withdrawal_id": None,
            "user_id": None,
            "fee_xtr": 0,
            "charge_id": charge_id,
        }

    if bool(row["fee_refunded"] or 0):
        return {
            "status": "already_refunded",
            "withdrawal_id": int(row["withdrawal_id"]),
            "user_id": int(row["user_id"]),
            "fee_xtr": int(row["fee_xtr"] or 0),
            "charge_id": charge_id,
        }

    async with tx(db):
        await mark_withdraw_fee_refunded(db, int(row["withdrawal_id"]))
        await xtr_ledger_add(
            db,
            user_id=int(row["user_id"]),
            withdrawal_id=int(row["withdrawal_id"]),
            delta_xtr=-int(row["fee_xtr"] or 0),
            reason="withdraw_fee_refunded",
            telegram_payment_charge_id=charge_id,
            meta=meta or "status=manual_refund",
        )

    return {
        "status": "refunded",
        "withdrawal_id": int(row["withdrawal_id"]),
        "user_id": int(row["user_id"]),
        "fee_xtr": int(row["fee_xtr"] or 0),
        "charge_id": charge_id,
    }
