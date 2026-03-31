from typing import Optional

from pydantic import BaseModel


class BotBootstrapUserRequest(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    start_referrer_id: Optional[int] = None


class BotUserProfileResponse(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    balance: float
    role: str
    role_level: int
    activity_index: float


class BotBootstrapUserResponse(BaseModel):
    ok: bool = True
    profile: BotUserProfileResponse
    referrer_bound: bool = False
