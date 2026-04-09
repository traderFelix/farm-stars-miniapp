from typing import Optional

from pydantic import BaseModel


class CampaignItem(BaseModel):
    campaign_key: str
    title: str
    reward_amount: float
    status: str
    post_url: Optional[str] = None
    created_at: Optional[str] = None


class CampaignsResponse(BaseModel):
    items: list[CampaignItem]


class CampaignCreateRequest(BaseModel):
    campaign_key: str
    title: str
    amount: float
    post_url: Optional[str] = None


class CampaignStatusRequest(BaseModel):
    status: str


class CampaignWinnersAddRequest(BaseModel):
    usernames: list[str]


class CampaignWinnersAddResponse(BaseModel):
    campaign_key: str
    added_count: int


class CampaignWinnerDeleteRequest(BaseModel):
    username: str


class CampaignWinnerDeleteResponse(BaseModel):
    ok: bool
    message: str


class CampaignStatsResponse(BaseModel):
    campaign_key: str
    claims_count: int
    winners_count: int
    total_paid: float
    claimed_usernames: list[str]


class CampaignWinnersResponse(BaseModel):
    campaign_key: str
    winners: list[str]
    claimed_usernames: list[str]


class CampaignSummaryResponse(BaseModel):
    total_assigned_amount: float
    unclaimed_amount: float
    total_claimed_amount: float
    claims_count: int
    active_count: int
    ended_count: int
    draft_count: int
    latest_items: list[CampaignItem]
