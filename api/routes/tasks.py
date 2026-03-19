from fastapi import APIRouter, Depends

from api.dependencies.auth import get_current_user_id
from api.schemas.tasks import (
    TaskCheckRequest,
    TaskCheckResponse,
    TaskListResponse,
    TaskOpenRequest,
    TaskOpenResponse,
)
from api.services.tasks import (
    check_task_for_user,
    list_tasks_for_user,
    open_task_for_user,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=TaskListResponse)
async def get_tasks(
        user_id: int = Depends(get_current_user_id),
):
    return await list_tasks_for_user(user_id)


@router.post("/{task_id}/open", response_model=TaskOpenResponse)
async def open_task(
        task_id: int,
        payload: TaskOpenRequest,
        user_id: int = Depends(get_current_user_id),
):
    return await open_task_for_user(user_id, task_id)


@router.post("/{task_id}/check", response_model=TaskCheckResponse)
async def check_task(
        task_id: int,
        payload: TaskCheckRequest,
        user_id: int = Depends(get_current_user_id),
):
    return await check_task_for_user(user_id, task_id)