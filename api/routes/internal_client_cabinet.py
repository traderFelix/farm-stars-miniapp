from fastapi import APIRouter, Depends

from api.db.connection import get_db
from api.dependencies.internal import require_internal_token
from api.schemas.client_cabinet import (
    ClientCabinetSummaryResponse,
    ClientChannelDetailResponse,
    ClientChannelPostsResponse,
    ClientChannelsResponse,
    ClientOrdersResponse,
    ClientSubscriptionCampaignsResponse,
    ClientSubscriptionStatsResponse,
    ClientViewStatsResponse,
)
from api.services.client_cabinet import (
    get_client_cabinet_summary,
    get_client_channel_detail,
    list_client_channel_posts,
    list_client_channel_subscription_campaigns,
    get_client_channel_subscription_stats,
    get_client_channel_view_stats,
    list_client_channels,
    list_client_orders,
)

router = APIRouter(
    prefix="/bot/clients",
    tags=["internal-client-cabinet"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("/{user_id}", response_model=ClientCabinetSummaryResponse)
async def get_client_cabinet_summary_route(user_id: int):
    db = await get_db()
    try:
        return await get_client_cabinet_summary(db, int(user_id))
    finally:
        await db.close()


@router.get("/{user_id}/channels", response_model=ClientChannelsResponse)
async def list_client_channels_route(user_id: int):
    db = await get_db()
    try:
        return await list_client_channels(db, int(user_id))
    finally:
        await db.close()


@router.get("/{user_id}/channels/{channel_id}", response_model=ClientChannelDetailResponse)
async def get_client_channel_detail_route(user_id: int, channel_id: int):
    db = await get_db()
    try:
        return await get_client_channel_detail(db, int(user_id), int(channel_id))
    finally:
        await db.close()


@router.get("/{user_id}/channels/{channel_id}/view-stats", response_model=ClientViewStatsResponse)
async def get_client_channel_view_stats_route(user_id: int, channel_id: int):
    db = await get_db()
    try:
        return await get_client_channel_view_stats(db, int(user_id), int(channel_id))
    finally:
        await db.close()


@router.get("/{user_id}/channels/{channel_id}/subscription-stats", response_model=ClientSubscriptionStatsResponse)
async def get_client_channel_subscription_stats_route(user_id: int, channel_id: int):
    db = await get_db()
    try:
        return await get_client_channel_subscription_stats(db, int(user_id), int(channel_id))
    finally:
        await db.close()


@router.get("/{user_id}/channels/{channel_id}/subscription-campaigns", response_model=ClientSubscriptionCampaignsResponse)
async def list_client_channel_subscription_campaigns_route(user_id: int, channel_id: int):
    db = await get_db()
    try:
        return await list_client_channel_subscription_campaigns(db, int(user_id), int(channel_id))
    finally:
        await db.close()


@router.get("/{user_id}/channels/{channel_id}/posts", response_model=ClientChannelPostsResponse)
async def list_client_channel_posts_route(user_id: int, channel_id: int, limit: int = 5, page: int = 0):
    db = await get_db()
    try:
        return await list_client_channel_posts(db, int(user_id), int(channel_id), limit=int(limit), page=int(page))
    finally:
        await db.close()


@router.get("/{user_id}/orders", response_model=ClientOrdersResponse)
async def list_client_orders_route(user_id: int, limit: int = 20):
    db = await get_db()
    try:
        return await list_client_orders(db, int(user_id), limit=int(limit))
    finally:
        await db.close()
