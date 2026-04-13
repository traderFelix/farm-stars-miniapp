from typing import Optional

from pydantic import BaseModel


class PromoRedeemRequest(BaseModel):
    code: str


class PromoRedeemResponse(BaseModel):
    ok: bool
    message: str
    new_balance: float = 0
    reward_amount: float = 0
    promo_code: Optional[str] = None
    title: Optional[str] = None
    code: Optional[str] = None
