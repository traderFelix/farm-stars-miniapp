from fastapi import APIRouter, Depends

from api.db.connection import get_db
from api.dependencies.auth import get_current_user_id
from api.schemas.profile import (
    BotBootstrapRequest,
    BotBootstrapResponse,
    ProfileResponse,
)
from api.services.users import bootstrap_bot_user, get_profile_by_user_id

router = APIRouter(prefix="/profile", tags=["profile"])


def _to_profile_response(profile: dict) -> ProfileResponse:
    return ProfileResponse(
        user_id=profile["user_id"],
        username=profile.get("username"),
        first_name=profile.get("first_name"),
        last_name=profile.get("last_name"),
        balance=float(profile.get("balance") or 0),
        role=profile.get("role") or "пользователь",
        role_level=int(profile.get("role_level") or 0),
        activity_index=float(profile.get("activity_index") or 0),
    )


@router.get("/me", response_model=ProfileResponse)
async def get_my_profile(user_id: int = Depends(get_current_user_id)):
    db = await get_db()
    try:
        profile = await get_profile_by_user_id(db, user_id)
    finally:
        await db.close()
    return _to_profile_response(profile)


@router.post("/bot/bootstrap", response_model=BotBootstrapResponse)
async def bot_bootstrap_profile(payload: BotBootstrapRequest):
    db = await get_db()
    try:
        profile, referrer_bound = await bootstrap_bot_user(
            db=db,
            user_id=payload.user_id,
            username=payload.username,
            first_name=payload.first_name,
            last_name=payload.last_name,
            start_referrer_id=payload.start_referrer_id,
        )
    finally:
        await db.close()

    return BotBootstrapResponse(
        ok=True,
        profile=_to_profile_response(profile),
        referrer_bound=referrer_bound,
    )


@router.get("/bot/{user_id}", response_model=ProfileResponse)
async def get_bot_profile(user_id: int):
    db = await get_db()
    try:
        profile = await get_profile_by_user_id(db, user_id)
    finally:
        await db.close()
    return _to_profile_response(profile)
