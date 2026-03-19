from typing import Any, Optional

from pydantic import BaseModel


class TelegramAuthRequest(BaseModel):
    init_data: Optional[str] = None


class TelegramAuthResponse(BaseModel):
    ok: bool
    token: str
    session: dict[str, Any]