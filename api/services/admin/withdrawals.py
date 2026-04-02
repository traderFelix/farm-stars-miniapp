from typing import Any

import aiosqlite
from fastapi import HTTPException

from shared.db.withdrawals import get_withdrawal, list_withdrawals


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
