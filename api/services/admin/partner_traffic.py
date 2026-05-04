from __future__ import annotations

from typing import Any, Optional

import aiosqlite
from fastapi import HTTPException

from api.services.admin.client_roles import ensure_partner_role
from shared.db.common import tx
from shared.db.partners import add_partner_traffic_event, get_partner_traffic_event
from shared.db.users import get_user_by_id


def _normalize_channel_chat_id(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Нужен chat_id канала")
    if not normalized.startswith("-100"):
        raise HTTPException(status_code=400, detail="chat_id канала должен быть в формате -100...")
    return normalized


def _normalize_channel_title(value: Optional[str]) -> Optional[str]:
    normalized = str(value or "").strip()
    return normalized or None


def _normalize_views_amount(value: int, *, field_label: str, allow_zero: bool) -> int:
    normalized = int(value)
    if normalized < 0 or (normalized == 0 and not allow_zero):
        comparator = "0 или больше" if allow_zero else "больше 0"
        raise HTTPException(status_code=400, detail=f"{field_label} должно быть числом {comparator}")
    return normalized


def _serialize_partner_traffic_event(row: Any, partner: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "partner_user_id": int(row["partner_user_id"]),
        "partner_username": (partner["username"] or None) if partner is not None else None,
        "partner_first_name": (partner["tg_first_name"] or None) if partner is not None else None,
        "channel_chat_id": str(row["channel_chat_id"]),
        "channel_title": (row["channel_title"] or None),
        "views_promised": int(row["views_promised"] or 0),
        "views_delivered": int(row["views_delivered"] or 0),
        "note": (row["note"] or None),
        "created_at": row["created_at"],
    }


async def create_partner_views_accrual(
        db: aiosqlite.Connection,
        *,
        partner_user_id: int,
        channel_chat_id: str,
        channel_title: Optional[str],
        views_promised: int,
        views_delivered: int = 0,
) -> dict[str, Any]:
    normalized_partner_user_id = int(partner_user_id)
    normalized_chat_id = _normalize_channel_chat_id(channel_chat_id)
    normalized_title = _normalize_channel_title(channel_title)
    normalized_views_promised = _normalize_views_amount(
        views_promised,
        field_label="Обещанные просмотры",
        allow_zero=False,
    )
    normalized_views_delivered = _normalize_views_amount(
        views_delivered,
        field_label="Выданные просмотры",
        allow_zero=True,
    )
    if normalized_views_delivered > normalized_views_promised:
        raise HTTPException(
            status_code=400,
            detail="Выданные просмотры не могут быть больше обещанных",
        )

    partner = await get_user_by_id(db, normalized_partner_user_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Партнер не найден")

    async with tx(db, immediate=True):
        await ensure_partner_role(db, normalized_partner_user_id)
        event_id = await add_partner_traffic_event(
            db,
            partner_user_id=normalized_partner_user_id,
            channel_chat_id=normalized_chat_id,
            channel_title=normalized_title,
            views_promised=normalized_views_promised,
            views_delivered=normalized_views_delivered,
            note="ручное начисление просмотров",
        )
        row = await get_partner_traffic_event(db, event_id)

    if row is None:
        raise HTTPException(status_code=500, detail="Не удалось сохранить начисление")

    return _serialize_partner_traffic_event(row, partner)
