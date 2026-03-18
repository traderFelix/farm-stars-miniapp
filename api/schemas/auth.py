from typing import Optional

from pydantic import BaseModel


class TelegramAuthRequest(BaseModel):
    init_data: Optional[str] = None


class TelegramAuthResponse(BaseModel):
    ok: bool
    token: str
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None