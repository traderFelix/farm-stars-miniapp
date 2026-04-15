import logging

from fastapi import HTTPException

from api.db.connection import get_db
from api.schemas.referrals import ReferralMeResponse
from shared.config import REFERRAL_PERCENT, TELEGRAM_BOT_USERNAME
from shared.db.users import get_referrals_count

logger = logging.getLogger(__name__)
REFERRALS_UNAVAILABLE_DETAIL = "Реферальная ссылка сейчас недоступна. Попробуй еще раз чуть позже."


async def get_referral_summary_for_user(user_id: int) -> ReferralMeResponse:
    bot_username = (TELEGRAM_BOT_USERNAME or "").strip().lstrip("@")
    if not bot_username:
        logger.error("TELEGRAM_BOT_USERNAME is not configured for referrals")
        raise HTTPException(status_code=500, detail=REFERRALS_UNAVAILABLE_DETAIL)

    db = await get_db()
    try:
        invited_count = await get_referrals_count(db, user_id)
    finally:
        await db.close()

    invite_link = f"https://t.me/{bot_username}?start={int(user_id)}"
    reward_percent = round(REFERRAL_PERCENT * 100, 2)

    return ReferralMeResponse(
        user_id=int(user_id),
        invited_count=int(invited_count),
        reward_percent=reward_percent,
        invite_link=invite_link,
        share_text=(
            "Присоединяйся к Felix Farm Stars. "
            f"Вот моя ссылка: {invite_link}"
        ),
    )
