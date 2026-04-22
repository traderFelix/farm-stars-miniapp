from typing import Optional

from pydantic import BaseModel


class SubscriptionTaskItem(BaseModel):
    id: int
    title: str
    channel_url: str
    total_reward: float
    participants_count: int
    max_subscribers: int


class SubscriptionAssignmentItem(BaseModel):
    id: int
    task_id: int
    title: str
    channel_url: str
    daily_claims_done: int
    daily_claim_days: int
    daily_reward_claimed: float
    daily_reward_total: float
    remaining_reward: float
    can_claim_today: bool
    last_daily_claim_day: Optional[str] = None
    can_abandon: bool
    abandon_available_at: Optional[str] = None
    abandon_cooldown_days_left: int


class SubscriptionStatusResponse(BaseModel):
    available: list[SubscriptionTaskItem]
    active: list[SubscriptionAssignmentItem]
    slots_used: int
    slot_limit: int
    abandon_available_at: Optional[str] = None
    abandon_cooldown_days_left: int


class SubscriptionActionResponse(BaseModel):
    ok: bool
    message: str
    reward_granted: float
    remaining_reward: float
    balance: float
    status: SubscriptionStatusResponse


class SubscriptionAbandonResponse(BaseModel):
    ok: bool
    message: str
    status: SubscriptionStatusResponse
