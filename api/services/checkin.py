from typing import Optional

from api.db.connection import get_db
from api.security.request_fingerprint import RequestFingerprint
from api.services.antiabuse import log_user_action_with_fingerprint
from api.schemas.checkin import CheckinStatusResponse, CheckinClaimResponse
from shared.db.abuse import count_recent_abuse_events
from shared.db.users import add_user_risk_score
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
        fingerprint: Optional[RequestFingerprint] = None,
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
        await log_user_action_with_fingerprint(
            db,
            user_id=int(user_id),
            action="daily_claim_attempt",
            fingerprint=fingerprint,
            entity_type="daily_checkin",
            entity_id=str(status["current_cycle_day"]),
        )
        ok, message, balance = await claim_daily_checkin(
            db=db,
            user_id=int(user_id),
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        if not ok:
            await log_user_action_with_fingerprint(
                db,
                user_id=int(user_id),
                action="daily_claim_fail",
                fingerprint=fingerprint,
                entity_type="daily_checkin",
                entity_id=str(status["current_cycle_day"]),
            )
            recent_fails = await count_recent_abuse_events(db, int(user_id), "daily_claim_fail", 60)
            if recent_fails >= 5:
                await add_user_risk_score(
                    db,
                    int(user_id),
                    8,
                    "Подозрительно частые попытки ежедневного бонуса",
                    source="checkin",
                )
            await db.commit()
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
