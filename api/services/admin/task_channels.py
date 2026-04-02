import sqlite3
from typing import Any, Optional

import aiosqlite
from fastapi import HTTPException

from shared.db.common import tx
from shared.db.tasks import (
    create_task_channel,
    get_task_channel,
    get_task_channel_allocated_views,
    list_task_channels,
    list_task_posts_by_channel,
    set_task_channel_active,
    task_channel_stats,
    update_task_channel_params,
)


def _serialize_channel(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "chat_id": str(row["chat_id"]),
        "title": row["title"] or "",
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
    row = await _get_channel_row(db, int(channel_id))
    stats = await task_channel_stats(db, int(channel_id))
    return {
        "channel": _serialize_channel(row),
        "stats": _serialize_stats(stats),
    }


async def list_channels(db: aiosqlite.Connection) -> dict[str, Any]:
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

    async with tx(db):
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
        total_bought_views: int,
        views_per_post: int,
        view_seconds: int,
) -> dict[str, Any]:
    chat_id = _validate_chat_id(chat_id)
    total_bought_views = _validate_positive_int(total_bought_views, field_name="total_bought_views")
    views_per_post = _validate_positive_int(views_per_post, field_name="views_per_post")
    view_seconds = _validate_positive_int(view_seconds, field_name="view_seconds")
    _validate_views_ratio(total_bought_views, views_per_post)

    try:
        async with tx(db):
            channel_id = await create_task_channel(
                db=db,
                chat_id=chat_id,
                title=title,
                total_bought_views=total_bought_views,
                views_per_post=views_per_post,
                view_seconds=view_seconds,
            )
    except sqlite3.IntegrityError as e:
        raise HTTPException(
            status_code=409,
            detail="Канал с таким chat_id уже существует.",
        ) from e

    return await build_channel_detail(db, int(channel_id))


async def get_channel_posts(
        db: aiosqlite.Connection,
        channel_id: int,
        *,
        limit: int = 20,
) -> dict[str, Any]:
    row = await _get_channel_row(db, int(channel_id))
    posts = await list_task_posts_by_channel(db, int(channel_id), limit=int(limit))
    return {
        "channel": _serialize_channel(row),
        "items": [_serialize_post(post) for post in posts],
    }
