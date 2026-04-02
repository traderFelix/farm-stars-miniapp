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
