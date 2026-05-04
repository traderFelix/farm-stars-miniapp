from fastapi import APIRouter, Depends

from api.db.connection import get_db
from api.dependencies.internal import require_internal_token
from api.schemas.admin.partner_traffic import (
    AdminPartnerTrafficEventResponse,
    AdminPartnerViewsAccrualCreateRequest,
)
from api.services.admin.partner_traffic import create_partner_views_accrual

router = APIRouter(
    prefix="/admin/partner-traffic",
    tags=["admin-partner-traffic"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("/views", response_model=AdminPartnerTrafficEventResponse)
async def create_partner_views_accrual_route(payload: AdminPartnerViewsAccrualCreateRequest):
    db = await get_db()
    try:
        return await create_partner_views_accrual(
            db,
            partner_user_id=payload.partner_user_id,
            channel_chat_id=payload.channel_chat_id,
            channel_title=payload.channel_title,
            views_promised=payload.views_promised,
            views_delivered=payload.views_delivered,
        )
    finally:
        await db.close()
