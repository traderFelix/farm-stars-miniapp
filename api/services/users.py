from typing import Any

import aiosqlite
from fastapi import HTTPException

from shared.db.users import (
    build_user_profile,
    get_user_by_id,
    register_user,
    update_user_telegram_fields,
)


async def get_or_create_telegram_user(
        db: aiosqlite.Connection,
        tg_user: dict[str, Any],
) -> dict[str, Any]:
    user_id = int(tg_user["user_id"])
    username = tg_user.get("username")
    first_name = tg_user.get("first_name")
    last_name = tg_user.get("last_name")

    existing = await get_user_by_id(db, user_id)

    if not existing:
        await register_user(
            db=db,
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
    else:
        await update_user_telegram_fields(
            db=db,
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )

    await db.commit()

    profile = await build_user_profile(db, user_id)
    if not profile:
        raise HTTPException(status_code=500, detail="Failed to load user after auth")

    return profile


async def get_profile_by_user_id(
        db: aiosqlite.Connection,
        user_id: int,
) -> dict[str, Any]:
    profile = await build_user_profile(db, int(user_id))
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile