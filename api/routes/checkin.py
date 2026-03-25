from fastapi import APIRouter, Depends

from api.dependencies.auth import get_current_user_id
from api.schemas.checkin import CheckinStatusResponse, CheckinClaimResponse
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
async def claim_checkin(user_id: int = Depends(get_current_user_id)):
    return await claim_checkin_service(user_id)


# ===== Bot (через user_id) =====

@router.get("/bot/status/{user_id}", response_model=CheckinStatusResponse)
async def get_checkin_status_for_bot(user_id: int):
    return await get_checkin_status_service(user_id)


@router.post("/bot/claim/{user_id}", response_model=CheckinClaimResponse)
async def claim_checkin_for_bot(user_id: int):
    return await claim_checkin_service(user_id)