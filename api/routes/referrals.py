from fastapi import APIRouter, Depends

from api.dependencies.auth import get_current_user_id
from api.schemas.referrals import ReferralMeResponse
from api.services.referrals import get_referral_summary_for_user

router = APIRouter(prefix="/referrals", tags=["referrals"])


@router.get("/me", response_model=ReferralMeResponse)
async def get_my_referrals(
        user_id: int = Depends(get_current_user_id),
) -> ReferralMeResponse:
    return await get_referral_summary_for_user(user_id)
