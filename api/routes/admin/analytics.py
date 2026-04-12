from fastapi import APIRouter, Depends

from api.db.connection import get_db
from api.dependencies.internal import require_internal_token
from api.schemas.admin.analytics import (
    AdminLedgerPageResponse,
    AuditResponse,
    GrowthResponse,
    TopBalancesResponse,
)
from api.services.admin.analytics import (
    get_admin_ledger_page,
    get_audit,
    get_growth,
    get_top_balances,
)

router = APIRouter(
    prefix="/admin/analytics",
    tags=["admin-analytics"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("/top-balances", response_model=TopBalancesResponse)
async def get_top_balances_route(limit: int = 10):
    db = await get_db()
    try:
        return await get_top_balances(db, limit=limit)
    finally:
        await db.close()


@router.get("/growth", response_model=GrowthResponse)
async def get_growth_route(days: int = 30):
    db = await get_db()
    try:
        return await get_growth(db, days=days)
    finally:
        await db.close()


@router.get("/ledger", response_model=AdminLedgerPageResponse)
async def get_admin_ledger_page_route(page: int = 0, page_size: int = 20):
    db = await get_db()
    try:
        return await get_admin_ledger_page(db, page=page, page_size=page_size)
    finally:
        await db.close()


@router.get("/audit", response_model=AuditResponse)
async def get_audit_route(limit: int = 10):
    db = await get_db()
    try:
        return await get_audit(db, limit=limit)
    finally:
        await db.close()
