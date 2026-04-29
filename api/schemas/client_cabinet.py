from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class ClientCabinetSummaryResponse(BaseModel):
    user_id: int
    balance: float
    channels_count: int
    orders_count: int


class ClientChannelItem(BaseModel):
    id: int
    chat_id: str
    title: str
    is_active: bool
    has_views: bool = False
    has_subscriptions: bool = False
    total_bought_views: int
    views_per_post: int
    view_seconds: int
    allocated_views: int
    remaining_views: int
    created_at: Optional[str] = None


class ClientChannelsResponse(BaseModel):
    items: list[ClientChannelItem]


class ClientChannelDetailResponse(BaseModel):
    channel: ClientChannelItem


class ClientViewStats(BaseModel):
    total_posts: int
    total_required: int
    total_current: int
    active_posts: int


class ClientViewStatsResponse(BaseModel):
    channel: ClientChannelItem
    stats: ClientViewStats


class ClientSubscriptionStats(BaseModel):
    tasks_count: int
    active_tasks_count: int
    total_subscribers_bought: int
    total_participants: int
    total_assignments: int
    active_assignments: int
    completed_assignments: int
    abandoned_assignments: int


class ClientSubscriptionStatsResponse(BaseModel):
    channel: ClientChannelItem
    stats: ClientSubscriptionStats


class ClientSubscriptionCampaignItem(BaseModel):
    id: int
    created_at: Optional[str] = None
    is_active: bool
    participants_count: int
    max_subscribers: int


class ClientSubscriptionCampaignsResponse(BaseModel):
    channel: ClientChannelItem
    items: list[ClientSubscriptionCampaignItem]


class ClientChannelPostItem(BaseModel):
    id: int
    channel_post_id: int
    required_views: int
    current_views: int
    is_active: bool
    source: str = "auto"
    added_by_admin_id: Optional[int] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


class ClientChannelPostsResponse(BaseModel):
    channel: ClientChannelItem
    items: list[ClientChannelPostItem]
    page: int = 0
    has_next: bool = False


class ClientOrderItem(BaseModel):
    kind: Literal["views", "subscriptions"]
    chat_id: str
    title: str
    created_at: Optional[str] = None
    price_stars: Optional[float] = None
    price_note: Optional[str] = None
    total_bought_views: Optional[int] = None
    views_per_post: Optional[int] = None
    view_seconds: Optional[int] = None
    max_subscribers: Optional[int] = None
    daily_claim_days: Optional[int] = None


class ClientOrdersResponse(BaseModel):
    items: list[ClientOrderItem]
