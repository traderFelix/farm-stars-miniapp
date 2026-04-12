from typing import Optional

from pydantic import BaseModel

from api.schemas.users import TelegramUserPayload


class CheckinContextRequest(BaseModel):
    user: TelegramUserPayload


class CheckinCycleReward(BaseModel):
    day: int
    reward: float
    tier: str


class CheckinStatusResponse(BaseModel):
    can_claim: bool
    already_claimed_today: bool

    current_cycle_day: int
    claimed_days_count: int
    claimed_total_reward: float
    season_length: int
    cycle_rewards: list[CheckinCycleReward]
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
