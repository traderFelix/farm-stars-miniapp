from fastapi import APIRouter, Depends, Query

from api.dependencies.auth import get_current_user_id
from api.dependencies.internal import require_internal_token
from api.schemas.ledger import LedgerListResponse, LedgerTotalResponse
from api.services.ledger import get_ledger_for_user, get_ledger_total_for_user

router = APIRouter(prefix="/ledger", tags=["ledger"])


async def _get_ledger_for_user(user_id: int, limit: int) -> LedgerListResponse:
    return await get_ledger_for_user(user_id=user_id, limit=limit)


async def _get_ledger_total_for_user(user_id: int) -> LedgerTotalResponse:
    return await get_ledger_total_for_user(user_id=user_id)


@router.get("", response_model=LedgerListResponse)
async def get_ledger(
        limit: int = Query(20, ge=1, le=100),
        user_id: int = Depends(get_current_user_id),
):
    return await _get_ledger_for_user(user_id=user_id, limit=limit)


@router.get("/sum", response_model=LedgerTotalResponse)
async def get_ledger_sum(
        user_id: int = Depends(get_current_user_id),
):
    return await _get_ledger_total_for_user(user_id=user_id)


@router.get("/bot/{user_id}", response_model=LedgerListResponse)
async def bot_get_ledger(
        user_id: int,
        limit: int = Query(20, ge=1, le=100),
        _: None = Depends(require_internal_token),
):
    return await _get_ledger_for_user(user_id=user_id, limit=limit)


@router.get("/bot/{user_id}/sum", response_model=LedgerTotalResponse)
async def bot_get_ledger_sum(
        user_id: int,
        _: None = Depends(require_internal_token),
):
    return await _get_ledger_total_for_user(user_id=user_id)
