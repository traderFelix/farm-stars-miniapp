from fastapi import APIRouter, Depends

from api.db.connection import get_db
from api.dependencies.auth import get_current_user_id
from api.schemas.users import UpdateGameNicknameRequest, UserProfileResponse
from api.services.users import change_game_nickname_for_user, get_profile_by_user_id

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(user_id: int = Depends(get_current_user_id)):
    db = await get_db()
    try:
        profile = await get_profile_by_user_id(db, user_id)
    finally:
        await db.close()

    return UserProfileResponse(
        user_id=profile["user_id"],
        game_nickname=profile.get("game_nickname"),
        game_nickname_change_count=int(profile.get("game_nickname_change_count") or 0),
        can_change_game_nickname=bool(profile.get("can_change_game_nickname")),
        balance=float(profile.get("balance") or 0),
        role=profile.get("role") or "пользователь",
        activity_index=float(profile.get("activity_index") or 0),
    )


@router.patch("/me/game-nickname", response_model=UserProfileResponse)
async def update_my_game_nickname(
        payload: UpdateGameNicknameRequest,
        user_id: int = Depends(get_current_user_id),
):
    db = await get_db()
    try:
        profile = await change_game_nickname_for_user(
            db,
            user_id=int(user_id),
            game_nickname=payload.game_nickname,
        )
    finally:
        await db.close()

    return UserProfileResponse(
        user_id=profile["user_id"],
        game_nickname=profile.get("game_nickname"),
        game_nickname_change_count=int(profile.get("game_nickname_change_count") or 0),
        can_change_game_nickname=bool(profile.get("can_change_game_nickname")),
        balance=float(profile.get("balance") or 0),
        role=profile.get("role") or "пользователь",
        activity_index=float(profile.get("activity_index") or 0),
    )
