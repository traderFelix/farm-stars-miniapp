import asyncio
import logging

from typing import Any, Optional, TypedDict, Union

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InaccessibleMessage,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

from bot.api_client import (
    ApiClientError,
    bootstrap_bot_user_via_api,
    get_battle_status,
    check_task,
    get_bot_main_menu_for_user_context_via_api,
    get_bot_main_menu_via_api,
    get_next_task,
    get_theft_status,
    ingest_task_channel_post_via_api,
    open_task,
    report_task_unavailable,
)
from bot.keyboards import (
    MAIN_MENU_REPLY_BUTTON_TEXT,
    main_menu,
    persistent_user_menu_kb,
    task_after_view_kb,
    tasks_menu,
)
from bot.pending_channel_posts import (
    TaskChannelPostPayload,
    build_task_channel_post_payload,
    enqueue_task_channel_post_for_retry,
    flush_pending_task_channel_posts,
)
from shared.assets import MINING_HERO_BANNER_PATH
from shared.config import ROLE_CLIENT, ROLE_PARTNER
from shared.formatting import fmt_stars

router = Router()

logger = logging.getLogger(__name__)

LAST_TASK_POST_MSG_ID_KEY = "last_task_post_message_id"
LAST_TASK_MENU_MSG_ID_KEY = "last_task_menu_message_id"
PERSISTENT_USER_MENU_ENABLED_KEY = "persistent_user_menu_enabled"
TASK_VIEW_LOCKS: dict[int, asyncio.Lock] = {}
TASK_UNAVAILABLE_MAX_RETRIES = 3
USER_API_UNAVAILABLE_TEXT = "⚠️ Сервис временно недоступен. Попробуй еще раз чуть позже."
START_TEXT = (
    "🔥 Начинай прямо сейчас фармить ТГ звезды и TON!\n\n"
    "⚡ Открывай Mini App\n"
    "💰 Забирай daily bonus\n"
    "🏆 Лови конкурсы\n"
    "🤝 Качай реферальный бонус\n"
    "🚀 И выводи заработанное"
)
START_VISUAL_PATH = MINING_HERO_BANNER_PATH


class TelegramUserContext(TypedDict):
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]


def _build_tg_user_payload(user: Optional[User]) -> TelegramUserContext:
    if user is None:
        raise ValueError("Telegram user is missing")

    return {
        "user_id": int(user.id),
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }


def _require_user(user: Optional[User]) -> User:
    if user is None:
        raise ValueError("Telegram user is missing")
    return user


def _require_message(message: Union[Message, InaccessibleMessage, None]) -> Message:
    if not isinstance(message, Message):
        raise ValueError("Editable message is missing")
    return message


def _optional_message(message: Union[Message, InaccessibleMessage, None]) -> Optional[Message]:
    return message if isinstance(message, Message) else None


def _to_optional_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        return int(stripped)

    return int(value)


def _is_forwarded_channel_post(message: Message) -> bool:
    forward_markers = (
        "forward_origin",
        "forward_from",
        "forward_from_chat",
        "forward_sender_name",
        "forward_date",
    )
    return (
        any(getattr(message, marker, None) is not None for marker in forward_markers)
        or bool(getattr(message, "is_automatic_forward", False))
    )


def _format_user_api_error(e: ApiClientError) -> str:
    detail = (e.detail or "").strip()
    if e.status_code is None or e.status_code >= 500:
        return USER_API_UNAVAILABLE_TEXT
    if detail:
        return f"❌ {detail}"
    return USER_API_UNAVAILABLE_TEXT


def _is_expired_callback_error(error: TelegramBadRequest) -> bool:
    message = str(error).lower()
    return (
        "query is too old" in message
        or "response timeout expired" in message
        or "query id is invalid" in message
    )


async def safe_callback_answer(
        callback: CallbackQuery,
        text: Optional[str] = None,
        *,
        show_alert: bool = False,
) -> None:
    try:
        await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest as e:
        if _is_expired_callback_error(e):
            logger.info(
                "Skipped expired callback answer callback_id=%s user_id=%s",
                callback.id,
                callback.from_user.id if callback.from_user else None,
            )
            return
        raise


def _log_user_api_error(context: str, e: ApiClientError) -> None:
    logger.warning(
        "User API request failed context=%s status=%s path=%s detail=%s",
        context,
        e.status_code,
        e.path,
        e.detail,
    )


async def _answer_user_api_error(
        callback: CallbackQuery,
        e: ApiClientError,
        *,
        context: str,
) -> None:
    _log_user_api_error(context, e)
    await safe_callback_answer(callback, _format_user_api_error(e), show_alert=True)


async def _reply_user_api_error(
        message: Message,
        e: ApiClientError,
        *,
        context: str,
        reply_markup=None,
) -> None:
    _log_user_api_error(context, e)
    await message.answer(_format_user_api_error(e), reply_markup=reply_markup)


async def _reply_user_api_error_via_callback_message(
        callback: CallbackQuery,
        e: ApiClientError,
        *,
        context: str,
        reply_markup=None,
) -> None:
    _log_user_api_error(context, e)

    if isinstance(callback.message, Message):
        await callback.message.answer(
            _format_user_api_error(e),
            reply_markup=reply_markup,
        )
        return

    await safe_callback_answer(callback, _format_user_api_error(e), show_alert=True)


async def _send_user_api_error(
        bot: Bot,
        user_id: int,
        e: ApiClientError,
        *,
        context: str,
        reply_markup=None,
) -> None:
    _log_user_api_error(context, e)
    await bot.send_message(
        chat_id=user_id,
        text=_format_user_api_error(e),
        reply_markup=reply_markup,
    )


async def _ingest_task_channel_post_payload_via_api(payload: TaskChannelPostPayload) -> None:
    await ingest_task_channel_post_via_api(
        chat_id=payload["chat_id"],
        channel_post_id=payload["channel_post_id"],
        title=payload["title"],
        reward=payload["reward"],
    )


async def _build_tasks_screen_text(user_id: int) -> str:
    menu_payload = await get_bot_main_menu_via_api(user_id)
    balance = float(menu_payload.get("balance") or 0)
    tasks_status_text: Optional[str] = None
    battle_status_text: Optional[str] = None
    theft_status_text: Optional[str] = None

    try:
        next_task = await get_next_task(user_id)
    except ApiClientError as e:
        _log_user_api_error("tasks_screen.next_task", e)
        next_task = None
        tasks_status_text = "⚠️ Не удалось проверить доступные посты."
    except Exception:
        next_task = None

    if next_task:
        tasks_status_text = "Сейчас есть доступные посты для просмотра."
    elif tasks_status_text is None:
        tasks_status_text = "Сейчас доступных постов нет."

    try:
        battle_status = await get_battle_status(user_id)
    except ApiClientError as e:
        _log_user_api_error("tasks_screen.battle_status", e)
        battle_status = None
    except Exception:
        battle_status = None

    if battle_status:
        battle_status_text = _format_battle_status_line(battle_status)

    try:
        theft_status = await get_theft_status(user_id)
    except ApiClientError as e:
        _log_user_api_error("tasks_screen.theft_status", e)
        theft_status = None
    except Exception:
        theft_status = None

    if theft_status:
        theft_status_text = _format_theft_status_line(theft_status)

    return (
        "👁 Просмотр постов\n\n"
        "За каждый просмотр начисляется награда.\n"
        f"{tasks_status_text}\n"
        f"{battle_status_text + chr(10) if battle_status_text else ''}\n"
        f"{theft_status_text + chr(10) if theft_status_text else ''}\n"
        f"Баланс: {fmt_stars(balance)}⭐️"
    )


def _format_battle_seconds(seconds: int) -> str:
    minutes, rest = divmod(max(int(seconds), 0), 60)
    return f"{minutes}:{rest:02d}"


def _format_battle_status_line(status: dict[str, Any]) -> Optional[str]:
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
            f" · { _format_battle_seconds(seconds_left) }"
        )

    return None


def _format_theft_status_line(status: dict[str, Any]) -> Optional[str]:
    state = str(status.get("state") or "").strip()
    if state == "protected":
        return "🛡 Защита от воровства активна"

    if state == "active":
        role = str(status.get("role") or "").strip()
        my_progress = int(status.get("my_progress") or 0)
        target_views = int(status.get("target_views") or 0)
        seconds_left = int(status.get("seconds_left") or 0)
        if role == "attacker":
            return f"🕵️ Кража: {my_progress}/{target_views} · {_format_battle_seconds(seconds_left)}"
        if role == "victim":
            return f"🚨 Защита от атаки: {my_progress}/{target_views} · {_format_battle_seconds(seconds_left)}"
        if role == "protector":
            return f"🛡 Заряд защиты: {my_progress}/{target_views} · {_format_battle_seconds(seconds_left)}"

    return None


def _format_task_battle_progress(status: Optional[dict[str, Any]]) -> Optional[str]:
    if not status:
        return None

    state = str(status.get("state") or "").strip()
    my_progress = int(status.get("my_progress") or 0)
    opponent_progress = int(status.get("opponent_progress") or 0)
    target_views = int(status.get("target_views") or 20)

    if state == "finished":
        result = str(status.get("result") or "").strip()
        if result == "won":
            return f"⚔️ Дуэль выиграна: {my_progress}/{target_views}"
        if result == "draw":
            return "⚔️ Дуэль завершилась вничью"
        if result == "lost":
            return f"⚔️ Дуэль проиграна: {my_progress}/{target_views}"

    seconds_left = int(status.get("seconds_left") or 0)
    return (
        f"⚔️ Дуэль: {my_progress}/{target_views} против {opponent_progress}/{target_views}\n"
        f"До конца: {_format_battle_seconds(seconds_left)}"
    )


def _format_task_theft_progress(status: Optional[dict[str, Any]]) -> Optional[str]:
    if not status:
        return None

    kind = str(status.get("kind") or "").strip()
    state = str(status.get("state") or "").strip()
    result = str(status.get("result") or "").strip()
    role = str(status.get("role") or "").strip()
    my_progress = int(status.get("my_progress") or 0)
    target_views = int(status.get("target_views") or 0)
    opponent_progress = int(status.get("opponent_progress") or 0)
    opponent_target_views = int(status.get("opponent_target_views") or 0)
    amount = float(status.get("amount") or 0)

    if state == "finished":
        if result == "stolen":
            if role == "attacker":
                return f"🕵️ Кража удалась: +{fmt_stars(amount)}⭐"
            return f"💥 У тебя украли -{fmt_stars(amount)}⭐"
        if result == "defended":
            return "🛡 Ты отбил атаку" if role == "victim" else "🛡 Кражу отбили"
        if result == "protected":
            return "🛡 Защита включена на сутки"
        if result == "expired":
            return "⌛ Время активности вышло"

    seconds_left = int(status.get("seconds_left") or 0)
    if kind == "attack":
        return (
            f"🕵️ Кража: {my_progress}/{target_views} против {opponent_progress}/{opponent_target_views}\n"
            f"До конца: {_format_battle_seconds(seconds_left)}"
        )
    if kind == "defense":
        return (
            f"🚨 Отбиваешь кражу: {my_progress}/{target_views} против {opponent_progress}/{opponent_target_views}\n"
            f"До конца: {_format_battle_seconds(seconds_left)}"
        )
    if kind == "protection":
        return (
            f"🛡 Заряд защиты: {my_progress}/{target_views}\n"
            f"До конца: {_format_battle_seconds(seconds_left)}"
        )

    return None


async def _ensure_persistent_user_menu(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get(PERSISTENT_USER_MENU_ENABLED_KEY):
        return

    sent = await message.answer(
        "🏠 Кнопка «Меню» закреплена снизу.",
        reply_markup=persistent_user_menu_kb(),
    )
    try:
        await sent.delete()
    except TelegramBadRequest as e:
        logger.info(
            "Could not delete persistent menu setup message chat_id=%s message_id=%s detail=%s",
            sent.chat.id,
            sent.message_id,
            e,
        )
    except Exception:
        logger.exception(
            "Could not delete persistent menu setup message chat_id=%s message_id=%s",
            sent.chat.id,
            sent.message_id,
        )
    await state.update_data(**{PERSISTENT_USER_MENU_ENABLED_KEY: True})


async def _send_start_screen(message: Message, role_level: int) -> None:
    if START_VISUAL_PATH.exists():
        try:
            await message.answer_photo(
                photo=FSInputFile(START_VISUAL_PATH),
                caption=START_TEXT,
                reply_markup=main_menu(role_level),
            )
            return
        except TelegramBadRequest:
            logger.exception("Failed to send start photo message to user_id=%s", message.chat.id)
    else:
        logger.warning("Start visual asset is missing: %s", START_VISUAL_PATH)

    await message.answer(START_TEXT, reply_markup=main_menu(role_level))


@router.channel_post()
async def ingest_task_channel_post(message: Message):
    has_content = bool(
        message.text
        or message.caption
        or message.photo
        or message.video
        or message.animation
        or message.document
    )
    if not has_content:
        return

    if _is_forwarded_channel_post(message):
        logger.info(
            "Skipped forwarded task channel post chat_id=%s post_id=%s title=%s",
            message.chat.id,
            message.message_id,
            message.chat.title,
        )
        return

    flush_result = await flush_pending_task_channel_posts(
        _ingest_task_channel_post_payload_via_api,
        limit=100,
    )
    if flush_result["flushed"] > 0:
        logger.info(
            "Flushed pending task channel posts before ingest count=%s remaining=%s",
            flush_result["flushed"],
            flush_result["remaining"],
        )

    payload = build_task_channel_post_payload(
        chat_id=str(message.chat.id),
        channel_post_id=int(message.message_id),
        title=message.chat.title,
        reward=0.01,
    )

    try:
        await _ingest_task_channel_post_payload_via_api(payload)
    except ApiClientError as e:
        queue_size = enqueue_task_channel_post_for_retry(payload)
        logger.warning(
            "Failed to ingest channel post via API chat_id=%s post_id=%s detail=%s queue_size=%s",
            message.chat.id,
            message.message_id,
            e.detail,
            queue_size,
        )


@router.message(CommandStart())
async def start(message: Message, bot: Bot, state: FSMContext):
    from_user = _require_user(message.from_user)
    user_id = from_user.id
    username = from_user.username
    first_name = from_user.first_name
    last_name = from_user.last_name

    start_arg = None
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1:
        start_arg = parts[1].strip()

    logger.info("START user_id=%s text=%r start_arg=%r", user_id, message.text, start_arg)
    await _ensure_persistent_user_menu(message, state)

    start_referrer_id = int(start_arg) if start_arg and start_arg.isdigit() else None
    try:
        menu_payload = await bootstrap_bot_user_via_api(
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            start_referrer_id=start_referrer_id,
        )
    except ApiClientError as e:
        await _reply_user_api_error(
            message,
            e,
            context="start.bootstrap",
        )
        return

    if start_referrer_id is not None:
        logger.info(
            "bind_referrer user_id=%s referrer_id=%s bound=%s",
            user_id,
            start_referrer_id,
            bool(menu_payload.get("referrer_bound")),
        )

    role_level = int(menu_payload.get("role_level") or 0)
    if start_arg == "tasks":
        try:
            tasks_screen_text = await _build_tasks_screen_text(user_id)
        except ApiClientError as e:
            await _reply_user_api_error(
                message,
                e,
                context="start.tasks_screen",
            )
            return

        await _delete_last_task_menu(bot, user_id, state)
        sent = await message.answer(tasks_screen_text, reply_markup=tasks_menu())
        await state.update_data(**{LAST_TASK_MENU_MSG_ID_KEY: sent.message_id})
        return

    await _delete_last_task_menu(bot, user_id, state)

    await _send_start_screen(message, role_level)


@router.message(F.text == MAIN_MENU_REPLY_BUTTON_TEXT)
async def open_main_menu_from_reply(message: Message, bot: Bot, state: FSMContext):
    from_user = _require_user(message.from_user)
    user_id = from_user.id

    await _ensure_persistent_user_menu(message, state)

    try:
        menu_payload = await bootstrap_bot_user_via_api(
            user_id=user_id,
            username=from_user.username,
            first_name=from_user.first_name,
            last_name=from_user.last_name,
            start_referrer_id=None,
        )
    except ApiClientError as e:
        await _reply_user_api_error(
            message,
            e,
            context="reply_menu.bootstrap",
        )
        return

    await _delete_last_task_post(bot, user_id, state)
    await _delete_last_task_menu(bot, user_id, state)
    await _send_start_screen(message, int(menu_payload.get("role_level") or 0))


@router.callback_query(F.data == "tasks")
async def show_tasks(callback: CallbackQuery, bot: Bot, state: FSMContext):
    await safe_callback_answer(callback)

    user_id = callback.from_user.id
    current_message = _optional_message(callback.message)
    if current_message is not None:
        await _ensure_persistent_user_menu(current_message, state)

    try:
        tasks_screen_text = await _build_tasks_screen_text(user_id)
    except ApiClientError as e:
        await _reply_user_api_error_via_callback_message(
            callback,
            e,
            context="show_tasks.screen",
        )
        return

    current_message_id = current_message.message_id if current_message else None
    await _delete_last_task_menu(
        bot,
        user_id,
        state,
        exclude_message_id=current_message_id,
    )
    await safe_edit_text(
        callback.message,
        tasks_screen_text,
        reply_markup=tasks_menu(),
    )
    if current_message_id is not None:
        await state.update_data(**{LAST_TASK_MENU_MSG_ID_KEY: current_message_id})


@router.callback_query(F.data == "task:view_post")
async def task_view_post(callback: CallbackQuery, bot: Bot, state: FSMContext):
    user_id = callback.from_user.id
    lock = TASK_VIEW_LOCKS.setdefault(user_id, asyncio.Lock())

    if lock.locked():
        await safe_callback_answer(callback, "⏳ Пост уже открывается.", show_alert=False)
        await _hide_task_trigger_message(callback.message)
        return

    await safe_callback_answer(callback, "Показываю пост...")
    async with lock:
        await _process_task_view_post(callback, bot, state, user_id)


async def _process_task_view_post(
        callback: CallbackQuery,
        bot: Bot,
        state: FSMContext,
        user_id: int,
        *,
        unavailable_attempt: int = 0,
):
    hidden_message_id = await _hide_task_trigger_message(callback.message)
    await _delete_last_task_menu(
        bot,
        user_id,
        state,
        exclude_message_id=hidden_message_id,
    )
    try:
        task = await get_next_task(user_id)
    except ApiClientError as e:
        await _send_user_api_error(
            bot,
            user_id,
            e,
            context="task_view_post.next_task",
            reply_markup=task_after_view_kb(),
        )
        return

    if not task:
        await bot.send_message(
            chat_id=user_id,
            text="❌ Доступных постов пока нет.",
            reply_markup=task_after_view_kb(),
        )
        return

    task_id = int(task["id"])
    chat_id = task.get("chat_id")
    raw_channel_post_id = task.get("channel_post_id")
    normalized_channel_post_id = _to_optional_int(raw_channel_post_id)

    try:
        open_result = await open_task(user_id, task_id)
    except ApiClientError as e:
        await _send_user_api_error(
            bot,
            user_id,
            e,
            context="task_view_post.open_task",
            reply_markup=task_after_view_kb(),
        )
        return
    except Exception:
        await bot.send_message(
            chat_id=user_id,
            text="❌ Не удалось открыть задание.",
            reply_markup=task_after_view_kb(),
        )
        return

    if not open_result.get("ok"):
        open_error_text = open_result.get("message") or "❌ Не удалось открыть задание."
        await bot.send_message(
            chat_id=user_id,
            text=open_error_text,
            reply_markup=task_after_view_kb(),
        )
        return

    reward = float(task.get("reward") or 0)
    view_seconds = float(open_result.get("hold_seconds") or task.get("hold_seconds") or 0)
    session_id = open_result.get("session_id")

    await _delete_last_task_post(bot, user_id, state)

    if not chat_id or normalized_channel_post_id is None:
        reported = await _report_unavailable_task(
            user_id=user_id,
            task_id=task_id,
            reason="missing task post data",
        )
        if reported and unavailable_attempt + 1 < TASK_UNAVAILABLE_MAX_RETRIES:
            await _process_task_view_post(
                callback,
                bot,
                state,
                user_id,
                unavailable_attempt=unavailable_attempt + 1,
            )
            return
        await bot.send_message(
            chat_id=user_id,
            text="❌ У задания нет данных поста.",
            reply_markup=task_after_view_kb(),
        )
        return

    sent_message_id: Optional[int] = None
    try:
        sent = await bot.forward_message(
            chat_id=user_id,
            from_chat_id=str(chat_id),
            message_id=normalized_channel_post_id,
        )
        sent_message_id = sent.message_id
    except TelegramBadRequest as e:
        logger.warning(
            "Failed to forward task post user_id=%s task_id=%s chat_id=%s channel_post_id=%s detail=%s",
            user_id,
            task_id,
            chat_id,
            normalized_channel_post_id,
            e,
        )
        try:
            copied = await bot.copy_message(
                chat_id=user_id,
                from_chat_id=str(chat_id),
                message_id=normalized_channel_post_id,
            )
            sent_message_id = int(copied.message_id)
        except TelegramBadRequest as copy_error:
            logger.warning(
                "Failed to copy task post user_id=%s task_id=%s chat_id=%s channel_post_id=%s detail=%s",
                user_id,
                task_id,
                chat_id,
                normalized_channel_post_id,
                copy_error,
            )
            reported = await _report_unavailable_task(
                user_id=user_id,
                task_id=task_id,
                reason=f"forward: {e}; copy: {copy_error}",
            )
            if reported and unavailable_attempt + 1 < TASK_UNAVAILABLE_MAX_RETRIES:
                await _process_task_view_post(
                    callback,
                    bot,
                    state,
                    user_id,
                    unavailable_attempt=unavailable_attempt + 1,
                )
                return
            await bot.send_message(
                chat_id=user_id,
                text=(
                    "❌ Не удалось показать пост.\n"
                    "Проверь, что бот есть в канале и видит этот пост."
                ),
                reply_markup=task_after_view_kb(),
            )
            return

    if sent_message_id is None:
        reported = await _report_unavailable_task(
            user_id=user_id,
            task_id=task_id,
            reason="missing sent message id",
        )
        if reported and unavailable_attempt + 1 < TASK_UNAVAILABLE_MAX_RETRIES:
            await _process_task_view_post(
                callback,
                bot,
                state,
                user_id,
                unavailable_attempt=unavailable_attempt + 1,
            )
            return
        await bot.send_message(
            chat_id=user_id,
            text=(
                "❌ Не удалось показать пост.\n"
                "Проверь, что бот есть в канале и видит этот пост."
            ),
            reply_markup=task_after_view_kb(),
        )
        return

    await state.update_data(
        **{
            LAST_TASK_POST_MSG_ID_KEY: sent_message_id,
            "active_task_id": task_id,
        }
    )

    await asyncio.sleep(max(view_seconds, 0.0))

    try:
        result = await check_task(user_id, task_id, session_id=session_id)
    except ApiClientError as e:
        await _send_user_api_error(
            bot,
            user_id,
            e,
            context="task_view_post.check_task",
            reply_markup=task_after_view_kb(),
        )
        return
    except Exception:
        await bot.send_message(
            chat_id=user_id,
            text="⚠️ Не удалось засчитать просмотр.\nПопробуй следующий пост.",
            reply_markup=task_after_view_kb(),
        )
        return

    status_value = result.get("status")
    message_text = result.get("message") or "Готово"
    new_balance = float(result.get("new_balance") or 0)
    remaining_text: Optional[str] = None

    try:
        next_task = await get_next_task(user_id)
    except ApiClientError as e:
        _log_user_api_error("task_view_post.next_task_after_check", e)
        next_task = None
        remaining_text = "⚠️ Не удалось проверить, есть ли еще доступные посты."
    except Exception:
        next_task = None

    has_more_tasks = next_task is not None
    if remaining_text is None:
        remaining_text = (
            "Доступные посты еще есть."
            if has_more_tasks
            else "Сейчас доступных постов больше нет."
        )

    if status_value == "completed":
        battle_progress_text = _format_task_battle_progress(result.get("battle"))
        theft_progress_text = _format_task_theft_progress(result.get("theft"))
        activity_progress_text = battle_progress_text or theft_progress_text
        activity_block = f"\n\n{activity_progress_text}" if activity_progress_text else ""
        await bot.send_message(
            chat_id=user_id,
            text=(
                "✅ Просмотр засчитан\n\n"
                f"Начислено: {fmt_stars(reward)}⭐\n"
                f"{remaining_text}\n"
                f"Баланс: {fmt_stars(new_balance)}⭐️"
                f"{activity_block}"
            ),
            reply_markup=task_after_view_kb(),
        )
        return

    if status_value == "already_completed":
        await bot.send_message(
            chat_id=user_id,
            text="✅ Этот пост уже был засчитан ранее.",
            reply_markup=task_after_view_kb(),
        )
        return

    await bot.send_message(
        chat_id=user_id,
        text=f"⚠️ {message_text}",
        reply_markup=task_after_view_kb(),
    )


async def _report_unavailable_task(
        *,
        user_id: int,
        task_id: int,
        reason: str,
) -> bool:
    try:
        await report_task_unavailable(
            user_id,
            task_id,
            reason=reason[:500],
        )
        return True
    except ApiClientError as e:
        _log_user_api_error("task_view_post.report_unavailable", e)
    except Exception:
        logger.exception(
            "Failed to report unavailable task task_id=%s user_id=%s",
            task_id,
            user_id,
        )
    return False


@router.callback_query(F.data == "back")
async def back_to_main(callback: CallbackQuery, bot: Bot, state: FSMContext):
    user_id = callback.from_user.id
    try:
        menu_payload = await get_bot_main_menu_via_api(user_id)
    except ApiClientError as e:
        await _answer_user_api_error(
            callback,
            e,
            context="back_to_main.main_menu",
        )
        return

    role_level = int(menu_payload.get("role_level") or 0)

    await _delete_last_task_post(bot, user_id, state)
    await state.update_data(**{LAST_TASK_MENU_MSG_ID_KEY: None})

    await safe_callback_answer(callback)
    await safe_edit_text(
        callback.message,
        START_TEXT,
        reply_markup=main_menu(role_level),
    )


async def _hide_task_trigger_message(
        message: Union[Message, InaccessibleMessage, None],
) -> Optional[int]:
    task_message = _optional_message(message)
    if task_message is None:
        return None

    try:
        await task_message.delete()
        return task_message.message_id
    except TelegramBadRequest as e:
        if "message to delete not found" in str(e).lower():
            return task_message.message_id
        logger.warning(
            "Failed to delete task trigger message chat_id=%s message_id=%s detail=%s",
            task_message.chat.id,
            task_message.message_id,
            e,
        )
    except Exception:
        logger.exception(
            "Failed to delete task trigger message chat_id=%s message_id=%s",
            task_message.chat.id,
            task_message.message_id,
        )

    try:
        await task_message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logger.warning(
                "Failed to remove task trigger keyboard chat_id=%s message_id=%s detail=%s",
                task_message.chat.id,
                task_message.message_id,
                e,
            )
    except Exception:
        logger.exception(
            "Failed to remove task trigger keyboard chat_id=%s message_id=%s",
            task_message.chat.id,
            task_message.message_id,
        )

    return task_message.message_id


async def _delete_last_task_menu(
        bot: Bot,
        user_id: int,
        state: FSMContext,
        *,
        exclude_message_id: Optional[int] = None,
) -> None:
    data = await state.get_data()
    last_msg_id = data.get(LAST_TASK_MENU_MSG_ID_KEY)
    if not last_msg_id:
        return

    normalized_last_msg_id = int(last_msg_id)
    if exclude_message_id is not None and normalized_last_msg_id == int(exclude_message_id):
        await state.update_data(**{LAST_TASK_MENU_MSG_ID_KEY: None})
        return

    try:
        await bot.delete_message(chat_id=user_id, message_id=normalized_last_msg_id)
    except Exception:
        pass

    await state.update_data(**{LAST_TASK_MENU_MSG_ID_KEY: None})


async def _delete_last_task_post(bot: Bot, user_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    last_msg_id = data.get(LAST_TASK_POST_MSG_ID_KEY)
    if not last_msg_id:
        return

    try:
        await bot.delete_message(chat_id=user_id, message_id=int(last_msg_id))
    except Exception:
        pass

    await state.update_data(**{LAST_TASK_POST_MSG_ID_KEY: None})


async def safe_edit_text(
        message: Union[Message, InaccessibleMessage, None],
        text: str,
        reply_markup=None,
        parse_mode: Optional[str] = None,
):
    editable_message = _require_message(message)
    try:
        has_media = bool(
            editable_message.photo
            or editable_message.animation
            or editable_message.document
            or editable_message.video
        )
        if has_media:
            await editable_message.edit_caption(
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        else:
            await editable_message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        raise


@router.callback_query(F.data == "client:home")
async def client_home(callback: CallbackQuery):
    try:
        menu_payload = await get_bot_main_menu_for_user_context_via_api(
            **_build_tg_user_payload(callback.from_user),
        )
    except ApiClientError as e:
        await safe_callback_answer(callback, f"❌ {e.detail}", show_alert=True)
        return

    role_level = int(menu_payload.get("role_level") or 0)

    if role_level < ROLE_CLIENT:
        await safe_callback_answer(callback, "❌ Раздел клиента тебе пока недоступен.", show_alert=True)
        return

    await safe_callback_answer(callback)
    await safe_edit_text(
        callback.message,
        "🤝 <b>Кабинет клиента</b>\n\n"
        "Тут потом будут:\n"
        "• мои заказы\n"
        "• запуск просмотров\n"
        "• запуск подписок\n"
        "• статистика заказов",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
            ]
        ),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "partner:home")
async def partner_home(callback: CallbackQuery):
    try:
        menu_payload = await get_bot_main_menu_for_user_context_via_api(
            **_build_tg_user_payload(callback.from_user),
        )
    except ApiClientError as e:
        await safe_callback_answer(callback, f"❌ {e.detail}", show_alert=True)
        return

    role_level = int(menu_payload.get("role_level") or 0)

    if role_level < ROLE_PARTNER:
        await safe_callback_answer(callback, "❌ Партнерский раздел тебе пока недоступен.", show_alert=True)
        return

    await safe_callback_answer(callback)
    await safe_edit_text(
        callback.message,
        "💼 <b>Кабинет партнера</b>\n\n"
        "Тут потом будут:\n"
        "• приглашенные клиенты\n"
        "• приглашенные юзеры\n"
        "• проценты / бонусы\n"
        "• партнерская статистика",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
            ]
        ),
        parse_mode=ParseMode.HTML,
    )
