from typing import Optional

from api.db.connection import get_db
from api.schemas.checkin import CheckinStatusResponse, CheckinClaimResponse
from shared.db.users import get_daily_checkin_status, claim_daily_checkin


async def get_checkin_status_service(
        user_id: int,
        *,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
) -> CheckinStatusResponse:
    db = await get_db()
    try:
        status = await get_daily_checkin_status(
            db=db,
            user_id=int(user_id),
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
    finally:
        await db.close()

    return CheckinStatusResponse(**status)


async def claim_checkin_service(
        user_id: int,
        *,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
) -> CheckinClaimResponse:
    db = await get_db()
    try:
        status = await get_daily_checkin_status(
            db=db,
            user_id=int(user_id),
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        ok, message, balance = await claim_daily_checkin(
            db=db,
            user_id=int(user_id),
            username=username,
            first_name=first_name,
            last_name=last_name,
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
