from __future__ import annotations

from typing import Optional, cast

import aiosqlite

from shared.config import (
    OWNER_TYPE_CLIENT,
    OWNER_TYPE_PARTNER,
    ROLE_ADMIN,
    ROLE_CLIENT,
    ROLE_PARTNER,
    ROLE_USER,
)
from shared.db.promos import ensure_promos_schema
from shared.db.partners import ensure_partner_traffic_schema
from shared.db.subscriptions import ensure_subscription_tasks_schema
from shared.db.tasks import ensure_task_channels_client_schema
from shared.db.users import get_user_role_level, set_user_role_level


def _normalize_owner_type(value: Optional[str]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == OWNER_TYPE_PARTNER:
        return OWNER_TYPE_PARTNER
    return OWNER_TYPE_CLIENT


async def ensure_client_role(
        db: aiosqlite.Connection,
        user_id: int,
) -> None:
    current_role_level = await get_user_role_level(db, int(user_id))
    if current_role_level >= ROLE_CLIENT:
        return

    await set_user_role_level(db, int(user_id), ROLE_CLIENT)


async def ensure_partner_role(
        db: aiosqlite.Connection,
        user_id: int,
) -> None:
    current_role_level = await get_user_role_level(db, int(user_id))
    if current_role_level >= ROLE_PARTNER:
        return

    await set_user_role_level(db, int(user_id), ROLE_PARTNER)


async def ensure_owner_role(
        db: aiosqlite.Connection,
        user_id: int,
        *,
        owner_type: str,
) -> None:
    normalized_owner_type = _normalize_owner_type(owner_type)
    if normalized_owner_type == OWNER_TYPE_PARTNER:
        await ensure_partner_role(db, int(user_id))
        return

    await ensure_client_role(db, int(user_id))


async def sync_client_role_after_rebind(
        db: aiosqlite.Connection,
        *,
        previous_user_id: Optional[int],
        next_user_id: Optional[int],
) -> None:
    await sync_owner_role_after_rebind(
        db,
        previous_user_id=previous_user_id,
        next_user_id=next_user_id,
        owner_type=OWNER_TYPE_CLIENT,
    )


async def sync_owner_role_after_rebind(
        db: aiosqlite.Connection,
        *,
        previous_user_id: Optional[int],
        next_user_id: Optional[int],
        owner_type: str,
) -> None:
    normalized_owner_type = _normalize_owner_type(owner_type)
    normalized_previous = int(previous_user_id) if previous_user_id is not None else None
    normalized_next = int(next_user_id) if next_user_id is not None else None

    if normalized_next is not None:
        await ensure_owner_role(db, normalized_next, owner_type=normalized_owner_type)

    if normalized_previous is None or normalized_previous == normalized_next:
        return
    previous_user_id_value = cast(int, normalized_previous)

    current_role_level = await get_user_role_level(db, previous_user_id_value)
    if normalized_owner_type == OWNER_TYPE_CLIENT:
        if current_role_level < ROLE_CLIENT or current_role_level >= ROLE_PARTNER:
            return
        if await _has_any_owner_bindings(db, previous_user_id_value, owner_type=OWNER_TYPE_CLIENT):
            return
        await set_user_role_level(db, previous_user_id_value, ROLE_USER)
        return

    if current_role_level < ROLE_PARTNER or current_role_level >= ROLE_ADMIN:
        return
    if await _has_any_owner_bindings(db, previous_user_id_value, owner_type=OWNER_TYPE_PARTNER):
        return
    if await _has_any_owner_bindings(db, previous_user_id_value, owner_type=OWNER_TYPE_CLIENT):
        await set_user_role_level(db, previous_user_id_value, ROLE_CLIENT)
        return
    await set_user_role_level(db, previous_user_id_value, ROLE_USER)


async def _has_any_owner_bindings(
        db: aiosqlite.Connection,
        user_id: int,
        *,
        owner_type: str,
) -> bool:
    normalized_owner_type = _normalize_owner_type(owner_type)
    await ensure_task_channels_client_schema(db)
    await ensure_subscription_tasks_schema(db)

    # noinspection SqlDialectInspection,SqlNoDataSourceInspection
    async with db.execute(
            """
        SELECT 1
        FROM task_channels
        WHERE client_user_id = ?
          AND owner_type = ?
        LIMIT 1
        """,
            (int(user_id), normalized_owner_type),
    ) as cur:
        if await cur.fetchone():
            return True

    # noinspection SqlDialectInspection,SqlNoDataSourceInspection
    async with db.execute(
            """
        SELECT 1
        FROM subscription_tasks
        WHERE client_user_id = ?
          AND owner_type = ?
        LIMIT 1
        """,
            (int(user_id), normalized_owner_type),
    ) as cur:
        if await cur.fetchone():
            return True

    if normalized_owner_type != OWNER_TYPE_PARTNER:
        return False

    await ensure_promos_schema(db)
    # noinspection SqlDialectInspection,SqlNoDataSourceInspection
    async with db.execute(
            """
        SELECT 1
        FROM promo_codes
        WHERE partner_user_id = ?
          AND status != 'archived'
        LIMIT 1
        """,
            (int(user_id),),
    ) as cur:
        if await cur.fetchone():
            return True

    await ensure_partner_traffic_schema(db)
    # noinspection SqlDialectInspection,SqlNoDataSourceInspection
    async with db.execute(
            """
        SELECT 1
        FROM partner_traffic_events
        WHERE partner_user_id = ?
        LIMIT 1
        """,
            (int(user_id),),
    ) as cur:
        return await cur.fetchone() is not None
