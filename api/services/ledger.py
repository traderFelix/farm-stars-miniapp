from api.db.connection import get_db
from api.schemas.ledger import LedgerItem, LedgerListResponse, LedgerTotalResponse
from shared.db.ledger import ledger_last, ledger_sum


async def get_ledger_for_user(user_id: int, limit: int = 20) -> LedgerListResponse:
    db = await get_db()
    try:
        rows = await ledger_last(db, user_id=user_id, limit=limit)
    finally:
        await db.close()

    items = [
        LedgerItem(
            created_at=row["created_at"],
            delta=float(row["delta"] or 0),
            reason=row["reason"],
            campaign_key=row["campaign_key"],
            meta=row["meta"],
        )
        for row in rows
    ]

    return LedgerListResponse(items=items)


async def get_ledger_total_for_user(user_id: int) -> LedgerTotalResponse:
    db = await get_db()
    try:
        total = await ledger_sum(db, user_id=user_id)
    finally:
        await db.close()

    return LedgerTotalResponse(total=float(total or 0))