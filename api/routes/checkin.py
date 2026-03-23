from fastapi import APIRouter, Depends

from api.db.connection import get_db
from api.dependencies.auth import get_current_user_id

from api.schemas.checkin import CheckinStatusResponse, CheckinClaimResponse

from shared.db.users import (
    get_daily_checkin_status,
    claim_daily_checkin,
)


router = APIRouter(prefix="/checkin", tags=["checkin"])


@router.get("/status", response_model=CheckinStatusResponse)
async def get_checkin_status(user_id: int = Depends(get_current_user_id)):
    db = await get_db()
    try:
        status = await get_daily_checkin_status(
            db=db,
            user_id=user_id,
        )
    finally:
        await db.close()

    return CheckinStatusResponse(**status)


@router.post("/claim", response_model=CheckinClaimResponse)
async def claim_checkin(user_id: int = Depends(get_current_user_id)):
    db = await get_db()
    try:
        status = await get_daily_checkin_status(
            db=db,
            user_id=user_id,
        )

        ok, message, balance = await claim_daily_checkin(
            db=db,
            user_id=user_id,
            username=None,
            first_name=None,
            last_name=None,
        )
    finally:
        await db.close()

    return CheckinClaimResponse(
        ok=ok,
        claimed_amount=float(status["reward_today"]) if ok else 0.0,
        current_cycle_day=int(status["current_cycle_day"]),
        balance=float(balance),
        claimed_at=status["server_time"],
        message=message,
    )