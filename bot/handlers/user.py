import asyncio
import html
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
    Message,
    User,
)

from bot.api_client import (
    ApiClientError,
    bootstrap_bot_user_via_api,
    check_task,
    get_battle_status,
    get_bot_main_menu_for_user_context_via_api,
    get_bot_main_menu_via_api,
    get_client_cabinet_summary_via_api,
    get_client_channel_subscription_campaigns_via_api,
    get_client_channel_subscription_stats_via_api,
    get_client_channel_via_api,
    get_client_channel_posts_via_api,
    get_client_channel_view_stats_via_api,
    get_partner_cabinet_summary_via_api,
    get_partner_channel_accruals_via_api,
    get_partner_channel_via_api,
    get_next_task,
    list_client_channels_via_api,
    list_client_orders_via_api,
    list_partner_channel_accrual_history_via_api,
    list_partner_channel_promos_via_api,
    list_partner_channels_via_api,
    get_theft_status,
    ingest_task_channel_post_via_api,
    open_task,
    report_task_unavailable,
)
from bot.keyboards import (
    client_back_kb,
    client_channel_kb,
    client_channels_kb,
    client_home_kb,
    client_posts_nav_kb,
    client_subscription_stats_kb,
    client_view_stats_kb,
    main_menu,
    miniapp_menu_button,
    partner_accruals_kb,
    partner_channel_kb,
    partner_home_kb,
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
from shared.config import ROLE_PARTNER
from shared.formatting import fmt_stars

router = Router()

logger = logging.getLogger(__name__)

LAST_TASK_POST_MSG_ID_KEY = "last_task_post_message_id"
LAST_TASK_MENU_MSG_ID_KEY = "last_task_menu_message_id"
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


def _has_visual_media(message: Message) -> bool:
    return bool(
        message.photo
        or message.animation
        or message.document
        or message.video
    )


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


def _format_client_channel_title(channel: dict[str, Any]) -> str:
    return html.escape((channel.get("title") or "").strip() or str(channel.get("chat_id") or "Канал"))


def _format_client_datetime(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else "не указано"


def _format_client_days(value: Any) -> str:
    days = int(value or 0)
    if days <= 0:
        return "без удержания"
    return f"{days} дн."


def _format_client_status(is_active: Any) -> str:
    return "🟢 активен" if bool(is_active) else "🔴 на паузе"


def _build_client_home_text(summary: dict[str, Any]) -> str:
    return (
        "🤝 <b>Кабинет клиента</b>\n\n"
        f"Каналов: <b>{int(summary.get('channels_count') or 0)}</b>\n"
        f"Заказов: <b>{int(summary.get('orders_count') or 0)}</b>"
    )


def _build_client_channels_text(items: list[dict[str, Any]]) -> str:
    if not items:
        return (
            "📋 <b>Мои каналы</b>\n\n"
            "У тебя пока нет подключенных каналов."
        )

    return (
        "📋 <b>Мои каналы</b>\n\n"
        "Выбери канал из списка ниже."
    )


def _build_client_channel_text(channel: dict[str, Any]) -> str:
    has_views = bool(channel.get("has_views") or False)
    has_subscriptions = bool(channel.get("has_subscriptions") or False)
    views_line = (
        f"Куплено просмотров: <b>{int(channel.get('total_bought_views') or 0)}</b>\n"
        f"Осталось просмотров: <b>{int(channel.get('remaining_views') or 0)}</b>\n"
        if has_views
        else "Просмотры: <b>не подключены</b>\n"
    )
    subscriptions_line = "Подписки: <b>подключены</b>\n" if has_subscriptions else ""
    return (
        f"📺 <b>{_format_client_channel_title(channel)}</b>\n\n"
        f"Статус: <b>{_format_client_status(channel.get('is_active'))}</b>\n"
        f"{views_line}"
        f"{subscriptions_line}\n"
        "Выбери нужную статистику."
    )


def _build_client_view_stats_text(payload: dict[str, Any]) -> str:
    channel = payload["channel"]
    stats = payload["stats"]
    return (
        f"📊 <b>Статистика просмотров</b>\n\n"
        f"Канал: <b>{_format_client_channel_title(channel)}</b>\n"
        f"Статус: <b>{_format_client_status(channel.get('is_active'))}</b>\n"
        f"Куплено просмотров: <b>{int(channel.get('total_bought_views') or 0)}</b>\n"
        f"Распределено: <b>{int(channel.get('allocated_views') or 0)}</b>\n"
        f"Осталось: <b>{int(channel.get('remaining_views') or 0)}</b>\n"
        "\n"
        f"Постов всего: <b>{int(stats.get('total_posts') or 0)}</b>\n"
        f"Требуется просмотров: <b>{int(stats.get('total_required') or 0)}</b>\n"
        f"Получено просмотров: <b>{int(stats.get('total_current') or 0)}</b>\n"
        f"Активных постов: <b>{int(stats.get('active_posts') or 0)}</b>"
    )


def _build_client_subscription_stats_text(payload: dict[str, Any]) -> str:
    channel = payload["channel"]
    stats = payload["stats"]
    return (
        f"📊 <b>Статистика подписок</b>\n\n"
        f"Канал: <b>{_format_client_channel_title(channel)}</b>\n"
        f"Кампаний всего: <b>{int(stats.get('tasks_count') or 0)}</b>\n"
        f"Активных кампаний: <b>{int(stats.get('active_tasks_count') or 0)}</b>\n"
        f"Куплено подписчиков: <b>{int(stats.get('total_subscribers_bought') or 0)}</b>"
    )


def _build_client_orders_text(items: list[dict[str, Any]]) -> str:
    if not items:
        return (
            "🧾 <b>Мои заказы</b>\n\n"
            "История заказов пока пустая."
        )

    lines = ["🧾 <b>Мои заказы</b>", ""]
    for index, item in enumerate(items, start=1):
        title = html.escape((item.get("title") or "").strip() or str(item.get("chat_id") or "Канал"))
        created_at = _format_client_datetime(item.get("created_at"))

        if item.get("kind") == "views":
            lines.extend([
                f"{index}. 📺 <b>Просмотры</b>",
                f"Канал: <b>{title}</b>",
                f"Дата: <b>{created_at}</b>",
                f"Куплено: <b>{int(item.get('total_bought_views') or 0)}</b> просмотров",
                f"Просмотров на пост: <b>{int(item.get('views_per_post') or 0)}</b>",
                f"Показ: <b>{int(item.get('view_seconds') or 0)} сек.</b>",
                "",
            ])
            continue

        lines.extend([
            f"{index}. 👥 <b>Подписчики</b>",
            f"Канал: <b>{title}</b>",
            f"Дата: <b>{created_at}</b>",
            f"Куплено: <b>{int(item.get('max_subscribers') or 0)}</b> подписчиков",
            f"Удержание: <b>{_format_client_days(item.get('daily_claim_days'))}</b>",
            "",
        ])

    return "\n".join(lines).strip()


def _build_client_posts_status_text(payload: dict[str, Any]) -> str:
    channel = payload["channel"]
    rows = list(payload.get("items") or [])

    if not rows:
        return (
            "📊 <b>Статус по постам</b>\n\n"
            f"Канал: <b>{_format_client_channel_title(channel)}</b>\n\n"
            "Пока нет добавленных постов."
        )

    lines = [
        "📊 <b>Статус по постам</b>",
        "",
        f"Канал: <b>{_format_client_channel_title(channel)}</b>",
        "",
    ]
    for row in rows:
        post_id = int(row.get("channel_post_id") or 0)
        current_views = int(row.get("current_views") or 0)
        required_views = int(row.get("required_views") or 0)
        source_label = "ручной" if row.get("source") == "manual" else "авто"
        done = current_views >= required_views and required_views > 0
        status = "✅" if done else "🔄"
        created_at = _format_client_datetime(row.get("created_at"))
        lines.append(
            f"📝 Пост #{post_id} ({source_label}, {created_at}) — {current_views}/{required_views} {status}"
        )
        lines.append("")

    return "\n".join(lines).strip()


def _build_client_campaigns_status_text(payload: dict[str, Any]) -> str:
    channel = payload["channel"]
    rows = list(payload.get("items") or [])

    if not rows:
        return (
            "📊 <b>Статус кампаний</b>\n\n"
            f"Канал: <b>{_format_client_channel_title(channel)}</b>\n\n"
            "Пока нет добавленных кампаний."
        )

    lines = [
        "📊 <b>Статус кампаний</b>",
        "",
        f"Канал: <b>{_format_client_channel_title(channel)}</b>",
        "",
    ]
    for row in rows:
        campaign_id = int(row.get("id") or 0)
        created_at = _format_client_datetime(row.get("created_at"))
        is_active = bool(row.get("is_active") or False)
        participants = int(row.get("participants_count") or 0)
        max_subscribers = int(row.get("max_subscribers") or 0)
        status_label = "Активная" if is_active else "Не активная"
        status_icon = "🟢" if is_active else "🔴"
        lines.append(
            f"{status_icon} {status_label} кампания #{campaign_id} {created_at} — {participants}/{max_subscribers}"
        )
        lines.append("")

    return "\n".join(lines).strip()


def _format_partner_promo_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return "активен" if normalized == "active" else "выключен"


def _build_partner_home_text(summary: dict[str, Any]) -> str:
    return (
        "💼 <b>Кабинет партнера</b>\n\n"
        f"Каналов: <b>{int(summary.get('channels_count') or 0)}</b>\n"
        f"Рефералов: <b>{int(summary.get('referrals_count') or 0)}</b>"
    )


def _build_partner_channel_text(channel: dict[str, Any]) -> str:
    return f"<b>{_format_client_channel_title(channel)}</b>"


def _build_partner_promos_text(payload: dict[str, Any]) -> str:
    channel = payload["channel"]
    rows = list(payload.get("items") or [])

    if not rows:
        return (
            "🎟 <b>Мои промокоды</b>\n\n"
            f"Канал: <b>{_format_client_channel_title(channel)}</b>\n\n"
            "Пока нет привязанных промокодов."
        )

    lines = [
        "🎟 <b>Мои промокоды</b>",
        "",
        f"Канал: <b>{_format_client_channel_title(channel)}</b>",
        "",
    ]
    for row in rows:
        promo_code = html.escape(str(row.get("promo_code") or ""))
        status = _format_partner_promo_status(row.get("status"))
        claims_count = int(row.get("claims_count") or 0)
        total_uses = int(row.get("total_uses") or 0)
        new_referrals_count = int(row.get("new_referrals_count") or 0)
        lines.extend([
            f"<b>{promo_code}</b>",
            f"Статус: <b>{status}</b>",
            f"Активации: <b>{claims_count}/{total_uses}</b>",
            f"Новых рефов: <b>{new_referrals_count}</b>",
            "",
        ])

    return "\n".join(lines).strip()


def _build_partner_accruals_text(payload: dict[str, Any]) -> str:
    channel = payload["channel"]
    summary = payload["summary"]
    subscribers_accrued = int(summary.get("subscribers_promised") or 0)
    subscribers_spent = int(summary.get("subscribers_delivered") or 0)
    views_accrued = int(summary.get("views_promised") or 0)
    views_spent = int(summary.get("views_delivered") or 0)
    subscribers_remaining = max(subscribers_accrued - subscribers_spent, 0)
    views_remaining = max(views_accrued - views_spent, 0)
    return (
        "🧾 <b>Мои начисления</b>\n\n"
        f"Канал: <b>{_format_client_channel_title(channel)}</b>\n\n"
        f"Подписчиков начислено: <b>{subscribers_accrued}</b>\n"
        f"Подписчиков использовано: <b>{subscribers_spent}</b>\n"
        f"Подписчиков осталось: <b>{subscribers_remaining}</b>\n\n"
        f"Просмотров начислено: <b>{views_accrued}</b>\n"
        f"Просмотров использовано на посты: <b>{views_spent}</b>\n"
        f"Просмотров осталось: <b>{views_remaining}</b>"
    )


def _build_partner_accrual_history_text(payload: dict[str, Any]) -> str:
    channel = payload["channel"]
    rows = list(payload.get("items") or [])

    if not rows:
        return (
            "🗓 <b>История начислений</b>\n\n"
            f"Канал: <b>{_format_client_channel_title(channel)}</b>\n\n"
            "Пока нет записей."
        )

    lines = [
        "🗓 <b>История начислений</b>",
        "",
        f"Канал: <b>{_format_client_channel_title(channel)}</b>",
        "",
    ]
    for row in rows:
        created_at = _format_client_datetime(row.get("created_at"))
        subscribers_accrued = int(row.get("subscribers_promised") or 0)
        views_accrued = int(row.get("views_promised") or 0)
        entry_lines = [f"<b>{created_at}</b>"]
        if subscribers_accrued > 0:
            entry_lines.append(f"Подписчики начислено: <b>{subscribers_accrued}</b>")
        if views_accrued > 0:
            entry_lines.append(f"Просмотры начислено: <b>{views_accrued}</b>")
        if len(entry_lines) == 1:
            continue

        lines.extend(entry_lines)
        lines.append("")

    return "\n".join(lines).strip()


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
        await _answer_visual_message(
            callback.message,
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
    await _send_visual_message(
        bot,
        user_id,
        _format_user_api_error(e),
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


async def _ensure_chat_menu_button(bot: Bot, chat_id: int) -> None:
    try:
        await bot.set_chat_menu_button(
            chat_id=int(chat_id),
            menu_button=miniapp_menu_button(),
        )
    except TelegramBadRequest as e:
        logger.info(
            "Could not set chat menu button chat_id=%s detail=%s",
            chat_id,
            e,
        )
    except Exception:
        logger.exception(
            "Could not set chat menu button chat_id=%s",
            chat_id,
        )


async def _send_start_screen(message: Message, role_level: int) -> None:
    await _answer_visual_message(
        message,
        START_TEXT,
        reply_markup=main_menu(role_level),
    )


async def _answer_visual_message(
        message: Message,
        text: str,
        *,
        reply_markup=None,
        parse_mode: Optional[str] = None,
) -> Message:
    if START_VISUAL_PATH.exists():
        try:
            return await message.answer_photo(
                photo=FSInputFile(START_VISUAL_PATH),
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        except TelegramBadRequest:
            logger.exception("Failed to send start photo message to user_id=%s", message.chat.id)
    else:
        logger.warning("Start visual asset is missing: %s", START_VISUAL_PATH)

    return await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)


async def _send_visual_message(
        bot: Bot,
        chat_id: int,
        text: str,
        *,
        reply_markup=None,
        parse_mode: Optional[str] = None,
) -> Message:
    if START_VISUAL_PATH.exists():
        try:
            return await bot.send_photo(
                chat_id=chat_id,
                photo=FSInputFile(START_VISUAL_PATH),
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        except TelegramBadRequest:
            logger.exception("Failed to send visual message to user_id=%s", chat_id)
    else:
        logger.warning("Start visual asset is missing: %s", START_VISUAL_PATH)

    return await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )


async def _replace_with_visual_message(
        bot: Bot,
        user_id: int,
        message: Union[Message, InaccessibleMessage, None],
        text: str,
        *,
        reply_markup=None,
        parse_mode: Optional[str] = None,
) -> Message:
    current_message = _optional_message(message)
    if current_message is not None and _has_visual_media(current_message):
        await safe_edit_text(
            current_message,
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
        return current_message

    if current_message is not None:
        try:
            await current_message.delete()
        except TelegramBadRequest:
            pass

    return await _send_visual_message(
        bot,
        user_id,
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
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
    await _ensure_chat_menu_button(bot, user_id)

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
        sent = await _answer_visual_message(
            message,
            tasks_screen_text,
            reply_markup=tasks_menu(),
        )
        await state.update_data(**{LAST_TASK_MENU_MSG_ID_KEY: sent.message_id})
        return

    await _delete_last_task_menu(bot, user_id, state)

    await _send_start_screen(message, role_level)


@router.callback_query(F.data == "tasks")
async def show_tasks(callback: CallbackQuery, bot: Bot, state: FSMContext):
    await safe_callback_answer(callback)

    user_id = callback.from_user.id
    await _ensure_chat_menu_button(bot, user_id)
    current_message = _optional_message(callback.message)

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
    rendered = await _replace_with_visual_message(
        bot,
        user_id,
        callback.message,
        tasks_screen_text,
        reply_markup=tasks_menu(),
    )
    await state.update_data(**{LAST_TASK_MENU_MSG_ID_KEY: rendered.message_id})


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
        await _send_visual_message(
            bot,
            user_id,
            "❌ Доступных постов пока нет.",
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
        await _send_visual_message(
            bot,
            user_id,
            "❌ Не удалось открыть задание.",
            reply_markup=task_after_view_kb(),
        )
        return

    if not open_result.get("ok"):
        open_error_text = open_result.get("message") or "❌ Не удалось открыть задание."
        await _send_visual_message(
            bot,
            user_id,
            open_error_text,
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
        await _send_visual_message(
            bot,
            user_id,
            "❌ У задания нет данных поста.",
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
            await _send_visual_message(
                bot,
                user_id,
                (
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
        await _send_visual_message(
            bot,
            user_id,
            (
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
        await _send_visual_message(
            bot,
            user_id,
            "⚠️ Не удалось засчитать просмотр.\nПопробуй следующий пост.",
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
        await _send_visual_message(
            bot,
            user_id,
            (
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
        await _send_visual_message(
            bot,
            user_id,
            "✅ Этот пост уже был засчитан ранее.",
            reply_markup=task_after_view_kb(),
        )
        return

    await _send_visual_message(
        bot,
        user_id,
        f"⚠️ {message_text}",
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
    await _replace_with_visual_message(
        bot,
        user_id,
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
        summary = await get_client_cabinet_summary_via_api(callback.from_user.id)
    except ApiClientError as e:
        await _answer_user_api_error(callback, e, context="client_home.summary")
        return

    await safe_callback_answer(callback)
    await safe_edit_text(
        callback.message,
        _build_client_home_text(summary),
        reply_markup=client_home_kb(),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "client:channels")
async def client_channels(callback: CallbackQuery):
    try:
        result = await list_client_channels_via_api(callback.from_user.id)
    except ApiClientError as e:
        await _answer_user_api_error(callback, e, context="client_channels.list")
        return

    items = list(result.get("items") or [])
    await safe_callback_answer(callback)
    await safe_edit_text(
        callback.message,
        _build_client_channels_text(items),
        reply_markup=client_channels_kb(items),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data.startswith("client:channel:"))
async def client_channel_router(callback: CallbackQuery):
    parts = (callback.data or "").split(":")
    if len(parts) < 3:
        await safe_callback_answer(callback, "❌ Канал не найден.", show_alert=True)
        return

    try:
        channel_id = int(parts[2])
    except ValueError:
        await safe_callback_answer(callback, "❌ Канал не найден.", show_alert=True)
        return

    mode = parts[3] if len(parts) > 3 else "card"
    page = 0
    if mode == "posts" and len(parts) > 4:
        try:
            page = max(int(parts[4]), 0)
        except ValueError:
            await safe_callback_answer(callback, "❌ Страница не найдена.", show_alert=True)
            return
    try:
        if mode == "views":
            payload = await get_client_channel_view_stats_via_api(callback.from_user.id, channel_id)
            text = _build_client_view_stats_text(payload)
            reply_markup = client_view_stats_kb(channel_id)
        elif mode == "posts":
            payload = await get_client_channel_posts_via_api(callback.from_user.id, channel_id, limit=5, page=page)
            text = _build_client_posts_status_text(payload)
            reply_markup = client_posts_nav_kb(
                channel_id,
                int(payload.get("page") or 0),
                bool(payload.get("has_next") or False),
            )
        elif mode in {"campaigns", "subs-status"}:
            payload = await get_client_channel_subscription_campaigns_via_api(callback.from_user.id, channel_id)
            text = _build_client_campaigns_status_text(payload)
            reply_markup = client_back_kb(f"client:channel:{channel_id}:subs")
        elif mode in {"subs", "subscriptions"}:
            payload = await get_client_channel_subscription_stats_via_api(callback.from_user.id, channel_id)
            text = _build_client_subscription_stats_text(payload)
            reply_markup = client_subscription_stats_kb(channel_id)
        else:
            payload = await get_client_channel_via_api(callback.from_user.id, channel_id)
            text = _build_client_channel_text(payload["channel"])
            reply_markup = client_channel_kb(payload["channel"])
    except ApiClientError as e:
        await _answer_user_api_error(callback, e, context=f"client_channel.{mode}")
        return

    await safe_callback_answer(callback)
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "client:orders")
async def client_orders(callback: CallbackQuery):
    try:
        result = await list_client_orders_via_api(callback.from_user.id, limit=20)
    except ApiClientError as e:
        await _answer_user_api_error(callback, e, context="client_orders.list")
        return

    items = list(result.get("items") or [])
    await safe_callback_answer(callback)
    await safe_edit_text(
        callback.message,
        _build_client_orders_text(items),
        reply_markup=client_back_kb("client:home"),
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

    try:
        summary = await get_partner_cabinet_summary_via_api(callback.from_user.id)
        channels = await list_partner_channels_via_api(callback.from_user.id)
    except ApiClientError as e:
        await _answer_user_api_error(callback, e, context="partner_home")
        return

    rows = list(channels.get("items") or [])
    await safe_callback_answer(callback)
    await safe_edit_text(
        callback.message,
        _build_partner_home_text(summary),
        reply_markup=partner_home_kb(rows),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data.startswith("partner:channel:"))
async def partner_channel_router(callback: CallbackQuery):
    parts = (callback.data or "").split(":")
    if len(parts) < 3:
        await safe_callback_answer(callback, "❌ Канал партнера не найден.", show_alert=True)
        return

    chat_id = parts[2]
    mode = parts[3] if len(parts) > 3 else "card"

    try:
        if mode == "promos":
            payload = await list_partner_channel_promos_via_api(callback.from_user.id, chat_id)
            text = _build_partner_promos_text(payload)
            reply_markup = client_back_kb(f"partner:channel:{chat_id}")
        elif mode == "accruals":
            payload = await get_partner_channel_accruals_via_api(callback.from_user.id, chat_id)
            text = _build_partner_accruals_text(payload)
            reply_markup = partner_accruals_kb(chat_id)
        elif mode == "history":
            payload = await list_partner_channel_accrual_history_via_api(
                callback.from_user.id,
                chat_id,
                limit=50,
            )
            text = _build_partner_accrual_history_text(payload)
            reply_markup = client_back_kb(f"partner:channel:{chat_id}:accruals")
        else:
            payload = await get_partner_channel_via_api(callback.from_user.id, chat_id)
            text = _build_partner_channel_text(payload["channel"])
            reply_markup = partner_channel_kb(chat_id)
    except ApiClientError as e:
        await _answer_user_api_error(callback, e, context=f"partner_channel.{mode}")
        return

    await safe_callback_answer(callback)
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )
