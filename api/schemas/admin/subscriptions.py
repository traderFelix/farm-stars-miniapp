from typing import Optional

from pydantic import BaseModel


class AdminSubscriptionTaskItem(BaseModel):
    id: int
    chat_id: str
    title: str
    channel_url: str
    instant_reward: float
    daily_reward_total: float
    daily_claim_days: int
    total_reward: float
    max_subscribers: int
    participants_count: int
    is_active: bool
    assignment_count: int = 0
    active_count: int = 0
    completed_count: int = 0
    abandoned_count: int = 0
    created_at: Optional[str] = None


class AdminSubscriptionTasksResponse(BaseModel):
    items: list[AdminSubscriptionTaskItem]


class AdminSubscriptionTaskCreateRequest(BaseModel):
    chat_id: str
    title: Optional[str] = None
    channel_url: str
    instant_reward: float
    daily_reward_total: float
    daily_claim_days: int
    max_subscribers: int


class AdminSubscriptionTaskDetailResponse(BaseModel):
    task: AdminSubscriptionTaskItem


class AdminSubscriptionTaskToggleRequest(BaseModel):
    is_active: bool
