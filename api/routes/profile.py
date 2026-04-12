from fastapi import APIRouter, Depends

from api.db.connection import get_db
from api.dependencies.auth import get_current_user_id
from api.schemas.users import UserProfileResponse
from api.services.users import get_profile_by_user_id

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
        username=profile.get("username"),
        first_name=profile.get("first_name"),
        balance=float(profile.get("balance") or 0),
        role=profile.get("role") or "пользователь",
        activity_index=float(profile.get("activity_index") or 0),
    )
