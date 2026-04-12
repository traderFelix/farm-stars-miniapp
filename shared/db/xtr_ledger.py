from __future__ import annotations

from typing import Optional

import aiosqlite


async def xtr_ledger_add(
        db: aiosqlite.Connection,
        user_id: int,
        delta_xtr: int,
        reason: str,
        withdrawal_id: Optional[int] = None,
        telegram_payment_charge_id: Optional[str] = None,
        invoice_payload: Optional[str] = None,
        meta: Optional[str] = None,
) -> None:
    await db.execute(
        """
        INSERT INTO xtr_ledger (
            user_id,
            withdrawal_id,
            delta_xtr,
            reason,
            telegram_payment_charge_id,
            invoice_payload,
            meta,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            int(user_id),
            int(withdrawal_id) if withdrawal_id is not None else None,
            int(delta_xtr),
            reason,
            telegram_payment_charge_id,
            invoice_payload,
            meta,
        ),
    )