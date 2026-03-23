from pydantic import BaseModel
from typing import Optional


class CheckinStatusResponse(BaseModel):
    can_claim: bool
    already_claimed_today: bool

    current_cycle_day: int
    reward_today: float

    next_cycle_day: int
    next_reward: float

    last_checkin_at: Optional[str] = None
    server_time: str


class CheckinClaimResponse(BaseModel):
    ok: bool
    claimed_amount: float
    current_cycle_day: int
    balance: float
    claimed_at: str
    message: str