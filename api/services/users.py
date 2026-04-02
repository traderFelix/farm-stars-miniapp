import logging
from typing import Any, Optional

import aiosqlite
from fastapi import HTTPException

from shared.db.common import tx
from shared.db.users import (
    bind_referrer,
    build_user_profile,
    fmt_stars,
    get_referrals_count,
    get_user_by_id,
    register_user,
    update_user_telegram_fields,
)

logger = logging.getLogger(__name__)


def build_main_menu_text(profile: dict[str, Any]) -> str:
    return (
        "🏠 Главное меню\n\n"
        f"Баланс: {fmt_stars(profile.get('balance') or 0)}⭐️\n\n"
        f"Роль: {profile.get('role') or 'пользователь'}\n"
        f"Индекс Активности: {float(profile.get('activity_index') or 0):.1f}%"
    )


def build_bot_main_menu_payload(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": int(profile["user_id"]),
        "balance": float(profile.get("balance") or 0),
        "role": profile.get("role") or "пользователь",
        "role_level": int(profile.get("role_level") or 0),
        "activity_index": float(profile.get("activity_index") or 0),
        "text": build_main_menu_text(profile),
    }


def build_bot_referrals_payload(
        *,
        user_id: int,
        invited_count: int,
) -> dict[str, Any]:
    return {
        "user_id": int(user_id),
        "invited_count": int(invited_count),
    }


async def touch_telegram_user(
        db: aiosqlite.Connection,
        tg_user: dict[str, Any],
) -> None:
    await register_user(
        db=db,
        user_id=int(tg_user["user_id"]),
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
        last_name=tg_user.get("last_name"),
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
        await touch_telegram_user(
            db=db,
            tg_user=tg_user,
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


async def bootstrap_bot_user(
        db: aiosqlite.Connection,
        tg_user: dict[str, Any],
        *,
        start_referrer_id: Optional[int] = None,
) -> dict[str, Any]:
    user_id = int(tg_user["user_id"])
    referrer_bound = False

    async with tx(db, immediate=False):
        await touch_telegram_user(db, tg_user)

        if start_referrer_id is not None:
            try:
                referrer_bound = await bind_referrer(db, user_id, int(start_referrer_id))
            except Exception:
                logger.exception(
                    "Failed to bind referrer user_id=%s referrer_id=%s",
                    user_id,
                    start_referrer_id,
                )

    profile = await get_profile_by_user_id(db, user_id)
    payload = build_bot_main_menu_payload(profile)
    payload["referrer_bound"] = referrer_bound
    return payload


async def touch_bot_user_and_get_main_menu(
        db: aiosqlite.Connection,
        tg_user: dict[str, Any],
) -> dict[str, Any]:
    async with tx(db, immediate=False):
        await touch_telegram_user(db, tg_user)

    profile = await get_profile_by_user_id(db, int(tg_user["user_id"]))
    return build_bot_main_menu_payload(profile)


async def get_bot_main_menu_by_user_id(
        db: aiosqlite.Connection,
        user_id: int,
) -> dict[str, Any]:
    profile = await get_profile_by_user_id(db, int(user_id))
    return build_bot_main_menu_payload(profile)


async def touch_bot_user_and_get_referrals(
        db: aiosqlite.Connection,
        tg_user: dict[str, Any],
) -> dict[str, Any]:
    async with tx(db, immediate=False):
        await touch_telegram_user(db, tg_user)

    user_id = int(tg_user["user_id"])
    invited_count = await get_referrals_count(db, user_id)
    return build_bot_referrals_payload(
        user_id=user_id,
        invited_count=invited_count,
    )
