from typing import Literal, Optional

from pydantic import BaseModel


class ProfileResponse(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    game_nickname: Optional[str] = None
    balance: float
    risk_score: float = 0
    role_level: int
    role: str
    withdrawal_ability: float
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


class UserStatsResponse(BaseModel):
    text: str


class UserBattleStatsResponse(BaseModel):
    text: str


class UserTheftStatsResponse(BaseModel):
    text: str


class UserLedgerEntry(BaseModel):
    created_at: str
    delta: float
    reason: str
    campaign_key: Optional[str] = None


class UserLedgerResponse(BaseModel):
    user_id: int
    page: int
    page_size: int
    has_next: bool
    items: list[UserLedgerEntry]


class UserRiskEventEntry(BaseModel):
    id: int
    created_at: str
    delta: float
    score_after: float
    reason: Optional[str] = None
    source: Optional[str] = None
    meta: Optional[str] = None


class UserRiskFlagEntry(BaseModel):
    risk_key: str
    score: float
    reason: Optional[str] = None
    source: Optional[str] = None
    meta: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class UserRiskCaseProgressEntry(BaseModel):
    risk_key: str
    source: Optional[str] = None
    reason: Optional[str] = None
    current_score: float
    max_score: float
    meta: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class UserRiskEventsResponse(BaseModel):
    user_id: int
    total_score: float
    score_cap: float
    page: int
    page_size: int
    has_next: bool
    flags: list[UserRiskFlagEntry]
    risk_cases: list[UserRiskCaseProgressEntry]
    items: list[UserRiskEventEntry]
