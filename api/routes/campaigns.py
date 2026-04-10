from fastapi import APIRouter, Depends

from api.dependencies.auth import get_current_user_id
from api.dependencies.internal import require_internal_token
from api.schemas.campaigns import (
    CampaignClaimContextRequest,
    CampaignClaimResponse,
    CampaignListResponse,
)
from api.services.campaigns import (
    claim_campaign_reward_for_user,
    get_active_campaigns_for_user,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("/active", response_model=CampaignListResponse)
async def get_active_campaigns(
        user_id: int = Depends(get_current_user_id),
) -> CampaignListResponse:
    return await get_active_campaigns_for_user(user_id=user_id)


@router.post("/{campaign_key}/claim", response_model=CampaignClaimResponse)
async def claim_campaign(
        campaign_key: str,
        user_id: int = Depends(get_current_user_id),
) -> CampaignClaimResponse:
    return await claim_campaign_reward_for_user(
        user_id=user_id,
        campaign_key=campaign_key,
    )


@router.get(
    "/bot/active",
    response_model=CampaignListResponse,
    dependencies=[Depends(require_internal_token)],
)
async def bot_get_active_campaigns() -> CampaignListResponse:
    return await get_active_campaigns_for_user()


@router.post(
    "/bot/{campaign_key}/claim/{user_id}",
    response_model=CampaignClaimResponse,
    dependencies=[Depends(require_internal_token)],
)
async def bot_claim_campaign(
        campaign_key: str,
        user_id: int,
        payload: CampaignClaimContextRequest,
) -> CampaignClaimResponse:
    return await claim_campaign_reward_for_user(
        user_id=user_id,
        campaign_key=campaign_key,
        username=payload.username,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
