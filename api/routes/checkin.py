from fastapi import APIRouter, Depends, Request

from api.dependencies.auth import get_current_user_id
from api.dependencies.internal import require_internal_token
from api.security.request_fingerprint import build_request_fingerprint
from api.schemas.checkin import CheckinContextRequest, CheckinStatusResponse, CheckinClaimResponse
from api.services.checkin import (
    get_checkin_status_service,
    claim_checkin_service,
)

router = APIRouter(prefix="/checkin", tags=["checkin"])


# ===== Web (через токен) =====

@router.get("/status", response_model=CheckinStatusResponse)
async def get_checkin_status(user_id: int = Depends(get_current_user_id)):
    return await get_checkin_status_service(user_id)


@router.post("/claim", response_model=CheckinClaimResponse)
async def claim_checkin(request: Request, user_id: int = Depends(get_current_user_id)):
    return await claim_checkin_service(
        user_id,
        fingerprint=build_request_fingerprint(request),
    )


# ===== Bot (через user_id) =====

@router.post(
    "/bot/status",
    response_model=CheckinStatusResponse,
    dependencies=[Depends(require_internal_token)],
)
async def get_checkin_status_for_bot_context(payload: CheckinContextRequest):
    return await get_checkin_status_service(
        payload.user.user_id,
        username=payload.user.username,
        first_name=payload.user.first_name,
        last_name=payload.user.last_name,
    )


@router.post(
    "/bot/claim",
    response_model=CheckinClaimResponse,
    dependencies=[Depends(require_internal_token)],
)
async def claim_checkin_for_bot_context(payload: CheckinContextRequest):
    return await claim_checkin_service(
        payload.user.user_id,
        username=payload.user.username,
        first_name=payload.user.first_name,
        last_name=payload.user.last_name,
    )

@router.get("/bot/status/{user_id}", response_model=CheckinStatusResponse)
async def get_checkin_status_for_bot(
        user_id: int,
        _: None = Depends(require_internal_token),
):
    return await get_checkin_status_service(user_id)


@router.post("/bot/claim/{user_id}", response_model=CheckinClaimResponse)
async def claim_checkin_for_bot(
        user_id: int,
        _: None = Depends(require_internal_token),
):
    return await claim_checkin_service(user_id)
