from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api.dependencies.auth import get_current_user_id
from api.dependencies.internal import require_internal_token
from api.schemas.thefts import TheftActionResponse, TheftStatusResponse
from api.security.request_fingerprint import build_request_fingerprint
from api.services.thefts import (
    get_theft_status_for_user,
    start_theft_for_user,
    start_theft_protection_for_user,
)

router = APIRouter(prefix="/thefts", tags=["thefts"])


@router.get("/me", response_model=TheftStatusResponse)
async def get_my_theft_status(
        user_id: int = Depends(get_current_user_id),
):
    return await get_theft_status_for_user(user_id)


@router.post("/start", response_model=TheftActionResponse)
async def start_theft(
        request: Request,
        user_id: int = Depends(get_current_user_id),
):
    return await start_theft_for_user(
        user_id,
        fingerprint=build_request_fingerprint(request),
    )


@router.post("/protect", response_model=TheftActionResponse)
async def start_theft_protection(
        request: Request,
        user_id: int = Depends(get_current_user_id),
):
    return await start_theft_protection_for_user(
        user_id,
        fingerprint=build_request_fingerprint(request),
    )


@router.get(
    "/bot/me/{user_id}",
    response_model=TheftStatusResponse,
    dependencies=[Depends(require_internal_token)],
)
async def bot_get_theft_status(user_id: int):
    return await get_theft_status_for_user(user_id)
