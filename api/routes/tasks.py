import json
import logging
import mimetypes
from pathlib import Path
from typing import Any, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from api.db.connection import get_db
from api.dependencies.auth import get_current_user_id
from api.dependencies.internal import require_internal_token
from api.schemas.tasks import (
    TaskChannelPostIngestRequest,
    TaskChannelPostIngestResponse,
    TaskCheckRequest,
    TaskCheckResponse,
    TaskListItem,
    TaskOpenRequest,
    TaskOpenResponse,
)
from api.services.battles import get_battle_status_for_user
from api.services.tasks import (
    check_task_for_user,
    get_next_task_for_user,
    ingest_task_channel_post_message,
    open_task_for_user,
)
from api.services.users import get_bot_main_menu_by_user_id
from shared.assets import MINING_HERO_BANNER_PATH
from shared.config import TELEGRAM_BOT_TOKEN

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
)
logger = logging.getLogger(__name__)

TASKS_BANNER_PATH = MINING_HERO_BANNER_PATH
TASKS_SERVICE_UNAVAILABLE_DETAIL = "Сервис временно недоступен. Попробуй еще раз чуть позже."


async def _get_next_task_or_404(user_id: int) -> TaskListItem:
    task = await get_next_task_for_user(user_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No available tasks",
        )
    return task


async def _open_task(user_id: int, task_id: int) -> TaskOpenResponse:
    return await open_task_for_user(
        user_id=user_id,
        task_id=task_id,
    )


async def _check_task(
        user_id: int,
        task_id: int,
        *,
        session_id: Optional[str] = None,
) -> TaskCheckResponse:
    return await check_task_for_user(
        user_id=user_id,
        task_id=task_id,
        session_id=session_id,
    )


async def _build_tasks_screen_text(user_id: int) -> str:
    db = await get_db()
    try:
        menu_payload = await get_bot_main_menu_by_user_id(db, user_id)
    finally:
        await db.close()

    balance = float(menu_payload.get("balance") or 0)
    tasks_status_text = "Сейчас доступных постов нет."
    battle_status_text = ""

    try:
        next_task = await get_next_task_for_user(user_id)
    except Exception:
        next_task = None
        tasks_status_text = "⚠️ Не удалось проверить доступные посты."
    else:
        if next_task:
            tasks_status_text = "Сейчас есть доступные посты для просмотра."

    try:
        battle_status = await get_battle_status_for_user(user_id)
        battle_status_text = _format_battle_status_line(battle_status.model_dump())
    except Exception:
        battle_status_text = ""

    return (
        "👁 Просмотр постов\n\n"
        "За каждый просмотр начисляется награда.\n"
        f"{tasks_status_text}\n"
        f"{battle_status_text + chr(10) if battle_status_text else ''}\n"
        f"Баланс: {balance:.2f}".replace(".00", "") + "⭐"
    )


def _format_battle_seconds(seconds: int) -> str:
    minutes, rest = divmod(max(int(seconds), 0), 60)
    return f"{minutes}:{rest:02d}"


def _format_battle_status_line(status: dict[str, Any]) -> str:
    state = str(status.get("state") or "").strip()
    if state == "waiting":
        return "⚔️ Дуэль: идет поиск соперника"

    if state == "active":
        my_progress = int(status.get("my_progress") or 0)
        opponent_progress = int(status.get("opponent_progress") or 0)
        target_views = int(status.get("target_views") or 20)
        seconds_left = int(status.get("seconds_left") or 0)
        return (
            f"⚔️ Дуэль: {my_progress}/{target_views} против {opponent_progress}/{target_views}"
            f" · {_format_battle_seconds(seconds_left)}"
        )

    return ""


def _build_tasks_reply_markup() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "👁 Смотреть пост", "callback_data": "task:view_post"}],
            [{"text": "⬅ Назад", "callback_data": "back"}],
        ]
    }


def _build_multipart_body(
        fields: dict[str, str],
        *,
        file_field: str,
        file_path: Path,
) -> tuple[bytes, str]:
    boundary = f"----FarmStars{uuid4().hex}"
    parts: list[bytes] = []

    for name, value in fields.items():
        parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )

    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    parts.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{file_path.name}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )

    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _telegram_api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def _raise_telegram_http_error(exc: urllib_error.HTTPError) -> None:
    detail = exc.reason
    try:
        payload = json.loads(exc.read().decode("utf-8"))
        detail = payload.get("description") or payload.get("detail") or detail
    except Exception:
        pass

    if exc.code == 403:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bot cannot send messages to this user",
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=str(detail),
    ) from exc


def _send_tasks_message_to_user(
        *,
        user_id: int,
        text: str,
) -> None:
    reply_markup = json.dumps(_build_tasks_reply_markup(), ensure_ascii=False)

    if TASKS_BANNER_PATH.exists():
        body, content_type = _build_multipart_body(
            {
                "chat_id": str(user_id),
                "caption": text,
                "reply_markup": reply_markup,
            },
            file_field="photo",
            file_path=TASKS_BANNER_PATH,
        )
        request = urllib_request.Request(
            _telegram_api_url("sendPhoto"),
            data=body,
            headers={"Content-Type": content_type},
            method="POST",
        )
    else:
        payload = json.dumps(
            {
                "chat_id": user_id,
                "text": text,
                "reply_markup": _build_tasks_reply_markup(),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib_request.Request(
            _telegram_api_url("sendMessage"),
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

    try:
        with urllib_request.urlopen(request, timeout=15) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        _raise_telegram_http_error(exc)
    except urllib_error.URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=TASKS_SERVICE_UNAVAILABLE_DETAIL,
        ) from exc

    if not response_payload.get("ok"):
        detail = response_payload.get("description") or "Telegram API request failed"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(detail),
        )


@router.get(
    "/next",
    response_model=TaskListItem,
    summary="Get next available task",
)
async def get_next_task(
        user_id: int = Depends(get_current_user_id),
):
    return await _get_next_task_or_404(user_id)


@router.post(
    "/{task_id}/open",
    response_model=TaskOpenResponse,
    summary="Open task",
)
async def open_task(
        task_id: int,
        payload: TaskOpenRequest,
        user_id: int = Depends(get_current_user_id),
):
    _ = payload
    return await _open_task(
        user_id=user_id,
        task_id=task_id,
    )


@router.post(
    "/{task_id}/check",
    response_model=TaskCheckResponse,
    summary="Check task completion",
)
async def check_task(
        task_id: int,
        payload: TaskCheckRequest,
        user_id: int = Depends(get_current_user_id),
):
    return await _check_task(
        user_id=user_id,
        task_id=task_id,
        session_id=payload.session_id,
    )


@router.post(
    "/open-in-bot",
    summary="Send tasks screen to the user's bot chat",
)
async def open_tasks_in_bot(
        user_id: int = Depends(get_current_user_id),
):
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not configured for tasks/open-in-bot")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=TASKS_SERVICE_UNAVAILABLE_DETAIL,
        )

    tasks_screen_text = await _build_tasks_screen_text(user_id)
    _send_tasks_message_to_user(
        user_id=user_id,
        text=tasks_screen_text,
    )

    return {"ok": True}


@router.get(
    "/bot/next/{user_id}",
    response_model=TaskListItem,
    summary="Bot internal: get next task for user",
    dependencies=[Depends(require_internal_token)],
)
async def bot_get_next_task(user_id: int):
    return await _get_next_task_or_404(user_id)


@router.post(
    "/bot/{task_id}/open/{user_id}",
    response_model=TaskOpenResponse,
    summary="Bot internal: open task for user",
    dependencies=[Depends(require_internal_token)],
)
async def bot_open_task(
        user_id: int,
        task_id: int,
):
    return await _open_task(
        user_id=user_id,
        task_id=task_id,
    )


@router.post(
    "/bot/{task_id}/check/{user_id}",
    response_model=TaskCheckResponse,
    summary="Bot internal: check task for user",
    dependencies=[Depends(require_internal_token)],
)
async def bot_check_task(
        user_id: int,
        task_id: int,
        payload: TaskCheckRequest,
):
    return await _check_task(
        user_id=user_id,
        task_id=task_id,
        session_id=payload.session_id,
    )


@router.post(
    "/bot/channel-posts/ingest",
    response_model=TaskChannelPostIngestResponse,
    summary="Bot internal: ingest channel post into task pool",
    dependencies=[Depends(require_internal_token)],
)
async def bot_ingest_channel_post(
        payload: TaskChannelPostIngestRequest,
):
    return await ingest_task_channel_post_message(
        chat_id=payload.chat_id,
        channel_post_id=payload.channel_post_id,
        title=payload.title,
        reward=payload.reward,
    )
