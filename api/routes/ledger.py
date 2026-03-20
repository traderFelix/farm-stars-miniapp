from fastapi import APIRouter, Depends, Query

from api.dependencies.auth import get_current_user_id
from api.schemas.ledger import LedgerListResponse, LedgerTotalResponse
from api.services.ledger import get_ledger_for_user, get_ledger_total_for_user

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.get("", response_model=LedgerListResponse)
async def get_ledger(
        limit: int = Query(20, ge=1, le=100),
        user_id: int = Depends(get_current_user_id),
):
    return await get_ledger_for_user(user_id=user_id, limit=limit)


@router.get("/sum", response_model=LedgerTotalResponse)
async def get_ledger_sum(
        user_id: int = Depends(get_current_user_id),
):
    return await get_ledger_total_for_user(user_id=user_id)