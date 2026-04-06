import asyncio
import logging

from pathlib import Path
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
    check_task,
    get_bot_main_menu_for_user_context_via_api,
    get_bot_main_menu_via_api,
    get_next_task,
    ingest_task_channel_post_via_api,
    open_task,
)
from bot.keyboards import main_menu, task_after_view_kb, tasks_menu
from bot.pending_channel_posts import (
    TaskChannelPostPayload,
    build_task_channel_post_payload,
    enqueue_task_channel_post_for_retry,
    flush_pending_task_channel_posts,
)
from shared.config import ROLE_CLIENT, ROLE_PARTNER
from shared.formatting import fmt_stars

router = Router()

logger = logging.getLogger(__name__)

LAST_TASK_POST_MSG_ID_KEY = "last_task_post_message_id"
USER_API_UNAVAILABLE_TEXT = "⚠️ Сервис временно недоступен. Попробуй еще раз чуть позже."
START_TEXT = (
    "🔥 Начинай прямо сейчас фармить ТГ звезды и TON!\n\n"
    "⚡ Открывай Mini App\n"
    "💰 Забирай daily bonus\n"
    "🏆 Лови конкурсы\n"
    "🤝 Качай реферальный бонус\n"
    "🚀 И выводи заработанное"
)
START_VISUAL_PATH = (
    Path(__file__).resolve().parents[2]
    / "web"
    / "public"
    / "hero"
    / "mining-hero-banner.png"
)


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


def _format_user_api_error(e: ApiClientError) -> str:
    detail = (e.detail or "").strip()
    if e.status_code is None or e.status_code >= 500:
        return USER_API_UNAVAILABLE_TEXT
    if detail:
        return f"❌ {detail}"
    return USER_API_UNAVAILABLE_TEXT


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
    await callback.answer(_format_user_api_error(e), show_alert=True)


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

    await callback.answer(_format_user_api_error(e), show_alert=True)


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

    return (
        "👁 Просмотр постов\n\n"
        "За каждый просмотр начисляется награда.\n"
        f"{tasks_status_text}\n\n"
        f"Баланс: {fmt_stars(balance)}⭐️"
    )


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
async def start(message: Message):
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

        await message.answer(tasks_screen_text, reply_markup=tasks_menu())
        return

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


@router.callback_query(F.data == "tasks")
async def show_tasks(callback: CallbackQuery):
    await callback.answer()

    user_id = callback.from_user.id
    try:
        tasks_screen_text = await _build_tasks_screen_text(user_id)
    except ApiClientError as e:
        await _reply_user_api_error_via_callback_message(
            callback,
            e,
            context="show_tasks.screen",
        )
        return

    await safe_edit_text(
        callback.message,
        tasks_screen_text,
        reply_markup=tasks_menu(),
    )


@router.callback_query(F.data == "task:view_post")
async def task_view_post(callback: CallbackQuery, bot: Bot, state: FSMContext):
    user_id = callback.from_user.id
    try:
        task = await get_next_task(user_id)
    except ApiClientError as e:
        await _answer_user_api_error(
            callback,
            e,
            context="task_view_post.next_task",
        )
        return

    if not task:
        await callback.answer("❌ Доступных постов пока нет.", show_alert=True)
        return

    task_id = int(task["id"])
    chat_id = task.get("chat_id")
    raw_channel_post_id = task.get("channel_post_id")
    normalized_channel_post_id = _to_optional_int(raw_channel_post_id)

    try:
        open_result = await open_task(user_id, task_id)
    except ApiClientError as e:
        await _answer_user_api_error(
            callback,
            e,
            context="task_view_post.open_task",
        )
        return
    except Exception:
        await callback.answer("❌ Не удалось открыть задание.", show_alert=True)
        return

    if not open_result.get("ok"):
        await callback.answer(
            open_result.get("message") or "❌ Не удалось открыть задание.",
            show_alert=True,
        )
        return

    reward = float(task.get("reward") or 0)
    view_seconds = int(open_result.get("hold_seconds") or task.get("hold_seconds") or 0)

    await callback.answer(open_result.get("message") or "Показываю пост...")
    await _delete_last_task_post(bot, user_id, state)

    try:
        callback_message = _require_message(callback.message)
        await callback_message.delete()
    except Exception:
        pass

    if not chat_id or normalized_channel_post_id is None:
        await bot.send_message(
            chat_id=user_id,
            text="❌ У задания нет данных поста.",
            reply_markup=task_after_view_kb(),
        )
        return

    try:
        sent = await bot.forward_message(
            chat_id=user_id,
            from_chat_id=str(chat_id),
            message_id=normalized_channel_post_id,
        )
    except TelegramBadRequest:
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
            LAST_TASK_POST_MSG_ID_KEY: sent.message_id,
            "active_task_id": task_id,
        }
    )

    await asyncio.sleep(view_seconds)

    try:
        result = await check_task(user_id, task_id)
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
        await bot.send_message(
            chat_id=user_id,
            text=(
                "✅ Просмотр засчитан\n\n"
                f"Начислено: {fmt_stars(reward)}⭐\n"
                f"{remaining_text}\n"
                f"Баланс: {fmt_stars(new_balance)}⭐️"
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

    await callback.answer()
    await safe_edit_text(
        callback.message,
        START_TEXT,
        reply_markup=main_menu(role_level),
    )


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
        await callback.answer(f"❌ {e.detail}", show_alert=True)
        return

    role_level = int(menu_payload.get("role_level") or 0)

    if role_level < ROLE_CLIENT:
        await callback.answer("❌ Раздел клиента тебе пока недоступен.", show_alert=True)
        return

    await callback.answer()
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
        await callback.answer(f"❌ {e.detail}", show_alert=True)
        return

    role_level = int(menu_payload.get("role_level") or 0)

    if role_level < ROLE_PARTNER:
        await callback.answer("❌ Партнерский раздел тебе пока недоступен.", show_alert=True)
        return

    await callback.answer()
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
