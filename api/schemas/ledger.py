from typing import Optional

from pydantic import BaseModel


class LedgerItem(BaseModel):
    created_at: str
    delta: float
    reason: str
    campaign_key: Optional[str] = None
    meta: Optional[str] = None


class LedgerListResponse(BaseModel):
    items: list[LedgerItem]


class LedgerTotalResponse(BaseModel):
    total: float