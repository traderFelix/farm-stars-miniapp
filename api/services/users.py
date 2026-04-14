import logging
import re
from typing import Any, Optional

import aiosqlite
from fastapi import HTTPException

from shared.db.common import tx
from shared.db.users import (
    bind_referrer,
    build_user_profile,
    get_user_by_id,
    is_game_nickname_taken,
    normalize_game_nickname,
    register_user,
    set_user_game_nickname_once,
    update_user_telegram_fields,
)

logger = logging.getLogger(__name__)
_GAME_NICKNAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9 _-]{1,22}[A-Za-zА-Яа-яЁё0-9]$")


def build_bot_main_menu_payload(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": int(profile["user_id"]),
        "balance": float(profile.get("balance") or 0),
        "role": profile.get("role") or "пользователь",
        "role_level": int(profile.get("role_level") or 0),
        "withdrawal_ability": float(profile.get("withdrawal_ability") or 0),
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


async def change_game_nickname_for_user(
        db: aiosqlite.Connection,
        user_id: int,
        game_nickname: str,
) -> dict[str, Any]:
    profile = await get_profile_by_user_id(db, int(user_id))
    current_nickname = normalize_game_nickname(profile.get("game_nickname"))
    next_nickname = normalize_game_nickname(game_nickname)

    if len(next_nickname) < 3:
        raise HTTPException(status_code=400, detail="Игровой ник слишком короткий")
    if len(next_nickname) > 24:
        raise HTTPException(status_code=400, detail="Игровой ник слишком длинный")
    if not _GAME_NICKNAME_RE.fullmatch(next_nickname):
        raise HTTPException(
            status_code=400,
            detail="Ник может содержать буквы, цифры, пробел, дефис и нижнее подчеркивание",
        )

    if next_nickname.casefold() == current_nickname.casefold():
        return profile

    if not bool(profile.get("can_change_game_nickname")):
        raise HTTPException(status_code=400, detail="Игровой ник можно изменить только один раз")

    if await is_game_nickname_taken(db, next_nickname, exclude_user_id=int(user_id)):
        raise HTTPException(status_code=409, detail="Такой игровой ник уже занят")

    async with tx(db, immediate=True):
        updated = await set_user_game_nickname_once(
            db,
            int(user_id),
            next_nickname,
        )

    if not updated:
        raise HTTPException(status_code=400, detail="Игровой ник уже был изменен")

    return await get_profile_by_user_id(db, int(user_id))


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
