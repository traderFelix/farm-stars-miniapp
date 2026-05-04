from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class PartnerCabinetSummaryResponse(BaseModel):
    user_id: int
    channels_count: int
    referrals_count: int


class PartnerChannelItem(BaseModel):
    chat_id: str
    title: str
    is_active: bool
    has_promos: bool = False
    has_accruals: bool = False
    created_at: Optional[str] = None


class PartnerChannelsResponse(BaseModel):
    items: list[PartnerChannelItem]


class PartnerChannelDetailResponse(BaseModel):
    channel: PartnerChannelItem


class PartnerPromoItem(BaseModel):
    promo_code: str
    title: Optional[str] = None
    status: str
    claims_count: int
    total_uses: int
    new_referrals_count: int
    created_at: Optional[str] = None


class PartnerPromosResponse(BaseModel):
    channel: PartnerChannelItem
    items: list[PartnerPromoItem]


class PartnerAccrualsSummary(BaseModel):
    subscribers_delivered: int
    subscribers_promised: int
    views_delivered: int
    views_promised: int


class PartnerAccrualsResponse(BaseModel):
    channel: PartnerChannelItem
    summary: PartnerAccrualsSummary


class PartnerAccrualHistoryItem(BaseModel):
    id: str
    created_at: Optional[str] = None
    subscribers_delivered: int
    subscribers_promised: int
    views_delivered: int
    views_promised: int
    note: Optional[str] = None


class PartnerAccrualHistoryResponse(BaseModel):
    channel: PartnerChannelItem
    items: list[PartnerAccrualHistoryItem]
