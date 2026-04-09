from typing import Optional

from pydantic import BaseModel


class CampaignItem(BaseModel):
    campaign_key: str
    title: str
    reward_amount: float
    post_url: Optional[str] = None


class CampaignListResponse(BaseModel):
    items: list[CampaignItem]


class CampaignClaimContextRequest(BaseModel):
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class CampaignClaimResponse(BaseModel):
    ok: bool
    message: str
    new_balance: float = 0
    code: Optional[str] = None
