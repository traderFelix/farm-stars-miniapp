from fastapi import APIRouter, Depends

from api.db.connection import get_db
from api.dependencies.auth import get_current_user_id
from api.services.users import get_profile_by_user_id

router = APIRouter(prefix="/api", tags=["miniapp-compat"])


@router.get("/me")
async def get_me(user_id: int = Depends(get_current_user_id)):
    db = await get_db()
    try:
        profile = await get_profile_by_user_id(db, user_id)
    finally:
        await db.close()

    return {
        "user": {
            "id": profile["user_id"],
            "username": profile.get("username"),
            "first_name": profile.get("first_name"),
            "role": profile.get("role"),
            "balance": float(profile.get("balance") or 0),
            "activity_index": float(profile.get("activity_index") or 0),
        }
    }


@router.get("/history")
async def get_history(user_id: int = Depends(get_current_user_id)):
    # Пока это compat-заглушка.
    # Главное здесь — уже использовать новый bearer token и current user context.
    return {
        "items": [
            {
                "id": 1,
                "delta": 0.03,
                "reason": "view_post_bonus",
                "created_at": "2026-03-18 12:00:00",
                "user_id": user_id,
            },
            {
                "id": 2,
                "delta": 0.05,
                "reason": "daily_bonus",
                "created_at": "2026-03-18 13:00:00",
                "user_id": user_id,
            },
        ]
    }
