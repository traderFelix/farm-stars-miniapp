from typing import Optional

from pydantic import BaseModel


class PromoItem(BaseModel):
    promo_code: str
    title: Optional[str] = None
    partner_user_id: Optional[int] = None
    partner_username: Optional[str] = None
    partner_first_name: Optional[str] = None
    partner_channel_chat_id: Optional[str] = None
    partner_channel_title: Optional[str] = None
    reward_amount: float
    total_uses: int
    claims_count: int
    remaining_uses: int
    status: str
    created_at: Optional[str] = None


class PromosResponse(BaseModel):
    items: list[PromoItem]


class PromoCreateRequest(BaseModel):
    promo_code: str
    title: Optional[str] = None
    partner_user_id: Optional[int] = None
    partner_channel_chat_id: Optional[str] = None
    partner_channel_title: Optional[str] = None
    amount: float
    total_uses: int


class PromoStatusRequest(BaseModel):
    status: str


class PromoStatsResponse(BaseModel):
    promo_code: str
    claims_count: int
    total_uses: int
    remaining_uses: int
    total_paid: float
    claimed_usernames: list[str]


class PromoSummaryResponse(BaseModel):
    total_assigned_amount: float
    unclaimed_amount: float
    total_claimed_amount: float
    claims_count: int
    active_count: int
    ended_count: int
    draft_count: int
    latest_items: list[PromoItem]
