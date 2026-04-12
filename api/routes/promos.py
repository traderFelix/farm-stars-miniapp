from fastapi import APIRouter, Depends, Request

from api.dependencies.auth import get_current_user_id
from api.security.request_fingerprint import build_request_fingerprint
from api.schemas.promos import PromoRedeemRequest, PromoRedeemResponse
from api.services.promos import redeem_promo_for_user

router = APIRouter(prefix="/promos", tags=["promos"])


@router.post("/redeem", response_model=PromoRedeemResponse)
async def redeem_promo(
        payload: PromoRedeemRequest,
        request: Request,
        user_id: int = Depends(get_current_user_id),
) -> PromoRedeemResponse:
    return await redeem_promo_for_user(
        user_id=user_id,
        code=payload.code,
        fingerprint=build_request_fingerprint(request),
    )
