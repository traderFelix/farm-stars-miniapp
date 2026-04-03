from typing import Optional

from pydantic import BaseModel


class TelegramUserPayload(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserBootstrapRequest(BaseModel):
    user: TelegramUserPayload
    start_referrer_id: Optional[int] = None


class UserMainMenuRequest(BaseModel):
    user: TelegramUserPayload


class UserMainMenuResponse(BaseModel):
    user_id: int
    balance: float
    role: str
    role_level: int
    activity_index: float


class UserBootstrapResponse(UserMainMenuResponse):
    referrer_bound: bool = False


class UserProfileResponse(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    balance: float
    role: str
    activity_index: float
