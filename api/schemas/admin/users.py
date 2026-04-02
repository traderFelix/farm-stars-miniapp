from typing import Literal, Optional

from pydantic import BaseModel


class ProfileResponse(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    balance: float
    role_level: int
    role: str
    activity_index: float
    is_suspicious: bool = False
    suspicious_reason: Optional[str] = None
    created_at: Optional[str] = None
    last_seen_at: Optional[str] = None


class LookupRequest(BaseModel):
    query: str


class RoleUpdateRequest(BaseModel):
    role_level: int


class RoleUpdateResponse(BaseModel):
    user_id: int
    role_level: int
    role: str


class BalanceAdjustRequest(BaseModel):
    amount: float
    mode: Literal["add", "sub"]


class BalanceAdjustResponse(BaseModel):
    user_id: int
    delta: float
    balance: float


class SuspiciousRequest(BaseModel):
    reason: Optional[str] = None
