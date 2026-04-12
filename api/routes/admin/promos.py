from fastapi import APIRouter, Depends

from api.db.connection import get_db
from api.dependencies.internal import require_internal_token
from api.schemas.admin.promos import (
    PromoCreateRequest,
    PromoItem,
    PromoStatsResponse,
    PromoStatusRequest,
    PromoSummaryResponse,
    PromosResponse,
)
from api.services.admin.promos import (
    create_promo_entry,
    delete_promo_entry,
    get_promo_detail,
    get_promo_stats_detail,
    get_promo_summary,
    list_all_promos,
    update_promo_status,
)

router = APIRouter(
    prefix="/admin/promos",
    tags=["admin-promos"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("", response_model=PromosResponse)
async def list_promos_route():
    db = await get_db()
    try:
        return await list_all_promos(db)
    finally:
        await db.close()


@router.get("/summary", response_model=PromoSummaryResponse)
async def get_promo_summary_route(latest_limit: int = 5):
    db = await get_db()
    try:
        return await get_promo_summary(db, latest_limit=latest_limit)
    finally:
        await db.close()


@router.get("/{promo_code}", response_model=PromoItem)
async def get_promo_route(promo_code: str):
    db = await get_db()
    try:
        return await get_promo_detail(db, promo_code)
    finally:
        await db.close()


@router.post("", response_model=PromoItem)
async def create_promo_route(payload: PromoCreateRequest):
    db = await get_db()
    try:
        return await create_promo_entry(
            db,
            promo_code=payload.promo_code,
            title=payload.title,
            amount=payload.amount,
            total_uses=payload.total_uses,
        )
    finally:
        await db.close()


@router.post("/{promo_code}/status", response_model=PromoItem)
async def update_promo_status_route(promo_code: str, payload: PromoStatusRequest):
    db = await get_db()
    try:
        return await update_promo_status(db, promo_code, status=payload.status)
    finally:
        await db.close()


@router.post("/{promo_code}/delete")
async def delete_promo_route(promo_code: str):
    db = await get_db()
    try:
        return await delete_promo_entry(db, promo_code)
    finally:
        await db.close()


@router.get("/{promo_code}/stats", response_model=PromoStatsResponse)
async def get_promo_stats_route(promo_code: str):
    db = await get_db()
    try:
        return await get_promo_stats_detail(db, promo_code)
    finally:
        await db.close()
