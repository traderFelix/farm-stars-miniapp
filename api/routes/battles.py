from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api.dependencies.auth import get_current_user_id
from api.dependencies.internal import require_internal_token
from api.schemas.battles import BattleStatusResponse
from api.security.request_fingerprint import build_request_fingerprint
from api.services.battles import (
    cancel_battle_for_user,
    get_battle_status_for_user,
    join_battle_for_user,
)

router = APIRouter(prefix="/battles", tags=["battles"])


@router.get("/me", response_model=BattleStatusResponse)
async def get_my_battle_status(
        user_id: int = Depends(get_current_user_id),
):
    return await get_battle_status_for_user(user_id)


@router.post("/join", response_model=BattleStatusResponse)
async def join_battle(
        request: Request,
        user_id: int = Depends(get_current_user_id),
):
    return await join_battle_for_user(
        user_id,
        fingerprint=build_request_fingerprint(request),
    )


@router.post("/cancel", response_model=BattleStatusResponse)
async def cancel_battle(
        request: Request,
        user_id: int = Depends(get_current_user_id),
):
    return await cancel_battle_for_user(
        user_id,
        fingerprint=build_request_fingerprint(request),
    )


@router.get(
    "/bot/me/{user_id}",
    response_model=BattleStatusResponse,
    dependencies=[Depends(require_internal_token)],
)
async def bot_get_battle_status(user_id: int):
    return await get_battle_status_for_user(user_id)
