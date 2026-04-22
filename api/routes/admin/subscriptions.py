from fastapi import APIRouter, Depends

from api.db.connection import get_db
from api.dependencies.internal import require_internal_token
from api.schemas.admin.subscriptions import (
    AdminSubscriptionTaskCreateRequest,
    AdminSubscriptionTaskDetailResponse,
    AdminSubscriptionTasksResponse,
    AdminSubscriptionTaskToggleRequest,
)
from api.services.admin.subscriptions import (
    build_admin_subscription_task_detail,
    create_admin_subscription_task,
    list_admin_subscription_tasks,
    set_admin_subscription_task_status,
)

router = APIRouter(
    prefix="/admin/subscription-tasks",
    tags=["admin-subscription-tasks"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("", response_model=AdminSubscriptionTasksResponse)
async def list_subscription_tasks_route():
    db = await get_db()
    try:
        return await list_admin_subscription_tasks(db)
    finally:
        await db.close()


@router.post("", response_model=AdminSubscriptionTaskDetailResponse)
async def create_subscription_task_route(payload: AdminSubscriptionTaskCreateRequest):
    db = await get_db()
    try:
        return await create_admin_subscription_task(
            db,
            chat_id=payload.chat_id,
            title=payload.title,
            channel_url=payload.channel_url,
            instant_reward=payload.instant_reward,
            daily_reward_total=payload.daily_reward_total,
            daily_claim_days=payload.daily_claim_days,
            max_subscribers=payload.max_subscribers,
        )
    finally:
        await db.close()


@router.get("/{task_id}", response_model=AdminSubscriptionTaskDetailResponse)
async def get_subscription_task_route(task_id: int):
    db = await get_db()
    try:
        return await build_admin_subscription_task_detail(db, int(task_id))
    finally:
        await db.close()


@router.post("/{task_id}/status", response_model=AdminSubscriptionTaskDetailResponse)
async def set_subscription_task_status_route(
        task_id: int,
        payload: AdminSubscriptionTaskToggleRequest,
):
    db = await get_db()
    try:
        return await set_admin_subscription_task_status(
            db,
            task_id=int(task_id),
            is_active=payload.is_active,
        )
    finally:
        await db.close()
