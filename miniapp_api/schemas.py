from typing import Optional
from pydantic import BaseModel


class MiniAppAuthRequest(BaseModel):
    init_data: str


class MiniAppUser(BaseModel):
    id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class MiniAppAuthResponse(BaseModel):
    ok: bool
    session_token: str
    user: MiniAppUser


class MiniAppMeUser(BaseModel):
    id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    balance: float
    role: str
    activity_index: float


class MiniAppMeResponse(BaseModel):
    ok: bool
    user: MiniAppMeUser


class MiniAppTask(BaseModel):
    id: int
    type: str
    title: str
    reward: float
    hold_seconds: int
    telegram_url: str
    channel_name: Optional[str] = None
    message_id: Optional[int] = None


class MiniAppNextTaskResponse(BaseModel):
    ok: bool
    task: Optional[MiniAppTask] = None
