from typing import Optional

from pydantic import BaseModel


class TaskChannelItem(BaseModel):
    id: int
    chat_id: str
    title: str = ""
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
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


class TaskChannelPostsResponse(BaseModel):
    channel: TaskChannelItem
    items: list[TaskChannelPostItem]


class TaskChannelCreateRequest(BaseModel):
    chat_id: str
    title: Optional[str] = None
    total_bought_views: int
    views_per_post: int
    view_seconds: int


class TaskChannelUpdateRequest(BaseModel):
    total_bought_views: int
    views_per_post: int
    view_seconds: int
