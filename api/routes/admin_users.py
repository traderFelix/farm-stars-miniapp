from fastapi import APIRouter, HTTPException
from api.db.connection import get_db
from api.services.users import get_profile_by_user_id

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

@router.get("/{user_id}")
async def get_admin_user_profile(user_id: int):
    db = await get_db()
    try:
        profile = await get_profile_by_user_id(db, user_id)
    finally:
        await db.close()

    if not profile:
        raise HTTPException(status_code=404, detail="User not found")

    return profile