from typing import Optional, List
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


class MiniAppTaskActionRequest(BaseModel):
    task_id: int


class MiniAppTaskOpenResponse(BaseModel):
    ok: bool
    opened_at: int


class MiniAppTaskCheckResponse(BaseModel):
    ok: bool
    reward: float
    new_balance: float
    message: str


class MiniAppHistoryItem(BaseModel):
    task_id: int
    title: str
    reward: float
    completed_at: int


class MiniAppHistoryResponse(BaseModel):
    ok: bool
    items: List[MiniAppHistoryItem]