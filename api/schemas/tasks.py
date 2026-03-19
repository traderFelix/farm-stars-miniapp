from typing import Literal, Optional

from pydantic import BaseModel, Field


TaskType = Literal["view_post"]
TaskStatus = Literal["available", "in_progress", "completed", "blocked"]


class TaskListItem(BaseModel):
    id: int
    type: TaskType = "view_post"
    title: str
    description: Optional[str] = None
    reward: float
    status: TaskStatus = "available"

    chat_id: Optional[str] = None
    channel_post_id: Optional[int] = None
    post_url: Optional[str] = None

    already_completed: bool = False
    can_claim: bool = False
    hold_seconds: int = 0


class TaskListResponse(BaseModel):
    items: list[TaskListItem]


class TaskOpenRequest(BaseModel):
    source: Optional[str] = Field(default="miniapp")


class TaskOpenResponse(BaseModel):
    ok: bool
    task_id: int
    opened_at: int
    hold_seconds: int = 0

    chat_id: Optional[str] = None
    channel_post_id: Optional[int] = None
    post_url: Optional[str] = None

    session_id: Optional[str] = None


class TaskCheckRequest(BaseModel):
    session_id: Optional[str] = None


class TaskCheckResponse(BaseModel):
    ok: bool
    task_id: int
    status: Literal["completed", "already_completed", "too_early", "rejected"]
    message: str
    reward_granted: float = 0
    new_balance: float = 0
    task_completed: bool = False