from fastapi import APIRouter, Depends

from api.db.connection import get_db
from api.dependencies.internal import require_internal_token
from api.schemas.admin.withdrawals import WithdrawalItem, WithdrawalsResponse
from api.services.admin.withdrawals import get_request, list_requests

router = APIRouter(
    prefix="/admin/withdrawals",
    tags=["admin-withdrawals"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("", response_model=WithdrawalsResponse)
async def list_withdrawal_requests(status: str = "pending", limit: int = 20):
    db = await get_db()
    try:
        return await list_requests(db, status=status, limit=limit)
    finally:
        await db.close()


@router.get("/{withdrawal_id}", response_model=WithdrawalItem)
async def get_withdrawal_request(withdrawal_id: int):
    db = await get_db()
    try:
        return await get_request(db, withdrawal_id)
    finally:
        await db.close()
