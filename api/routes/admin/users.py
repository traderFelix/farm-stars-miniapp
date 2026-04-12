from fastapi import APIRouter, Depends

from api.dependencies.internal import require_internal_token
from api.db.connection import get_db
from api.schemas.admin.users import (
    BalanceAdjustRequest,
    BalanceAdjustResponse,
    LookupRequest,
    ProfileResponse,
    RoleUpdateRequest,
    RoleUpdateResponse,
    SuspiciousRequest,
    UserLedgerResponse,
    UserRiskEventsResponse,
    UserStatsResponse,
)
from api.services.admin.users import (
    adjust_balance,
    clear_suspicious,
    get_profile,
    get_user_risk_history,
    get_stats,
    get_user_ledger,
    lookup_profile,
    mark_suspicious,
    update_role,
)

router = APIRouter(
    prefix="/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("/lookup", response_model=ProfileResponse)
async def lookup_user(payload: LookupRequest):
    db = await get_db()
    try:
        return await lookup_profile(db, payload.query)
    finally:
        await db.close()


@router.get("/{user_id}", response_model=ProfileResponse)
async def get_user_profile(user_id: int):
    db = await get_db()
    try:
        return await get_profile(db, user_id)
    finally:
        await db.close()


@router.get("/{user_id}/stats", response_model=UserStatsResponse)
async def get_user_stats(user_id: int):
    db = await get_db()
    try:
        return await get_stats(db, user_id)
    finally:
        await db.close()


@router.get("/{user_id}/ledger", response_model=UserLedgerResponse)
async def get_user_ledger_route(user_id: int, page: int = 0, page_size: int = 20):
    db = await get_db()
    try:
        return await get_user_ledger(db, user_id, page=page, page_size=page_size)
    finally:
        await db.close()


@router.get("/{user_id}/risk", response_model=UserRiskEventsResponse)
async def get_user_risk_route(user_id: int, page: int = 0, page_size: int = 20):
    db = await get_db()
    try:
        return await get_user_risk_history(db, user_id, page=page, page_size=page_size)
    finally:
        await db.close()


@router.post("/{user_id}/role", response_model=RoleUpdateResponse)
async def set_user_role(user_id: int, payload: RoleUpdateRequest):
    db = await get_db()
    try:
        return await update_role(db, user_id, payload.role_level)
    finally:
        await db.close()


@router.post("/{user_id}/balance-adjust", response_model=BalanceAdjustResponse)
async def adjust_user_balance(user_id: int, payload: BalanceAdjustRequest):
    db = await get_db()
    try:
        return await adjust_balance(
            db,
            user_id,
            amount=payload.amount,
            mode=payload.mode,
        )
    finally:
        await db.close()


@router.post("/{user_id}/mark-suspicious", response_model=ProfileResponse)
async def mark_user_suspicious(user_id: int, payload: SuspiciousRequest):
    db = await get_db()
    try:
        return await mark_suspicious(db, user_id, payload.reason)
    finally:
        await db.close()


@router.post("/{user_id}/clear-suspicious", response_model=ProfileResponse)
async def clear_user_suspicious(user_id: int):
    db = await get_db()
    try:
        return await clear_suspicious(db, user_id)
    finally:
        await db.close()
