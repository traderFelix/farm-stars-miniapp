from typing import Optional

from pydantic import BaseModel


class ProfileResponse(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    balance: float
    role: str