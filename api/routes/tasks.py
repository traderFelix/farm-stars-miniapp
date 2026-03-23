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

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
)


@router.get(
    "/next",
    response_model=TaskListItem,
    summary="Get next available task",
)
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


@router.post(
    "/{task_id}/open",
    response_model=TaskOpenResponse,
    summary="Open task",
)
async def open_task(
        task_id: int,
        payload: TaskOpenRequest,
        user_id: int = Depends(get_current_user_id),
):
    # payload пока сохраняем в контракте.
    # source/session пригодятся дальше, но уже сейчас web и api
    # работают по одному стабильному формату.
    _ = payload

    return await open_task_for_user(
        user_id=user_id,
        task_id=task_id,
    )


@router.post(
    "/{task_id}/check",
    response_model=TaskCheckResponse,
    summary="Check task completion",
)
async def check_task(
        task_id: int,
        payload: TaskCheckRequest,
        user_id: int = Depends(get_current_user_id),
):
    # payload пока сохраняем в контракте.
    # session_id можно будет подключить позже без ломки API.
    _ = payload

    return await check_task_for_user(
        user_id=user_id,
        task_id=task_id,
    )


# ---- internal bot endpoints ----
# Бот пока еще не полностью thin client, но уже должен ходить
# в тот же task API, а не жить на отдельной логике.


@router.get(
    "/bot/next/{user_id}",
    response_model=TaskListItem,
    summary="Bot internal: get next task for user",
)
async def bot_get_next_task(user_id: int):
    task = await get_next_task_for_user(user_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No available tasks",
        )
    return task


@router.post(
    "/bot/{task_id}/open/{user_id}",
    response_model=TaskOpenResponse,
    summary="Bot internal: open task for user",
)
async def bot_open_task(
        user_id: int,
        task_id: int,
):
    return await open_task_for_user(
        user_id=user_id,
        task_id=task_id,
    )


@router.post(
    "/bot/{task_id}/check/{user_id}",
    response_model=TaskCheckResponse,
    summary="Bot internal: check task for user",
)
async def bot_check_task(
        user_id: int,
        task_id: int,
):
    return await check_task_for_user(
        user_id=user_id,
        task_id=task_id,
    )