from typing import Literal, Optional

from pydantic import BaseModel

WithdrawalMethod = Literal["ton", "stars"]
WithdrawalStatus = Literal["pending", "approved", "rejected", "paid", "cancelled"]


class WithdrawalEligibilityResponse(BaseModel):
    can_withdraw: bool
    min_withdraw: float
    min_task_percent: float
    has_pending_withdrawal: bool
    account_age_hours: float
    required_account_age_hours: float
    task_earnings_percent: float
    available_balance: float
    message: str


class WithdrawalCreateRequest(BaseModel):
    method: WithdrawalMethod
    amount: float
    wallet: Optional[str] = None

    paid_fee: int = 0
    fee_payment_charge_id: Optional[str] = None
    fee_invoice_payload: Optional[str] = None


class WithdrawalPreviewRequest(BaseModel):
    method: WithdrawalMethod
    amount: float
    wallet: Optional[str] = None


class WithdrawalPreviewResponse(BaseModel):
    ok: bool
    amount: float
    method: WithdrawalMethod
    wallet: Optional[str] = None
    available_balance: float
    expected_fee: int
    message: str


class WithdrawalCreateResponse(BaseModel):
    ok: bool
    withdrawal_id: int
    status: WithdrawalStatus
    message: str
    balance: float = 0
    fee_xtr: int = 0


class WithdrawalItem(BaseModel):
    id: int
    amount: float
    method: WithdrawalMethod
    status: WithdrawalStatus
    wallet: Optional[str] = None
    created_at: str
    processed_at: Optional[str] = None
    fee_xtr: int = 0
    fee_paid: bool = False
    fee_refunded: bool = False


class WithdrawalListResponse(BaseModel):
    items: list[WithdrawalItem]
