import sqlite3
from typing import Any, Optional

import aiosqlite
from fastapi import HTTPException

from api.services.admin.client_roles import ensure_client_role, sync_client_role_after_rebind
from api.services.admin.telegram_channels import verified_telegram_channel_title
from shared.db.common import tx
from shared.db.tasks import (
    allocate_task_post_from_channel_post,
    create_task_channel,
    ensure_task_channels_client_schema,
    get_task_post_by_channel_post,
    get_task_channel,
    get_task_channel_allocated_views,
    list_task_channels,
    list_task_posts_by_channel,
    set_task_channel_client,
    set_task_channel_title,
    set_task_channel_active,
    task_channel_stats,
    update_task_channel_params,
)
from shared.db.users import get_user_by_id


def _serialize_channel(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "chat_id": str(row["chat_id"]),
        "title": row["title"] or "",
        "client_user_id": int(row["client_user_id"]) if row["client_user_id"] is not None else None,
        "client_username": row["client_username"] or None,
        "client_first_name": row["client_first_name"] or None,
        "is_active": bool(row["is_active"] or 0),
        "total_bought_views": int(row["total_bought_views"] or 0),
        "views_per_post": int(row["views_per_post"] or 0),
        "view_seconds": int(row["view_seconds"] or 0),
        "allocated_views": int(row["allocated_views"] or 0),
        "remaining_views": int(row["remaining_views"] or 0),
        "created_at": row["created_at"],
    }


def _serialize_stats(row: Any) -> dict[str, Any]:
    return {
        "total_posts": int(row["total_posts"] or 0),
        "total_required": int(row["total_required"] or 0),
        "total_current": int(row["total_current"] or 0),
        "active_posts": int(row["active_posts"] or 0),
    }


def _serialize_post(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "channel_post_id": int(row["channel_post_id"]),
        "required_views": int(row["required_views"] or 0),
        "current_views": int(row["current_views"] or 0),
        "is_active": bool(row["is_active"] or 0),
        "source": row["source"] if "source" in row.keys() else "auto",
        "added_by_admin_id": (
            int(row["added_by_admin_id"])
            if "added_by_admin_id" in row.keys() and row["added_by_admin_id"] is not None
            else None
        ),
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
    }


async def _get_channel_row(db: aiosqlite.Connection, channel_id: int) -> Any:
    row = await get_task_channel(db, int(channel_id))
    if not row:
        raise HTTPException(status_code=404, detail="Канал не найден.")
    return row


def _validate_positive_int(value: int, *, field_name: str) -> int:
    normalized = int(value)
    if normalized <= 0:
        raise HTTPException(status_code=400, detail=f"{field_name} должно быть больше 0")
    return normalized


def _validate_chat_id(chat_id: str) -> str:
    normalized = (chat_id or "").strip()
    if not normalized.startswith("-100"):
        raise HTTPException(status_code=400, detail="Нужен channel id в формате -100...")
    return normalized


def _validate_views_ratio(total_bought_views: int, views_per_post: int) -> None:
    if int(views_per_post) > int(total_bought_views):
        raise HTTPException(
            status_code=400,
            detail="Просмотров на 1 пост не может быть больше, чем куплено всего.",
        )


async def build_channel_detail(
        db: aiosqlite.Connection,
        channel_id: int,
) -> dict[str, Any]:
    await ensure_task_channels_client_schema(db)
    row = await _get_channel_row(db, int(channel_id))
    stats = await task_channel_stats(db, int(channel_id))
    return {
        "channel": _serialize_channel(row),
        "stats": _serialize_stats(stats),
    }


async def list_channels(db: aiosqlite.Connection) -> dict[str, Any]:
    await ensure_task_channels_client_schema(db)
    rows = await list_task_channels(db)
    return {
        "items": [_serialize_channel(row) for row in rows],
    }


async def toggle_channel(
        db: aiosqlite.Connection,
        channel_id: int,
) -> dict[str, Any]:
    row = await _get_channel_row(db, int(channel_id))
    new_active = 0 if int(row["is_active"] or 0) == 1 else 1
    verified_title: Optional[str] = None

    if new_active == 1:
        verified_title = await verified_telegram_channel_title(
            str(row["chat_id"]),
            activation_subject="канал просмотров",
        )

    async with tx(db):
        if verified_title:
            await set_task_channel_title(db, int(channel_id), verified_title)
        await set_task_channel_active(db, int(channel_id), new_active)

    return await build_channel_detail(db, int(channel_id))


async def update_channel(
        db: aiosqlite.Connection,
        channel_id: int,
        *,
        total_bought_views: int,
        views_per_post: int,
        view_seconds: int,
) -> dict[str, Any]:
    _ = await _get_channel_row(db, int(channel_id))

    total_bought_views = _validate_positive_int(total_bought_views, field_name="total_bought_views")
    views_per_post = _validate_positive_int(views_per_post, field_name="views_per_post")
    view_seconds = _validate_positive_int(view_seconds, field_name="view_seconds")
    _validate_views_ratio(total_bought_views, views_per_post)

    allocated_views = await get_task_channel_allocated_views(db, int(channel_id))
    if total_bought_views < allocated_views:
        raise HTTPException(
            status_code=400,
            detail=(
                "Нельзя поставить меньше, чем уже распределено по постам.\n\n"
                f"Уже распределено: {allocated_views}"
            ),
        )

    async with tx(db):
        await update_task_channel_params(
            db=db,
            channel_id=int(channel_id),
            total_bought_views=total_bought_views,
            views_per_post=views_per_post,
            view_seconds=view_seconds,
        )

    return await build_channel_detail(db, int(channel_id))


async def create_channel(
        db: aiosqlite.Connection,
        *,
        chat_id: str,
        title: Optional[str],
        client_user_id: Optional[int],
        total_bought_views: int,
        views_per_post: int,
        view_seconds: int,
) -> dict[str, Any]:
    chat_id = _validate_chat_id(chat_id)
    total_bought_views = _validate_positive_int(total_bought_views, field_name="total_bought_views")
    views_per_post = _validate_positive_int(views_per_post, field_name="views_per_post")
    view_seconds = _validate_positive_int(view_seconds, field_name="view_seconds")
    _validate_views_ratio(total_bought_views, views_per_post)

    if client_user_id is not None and not await get_user_by_id(db, int(client_user_id)):
        raise HTTPException(status_code=404, detail="Клиент не найден")

    try:
        async with tx(db):
            channel_id = await create_task_channel(
                db=db,
                chat_id=chat_id,
                title=title,
                client_user_id=client_user_id,
                total_bought_views=total_bought_views,
                views_per_post=views_per_post,
                view_seconds=view_seconds,
            )
            if client_user_id is not None:
                await ensure_client_role(db, int(client_user_id))
    except sqlite3.IntegrityError as e:
        raise HTTPException(
            status_code=409,
            detail="Канал с таким chat_id уже существует.",
        ) from e

    return await build_channel_detail(db, int(channel_id))


async def bind_channel_client(
        db: aiosqlite.Connection,
        channel_id: int,
        *,
        client_user_id: int,
) -> dict[str, Any]:
    row = await _get_channel_row(db, int(channel_id))

    if not await get_user_by_id(db, int(client_user_id)):
        raise HTTPException(status_code=404, detail="Клиент не найден")

    previous_client_user_id = (
        int(row["client_user_id"])
        if row["client_user_id"] is not None
        else None
    )
    async with tx(db):
        await set_task_channel_client(db, int(channel_id), int(client_user_id))
        await sync_client_role_after_rebind(
            db,
            previous_user_id=previous_client_user_id,
            next_user_id=int(client_user_id),
        )

    return await build_channel_detail(db, int(channel_id))


async def update_channel_title(
        db: aiosqlite.Connection,
        channel_id: int,
        *,
        title: str,
) -> dict[str, Any]:
    await _get_channel_row(db, int(channel_id))
    normalized_title = (title or "").strip()
    if not normalized_title:
        raise HTTPException(status_code=400, detail="Название канала не может быть пустым.")

    async with tx(db):
        await set_task_channel_title(db, int(channel_id), normalized_title)

    return await build_channel_detail(db, int(channel_id))


async def get_channel_posts(
        db: aiosqlite.Connection,
        channel_id: int,
        *,
        limit: int = 5,
        page: int = 0,
) -> dict[str, Any]:
    row = await _get_channel_row(db, int(channel_id))
    normalized_limit = max(int(limit), 1)
    normalized_page = max(int(page), 0)
    offset = normalized_page * normalized_limit
    posts = await list_task_posts_by_channel(
        db,
        int(channel_id),
        limit=normalized_limit + 1,
        offset=offset,
    )
    has_next = len(posts) > normalized_limit
    return {
        "channel": _serialize_channel(row),
        "items": [_serialize_post(post) for post in posts[:normalized_limit]],
        "page": normalized_page,
        "has_next": has_next,
    }


async def add_manual_channel_post(
        db: aiosqlite.Connection,
        channel_id: int,
        *,
        channel_post_id: int,
        added_by_admin_id: int,
) -> dict[str, Any]:
    row = await _get_channel_row(db, int(channel_id))
    channel_post_id = _validate_positive_int(channel_post_id, field_name="channel_post_id")

    if int(row["is_active"] or 0) != 1:
        raise HTTPException(status_code=400, detail="Канал отключен. Сначала включи канал.")

    if int(row["remaining_views"] or 0) <= 0:
        raise HTTPException(status_code=400, detail="У канала закончились купленные просмотры.")

    existing = await get_task_post_by_channel_post(
        db,
        channel_id=int(channel_id),
        channel_post_id=int(channel_post_id),
    )
    if existing:
        raise HTTPException(status_code=409, detail="Этот пост уже есть в базе.")

    async with tx(db, immediate=True):
        allocated = await allocate_task_post_from_channel_post(
            db=db,
            chat_id=str(row["chat_id"]),
            channel_post_id=int(channel_post_id),
            title=row["title"] or None,
            reward=0.01,
            source="manual",
            added_by_admin_id=int(added_by_admin_id),
        )
        if not allocated:
            raise HTTPException(
                status_code=409,
                detail="Не удалось добавить пост. Возможно, он уже есть или закончились просмотры.",
            )

        post = await get_task_post_by_channel_post(
            db,
            channel_id=int(channel_id),
            channel_post_id=int(channel_post_id),
        )

    detail = await build_channel_detail(db, int(channel_id))
    return {
        **detail,
        "post": _serialize_post(post),
    }
