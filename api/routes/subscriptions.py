from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api.dependencies.auth import get_current_user_id
from api.schemas.subscriptions import SubscriptionActionResponse, SubscriptionStatusResponse
from api.security.request_fingerprint import build_request_fingerprint
from api.services.subscriptions import (
    abandon_subscription_for_user,
    claim_subscription_daily_for_user,
    get_subscription_status_for_user,
    join_subscription_task_for_user,
)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.get("/me", response_model=SubscriptionStatusResponse)
async def get_my_subscription_status(
        user_id: int = Depends(get_current_user_id),
):
    return await get_subscription_status_for_user(int(user_id))


@router.post("/{task_id}/join", response_model=SubscriptionActionResponse)
async def join_subscription_task(
        task_id: int,
        request: Request,
        user_id: int = Depends(get_current_user_id),
):
    return await join_subscription_task_for_user(
        user_id=int(user_id),
        task_id=int(task_id),
        fingerprint=build_request_fingerprint(request),
    )


@router.post("/assignments/{assignment_id}/claim", response_model=SubscriptionActionResponse)
async def claim_subscription_daily(
        assignment_id: int,
        request: Request,
        user_id: int = Depends(get_current_user_id),
):
    return await claim_subscription_daily_for_user(
        user_id=int(user_id),
        assignment_id=int(assignment_id),
        fingerprint=build_request_fingerprint(request),
    )


@router.post("/assignments/{assignment_id}/abandon", response_model=SubscriptionActionResponse)
async def abandon_subscription_assignment(
        assignment_id: int,
        request: Request,
        user_id: int = Depends(get_current_user_id),
):
    return await abandon_subscription_for_user(
        user_id=int(user_id),
        assignment_id=int(assignment_id),
        fingerprint=build_request_fingerprint(request),
    )
