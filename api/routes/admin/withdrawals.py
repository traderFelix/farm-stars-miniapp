from fastapi import APIRouter, Depends

from api.db.connection import get_db
from api.dependencies.internal import require_internal_token
from api.schemas.admin.withdrawals import (
    ActionRequest,
    ChargeIdRefundRecordRequest,
    FeeRefundRecordRequest,
    FeeRefundRecordResponse,
    PaidActionResponse,
    RecentFeePaymentsResponse,
    RejectActionResponse,
    WithdrawalItem,
    WithdrawalsResponse,
)
from api.services.admin.withdrawals import (
    get_request,
    list_recent_fee_payment_requests,
    list_requests,
    mark_paid,
    record_fee_refund,
    record_fee_refund_by_charge_id,
    reject,
)

router = APIRouter(
    prefix="/admin/withdrawals",
    tags=["admin-withdrawals"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("", response_model=WithdrawalsResponse)
async def list_withdrawal_requests(status: str = "pending", limit: int = 20):
    db = await get_db()
    try:
        return await list_requests(db, status=status, limit=limit)
    finally:
        await db.close()


@router.get("/fee-payments/recent", response_model=RecentFeePaymentsResponse)
async def list_recent_fee_payments_route(limit: int = 10):
    db = await get_db()
    try:
        return await list_recent_fee_payment_requests(db, limit=limit)
    finally:
        await db.close()


@router.get("/{withdrawal_id}", response_model=WithdrawalItem)
async def get_withdrawal_request(withdrawal_id: int):
    db = await get_db()
    try:
        return await get_request(db, withdrawal_id)
    finally:
        await db.close()


@router.post("/{withdrawal_id}/mark-paid", response_model=PaidActionResponse)
async def mark_withdrawal_paid(withdrawal_id: int, payload: ActionRequest):
    db = await get_db()
    try:
        return await mark_paid(db, withdrawal_id, admin_id=payload.admin_id)
    finally:
        await db.close()


@router.post("/{withdrawal_id}/reject", response_model=RejectActionResponse)
async def reject_withdrawal(withdrawal_id: int, payload: ActionRequest):
    db = await get_db()
    try:
        return await reject(db, withdrawal_id, admin_id=payload.admin_id)
    finally:
        await db.close()


@router.post("/{withdrawal_id}/fee-refund", response_model=FeeRefundRecordResponse)
async def record_withdrawal_fee_refund(
        withdrawal_id: int,
        payload: FeeRefundRecordRequest,
):
    db = await get_db()
    try:
        return await record_fee_refund(db, withdrawal_id, meta=payload.meta)
    finally:
        await db.close()


@router.post("/fee-refunds/by-charge-id", response_model=FeeRefundRecordResponse)
async def record_fee_refund_by_charge(payload: ChargeIdRefundRecordRequest):
    db = await get_db()
    try:
        return await record_fee_refund_by_charge_id(
            db,
            payload.charge_id,
            meta=payload.meta,
        )
    finally:
        await db.close()
