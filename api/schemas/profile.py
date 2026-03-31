from typing import Optional

from pydantic import BaseModel


class ProfileResponse(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    balance: float
    role: str
    role_level: int
    activity_index: float


class BotBootstrapRequest(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    start_referrer_id: Optional[int] = None


class BotBootstrapResponse(BaseModel):
    ok: bool = True
    profile: ProfileResponse
    referrer_bound: bool = False
