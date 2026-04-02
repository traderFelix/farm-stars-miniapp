from fastapi import APIRouter, Depends

from api.db.connection import get_db
from api.dependencies.internal import require_internal_token
from api.schemas.admin.campaigns import (
    CampaignCreateRequest,
    CampaignItem,
    CampaignStatusRequest,
    CampaignStatsResponse,
    CampaignSummaryResponse,
    CampaignsResponse,
    CampaignWinnerDeleteRequest,
    CampaignWinnerDeleteResponse,
    CampaignWinnersAddRequest,
    CampaignWinnersAddResponse,
    CampaignWinnersResponse,
)
from api.services.admin.campaigns import (
    add_campaign_winners,
    create_campaign_entry,
    delete_campaign_entry,
    delete_campaign_winner,
    get_campaign_detail,
    get_campaign_stats_detail,
    get_campaign_summary,
    get_campaign_winners_detail,
    list_all_campaigns,
    update_campaign_status,
)

router = APIRouter(
    prefix="/admin/campaigns",
    tags=["admin-campaigns"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("", response_model=CampaignsResponse)
async def list_campaigns_route():
    db = await get_db()
    try:
        return await list_all_campaigns(db)
    finally:
        await db.close()


@router.get("/summary", response_model=CampaignSummaryResponse)
async def get_campaign_summary_route(latest_limit: int = 5):
    db = await get_db()
    try:
        return await get_campaign_summary(db, latest_limit=latest_limit)
    finally:
        await db.close()


@router.get("/{campaign_key}", response_model=CampaignItem)
async def get_campaign_route(campaign_key: str):
    db = await get_db()
    try:
        return await get_campaign_detail(db, campaign_key)
    finally:
        await db.close()


@router.post("", response_model=CampaignItem)
async def create_campaign_route(payload: CampaignCreateRequest):
    db = await get_db()
    try:
        return await create_campaign_entry(
            db,
            campaign_key=payload.campaign_key,
            title=payload.title,
            amount=payload.amount,
        )
    finally:
        await db.close()


@router.post("/{campaign_key}/status", response_model=CampaignItem)
async def update_campaign_status_route(campaign_key: str, payload: CampaignStatusRequest):
    db = await get_db()
    try:
        return await update_campaign_status(db, campaign_key, status=payload.status)
    finally:
        await db.close()


@router.post("/{campaign_key}/delete")
async def delete_campaign_route(campaign_key: str):
    db = await get_db()
    try:
        return await delete_campaign_entry(db, campaign_key)
    finally:
        await db.close()


@router.post("/{campaign_key}/winners", response_model=CampaignWinnersAddResponse)
async def add_campaign_winners_route(campaign_key: str, payload: CampaignWinnersAddRequest):
    db = await get_db()
    try:
        return await add_campaign_winners(db, campaign_key, payload.usernames)
    finally:
        await db.close()


@router.get("/{campaign_key}/stats", response_model=CampaignStatsResponse)
async def get_campaign_stats_route(campaign_key: str):
    db = await get_db()
    try:
        return await get_campaign_stats_detail(db, campaign_key)
    finally:
        await db.close()


@router.get("/{campaign_key}/winners", response_model=CampaignWinnersResponse)
async def get_campaign_winners_route(campaign_key: str):
    db = await get_db()
    try:
        return await get_campaign_winners_detail(db, campaign_key)
    finally:
        await db.close()


@router.post("/{campaign_key}/winners/delete", response_model=CampaignWinnerDeleteResponse)
async def delete_campaign_winner_route(campaign_key: str, payload: CampaignWinnerDeleteRequest):
    db = await get_db()
    try:
        return await delete_campaign_winner(
            db,
            campaign_key,
            username=payload.username,
        )
    finally:
        await db.close()
