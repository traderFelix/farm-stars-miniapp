from fastapi import APIRouter

from api.db.connection import get_db
from api.schemas.bot_users import (
    BotBootstrapUserRequest,
    BotBootstrapUserResponse,
    BotUserProfileResponse,
)
from api.services.users import bootstrap_bot_user, get_profile_by_user_id

router = APIRouter(prefix="/bot/users", tags=["bot-users"])


@router.post("/bootstrap", response_model=BotBootstrapUserResponse)
async def bot_bootstrap_user(payload: BotBootstrapUserRequest):
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

    return BotBootstrapUserResponse(
        ok=True,
        profile=BotUserProfileResponse(**profile),
        referrer_bound=referrer_bound,
    )


@router.get("/{user_id}/profile", response_model=BotUserProfileResponse)
async def bot_get_user_profile(user_id: int):
    db = await get_db()
    try:
        profile = await get_profile_by_user_id(db, user_id)
    finally:
        await db.close()

    return BotUserProfileResponse(**profile)
