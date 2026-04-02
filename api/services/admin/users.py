from typing import Any, Optional

import aiosqlite
from fastapi import HTTPException

from shared.config import ROLE_OWNER
from shared.db.common import tx
from shared.db.ledger import apply_balance_delta
from shared.db.users import (
    build_user_profile,
    clear_user_suspicious,
    get_balance,
    get_user_by_id,
    get_user_role_level,
    mark_user_suspicious,
    role_title_from_level,
    set_user_role_level,
)


async def get_profile(
        db: aiosqlite.Connection,
        user_id: int,
) -> dict[str, Any]:
    profile = await build_user_profile(db, int(user_id))
    if not profile:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return profile


async def lookup_profile(
        db: aiosqlite.Connection,
        query: str,
) -> dict[str, Any]:
    value = (query or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="Пустой запрос")

    if value.isdigit():
        return await get_profile(db, int(value))

    username = value.lstrip("@")
    async with db.execute(
            "SELECT user_id FROM users WHERE username = ? LIMIT 1",
            (username,),
    ) as cur:
        row = await cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return await get_profile(db, int(row["user_id"]))


async def update_role(
        db: aiosqlite.Connection,
        user_id: int,
        role_level: int,
) -> dict[str, Any]:
    target_level = int(role_level)
    if target_level >= ROLE_OWNER:
        raise HTTPException(status_code=400, detail="Роль владельца назначить нельзя.")

    async with tx(db, immediate=False):
        ok = await set_user_role_level(db, int(user_id), target_level)
        if not ok:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

    final_level = await get_user_role_level(db, int(user_id))
    return {
        "user_id": int(user_id),
        "role_level": int(final_level),
        "role": role_title_from_level(final_level),
    }


async def adjust_balance(
        db: aiosqlite.Connection,
        user_id: int,
        amount: float,
        mode: str,
) -> dict[str, Any]:
    value = float(amount)
    if value <= 0:
        raise HTTPException(status_code=400, detail="Сумма должна быть больше 0")

    normalized_mode = (mode or "").strip().lower()
    if normalized_mode not in {"add", "sub"}:
        raise HTTPException(status_code=400, detail="Некорректный режим операции")

    if not await get_user_by_id(db, int(user_id)):
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    delta = value if normalized_mode == "add" else -value

    async with tx(db):
        await apply_balance_delta(
            db,
            user_id=int(user_id),
            delta=delta,
            reason="admin_adjust",
            meta=f"mode={normalized_mode}",
        )

    balance = await get_balance(db, int(user_id))
    return {
        "user_id": int(user_id),
        "delta": float(delta),
        "balance": float(balance or 0),
    }


async def mark_suspicious(
        db: aiosqlite.Connection,
        user_id: int,
        reason: Optional[str],
) -> dict[str, Any]:
    if not await get_user_by_id(db, int(user_id)):
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    await mark_user_suspicious(
        db,
        int(user_id),
        (reason or "").strip() or "Помечен администратором",
    )
    return await get_profile(db, int(user_id))


async def clear_suspicious(
        db: aiosqlite.Connection,
        user_id: int,
) -> dict[str, Any]:
    if not await get_user_by_id(db, int(user_id)):
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    await clear_user_suspicious(db, int(user_id))
    return await get_profile(db, int(user_id))
