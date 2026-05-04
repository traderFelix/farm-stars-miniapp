from fastapi import APIRouter, Depends

from api.db.connection import get_db
from api.dependencies.internal import require_internal_token
from api.schemas.partner_cabinet import (
    PartnerAccrualHistoryResponse,
    PartnerAccrualsResponse,
    PartnerCabinetSummaryResponse,
    PartnerChannelDetailResponse,
    PartnerChannelsResponse,
    PartnerPromosResponse,
)
from api.services.partner_cabinet import (
    get_partner_cabinet_summary,
    get_partner_channel_accruals,
    get_partner_channel_detail,
    list_partner_channel_accrual_history,
    list_partner_channel_promos,
    list_partner_channels,
)

router = APIRouter(
    prefix="/bot/partners",
    tags=["internal-partner-cabinet"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("/{user_id}", response_model=PartnerCabinetSummaryResponse)
async def get_partner_cabinet_summary_route(user_id: int):
    db = await get_db()
    try:
        return await get_partner_cabinet_summary(db, int(user_id))
    finally:
        await db.close()


@router.get("/{user_id}/channels", response_model=PartnerChannelsResponse)
async def list_partner_channels_route(user_id: int):
    db = await get_db()
    try:
        return await list_partner_channels(db, int(user_id))
    finally:
        await db.close()


@router.get("/{user_id}/channels/{chat_id}", response_model=PartnerChannelDetailResponse)
async def get_partner_channel_detail_route(user_id: int, chat_id: str):
    db = await get_db()
    try:
        return await get_partner_channel_detail(db, int(user_id), str(chat_id))
    finally:
        await db.close()


@router.get("/{user_id}/channels/{chat_id}/promos", response_model=PartnerPromosResponse)
async def list_partner_channel_promos_route(user_id: int, chat_id: str):
    db = await get_db()
    try:
        return await list_partner_channel_promos(db, int(user_id), str(chat_id))
    finally:
        await db.close()


@router.get("/{user_id}/channels/{chat_id}/accruals", response_model=PartnerAccrualsResponse)
async def get_partner_channel_accruals_route(user_id: int, chat_id: str):
    db = await get_db()
    try:
        return await get_partner_channel_accruals(db, int(user_id), str(chat_id))
    finally:
        await db.close()


@router.get("/{user_id}/channels/{chat_id}/accrual-history", response_model=PartnerAccrualHistoryResponse)
async def list_partner_channel_accrual_history_route(user_id: int, chat_id: str, limit: int = 50):
    db = await get_db()
    try:
        return await list_partner_channel_accrual_history(
            db,
            int(user_id),
            str(chat_id),
            limit=int(limit),
        )
    finally:
        await db.close()
