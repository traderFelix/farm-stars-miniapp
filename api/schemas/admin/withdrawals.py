from typing import Optional

from pydantic import BaseModel


class WithdrawalItem(BaseModel):
    id: int
    user_id: int
    username: Optional[str] = None
    amount: float
    method: str
    wallet: Optional[str] = None
    status: str
    created_at: str
    processed_at: Optional[str] = None
    fee_xtr: int = 0
    fee_paid: bool = False
    fee_refunded: bool = False
    fee_telegram_charge_id: Optional[str] = None
    fee_invoice_payload: Optional[str] = None


class WithdrawalsResponse(BaseModel):
    status: str
    limit: int
    items: list[WithdrawalItem]


class ActionRequest(BaseModel):
    admin_id: int


class ReferralBonusResult(BaseModel):
    added: bool = False
    referrer_id: Optional[int] = None
    amount: float = 0.0


class FeeRefundContext(BaseModel):
    status: str
    user_id: int
    fee_xtr: int = 0
    charge_id: Optional[str] = None


class PaidActionResponse(BaseModel):
    withdrawal: WithdrawalItem
    referral_bonus: ReferralBonusResult


class RejectActionResponse(BaseModel):
    withdrawal: WithdrawalItem
    fee_refund: FeeRefundContext


class FeeRefundRecordRequest(BaseModel):
    meta: Optional[str] = None


class ChargeIdRefundRecordRequest(BaseModel):
    charge_id: str
    meta: Optional[str] = None


class FeeRefundRecordResponse(BaseModel):
    status: str
    withdrawal_id: Optional[int] = None
    user_id: Optional[int] = None
    fee_xtr: int = 0
    charge_id: Optional[str] = None


class RecentFeePaymentItem(BaseModel):
    withdrawal_id: int
    user_id: int
    username: Optional[str] = None
    fee_xtr: int = 0
    fee_paid: bool = False
    fee_refunded: bool = False
    fee_telegram_charge_id: Optional[str] = None
    created_at: str


class RecentFeePaymentsResponse(BaseModel):
    limit: int
    items: list[RecentFeePaymentItem]
