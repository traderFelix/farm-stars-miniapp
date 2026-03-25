from api.db.connection import get_db
from api.schemas.checkin import CheckinStatusResponse, CheckinClaimResponse
from shared.db.users import get_daily_checkin_status, claim_daily_checkin


async def get_checkin_status_service(user_id: int) -> CheckinStatusResponse:
    db = await get_db()
    try:
        status = await get_daily_checkin_status(
            db=db,
            user_id=int(user_id),
            username=None,
            first_name=None,
            last_name=None,
        )
    finally:
        await db.close()

    return CheckinStatusResponse(**status)


async def claim_checkin_service(user_id: int) -> CheckinClaimResponse:
    db = await get_db()
    try:
        status = await get_daily_checkin_status(
            db=db,
            user_id=int(user_id),
            username=None,
            first_name=None,
            last_name=None,
        )
        ok, message, balance = await claim_daily_checkin(
            db=db,
            user_id=int(user_id),
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