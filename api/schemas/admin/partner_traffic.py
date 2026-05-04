from typing import Optional

from pydantic import BaseModel


class AdminPartnerViewsAccrualCreateRequest(BaseModel):
    partner_user_id: int
    channel_chat_id: str
    channel_title: Optional[str] = None
    views_promised: int
    views_delivered: int = 0


class AdminPartnerTrafficEventResponse(BaseModel):
    id: int
    partner_user_id: int
    partner_username: Optional[str] = None
    partner_first_name: Optional[str] = None
    channel_chat_id: str
    channel_title: Optional[str] = None
    views_promised: int
    views_delivered: int
    note: Optional[str] = None
    created_at: Optional[str] = None
