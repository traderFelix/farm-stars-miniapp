from typing import Literal, Optional

from pydantic import BaseModel


class AdminSubscriptionTaskItem(BaseModel):
    id: int
    chat_id: str
    title: str
    client_user_id: Optional[int] = None
    owner_type: Literal["client", "partner"] = "client"
    client_username: Optional[str] = None
    client_first_name: Optional[str] = None
    channel_url: str
    instant_reward: float
    daily_reward_total: float
    daily_claim_days: int
    total_reward: float
    max_subscribers: int
    participants_count: int
    is_active: bool
    is_archived: bool = False
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
    client_user_id: Optional[int] = None
    owner_type: Literal["client", "partner"] = "client"
    channel_url: str
    instant_reward: float
    daily_reward_total: float
    daily_claim_days: int
    max_subscribers: int


class AdminSubscriptionTaskDetailResponse(BaseModel):
    task: AdminSubscriptionTaskItem


class AdminSubscriptionTaskToggleRequest(BaseModel):
    is_active: bool


class AdminSubscriptionTaskClientBindRequest(BaseModel):
    client_user_id: int
    owner_type: Literal["client", "partner"] = "client"
