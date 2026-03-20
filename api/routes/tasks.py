from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies.auth import get_current_user_id
from api.schemas.tasks import (
    TaskCheckRequest,
    TaskCheckResponse,
    TaskListItem,
    TaskOpenRequest,
    TaskOpenResponse,
)
from api.services.tasks import (
    check_task_for_user,
    get_next_task_for_user,
    open_task_for_user,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/next", response_model=TaskListItem)
async def get_next_task(
        user_id: int = Depends(get_current_user_id),
):
    task = await get_next_task_for_user(user_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No available tasks",
        )
    return task


@router.post("/{task_id}/open", response_model=TaskOpenResponse)
async def open_task(
        task_id: int,
        payload: TaskOpenRequest,
        user_id: int = Depends(get_current_user_id),
):
    return await open_task_for_user(
        user_id=user_id,
        task_id=task_id,
    )


@router.post("/{task_id}/check", response_model=TaskCheckResponse)
async def check_task(
        task_id: int,
        payload: TaskCheckRequest,
        user_id: int = Depends(get_current_user_id),
):
    return await check_task_for_user(user_id, task_id)