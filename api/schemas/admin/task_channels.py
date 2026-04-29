from typing import Optional

from pydantic import BaseModel


class TaskChannelItem(BaseModel):
    id: int
    chat_id: str
    title: str = ""
    client_user_id: Optional[int] = None
    client_username: Optional[str] = None
    client_first_name: Optional[str] = None
    is_active: bool
    total_bought_views: int
    views_per_post: int
    view_seconds: int
    allocated_views: int
    remaining_views: int
    created_at: Optional[str] = None


class TaskChannelStats(BaseModel):
    total_posts: int
    total_required: int
    total_current: int
    active_posts: int


class TaskChannelDetailResponse(BaseModel):
    channel: TaskChannelItem
    stats: TaskChannelStats


class TaskChannelsResponse(BaseModel):
    items: list[TaskChannelItem]


class TaskChannelPostItem(BaseModel):
    id: int
    channel_post_id: int
    required_views: int
    current_views: int
    is_active: bool
    source: str = "auto"
    added_by_admin_id: Optional[int] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


class TaskChannelPostsResponse(BaseModel):
    channel: TaskChannelItem
    items: list[TaskChannelPostItem]
    page: int = 0
    has_next: bool = False


class TaskChannelCreateRequest(BaseModel):
    chat_id: str
    title: Optional[str] = None
    client_user_id: Optional[int] = None
    total_bought_views: int
    views_per_post: int
    view_seconds: int


class TaskChannelUpdateRequest(BaseModel):
    total_bought_views: int
    views_per_post: int
    view_seconds: int


class TaskChannelClientBindRequest(BaseModel):
    client_user_id: int


class TaskChannelTitleUpdateRequest(BaseModel):
    title: str


class TaskChannelManualPostRequest(BaseModel):
    channel_post_id: int
    added_by_admin_id: int


class TaskChannelManualPostResponse(TaskChannelDetailResponse):
    post: TaskChannelPostItem
