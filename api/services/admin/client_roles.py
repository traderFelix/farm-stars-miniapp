from __future__ import annotations

from typing import Optional, cast

import aiosqlite

from shared.config import ROLE_CLIENT, ROLE_PARTNER, ROLE_USER
from shared.db.subscriptions import ensure_subscription_tasks_schema
from shared.db.tasks import ensure_task_channels_client_schema
from shared.db.users import get_user_role_level, set_user_role_level


async def ensure_client_role(
        db: aiosqlite.Connection,
        user_id: int,
) -> None:
    current_role_level = await get_user_role_level(db, int(user_id))
    if current_role_level >= ROLE_CLIENT:
        return

    await set_user_role_level(db, int(user_id), ROLE_CLIENT)


async def sync_client_role_after_rebind(
        db: aiosqlite.Connection,
        *,
        previous_user_id: Optional[int],
        next_user_id: Optional[int],
) -> None:
    normalized_previous = int(previous_user_id) if previous_user_id is not None else None
    normalized_next = int(next_user_id) if next_user_id is not None else None

    if normalized_next is not None:
        await ensure_client_role(db, normalized_next)

    if normalized_previous is None or normalized_previous == normalized_next:
        return

    previous_user_id_value = cast(int, normalized_previous)
    current_role_level = await get_user_role_level(db, previous_user_id_value)
    if current_role_level < ROLE_CLIENT or current_role_level >= ROLE_PARTNER:
        return

    if await _has_any_client_bindings(db, previous_user_id_value):
        return

    await set_user_role_level(db, previous_user_id_value, ROLE_USER)


async def _has_any_client_bindings(
        db: aiosqlite.Connection,
        user_id: int,
) -> bool:
    await ensure_task_channels_client_schema(db)
    await ensure_subscription_tasks_schema(db)

    async with db.execute(
            """
        SELECT 1
        FROM task_channels
        WHERE client_user_id = ?
        LIMIT 1
        """,
            (int(user_id),),
    ) as cur:
        if await cur.fetchone():
            return True

    async with db.execute(
            """
        SELECT 1
        FROM subscription_tasks
        WHERE client_user_id = ?
        LIMIT 1
        """,
            (int(user_id),),
    ) as cur:
        return await cur.fetchone() is not None
