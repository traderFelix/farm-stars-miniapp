from fastapi import APIRouter, Depends

from api.db.connection import get_db
from api.dependencies.internal import require_internal_token
from api.schemas.admin.task_channels import (
    TaskChannelClientBindRequest,
    TaskChannelCreateRequest,
    TaskChannelDetailResponse,
    TaskChannelPostsResponse,
    TaskChannelsResponse,
    TaskChannelUpdateRequest,
)
from api.services.admin.task_channels import (
    bind_channel_client,
    build_channel_detail,
    create_channel,
    get_channel_posts,
    list_channels,
    toggle_channel,
    update_channel,
)

router = APIRouter(
    prefix="/admin/task-channels",
    tags=["admin-task-channels"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("", response_model=TaskChannelsResponse)
async def list_task_channels_route():
    db = await get_db()
    try:
        return await list_channels(db)
    finally:
        await db.close()


@router.get("/{channel_id}", response_model=TaskChannelDetailResponse)
async def get_task_channel_route(channel_id: int):
    db = await get_db()
    try:
        return await build_channel_detail(db, channel_id)
    finally:
        await db.close()


@router.post("", response_model=TaskChannelDetailResponse)
async def create_task_channel_route(payload: TaskChannelCreateRequest):
    db = await get_db()
    try:
        return await create_channel(
            db,
            chat_id=payload.chat_id,
            title=payload.title,
            client_user_id=payload.client_user_id,
            total_bought_views=payload.total_bought_views,
            views_per_post=payload.views_per_post,
            view_seconds=payload.view_seconds,
        )
    finally:
        await db.close()


@router.post("/{channel_id}/toggle", response_model=TaskChannelDetailResponse)
async def toggle_task_channel_route(channel_id: int):
    db = await get_db()
    try:
        return await toggle_channel(db, channel_id)
    finally:
        await db.close()


@router.post("/{channel_id}/params", response_model=TaskChannelDetailResponse)
async def update_task_channel_params_route(
        channel_id: int,
        payload: TaskChannelUpdateRequest,
):
    db = await get_db()
    try:
        return await update_channel(
            db,
            channel_id=channel_id,
            total_bought_views=payload.total_bought_views,
            views_per_post=payload.views_per_post,
            view_seconds=payload.view_seconds,
        )
    finally:
        await db.close()


@router.post("/{channel_id}/client", response_model=TaskChannelDetailResponse)
async def bind_task_channel_client_route(
        channel_id: int,
        payload: TaskChannelClientBindRequest,
):
    db = await get_db()
    try:
        return await bind_channel_client(
            db,
            channel_id=channel_id,
            client_user_id=payload.client_user_id,
        )
    finally:
        await db.close()


@router.get("/{channel_id}/posts", response_model=TaskChannelPostsResponse)
async def get_task_channel_posts_route(channel_id: int, limit: int = 20):
    db = await get_db()
    try:
        return await get_channel_posts(db, channel_id, limit=limit)
    finally:
        await db.close()
