from typing import Optional

from pydantic import BaseModel


class TopBalanceItem(BaseModel):
    username: Optional[str] = None
    balance: float


class TopBalancesResponse(BaseModel):
    items: list[TopBalanceItem]


class GrowthPoint(BaseModel):
    date: str
    count: int


class GrowthResponse(BaseModel):
    days: int
    total_users: int
    new_1d: int
    new_7d: int
    new_30d: int
    active_1d: int
    active_7d: int
    active_30d: int
    points: list[GrowthPoint]


class AdminLedgerEntry(BaseModel):
    created_at: str
    username: Optional[str] = None
    delta: float
    reason: str
    campaign_key: Optional[str] = None


class AdminLedgerPageResponse(BaseModel):
    page: int
    page_size: int
    has_next: bool
    items: list[AdminLedgerEntry]


class AuditMismatchItem(BaseModel):
    user_id: int
    username: Optional[str] = None
    users_balance: float
    ledger_sum: float
    diff: float


class AuditResponse(BaseModel):
    total_balances: float
    campaign_claims_count: int
    campaign_claimed_total: float
    promo_claims_count: int
    promo_claimed_total: float
    referral_bonus: float
    view_post_bonus: float
    daily_bonus: float
    subscription_bonus: float
    battle_bonus: float
    admin_adjust_net: float
    total_withdrawn: float
    pending_withdrawn: float
    mismatch_count: int
    mismatches: list[AuditMismatchItem]
