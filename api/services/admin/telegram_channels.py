from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from fastapi import HTTPException

from shared.config import TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)


def _telegram_api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def _telegram_request_json_sync(method: str, params: Optional[dict[str, object]] = None) -> dict[str, Any]:
    query = urllib_parse.urlencode(params or {})
    url = _telegram_api_url(method)
    if query:
        url = f"{url}?{query}"

    request = urllib_request.Request(url, method="GET")
    with urllib_request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not payload.get("ok"):
        raise RuntimeError(str(payload.get("description") or "Telegram API request failed"))

    return payload


def _telegram_channel_title_sync(chat_id: str) -> str:
    payload = _telegram_request_json_sync("getChat", {"chat_id": str(chat_id)})
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("Telegram API returned an empty chat result")

    title = str(result.get("title") or result.get("username") or "").strip()
    if not title:
        raise RuntimeError("Telegram API returned chat without title")
    return title


def _verify_telegram_channel_access_sync(chat_id: str) -> str:
    title = _telegram_channel_title_sync(chat_id)

    me_payload = _telegram_request_json_sync("getMe")
    me = me_payload.get("result")
    if not isinstance(me, dict) or me.get("id") is None:
        raise RuntimeError("Telegram API returned an empty bot result")

    member_payload = _telegram_request_json_sync(
        "getChatMember",
        {
            "chat_id": str(chat_id),
            "user_id": int(me["id"]),
        },
    )
    member = member_payload.get("result")
    status = str(member.get("status") or "").lower() if isinstance(member, dict) else ""
    if status in {"left", "kicked"} or not status:
        raise RuntimeError("Bot is not a member of the channel")

    return title


async def try_fetch_telegram_channel_title(chat_id: str) -> Optional[str]:
    try:
        return await asyncio.to_thread(_telegram_channel_title_sync, chat_id)
    except (urllib_error.HTTPError, urllib_error.URLError, RuntimeError, json.JSONDecodeError) as exc:
        logger.info("Could not fetch Telegram channel title chat_id=%s detail=%s", chat_id, exc)
        return None


async def verified_telegram_channel_title(chat_id: str, *, activation_subject: str) -> str:
    try:
        return await asyncio.to_thread(_verify_telegram_channel_access_sync, chat_id)
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        logger.warning(
            "Could not verify Telegram channel access chat_id=%s http=%s detail=%s",
            chat_id,
            exc.code,
            detail,
        )
    except (urllib_error.URLError, RuntimeError, json.JSONDecodeError) as exc:
        logger.warning("Could not verify Telegram channel access chat_id=%s detail=%s", chat_id, exc)

    raise HTTPException(
        status_code=400,
        detail=(
            f"Нельзя включить {activation_subject}: бот не добавлен в канал или не видит канал. "
            "Добавь бота в канал и попробуй снова."
        ),
    )
