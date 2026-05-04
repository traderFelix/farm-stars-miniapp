import io, logging
from datetime import date, timedelta
from typing import Any, Literal, Optional
from urllib.parse import urlparse

import matplotlib

from bot.api_client import (
    ApiClientError,
    add_task_channel_manual_post_via_api,
    add_campaign_winners_via_api,
    archive_campaign_via_api,
    archive_promo_via_api,
    archive_subscription_task_via_api,
    adjust_user_balance,
    add_task_channel_views_via_api,
    bind_subscription_task_client_via_api,
    bind_task_channel_client_via_api,
    clear_user_suspicious,
    create_campaign_via_api,
    create_partner_views_accrual_via_api,
    create_promo_via_api,
    create_subscription_task_via_api,
    create_task_channel_via_api,
    delete_campaign_winner_via_api,
    get_admin_ledger_page_via_api,
    get_audit_via_api,
    get_campaign_stats_via_api,
    get_campaign_via_api,
    get_campaign_winners_via_api,
    get_campaigns_summary_via_api,
    get_growth_via_api,
    get_promo_stats_via_api,
    get_promo_via_api,
    get_promos_summary_via_api,
    get_subscription_task_via_api,
    get_top_balances_via_api,
    get_withdrawal_details,
    get_task_channel_posts_via_api,
    get_task_channel_via_api,
    get_user_ledger_page,
    get_user_battle_stats,
    get_user_theft_stats,
    get_user_profile,
    get_user_risk_page,
    get_user_stats,
    list_campaigns_via_api,
    list_promos_via_api,
    list_subscription_tasks_via_api,
    list_withdrawals_queue,
    list_recent_fee_payments_via_api,
    list_task_channels_via_api,
    lookup_user,
    mark_user_suspicious,
    mark_withdrawal_paid,
    record_fee_refund_by_charge_id,
    record_withdrawal_fee_refund,
    reject_withdrawal,
    set_campaign_status_via_api,
    set_promo_status_via_api,
    set_subscription_task_status_via_api,
    set_user_role,
    toggle_task_channel_via_api,
    update_task_channel_title_via_api,
    update_task_channel_params_via_api,
)
from bot.profile_texts import format_user_profile_card

matplotlib.use("Agg")  # важно для серверов без GUI

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from aiogram.enums import ParseMode
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, TelegramObject, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import Filter, StateFilter
from aiogram.methods import RefundStarPayment
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

from shared.config import ADMIN_IDS, LEDGER_PAGE_SIZE, OWNER_ID, ROLE_ADMIN
from shared.config import OWNER_TYPE_CLIENT, OWNER_TYPE_PARTNER

from bot.handlers.user import safe_edit_text

from shared.formatting import fmt_stars

from bot.keyboards import (
    admin_menu_kb, admin_back_kb, campaigns_list_kb, campaign_manage_kb, stats_list_kb, admin_fee_refund_kb,
    campaign_created_kb, user_actions_kb, admin_withdraw_list_kb, admin_withdraw_actions_kb, campaign_delete_confirm_kb,
    admin_task_channels_kb, admin_task_channel_card_kb, admin_growth_photo_kb, promos_list_kb, promo_manage_kb,
    promo_delete_confirm_kb, promo_created_kb, promo_stats_list_kb, admin_campaigns_menu_kb, admin_promos_menu_kb,
    admin_task_channel_manual_post_confirm_kb, admin_subscription_tasks_kb, admin_subscription_task_archive_confirm_kb,
    admin_subscription_task_card_kb, admin_owner_type_kb, promo_scope_kb,
)

from bot.states import (
    CampaignCreate, PromoCreate, AddWinners, DeleteWinner, UserLookup, AdminAdjust, AdminRefundFee, PartnerViewsAccrualCreate, TaskChannelAddViews, TaskChannelBindClient, TaskChannelCreate, TaskChannelEdit, TaskChannelManualPost, SubscriptionTaskCreate, SubscriptionTaskBindClient,
)

router = Router()
fallback_router = Router()

logger = logging.getLogger(__name__)
ADMIN_API_UNAVAILABLE_TEXT = (
    "⚠️ Админка временно недоступна.\n"
    "API не отвечает, поэтому бот не может проверить админский доступ.\n"
    "Попробуй еще раз чуть позже."
)
STATIC_ADMIN_IDS = set(ADMIN_IDS)
if OWNER_ID and str(OWNER_ID).isdigit():
    STATIC_ADMIN_IDS.add(int(OWNER_ID))


def _is_myrole_command_text(text: Optional[str]) -> bool:
    normalized = (text or "").strip()
    if not normalized:
        return False

    command = normalized.split(maxsplit=1)[0].split("@", 1)[0].lower()
    return command in {"/myrole", ".myrole"}


def _is_myrole_command(message: Message) -> bool:
    return _is_myrole_command_text(message.text)


def _require_bot(bot: Optional[Bot]) -> Bot:
    if bot is None:
        raise ValueError("Bot instance is missing")
    return bot


def _is_static_admin_user(user_id: int) -> bool:
    return int(user_id) in STATIC_ADMIN_IDS


def _to_optional_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_owner_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == OWNER_TYPE_PARTNER:
        return OWNER_TYPE_PARTNER
    return OWNER_TYPE_CLIENT


def _owner_type_label(value: Any) -> str:
    return "партнер" if _normalize_owner_type(value) == OWNER_TYPE_PARTNER else "клиент"


def _owner_type_title(value: Any) -> str:
    return "Партнер" if _normalize_owner_type(value) == OWNER_TYPE_PARTNER else "Клиент"


def _owner_user_label(
        *,
        user_id: Optional[int],
        username: str,
        first_name: str,
) -> str:
    if user_id is None:
        return "не привязан"

    label = f"id:{int(user_id)}"
    if username:
        return f"@{username}"
    if first_name:
        return f"{first_name} ({label})"
    return label


def _build_partner_views_accrual_created_text(detail: dict[str, Any]) -> str:
    partner_user_id = _to_optional_int(detail.get("partner_user_id"))
    partner_label = _owner_user_label(
        user_id=partner_user_id,
        username=str(detail.get("partner_username") or "").strip(),
        first_name=str(detail.get("partner_first_name") or "").strip(),
    )
    channel_title = str(detail.get("channel_title") or "").strip()
    channel_chat_id = str(detail.get("channel_chat_id") or "").strip()
    views_promised = int(detail.get("views_promised") or 0)
    return (
        "✅ Начисление просмотров сохранено\n\n"
        f"Партнер: {partner_label}\n"
        f"Канал: {channel_title or channel_chat_id}\n"
        f"chat_id: {channel_chat_id}\n"
        f"Добавлено в доп. начисления: {views_promised}\n"
        "Дальше они будут списываться автоматически по новым постам."
    )


def _parse_task_post_reference(value: str) -> tuple[Optional[str], Optional[str], int]:
    raw = (value or "").strip()
    if raw.isdigit():
        return None, None, int(raw)

    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlparse(candidate)
    host = (parsed.netloc or "").lower()
    if host not in {"t.me", "telegram.me"}:
        raise ValueError("Нужна ссылка на пост t.me или номер поста.")

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) >= 3 and parts[0] == "c" and parts[1].isdigit() and parts[2].isdigit():
        return f"-100{parts[1]}", None, int(parts[2])

    if len(parts) >= 3 and parts[0] == "s" and parts[2].isdigit():
        return None, parts[1].lstrip("@"), int(parts[2])

    if len(parts) >= 2 and parts[1].isdigit():
        return None, parts[0].lstrip("@"), int(parts[1])

    raise ValueError("Не смог определить post_id из ссылки. Пример: https://t.me/.../123")


async def _get_channel_title_for_admin(bot: Bot, chat_id: str) -> Optional[str]:
    try:
        chat = await bot.get_chat(int(chat_id))
    except TelegramAPIError as e:
        logger.warning("Could not fetch task channel title chat_id=%s detail=%s", chat_id, e)
        return None

    title = (chat.title or "").strip()
    return title or None


async def _refresh_task_channel_title_if_missing(bot: Bot, channel: dict) -> dict:
    title = (channel.get("title") or "").strip()
    if title:
        return channel

    channel_id = _to_optional_int(channel.get("id"))
    chat_id = str(channel.get("chat_id") or "").strip()
    if channel_id is None or not chat_id:
        return channel

    refreshed_title = await _get_channel_title_for_admin(bot, chat_id)
    if not refreshed_title:
        return channel

    try:
        updated = await update_task_channel_title_via_api(
            int(channel_id),
            title=refreshed_title,
        )
    except ApiClientError as e:
        logger.warning(
            "Could not persist task channel title channel_id=%s title=%r detail=%s",
            channel_id,
            refreshed_title,
            e.detail,
        )
        return {**channel, "title": refreshed_title}

    return updated.get("channel") or {**channel, "title": refreshed_title}


async def _resolve_task_post_chat_id(
        bot: Bot,
        *,
        raw_chat_id: Optional[str],
        username: Optional[str],
        fallback_chat_id: str,
) -> tuple[str, str]:
    if raw_chat_id:
        return raw_chat_id, raw_chat_id

    if username:
        chat = await bot.get_chat(f"@{username}")
        return str(chat.id), str(chat.id)

    return fallback_chat_id, fallback_chat_id


async def _get_admin_guard_status(
        user_id: int,
        *,
        log_failure: bool,
) -> Literal["allowed", "denied", "api_unavailable"]:
    try:
        profile = await get_user_profile(user_id)
    except ApiClientError as e:
        if log_failure:
            logger.warning(
                "Admin access check failed user_id=%s status=%s path=%s detail=%s",
                user_id,
                e.status_code,
                e.path,
                e.detail,
                exc_info=True,
            )
        return "api_unavailable"

    if int(profile.get("role_level") or 0) >= ROLE_ADMIN:
        return "allowed"

    return "denied"

class AdminOnly(Filter):
    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        if not user:
            return False

        status = await _get_admin_guard_status(int(user.id), log_failure=True)
        return status == "allowed"


class AdminApiUnavailable(Filter):
    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        if not user or not _is_static_admin_user(int(user.id)):
            return False

        status = await _get_admin_guard_status(int(user.id), log_failure=False)
        return status == "api_unavailable"


router.message.filter(AdminOnly())
router.callback_query.filter(AdminOnly())
fallback_router.message.filter(AdminApiUnavailable())
fallback_router.callback_query.filter(AdminApiUnavailable())


@fallback_router.callback_query(F.data.startswith("adm:"))
async def admin_api_unavailable_callback(callback: CallbackQuery):
    await callback.answer(ADMIN_API_UNAVAILABLE_TEXT, show_alert=True)


@fallback_router.message(_is_myrole_command)
async def admin_api_unavailable_myrole(message: Message):
    await message.answer(ADMIN_API_UNAVAILABLE_TEXT)


@fallback_router.message(
    StateFilter(
        AddWinners.usernames,
        CampaignCreate.key,
        CampaignCreate.amount,
        CampaignCreate.title,
        CampaignCreate.post_url,
        PromoCreate.code,
        PromoCreate.amount,
        PromoCreate.total_uses,
        PromoCreate.title,
        DeleteWinner.username,
        UserLookup.user,
        AdminAdjust.amount,
        AdminRefundFee.waiting_manual_data,
        PartnerViewsAccrualCreate.partner_ref,
        PartnerViewsAccrualCreate.channel_chat_id,
        PartnerViewsAccrualCreate.views_promised,
        TaskChannelCreate.chat_id,
        TaskChannelCreate.client_ref,
        TaskChannelCreate.total_bought_views,
        TaskChannelCreate.views_per_post,
        TaskChannelCreate.view_seconds,
        TaskChannelAddViews.amount,
        TaskChannelBindClient.client_ref,
        TaskChannelEdit.views_per_post,
        TaskChannelEdit.view_seconds,
        TaskChannelManualPost.post_url,
        SubscriptionTaskCreate.chat_id,
        SubscriptionTaskCreate.client_ref,
        SubscriptionTaskCreate.channel_url,
        SubscriptionTaskCreate.instant_reward,
        SubscriptionTaskCreate.daily_reward_total,
        SubscriptionTaskCreate.daily_claim_days,
        SubscriptionTaskCreate.max_subscribers,
        SubscriptionTaskBindClient.client_ref,
    )
)
async def admin_api_unavailable_state_message(message: Message):
    await message.answer(ADMIN_API_UNAVAILABLE_TEXT)


def _admin_ledger_nav_kb(page: int, has_next: bool) -> InlineKeyboardMarkup:
    row = []
    if page > 0:
        row.append(
            InlineKeyboardButton(
                text="⬅ Пред",
                callback_data=f"adm:ledger_last:{page - 1}",
            )
        )
    if has_next:
        row.append(
            InlineKeyboardButton(
                text="След ➡",
                callback_data=f"adm:ledger_last:{page + 1}",
            )
        )

    keyboard = []
    if row:
        keyboard.append(row)

    keyboard.append([
        InlineKeyboardButton(text="⬅ Назад", callback_data="adm:back")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def _user_ledger_nav_kb(user_id: int, page: int, has_next: bool) -> InlineKeyboardMarkup:
    row = []
    if page > 0:
        row.append(
            InlineKeyboardButton(
                text="⬅ Пред",
                callback_data=f"adm:user:ledger:{user_id}:{page - 1}",
            )
        )
    if has_next:
        row.append(
            InlineKeyboardButton(
                text="След ➡",
                callback_data=f"adm:user:ledger:{user_id}:{page + 1}",
            )
        )

    keyboard = []
    if row:
        keyboard.append(row)

    keyboard.append([
        InlineKeyboardButton(
            text="⬅ Назад",
            callback_data=f"adm:user:details:{user_id}",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def _user_risk_nav_kb(user_id: int, page: int, has_next: bool) -> InlineKeyboardMarkup:
    row = []
    if page > 0:
        row.append(
            InlineKeyboardButton(
                text="⬅ Пред",
                callback_data=f"adm:user:risk:{user_id}:{page - 1}",
            )
        )
    if has_next:
        row.append(
            InlineKeyboardButton(
                text="След ➡",
                callback_data=f"adm:user:risk:{user_id}:{page + 1}",
            )
        )

    keyboard = []
    if row:
        keyboard.append(row)

    keyboard.append([
        InlineKeyboardButton(
            text="⬅ Назад",
            callback_data=f"adm:user:details:{user_id}",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def _task_channel_posts_nav_kb(channel_id: int, page: int, has_next: bool) -> InlineKeyboardMarkup:
    row = []
    if page > 0:
        row.append(
            InlineKeyboardButton(
                text="⬅ Пред",
                callback_data=f"adm:tch:posts:{channel_id}:{page - 1}",
            )
        )
    if has_next:
        row.append(
            InlineKeyboardButton(
                text="След ➡",
                callback_data=f"adm:tch:posts:{channel_id}:{page + 1}",
            )
        )

    keyboard = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(text="⬅ Назад к каналу", callback_data=f"adm:tch:open:{channel_id}")])
    keyboard.append([InlineKeyboardButton(text="📺 Все каналы", callback_data="adm:tch:list")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def _format_risk_meta(meta: Optional[str]) -> Optional[str]:
    normalized = (meta or "").strip()
    if not normalized:
        return None

    parts: dict[str, str] = {}
    for chunk in normalized.split(";"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        parts[key.strip()] = value.strip()

    lines: list[str] = []
    related_users = parts.get("related_users")
    if related_users:
        lines.append(f"связанные пользователи: {related_users}")

    related_referrals = parts.get("related_referrals")
    if related_referrals:
        lines.append(f"подозрительные рефералы: {related_referrals}")

    cluster_size = parts.get("cluster_size")
    if cluster_size:
        lines.append(f"размер кластера: {cluster_size}")

    session_cluster = parts.get("session_cluster")
    fingerprint_cluster = parts.get("fingerprint_cluster")
    if (session_cluster or fingerprint_cluster) and not related_referrals:
        cluster_parts: list[str] = []
        if session_cluster:
            cluster_parts.append(f"session={session_cluster}")
        if fingerprint_cluster:
            cluster_parts.append(f"fingerprint={fingerprint_cluster}")
        lines.append("кластер: " + ", ".join(cluster_parts))

    return "\n".join(lines) if lines else normalized


async def _get_user_card_text(user_id: int) -> str:
    profile = await get_user_profile(user_id)
    return format_user_profile_card(profile)


def _build_task_channel_card_text(detail: dict) -> tuple[str, bool, int, bool, bool]:
    channel = detail["channel"]
    stats = detail["stats"]
    partner_accruals = detail.get("partner_accruals") or None

    channel_id = int(channel["id"])
    title = channel.get("title") or "Без названия"
    chat_id = channel["chat_id"]
    is_active = bool(channel.get("is_active") or False)
    total_bought = int(channel.get("total_bought_views") or 0)
    views_per_post = int(channel.get("views_per_post") or 0)
    partner_views_per_post = int(channel.get("partner_views_per_post") or 0)
    allocated = int(channel.get("allocated_views") or 0)
    remaining = int(channel.get("remaining_views") or 0)
    view_seconds = int(channel.get("view_seconds") or 0)
    partner_view_seconds = int(channel.get("partner_view_seconds") or 0)
    total_posts = int(stats.get("total_posts") or 0)
    total_required = int(stats.get("total_required") or 0)
    total_current = int(stats.get("total_current") or 0)
    active_posts = int(stats.get("active_posts") or 0)
    client_user_id = _to_optional_int(channel.get("client_user_id"))
    owner_type = _normalize_owner_type(channel.get("owner_type"))
    client_username = (channel.get("client_username") or "").strip()
    client_first_name = (channel.get("client_first_name") or "").strip()

    status_text = "🟢 Включен" if is_active else "🔴 Отключен"
    client_label = _owner_user_label(
        user_id=client_user_id,
        username=client_username,
        first_name=client_first_name,
    )
    can_partner_views_accrual = client_user_id is not None
    can_add_client_views = owner_type == OWNER_TYPE_CLIENT and client_user_id is not None
    main_pool_block = ""
    if owner_type == OWNER_TYPE_CLIENT:
        main_pool_block = (
            "Покупка клиента\n"
            f"Куплено просмотров: {total_bought}\n"
            f"На один пост: {views_per_post}\n"
            f"Секунд просмотра: {view_seconds}\n"
            f"Уже распределено: {allocated}\n"
            f"Осталось распределить: {remaining}"
        )

    partner_accruals_block = ""
    if partner_accruals is not None:
        manual_views_promised = int(partner_accruals.get("views_promised") or 0)
        manual_views_delivered = int(partner_accruals.get("views_delivered") or 0)
        if (
                owner_type == OWNER_TYPE_PARTNER
                or manual_views_promised > 0
                or manual_views_delivered > 0
        ):
            manual_remaining = max(manual_views_promised - manual_views_delivered, 0)
            partner_accruals_block = (
                ("\n\n" if main_pool_block else "") +
                "Доп. партнерские начисления\n"
                f"Начислено отдельно: {manual_views_promised}\n"
                f"На один пост: {partner_views_per_post}\n"
                f"Секунд просмотра: {partner_view_seconds}\n"
                f"Уже распределено: {manual_views_delivered}\n"
                f"Осталось распределить: {manual_remaining}"
            )

    text = (
        "📺 Канал просмотров\n\n"
        f"Название: {title}\n"
        f"ID канала: {chat_id}\n"
        f"Тип: {_owner_type_label(owner_type)}\n"
        f"Пользователь: {client_label}\n"
        f"Статус: {status_text}\n\n"
        f"{main_pool_block}"
        f"{partner_accruals_block}\n\n"
        f"Постов в системе: {total_posts}\n"
        f"Активных постов: {active_posts}\n"
        f"Всего нужно просмотров по постам: {total_required}\n"
        f"Фактически набрано: {total_current}"
    )
    return text, is_active, channel_id, can_partner_views_accrual, can_add_client_views


def _build_subscription_task_card_text(detail: dict) -> tuple[str, bool, int]:
    task = detail["task"]

    task_id = int(task["id"])
    title = task.get("title") or "Без названия"
    chat_id = task["chat_id"]
    channel_url = task["channel_url"]
    is_active = bool(task.get("is_active") or False)
    instant_reward = float(task.get("instant_reward") or 0)
    daily_reward_total = float(task.get("daily_reward_total") or 0)
    daily_claim_days = int(task.get("daily_claim_days") or 0)
    total_reward = float(task.get("total_reward") or 0)
    participants = int(task.get("participants_count") or 0)
    max_subscribers = int(task.get("max_subscribers") or 0)
    active_count = int(task.get("active_count") or 0)
    completed_count = int(task.get("completed_count") or 0)
    abandoned_count = int(task.get("abandoned_count") or 0)
    client_user_id = _to_optional_int(task.get("client_user_id"))
    owner_type = _normalize_owner_type(task.get("owner_type"))
    client_username = (task.get("client_username") or "").strip()
    client_first_name = (task.get("client_first_name") or "").strip()
    status_text = "🟢 Включено" if is_active else "🔴 Отключено"
    client_label = _owner_user_label(
        user_id=client_user_id,
        username=client_username,
        first_name=client_first_name,
    )

    text = (
        "📢 Задание подписки\n\n"
        f"Название: {title}\n"
        f"ID канала: {chat_id}\n"
        f"Тип: {_owner_type_label(owner_type)}\n"
        f"Пользователь: {client_label}\n"
        f"Ссылка: {channel_url}\n"
        f"Статус: {status_text}\n\n"
        f"Награда пользователю: {fmt_stars(total_reward)}⭐\n"
        f"Сразу: {fmt_stars(instant_reward)}⭐\n"
        f"Ежедневный фонд: {fmt_stars(daily_reward_total)}⭐ / {daily_claim_days} дн.\n\n"
        f"Лимит: {participants}/{max_subscribers}\n"
        f"Активных доклеймов: {active_count}\n"
        f"Завершено: {completed_count}\n"
        f"Удалено юзерами: {abandoned_count}"
    )
    return text, is_active, task_id


def _build_campaign_card_text(detail: dict) -> tuple[str, str]:
    key = detail["campaign_key"]
    title = detail.get("title") or ""
    amount = float(detail.get("reward_amount") or 0)
    status = detail.get("status") or "draft"
    post_url = detail.get("post_url") or ""

    if status == "active":
        status_text = "🟢 Активен"
    elif status == "draft":
        status_text = "🟡 Черновик"
    elif status == "ended":
        status_text = "🔴 Завершен"
    elif status == "archived":
        status_text = "🗃 Архив"
    else:
        status_text = f"⚪ {status}"

    text = (
        f"🏷 {key}\n"
        f"📝 {title}\n"
        f"🎁 Награда: {amount}⭐\n"
        f"📌 Статус: {status_text}"
    )
    if post_url:
        text += f"\n🔗 Пост: {post_url}"
    return text, status


def _build_promo_card_text(detail: dict) -> tuple[str, str]:
    code = detail["promo_code"]
    title = detail.get("title") or "—"
    amount = float(detail.get("reward_amount") or 0)
    total_uses = int(detail.get("total_uses") or 0)
    claims_count = int(detail.get("claims_count") or 0)
    remaining_uses = int(detail.get("remaining_uses") or 0)
    status = detail.get("status") or "draft"
    partner_user_id = _to_optional_int(detail.get("partner_user_id"))
    partner_username = (detail.get("partner_username") or "").strip()
    partner_first_name = (detail.get("partner_first_name") or "").strip()
    partner_channel_chat_id = (detail.get("partner_channel_chat_id") or "").strip()
    partner_channel_title = (detail.get("partner_channel_title") or "").strip()

    if status == "active":
        status_text = "🟢 Активен"
    elif status == "draft":
        status_text = "🟡 Черновик"
    elif status == "ended":
        status_text = "🔴 Завершен"
    elif status == "archived":
        status_text = "🗃 Архив"
    else:
        status_text = f"⚪ {status}"

    scope_text = "🌐 Общий"
    partner_label = None
    channel_label = None
    if partner_user_id is not None:
        scope_text = "🤝 Партнерский"
        partner_label = _owner_user_label(
            user_id=partner_user_id,
            username=partner_username,
            first_name=partner_first_name,
        )
        if partner_channel_chat_id:
            channel_label = partner_channel_title or partner_channel_chat_id

    text = (
        f"🎟 {code}\n"
        f"📝 {title}\n"
        f"👁 Тип: {scope_text}\n"
        f"🎁 Награда: {amount:g}⭐\n"
        f"📦 Лимит активаций: {total_uses}\n"
        f"✅ Уже забрали: {claims_count}\n"
        f"🪫 Осталось: {remaining_uses}\n"
        f"📌 Статус: {status_text}"
    )
    if partner_label:
        text += f"\n👤 Партнер: {partner_label}"
    if channel_label:
        text += f"\n📺 Канал: {channel_label}"
    return text, status


def _is_valid_post_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


async def _render_campaign_card(callback: CallbackQuery, key: str):
    try:
        detail = await get_campaign_via_api(key)
    except ApiClientError as e:
        if e.status_code == 404:
            await safe_edit_text(callback.message, "❌ Конкурс не найден.", reply_markup=admin_back_kb("adm:list"))
            return

        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить конкурс из API.\n\n{e.detail}",
            reply_markup=admin_back_kb("adm:list"),
        )
        return

    text, status = _build_campaign_card_text(detail)
    await safe_edit_text(callback.message, text, reply_markup=campaign_manage_kb(key, status))


async def _render_promo_card(callback: CallbackQuery, code: str):
    try:
        detail = await get_promo_via_api(code)
    except ApiClientError as e:
        if e.status_code == 404:
            await safe_edit_text(callback.message, "❌ Промокод не найден.", reply_markup=admin_back_kb("adm:promo:list"))
            return

        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить промокод из API.\n\n{e.detail}",
            reply_markup=admin_back_kb("adm:promo:list"),
        )
        return

    text, status = _build_promo_card_text(detail)
    await safe_edit_text(callback.message, text, reply_markup=promo_manage_kb(code, status))


@router.callback_query(F.data == "adm:back")
async def adm_back(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_text(callback.message, "🛠 Админ-панель", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "adm:campaigns_menu")
async def adm_campaigns_menu(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "🏆 Раздел конкурсов",
        reply_markup=admin_campaigns_menu_kb(),
    )


@router.callback_query(F.data == "adm:partner_views:new")
async def adm_partner_views_new(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await state.set_state(PartnerViewsAccrualCreate.partner_ref)
    await safe_edit_text(
        callback.message,
        "🚀 Начисление просмотров партнеру\n\n"
        "Пришли @username или user_id партнера:",
        reply_markup=admin_back_kb("adm:back"),
    )


@router.message(PartnerViewsAccrualCreate.partner_ref)
async def adm_partner_views_partner_ref(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    if not query:
        await message.answer("❌ Нужен @username или user_id партнера")
        return

    try:
        profile = await lookup_user(query)
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    partner_user_id = int(profile["user_id"])
    partner_username = (profile.get("username") or "").strip()
    partner_name = (profile.get("first_name") or "").strip()
    partner_label = _owner_user_label(
        user_id=partner_user_id,
        username=partner_username,
        first_name=partner_name,
    )

    await state.update_data(
        partner_user_id=partner_user_id,
        partner_username=partner_username,
        partner_first_name=partner_name,
    )
    await state.set_state(PartnerViewsAccrualCreate.channel_chat_id)
    await message.answer(
        f"Партнер выбран: {partner_label}\n\n"
        "Теперь пришли chat_id канала, куда начисляем просмотры.\n"
        "Формат: -100...",
    )


@router.message(PartnerViewsAccrualCreate.channel_chat_id)
async def adm_partner_views_channel_chat_id(message: Message, state: FSMContext):
    chat_id = (message.text or "").strip()
    if not chat_id.startswith("-100"):
        await message.answer("❌ Нужен channel id в формате -100...")
        return

    title = await _get_channel_title_for_admin(_require_bot(message.bot), chat_id) if message.bot is not None else None
    await state.update_data(channel_chat_id=chat_id, channel_title=title)
    await state.set_state(PartnerViewsAccrualCreate.views_promised)
    await message.answer(
        f"Канал: {title or chat_id}\n\n"
        "Сколько просмотров добавить в доп. начисления партнеру?"
    )


@router.message(PartnerViewsAccrualCreate.views_promised)
async def adm_partner_views_views_promised(message: Message, state: FSMContext):
    try:
        views_promised = int((message.text or "").strip())
        if views_promised <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое число больше 0.")
        return

    data = await state.get_data()
    try:
        detail = await create_partner_views_accrual_via_api(
            partner_user_id=int(data["partner_user_id"]),
            channel_chat_id=str(data["channel_chat_id"]),
            channel_title=(str(data.get("channel_title") or "").strip() or None),
            views_promised=views_promised,
        )
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail or 'Не удалось сохранить начисление'}")
        return

    channel_id = _to_optional_int(data.get("channel_id"))
    await state.clear()
    await message.answer(_build_partner_views_accrual_created_text(detail))
    if channel_id is None:
        await message.answer(
            "⬅ Вернуться в админку",
            reply_markup=admin_back_kb("adm:back"),
        )
        return

    try:
        channel_detail = await get_task_channel_via_api(int(channel_id))
    except ApiClientError as e:
        await message.answer(
            f"❌ Не удалось заново загрузить канал.\n\n{e.detail}",
            reply_markup=admin_back_kb(f"adm:tch:open:{channel_id}"),
        )
        return

    text, is_active, resolved_channel_id, can_partner_views_accrual, can_add_client_views = _build_task_channel_card_text(channel_detail)
    await message.answer(
        text,
        reply_markup=admin_task_channel_card_kb(
            resolved_channel_id,
            is_active,
            can_partner_views_accrual=can_partner_views_accrual,
            can_add_client_views=can_add_client_views,
        ),
    )


@router.callback_query(F.data == "adm:promos_menu")
async def adm_promos_menu(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_text(
        callback.message,
        "🎟 Раздел промокодов",
        reply_markup=admin_promos_menu_kb(),
    )


@router.callback_query(F.data == "adm:list")
async def adm_list(callback: CallbackQuery):
    await callback.answer()

    try:
        result = await list_campaigns_via_api()
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить конкурсы из API.\n\n{e.detail}",
            reply_markup=admin_back_kb("adm:campaigns_menu"),
        )
        return

    rows = result.get("items") or []
    if not rows:
        await safe_edit_text(callback.message, "Пока нет конкурсов.", reply_markup=admin_back_kb("adm:campaigns_menu"))
        return

    await safe_edit_text(
        callback.message,
        "📋 Список всех конкурсов:",
        reply_markup=campaigns_list_kb(rows, back_callback="adm:campaigns_menu"),
    )


@router.callback_query(F.data.startswith("adm:open:"))
async def adm_open(callback: CallbackQuery):
    await callback.answer()
    key = callback.data.split(":", 2)[2]
    await _render_campaign_card(callback, key)


@router.callback_query(F.data.startswith("adm:on:"))
async def adm_on(callback: CallbackQuery):
    await callback.answer()
    key = callback.data.split(":", 2)[2]
    try:
        detail = await set_campaign_status_via_api(key, status="active")
    except ApiClientError as e:
        if e.status_code == 404:
            await safe_edit_text(callback.message, "❌ Конкурс не найден.", reply_markup=admin_back_kb("adm:list"))
            return
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось обновить статус конкурса через API.\n\n{e.detail}",
            reply_markup=admin_back_kb("adm:list"),
        )
        return

    text, status = _build_campaign_card_text(detail)
    await safe_edit_text(callback.message, text, reply_markup=campaign_manage_kb(key, status))


@router.callback_query(F.data.startswith("adm:off:"))
async def adm_off(callback: CallbackQuery):
    await callback.answer()
    key = callback.data.split(":", 2)[2]
    try:
        detail = await set_campaign_status_via_api(key, status="ended")
    except ApiClientError as e:
        if e.status_code == 404:
            await safe_edit_text(callback.message, "❌ Конкурс не найден.", reply_markup=admin_back_kb("adm:list"))
            return
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось обновить статус конкурса через API.\n\n{e.detail}",
            reply_markup=admin_back_kb("adm:list"),
        )
        return

    text, status = _build_campaign_card_text(detail)
    await safe_edit_text(callback.message, text, reply_markup=campaign_manage_kb(key, status))


@router.callback_query(F.data.startswith("adm:del:ask:"))
async def adm_delete_ask(callback: CallbackQuery):
    await callback.answer()
    key = callback.data.split(":", 3)[3]

    try:
        detail = await get_campaign_via_api(key)
    except ApiClientError as e:
        if e.status_code == 404:
            await safe_edit_text(
                callback.message,
                "❌ Конкурс не найден.",
                reply_markup=admin_back_kb("adm:list")
            )
            return
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить конкурс из API.\n\n{e.detail}",
            reply_markup=admin_back_kb("adm:list"),
        )
        return

    title = detail.get("title") or ""
    amount = float(detail.get("reward_amount") or 0)
    status = detail.get("status") or "draft"

    await safe_edit_text(
        callback.message,
        f"⚠️ Зархивировать конкурс?\n\n"
        f"KEY: {key}\n"
        f"Название: {title}\n"
        f"Награда: {amount}⭐\n"
        f"Статус: {status}\n\n"
        "Он исчезнет из списков, но клеймы, победители и леджер останутся.",
        reply_markup=campaign_delete_confirm_kb(key),
    )


@router.callback_query(F.data.startswith("adm:del:do:"))
async def adm_delete_do(callback: CallbackQuery):
    await callback.answer()
    key = callback.data.split(":", 3)[3]

    try:
        await archive_campaign_via_api(key)
    except ApiClientError as e:
        await callback.answer(f"❌ {e.detail}", show_alert=True)
        return

    await adm_list(callback)


@router.callback_query(F.data.startswith("adm:add_winners:"))
async def add_winners_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    key = callback.data.split(":")[2]
    await state.set_state(AddWinners.usernames)
    await state.update_data(campaign_key=key)

    await callback.message.answer(
        f"Введи username победителей для конкурса: {key}\n\n"
        "@username1\n"
        "@username2"
    )


@router.message(AddWinners.usernames)
async def save_winners_msg(message: Message, state: FSMContext):

    data = await state.get_data()
    key = data.get("campaign_key")
    usernames = [
        line.strip().lstrip("@")
        for line in (message.text or "").splitlines()
        if line.strip()
    ]

    try:
        result = await add_campaign_winners_via_api(key, usernames)
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    await state.clear()
    count = int(result.get("added_count") or 0)
    await message.answer(f"✅ Добавлено {count} победителей к конкурсу {key}")


@router.callback_query(F.data == "adm:new")
async def adm_new(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(CampaignCreate.key)
    await safe_edit_text(
        callback.message,
        "➕ Создание конкурса\n\nВведи KEY (например: march2026):",
        reply_markup=admin_back_kb("adm:campaigns_menu"),
    )


@router.message(CampaignCreate.key)
async def adm_new_key(message: Message, state: FSMContext):
    key = (message.text or "").strip()
    if " " in key or len(key) < 3:
        await message.answer("❌ KEY без пробелов, минимум 3 символа. Введи снова:")
        return
    await state.update_data(key=key)
    await state.set_state(CampaignCreate.amount)
    await message.answer("Теперь введи награду (число), например: 10")


@router.message(CampaignCreate.amount)
async def adm_new_amount(message: Message, state: FSMContext):
    try:
        amount = float((message.text or "").strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Нужна награда числом > 0. Пример: 10")
        return
    await state.update_data(amount=amount)
    await state.set_state(CampaignCreate.title)
    await message.answer("Теперь введи название конкурса")


@router.message(CampaignCreate.title)
async def adm_new_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title:
        await message.answer("❌ Название не может быть пустым. Введи снова:")
        return

    await state.update_data(title=title)
    await state.set_state(CampaignCreate.post_url)
    await message.answer("Теперь отправь ссылку на пост с розыгрышем, например: https://t.me/...")


@router.message(CampaignCreate.post_url)
async def adm_new_post_url(message: Message, state: FSMContext):
    post_url = (message.text or "").strip()
    if not _is_valid_post_url(post_url):
        await message.answer("❌ Нужна полная ссылка на пост. Пример: https://t.me/...")
        return

    data = await state.get_data()
    key = data["key"]
    amount = data["amount"]
    title = data["title"]

    try:
        detail = await create_campaign_via_api(
            campaign_key=key,
            title=title,
            amount=amount,
            post_url=post_url,
        )
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    await state.clear()
    final_key = detail["campaign_key"]
    final_amount = float(detail.get("reward_amount") or 0)
    final_title = detail.get("title") or ""
    final_post_url = detail.get("post_url") or ""
    post_line = f"🔗 {final_post_url}\n" if final_post_url else ""

    await message.answer(
        f"✅ Конкурс создан:\n"
        f"🏷 {final_key}\n"
        f"🎁 {final_amount}⭐\n"
        f"📝 {final_title}\n"
        f"{post_line}"
        f"Статус: 🟡 Черновик",
        reply_markup=campaign_created_kb(final_key)
    )


@router.callback_query(F.data == "adm:stats_menu")
async def adm_stats_menu(callback: CallbackQuery):
    await callback.answer()

    try:
        summary = await get_campaigns_summary_via_api(latest_limit=5)
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить статистику конкурсов из API.\n\n{e.detail}",
            reply_markup=admin_back_kb("adm:campaigns_menu"),
        )
        return

    rows = summary.get("latest_items") or []
    if not rows:
        await safe_edit_text(callback.message, "Нет конкурсов", reply_markup=admin_back_kb("adm:campaigns_menu"))
        return

    total_assigned_sum = float(summary.get("total_assigned_amount") or 0)
    claims_count_all = int(summary.get("claims_count") or 0)
    total_claimed_all = float(summary.get("total_claimed_amount") or 0)
    active_cnt = int(summary.get("active_count") or 0)
    ended_cnt = int(summary.get("ended_count") or 0)
    draft_cnt = int(summary.get("draft_count") or 0)
    unclaimed_sum = float(summary.get("unclaimed_amount") or 0)

    await safe_edit_text(
        callback.message,
        "📊 Полная статистика:\n\n"
        f"🎁 Начислено в конкурсах: {total_assigned_sum:.2f}⭐\n"
        f"📦 Невостребовано: {unclaimed_sum:.2f}⭐\n"
        f"💰 Всего заклеймили: {total_claimed_all:.2f}⭐\n ({claims_count_all} клеймов)\n"
        f"🟡 Черновиков: {draft_cnt}\n"
        f"🟢 Активных конкурсов: {active_cnt}\n"
        f"🔴 Завершенных: {ended_cnt}\n\n"
        "Последние 5 конкурсов:",
        reply_markup=stats_list_kb(rows, back_callback="adm:campaigns_menu")
    )


@router.callback_query(F.data.startswith("adm:stats:"))
async def adm_stats(callback: CallbackQuery):
    await callback.answer()

    key = callback.data.split(":")[2]

    try:
        stats = await get_campaign_stats_via_api(key)
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить статистику конкурса из API.\n\n{e.detail}",
            reply_markup=admin_back_kb("adm:stats_menu"),
        )
        return

    claims_count = int(stats.get("claims_count") or 0)
    winners_cnt = int(stats.get("winners_count") or 0)
    total_paid = float(stats.get("total_paid") or 0)
    claimed = stats.get("claimed_usernames") or []

    if claimed:
        claimed_text = "\n".join([f"@{u}" for u in claimed[:50]])
        if len(claimed) > 50:
            claimed_text += f"\n… и еще {len(claimed) - 50}"
    else:
        claimed_text = "—"

    await safe_edit_text(
        callback.message,
        f"📊 Статистика конкурса {key}\n\n"
        f"👥 Клеймов: {claims_count}/{winners_cnt}\n"
        f"⭐ Выплачено всего: {total_paid}\n\n"
        f"✅ Заклеймили:\n{claimed_text}",
        reply_markup=admin_back_kb("adm:stats_menu")
    )


@router.callback_query(F.data.startswith("adm:show_winners:"))
async def adm_show_winners(callback: CallbackQuery):
    await callback.answer()

    key = callback.data.split(":")[2]

    try:
        result = await get_campaign_winners_via_api(key)
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить победителей конкурса из API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    winners = result.get("winners") or []
    claimed = set(result.get("claimed_usernames") or [])

    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅ Назад", callback_data=f"adm:open:{key}")]
        ]
    )

    if not winners:
        text = "Победителей нет"
    else:
        lines = []
        for i, u in enumerate(winners[:50], start=1):
            mark = " ✅" if u in claimed else ""
            lines.append(f"{i}. @{u}{mark}")
        text = "\n".join(lines)

    await safe_edit_text(
        callback.message,
        f"🏆 Победители конкурса {key}:\n\n{text}",
        reply_markup=back_kb
    )


@router.callback_query(F.data == "adm:promo:list")
async def adm_promo_list(callback: CallbackQuery):
    await callback.answer()

    try:
        result = await list_promos_via_api()
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить промокоды из API.\n\n{e.detail}",
            reply_markup=admin_back_kb("adm:promos_menu"),
        )
        return

    rows = result.get("items") or []
    if not rows:
        await safe_edit_text(callback.message, "🎟 Промокодов пока нет", reply_markup=admin_back_kb("adm:promos_menu"))
        return

    await safe_edit_text(
        callback.message,
        "🎟 Список всех промокодов:",
        reply_markup=promos_list_kb(rows, back_callback="adm:promos_menu"),
    )


@router.callback_query(F.data.startswith("adm:promo:open:"))
async def adm_promo_open(callback: CallbackQuery):
    await callback.answer()
    code = callback.data.split(":")[3]
    await _render_promo_card(callback, code)


@router.callback_query(F.data.startswith("adm:promo:on:"))
async def adm_promo_on(callback: CallbackQuery):
    await callback.answer()
    code = callback.data.split(":")[3]

    try:
        detail = await set_promo_status_via_api(code, status="active")
    except ApiClientError as e:
        await callback.answer(f"❌ {e.detail}", show_alert=True)
        return

    text, status = _build_promo_card_text(detail)
    await safe_edit_text(callback.message, text, reply_markup=promo_manage_kb(code, status))


@router.callback_query(F.data.startswith("adm:promo:off:"))
async def adm_promo_off(callback: CallbackQuery):
    await callback.answer()
    code = callback.data.split(":")[3]

    try:
        detail = await set_promo_status_via_api(code, status="ended")
    except ApiClientError as e:
        await callback.answer(f"❌ {e.detail}", show_alert=True)
        return

    text, status = _build_promo_card_text(detail)
    await safe_edit_text(callback.message, text, reply_markup=promo_manage_kb(code, status))


@router.callback_query(F.data.startswith("adm:promo:del:ask:"))
async def adm_promo_delete_ask(callback: CallbackQuery):
    await callback.answer()
    code = callback.data.split(":")[4]

    try:
        detail = await get_promo_via_api(code)
    except ApiClientError as e:
        await callback.answer(f"❌ {e.detail}", show_alert=True)
        return

    text, _ = _build_promo_card_text(detail)
    await safe_edit_text(
        callback.message,
        f"{text}\n\n"
        "❓ Заархивировать этот промокод?\n\n"
        "Он исчезнет из списков, но активации и леджер останутся.",
        reply_markup=promo_delete_confirm_kb(code),
    )


@router.callback_query(F.data.startswith("adm:promo:del:do:"))
async def adm_promo_delete_do(callback: CallbackQuery):
    await callback.answer()
    code = callback.data.split(":")[4]

    try:
        await archive_promo_via_api(code)
    except ApiClientError as e:
        await callback.answer(f"❌ {e.detail}", show_alert=True)
        return

    await safe_edit_text(
        callback.message,
        f"✅ Промокод {code} отправлен в архив",
        reply_markup=admin_back_kb("adm:promos_menu"),
    )


@router.callback_query(F.data == "adm:promo:new")
async def adm_promo_new(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(PromoCreate.code)
    await safe_edit_text(
        callback.message,
        "➕ Создание промокода\n\nВведи код промокода, например: WELCOME2026",
        reply_markup=admin_back_kb("adm:promos_menu"),
    )


@router.message(PromoCreate.code)
async def adm_promo_new_code(message: Message, state: FSMContext):
    code = "".join((message.text or "").strip().upper().split())
    if len(code) < 3:
        await message.answer("❌ Код без пробелов, минимум 3 символа. Введи снова:")
        return

    try:
        await get_promo_via_api(code)
    except ApiClientError as e:
        if e.status_code != 404:
            await message.answer(f"❌ {e.detail}")
            return
    else:
        await message.answer("❌ Промокод с таким кодом уже существует. Введи другой:")
        return

    await state.update_data(code=code)
    await state.set_state(PromoCreate.amount)
    await message.answer("Теперь введи награду за один клейм, например: 0.5")


@router.message(PromoCreate.amount)
async def adm_promo_new_amount(message: Message, state: FSMContext):
    try:
        amount = float((message.text or "").strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Нужна награда числом > 0. Пример: 0.5")
        return

    await state.update_data(amount=amount)
    await state.set_state(PromoCreate.total_uses)
    await message.answer("Теперь введи количество активаций, например: 100")


@router.message(PromoCreate.total_uses)
async def adm_promo_new_total_uses(message: Message, state: FSMContext):
    try:
        total_uses = int((message.text or "").strip())
        if total_uses <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Нужна целая цифра > 0. Пример: 100")
        return

    await state.update_data(total_uses=total_uses)
    await state.set_state(PromoCreate.title)
    await message.answer("Теперь введи внутреннее название или комментарий. Если не нужно, отправь -")


async def _create_promo_from_state(
        state: FSMContext,
        *,
        partner_user_id: Optional[int] = None,
        partner_channel_chat_id: Optional[str] = None,
        partner_channel_title: Optional[str] = None,
) -> dict:
    data = await state.get_data()
    return await create_promo_via_api(
        promo_code=str(data["code"]),
        title=(data.get("title") or None),
        partner_user_id=partner_user_id,
        partner_channel_chat_id=partner_channel_chat_id,
        partner_channel_title=partner_channel_title,
        amount=float(data["amount"]),
        total_uses=int(data["total_uses"]),
    )


def _build_promo_created_message(detail: dict) -> str:
    text, _ = _build_promo_card_text(detail)
    return "✅ Промокод создан\n\n" + text


async def _handle_promo_create_error_from_callback(
        callback: CallbackQuery,
        state: FSMContext,
        e: ApiClientError,
) -> None:
    if e.status_code == 409:
        await state.set_state(PromoCreate.code)
        await safe_edit_text(
            callback.message,
            "❌ Промокод с таким кодом уже существует.\n\n"
            "Введи другой код промокода, например: WELCOME2026",
            reply_markup=admin_back_kb("adm:promos_menu"),
        )
        return

    await callback.answer(f"❌ {e.detail}", show_alert=True)


async def _handle_promo_create_error_from_message(
        message: Message,
        state: FSMContext,
        e: ApiClientError,
) -> None:
    if e.status_code == 409:
        await state.set_state(PromoCreate.code)
        await message.answer(
            "❌ Промокод с таким кодом уже существует.\n\n"
            "Введи другой код промокода, например: WELCOME2026"
        )
        return

    await message.answer(f"❌ {e.detail}")


@router.message(PromoCreate.title)
async def adm_promo_new_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if title == "-":
        title = ""

    await state.update_data(title=title or None)
    await state.set_state(PromoCreate.scope)
    await message.answer(
        "Теперь выбери тип промокода:",
        reply_markup=promo_scope_kb(),
    )


@router.callback_query(F.data == "adm:promo:scope:general")
async def adm_promo_new_scope_general(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    try:
        detail = await _create_promo_from_state(state)
    except ApiClientError as e:
        await _handle_promo_create_error_from_callback(callback, state, e)
        return

    await state.clear()
    final_code = detail["promo_code"]
    await safe_edit_text(
        callback.message,
        _build_promo_created_message(detail),
        reply_markup=promo_created_kb(final_code),
    )


@router.callback_query(F.data == "adm:promo:scope:partner")
async def adm_promo_new_scope_partner(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(PromoCreate.partner_ref)
    await safe_edit_text(
        callback.message,
        "Пришли @username или user_id партнера для этого промокода:",
        reply_markup=admin_back_kb("adm:promos_menu"),
    )


@router.message(PromoCreate.partner_ref)
async def adm_promo_new_partner_ref(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    if not query:
        await message.answer("❌ Нужен @username или user_id партнера")
        return

    try:
        profile = await lookup_user(query)
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    partner_user_id = int(profile["user_id"])
    partner_username = (profile.get("username") or "").strip()
    partner_name = (profile.get("first_name") or "").strip()
    partner_label = _owner_user_label(
        user_id=partner_user_id,
        username=partner_username,
        first_name=partner_name,
    )
    await state.update_data(partner_user_id=partner_user_id)
    await state.set_state(PromoCreate.partner_channel_chat_id)
    await message.answer(
        f"Партнер привязан: {partner_label}\n\n"
        "Теперь пришли chat_id канала партнера, к которому привязать промокод.\n"
        "Пример: -1001234567890"
    )


@router.message(PromoCreate.partner_channel_chat_id)
async def adm_promo_new_partner_channel_chat_id(message: Message, state: FSMContext):
    chat_id = (message.text or "").strip()
    if not chat_id.startswith("-100"):
        await message.answer("❌ Нужен chat_id канала в формате -100...")
        return

    bot = message.bot
    channel_title = await _get_channel_title_for_admin(bot, chat_id) if bot is not None else None
    data = await state.get_data()

    try:
        detail = await _create_promo_from_state(
            state,
            partner_user_id=int(data["partner_user_id"]),
            partner_channel_chat_id=chat_id,
            partner_channel_title=channel_title,
        )
    except ApiClientError as e:
        await _handle_promo_create_error_from_message(message, state, e)
        return

    await state.clear()
    final_code = detail["promo_code"]
    await message.answer(
        _build_promo_created_message(detail),
        reply_markup=promo_created_kb(final_code),
    )


@router.callback_query(F.data == "adm:promo:stats_menu")
async def adm_promo_stats_menu(callback: CallbackQuery):
    await callback.answer()

    try:
        summary = await get_promos_summary_via_api(latest_limit=5)
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить статистику промокодов из API.\n\n{e.detail}",
            reply_markup=admin_back_kb("adm:promos_menu"),
        )
        return

    rows = summary.get("latest_items") or []
    if not rows:
        await safe_edit_text(callback.message, "Промокодов пока нет", reply_markup=admin_back_kb("adm:promos_menu"))
        return

    total_assigned_sum = float(summary.get("total_assigned_amount") or 0)
    claims_count_all = int(summary.get("claims_count") or 0)
    total_claimed_all = float(summary.get("total_claimed_amount") or 0)
    active_cnt = int(summary.get("active_count") or 0)
    ended_cnt = int(summary.get("ended_count") or 0)
    draft_cnt = int(summary.get("draft_count") or 0)
    unclaimed_sum = float(summary.get("unclaimed_amount") or 0)

    await safe_edit_text(
        callback.message,
        "📊 Статистика промокодов:\n\n"
        f"🎁 Начислено по лимитам: {total_assigned_sum:.2f}⭐\n"
        f"📦 Невостребовано: {unclaimed_sum:.2f}⭐\n"
        f"💰 Всего заклеймили: {total_claimed_all:.2f}⭐\n ({claims_count_all} клеймов)\n"
        f"🟡 Черновиков: {draft_cnt}\n"
        f"🟢 Активных промокодов: {active_cnt}\n"
        f"🔴 Завершенных: {ended_cnt}\n\n"
        "Последние 5 промокодов:",
        reply_markup=promo_stats_list_kb(rows, back_callback="adm:promos_menu"),
    )


@router.callback_query(F.data.startswith("adm:promo:stats:"))
async def adm_promo_stats(callback: CallbackQuery):
    await callback.answer()
    code = callback.data.split(":")[3]

    try:
        stats = await get_promo_stats_via_api(code)
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить статистику промокода из API.\n\n{e.detail}",
            reply_markup=admin_back_kb("adm:promo:stats_menu"),
        )
        return

    claims_count = int(stats.get("claims_count") or 0)
    total_uses = int(stats.get("total_uses") or 0)
    remaining_uses = int(stats.get("remaining_uses") or 0)
    total_paid = float(stats.get("total_paid") or 0)
    claimed = stats.get("claimed_usernames") or []

    if claimed:
        claimed_text = "\n".join([f"@{u}" for u in claimed[:50]])
        if len(claimed) > 50:
            claimed_text += f"\n… и еще {len(claimed) - 50}"
    else:
        claimed_text = "—"

    await safe_edit_text(
        callback.message,
        f"📊 Статистика промокода {code}\n\n"
        f"👥 Клеймов: {claims_count}/{total_uses}\n"
        f"🪫 Осталось: {remaining_uses}\n"
        f"⭐ Выплачено всего: {total_paid:g}\n\n"
        f"✅ Активировали:\n{claimed_text}",
        reply_markup=admin_back_kb("adm:promo:stats_menu"),
    )


@router.callback_query(F.data == "adm:home")
async def adm_home(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_text(callback.message, "🛠 Админ-панель", reply_markup=admin_menu_kb())


@router.callback_query(F.data.startswith("adm:winner_del:"))
async def winner_del_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    key = callback.data.split(":")[2]

    await state.set_state(DeleteWinner.username)
    await state.update_data(campaign_key=key)

    await callback.message.answer(
        f"➖ Удаление победителя из конкурса {key}\n\n"
        "Введи username:"
    )


@router.message(DeleteWinner.username)
async def winner_del_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data["campaign_key"]
    username = (message.text or "").strip()

    try:
        result = await delete_campaign_winner_via_api(key, username=username)
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    await state.clear()
    ok = bool(result.get("ok"))
    msg = result.get("message") or "Неизвестная ошибка"

    if ok:
        await message.answer(f"✅ Удалил {username} из победителей конкурса {key}")
    else:
        await message.answer(f"⚠️ {msg}")


@router.callback_query(F.data == "adm:top")
async def adm_top_balances(callback: CallbackQuery):
    await callback.answer()

    try:
        result = await get_top_balances_via_api(limit=10)
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить топ из API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    rows = result.get("items") or []

    if not rows:
        text = "🏆 Топ-10 по балансу:\n\nПока нет пользователей с балансом ⭐️"
    else:
        lines = []
        for i, row in enumerate(rows, start=1):
            username = row.get("username")
            balance = float(row.get("balance") or 0)
            name = f"@{username}" if username else "(без username)"
            lines.append(f"{i}. {name} — {balance:.2f}⭐️")
        text = "🏆 Топ-10 по балансу:\n\n" + "\n".join(lines)

    await safe_edit_text(callback.message, text, reply_markup=admin_back_kb())


@router.callback_query(F.data == "adm:growth_png")
async def adm_growth_png(callback: CallbackQuery):
    await callback.answer()

    days = 30
    try:
        growth = await get_growth_via_api(days=days)
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить рост пользователей из API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    total = int(growth.get("total_users") or 0)
    new_1d = int(growth.get("new_1d") or 0)
    new_7d = int(growth.get("new_7d") or 0)
    new_30d = int(growth.get("new_30d") or 0)
    active_1d = int(growth.get("active_1d") or 0)
    active_7d = int(growth.get("active_7d") or 0)
    active_30d = int(growth.get("active_30d") or 0)
    points = growth.get("points") or []

    fig = plt.figure()
    ax = fig.add_subplot(111)

    if points:
        data = {str(point["date"]): int(point["count"] or 0) for point in points}

        xs = [(date.today() - timedelta(days=days - 1 - i)).isoformat() for i in range(days)]
        ys = [data.get(d, 0) for d in xs]

        x_positions = list(range(len(xs)))
        ax.bar(x_positions, ys)
        ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
        ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%d"))

        ax.set_ylim(bottom=0)
        tick_step = max(1, len(xs) // 15)
        tick_positions = x_positions[::tick_step]
        ax.set_xticks(tick_positions)
        ax.set_xticklabels([xs[i] for i in tick_positions], rotation=45, ha="right")
        ax.set_xlabel("Date")
        ax.set_ylabel("New users")
        ax.set_title(f"User growth (last {days} days)")
    else:
        ax.text(0.5, 0.5, "No data yet", ha="center", va="center")
        ax.set_axis_off()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)

    photo = BufferedInputFile(buf.read(), filename="growth.png")

    caption = (
        f"📈Рост пользователей\n\n"
        f"👥Всего: {total}\n\n"
        f"🆕Новые:\n"
        f"1д - {new_1d}\n"
        f"7д - {new_7d}\n"
        f"30д - {new_30d}\n\n"
        f"🔥 Активные:\n"
        f"1д - {active_1d}\n"
        f"7д - {active_7d}\n"
        f"30д - {active_30d}"
    )

    origin_message_id = callback.message.message_id

    await callback.message.answer_photo(
        photo=photo,
        caption=caption,
        reply_markup=admin_growth_photo_kb(origin_message_id),
    )


@router.callback_query(F.data.startswith("adm:ledger_last"))
async def adm_ledger_last(callback: CallbackQuery):
    await callback.answer()

    parts = (callback.data or "").split(":")
    page = 0
    if len(parts) >= 3:
        try:
            page = max(int(parts[2]), 0)
        except ValueError:
            page = 0

    try:
        result = await get_admin_ledger_page_via_api(
            page=page,
            page_size=LEDGER_PAGE_SIZE,
        )
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить леджер из API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    rows = result.get("items") or []

    if not rows and page == 0:
        await safe_edit_text(
            callback.message,
            "📜 Леджер пуст.",
            reply_markup=admin_back_kb()
        )
        return

    if not rows and page > 0:
        return

    has_next = bool(result.get("has_next") or False)

    lines = []
    start_n = page * LEDGER_PAGE_SIZE + 1

    for i, row in enumerate(rows, start=start_n):
        created_at = row["created_at"]
        username = row.get("username")
        delta = float(row.get("delta") or 0)
        reason = row["reason"]
        campaign_key = row.get("campaign_key")
        name = f"@{username}" if username else "(no-username)"
        ck = f" [{campaign_key}]" if campaign_key else ""
        lines.append(
            f"{i}. {created_at} — {name}: {delta:g}⭐ — {reason}{ck}"
        )

    await safe_edit_text(
        callback.message,
        f"📜 Леджер, страница {page + 1}:\n\n" + "\n".join(lines),
        reply_markup=_admin_ledger_nav_kb(page, has_next),
        )


@router.callback_query(F.data == "adm:user_balance")
async def adm_user_balance(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(UserLookup.user)
    await callback.message.answer("Введи username или user_id пользователя:")


@router.message(UserLookup.user)
async def adm_user_balance_show(message: Message, state: FSMContext):
    value = (message.text or "").strip()

    try:
        profile = await lookup_user(value)
        user_id = int(profile["user_id"])
        text = format_user_profile_card(profile)
    except ApiClientError as e:
        if e.status_code == 404:
            await message.answer("❌ Пользователь не найден")
            return

        await message.answer(f"❌ Не удалось загрузить профиль из API.\n\n{e.detail}")
        return


    await message.answer(
        text,
        reply_markup=user_actions_kb(user_id),
    )
    await state.clear()


@router.callback_query(F.data.startswith("adm:ub:add:"))
async def adm_user_add_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = int(callback.data.split(":")[3])

    await state.update_data(adj_user_id=user_id, adj_mode="add")
    await state.set_state(AdminAdjust.amount)

    await callback.message.answer("Введите сумму ⭐ для начисления:")


@router.callback_query(F.data.startswith("adm:ub:sub:"))
async def adm_user_sub_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = int(callback.data.split(":")[3])

    await state.update_data(adj_user_id=user_id, adj_mode="sub")
    await state.set_state(AdminAdjust.amount)

    await callback.message.answer("Введите сумму ⭐ для списания:")


@router.message(AdminAdjust.amount)
async def adm_user_adjust_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = int(data["adj_user_id"])
    mode = data["adj_mode"]

    try:
        amount = float((message.text or "").strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи число > 0, например 10")
        return

    delta = amount if mode == "add" else -amount

    try:
        result = await adjust_user_balance(
            user_id,
            amount=amount,
            mode=mode,
        )
    except ApiClientError as e:
        if e.status_code == 404:
            await message.answer("❌ Пользователь не найден")
            return
        if e.status_code == 400:
            await message.answer(f"❌ {e.detail}")
            return

        await message.answer("❌ Ошибка операции, попробуй еще раз")
        logger.exception(
            "Failed to adjust user balance via API user_id=%s mode=%s amount=%s detail=%s",
            user_id,
            mode,
            amount,
            e.detail,
        )
        return

    balance = float(result.get("balance") or 0)
    await state.clear()

    await message.answer(
        f"✅ Готово\n"
        f"Изменение: {delta:+.2f}⭐\n"
        f"Новый баланс: {fmt_stars(balance)}⭐",
        reply_markup=user_actions_kb(user_id)
    )


@router.callback_query(F.data == "adm:wd:list")
async def adm_withdraw_list(callback: CallbackQuery):
    await callback.answer()

    try:
        result = await list_withdrawals_queue(status="pending", limit=20)
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить заявки из API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    rows = result.get("items") or []

    if not rows:
        await safe_edit_text(
            callback.message,
            "✅ Нет заявок на вывод (pending).",
            reply_markup=admin_back_kb()
        )
        return

    await safe_edit_text(
        callback.message,
        "💸 Заявки на вывод (pending):",
        reply_markup=admin_withdraw_list_kb(rows)
    )


async def _render_withdraw_card(callback: CallbackQuery, wid: int):
    try:
        withdrawal = await get_withdrawal_details(wid)
    except ApiClientError as e:
        if e.status_code == 404:
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            return

        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить заявку из API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    _id = int(withdrawal["id"])
    user_id = int(withdrawal["user_id"])
    username = withdrawal.get("username")
    amount = float(withdrawal.get("amount") or 0)
    method = withdrawal.get("method")
    wallet = withdrawal.get("wallet")
    status = withdrawal.get("status")
    created_at = withdrawal.get("created_at")

    name = f"@{username}" if username else f"id:{user_id}"
    det = wallet or "—"

    await safe_edit_text(
        callback.message,
        f"💸 Заявка #{_id}\n\n"
        f"👤 {name}\n"
        f"⭐ Сумма: {float(amount):g}\n"
        f"🔧 Метод: {method}\n"
        f"🧾 Детали: {det}\n"
        f"📌 Статус: {status}\n"
        f"🕒 Создано: {created_at}",
        reply_markup=admin_withdraw_actions_kb(_id)
    )


@router.callback_query(F.data.startswith("adm:wd:open:"))
async def adm_withdraw_open(callback: CallbackQuery):
    await callback.answer()
    wid = int(callback.data.split(":")[3])
    await _render_withdraw_card(callback, wid)


@router.callback_query(F.data.startswith("adm:wd:paid:"))
async def adm_withdraw_paid(callback: CallbackQuery):
    await callback.answer()

    wid = int(callback.data.split(":")[3])
    admin_id = callback.from_user.id
    bot = _require_bot(callback.bot)

    try:
        result = await mark_withdrawal_paid(wid, admin_id=admin_id)
        withdrawal = result["withdrawal"]
        referral_bonus = result.get("referral_bonus") or {}

        user_id = int(withdrawal["user_id"])
        amount = float(withdrawal["amount"] or 0)
        method = str(withdrawal["method"])
        bonus_added = bool(referral_bonus.get("added") or False)
        referrer_id_value = _to_optional_int(referral_bonus.get("referrer_id"))
        bonus_amount = float(referral_bonus.get("amount") or 0)

        if bonus_added and referrer_id_value is not None and bonus_amount > 0:
            try:
                await bot.send_message(
                    referrer_id_value,
                    f"🎉 Ваш друг вывел {float(amount):g}⭐.\n"
                    f"Вы получили рефбек: {bonus_amount:g}⭐"
                )
            except Exception:
                logger.exception("Failed to notify referrer %s for withdrawal %s", referrer_id_value, wid)

        try:
            await bot.send_message(
                user_id,
                f"✅ Твоя заявка на вывод #{wid} выплачена.\n"
                f"Сумма: {float(amount):g}⭐\n"
                f"Метод: {str(method).upper()}"
            )
        except Exception:
            pass  # юзер мог заблокировать бота / закрыть ЛС

    except ApiClientError as e:
        await callback.answer(f"❌ {e.detail}", show_alert=True)
        return
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {type(e).__name__}: {e}", show_alert=True)
        return

    await callback.answer("✅ Отмечено как выплачено", show_alert=True)
    await _render_withdraw_card(callback, wid)


async def refund_withdraw_fee_if_needed(
        bot: Bot,
        withdrawal_id: int,
        fee_refund: dict[str, Any],
) -> tuple[bool, str]:
    refund_status = str(fee_refund.get("status") or "no_fee_paid")

    if refund_status != "ready":
        return refund_status in {"no_fee_paid", "already_refunded"}, refund_status

    user_id = int(fee_refund["user_id"])
    charge_id = fee_refund.get("charge_id")
    if not isinstance(charge_id, str) or not charge_id:
        return False, "missing_charge_id"

    ok = await bot(
        RefundStarPayment(
            user_id=user_id,
            telegram_payment_charge_id=charge_id,
        )
    )

    if not ok:
        return False, "refund_failed"

    try:
        result = await record_withdrawal_fee_refund(
            withdrawal_id,
            meta="status=rejected",
        )
    except ApiClientError:
        return False, "refund_record_failed"

    final_status = str(result.get("status") or "refund_record_failed")
    return final_status == "refunded", final_status


@router.callback_query(F.data.startswith("adm:wd:reject:"))
async def adm_withdraw_reject(callback: CallbackQuery):
    wid = int(callback.data.split(":")[3])
    admin_id = callback.from_user.id
    bot = _require_bot(callback.bot)

    try:
        result = await reject_withdrawal(wid, admin_id=admin_id)
        withdrawal = result["withdrawal"]
        fee_refund = result.get("fee_refund") or {}
        user_id = int(withdrawal["user_id"])
        amount = float(withdrawal["amount"] or 0)

        fee_refund_text = ""

        refunded, refund_status = await refund_withdraw_fee_if_needed(bot, wid, fee_refund)

        if refund_status == "refunded":
            fee_xtr = int(fee_refund.get("fee_xtr") or 0)
            fee_refund_text = f"\nКомиссия {fee_xtr}⭐ возвращена."

        elif refund_status == "refund_failed":
            fee_refund_text = "\n⚠️ Комиссию вернуть не удалось."

        elif refund_status == "refund_record_failed":
            fee_refund_text = "\n⚠️ Комиссия возвращена в Telegram, но статус возврата не записался."

        elif refund_status == "missing_charge_id":
            fee_refund_text = "\n⚠️ У комиссии нет charge_id, вернуть автоматически не удалось."

        try:
            await bot.send_message(
                int(user_id),
                f"❌ Твоя заявка на вывод #{wid} отклонена.\n"
                f"Сумма: {float(amount):g}⭐ возвращена на баланс."
                f"{fee_refund_text}"
            )
        except Exception:
            pass

    except ApiClientError as e:
        await callback.answer(f"❌ {e.detail}", show_alert=True)
        return
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {type(e).__name__}: {e}", show_alert=True)
        return

    await _render_withdraw_card(callback, wid)
    await callback.answer("✅ Отклонено и возвращено на баланс", show_alert=True)


@router.callback_query(F.data == "adm:audit")
async def adm_audit_balances(callback: CallbackQuery):
    await callback.answer()

    try:
        audit = await get_audit_via_api(limit=10)
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить сверку из API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    mismatches = audit.get("mismatches") or []
    total_balances_sum = float(audit.get("total_balances") or 0)
    total_claimed_all = float(audit.get("campaign_claimed_total") or 0)
    total_promo_claimed_all = float(audit.get("promo_claimed_total") or 0)
    admin_adjust_net = float(audit.get("admin_adjust_net") or 0)
    total_withdrawn_sum = float(audit.get("total_withdrawn") or 0)
    pending_withdrawn_sum = float(audit.get("pending_withdrawn") or 0)
    referral_bonus = float(audit.get("referral_bonus") or 0)
    view_post_bonus = float(audit.get("view_post_bonus") or 0)
    daily_bonus = float(audit.get("daily_bonus") or 0)
    subscription_bonus = float(audit.get("subscription_bonus") or 0)
    battle_bonus = float(audit.get("battle_bonus") or 0)
    battle_negative = float(audit.get("battle_negative") or 0)
    battle_positive = float(audit.get("battle_positive") or 0)
    theft_bonus = float(audit.get("theft_bonus") or 0)
    theft_negative = float(audit.get("theft_negative") or 0)
    theft_positive = float(audit.get("theft_positive") or 0)
    other_ledger_net = float(audit.get("other_ledger_net") or 0)

    def fmt_signed(value: float) -> str:
        return f"+{fmt_stars(value)}" if float(value) > 0 else fmt_stars(value)

    lines = [
        "🧮 Сверка балансов\n",
        f"Баланс пользователей: {fmt_stars(total_balances_sum)}⭐\n",
        f"Получено в конкурсах: {fmt_stars(total_claimed_all)}⭐",
        f"Получено по промокодам: {fmt_stars(total_promo_claimed_all)}⭐",
        f"Получено за рефералов: {fmt_stars(referral_bonus)}⭐\n"
        f"Получено за просмотры постов: {fmt_stars(view_post_bonus)}⭐\n"
        f"Получено за ежедневный бонус: {fmt_stars(daily_bonus)}⭐\n"
        f"Получено за подписки: {fmt_stars(subscription_bonus)}⭐\n"
        f"Результат батлов: {fmt_stars(battle_bonus)}⭐ "
        f"({fmt_signed(battle_negative)} и {fmt_signed(battle_positive)})\n"
        f"Результат воровства: {fmt_stars(theft_bonus)}⭐ "
        f"({fmt_signed(theft_negative)} и {fmt_signed(theft_positive)})\n"
        f"Получено от админа: {fmt_stars(admin_adjust_net)}⭐\n",
        f"Выведено: {fmt_stars(total_withdrawn_sum)}⭐",
        f"В обработке: {fmt_stars(pending_withdrawn_sum)}⭐\n",
    ]
    if abs(other_ledger_net) > 0.000001:
        lines.append(f"⚠️ Прочее в леджере: {fmt_stars(other_ledger_net)}⭐\n")

    if not mismatches:
        lines.append("✅ Расхождений не найдено")
    else:
        lines.append(f"⚠️ Найдено расхождений: {len(mismatches)}")
        lines.append("")
        lines.append("Первые 10:")
        for row in mismatches[:10]:
            user_id = int(row["user_id"])
            username = row.get("username")
            balance = float(row.get("users_balance") or 0)
            ledger_sum = float(row.get("ledger_sum") or 0)
            diff = float(row.get("diff") or 0)

            uname = f"@{username}" if username else "без username"

            lines.append(
                f"user_id={user_id} ({uname}): "
                f"balance={fmt_stars(balance)}⭐ / "
                f"ledger={fmt_stars(ledger_sum)}⭐ / "
                f"diff={fmt_stars(diff)}⭐"
            )

    await safe_edit_text(
        callback.message,
        "\n".join(lines),
        reply_markup=admin_back_kb(),
    )

@router.callback_query(F.data.startswith("adm:user:details:"))
async def adm_user_details(callback: CallbackQuery):
    try:
        user_id = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer("Некорректный user_id", show_alert=True)
        return

    try:
        text = await _get_user_card_text(user_id)
    except ApiClientError as e:
        text = f"❌ Не удалось загрузить профиль из API.\n\n{e.detail}"

    try:
        await safe_edit_text(
            callback.message,
            text,
            reply_markup=user_actions_kb(user_id),
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise

    await callback.answer()

@router.callback_query(F.data.startswith("adm:user:mark_susp:"))
async def adm_user_mark_susp(callback: CallbackQuery):
    try:
        user_id = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer("Некорректный user_id", show_alert=True)
        return

    try:
        profile = await mark_user_suspicious(user_id, reason="Помечен администратором")
        text = format_user_profile_card(profile)
        alert_text = "Пользователь помечен"
    except ApiClientError as e:
        text = f"❌ Не удалось обновить пользователя через API.\n\n{e.detail}"
        alert_text = "Не удалось обновить пользователя"

    await safe_edit_text(
        callback.message,
        text,
        reply_markup=user_actions_kb(user_id),
    )
    await callback.answer(alert_text)


@router.callback_query(F.data.startswith("adm:user:clear_susp:"))
async def adm_user_clear_susp(callback: CallbackQuery):
    try:
        user_id = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer("Некорректный user_id", show_alert=True)
        return

    try:
        profile = await clear_user_suspicious(user_id)
        text = format_user_profile_card(profile)
        alert_text = "Подозрение снято"
    except ApiClientError as e:
        text = f"❌ Не удалось обновить пользователя через API.\n\n{e.detail}"
        alert_text = "Не удалось обновить пользователя"

    await safe_edit_text(
        callback.message,
        text,
        reply_markup=user_actions_kb(user_id),
    )
    await callback.answer(alert_text)

@router.callback_query(F.data.startswith("adm:user:ledger:"))
async def adm_user_ledger(callback: CallbackQuery):
    parts = (callback.data or "").split(":")

    try:
        user_id = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer("Некорректный user_id", show_alert=True)
        return

    page = 0
    if len(parts) >= 5:
        try:
            page = max(int(parts[4]), 0)
        except ValueError:
            page = 0

    try:
        result = await get_user_ledger_page(
            user_id,
            page=page,
            page_size=LEDGER_PAGE_SIZE,
        )
    except ApiClientError as e:
        await callback.answer(f"❌ {e.detail}", show_alert=True)
        return

    history = result.get("items") or []

    if not history and page > 0:
        await callback.answer("Дальше записей нет")
        return

    has_next = bool(result.get("has_next") or False)

    lines = []
    start_n = page * LEDGER_PAGE_SIZE + 1

    for i, row in enumerate(history, start=start_n):
        created_at = row["created_at"]
        delta = float(row.get("delta") or 0)
        reason = row["reason"]
        campaign_key = row.get("campaign_key")
        ck = f" ({campaign_key})" if campaign_key else ""
        lines.append(f"{i}. {created_at}: {delta:g}⭐ {reason}{ck}")

    if not lines:
        lines = ["нет операций"]

    text = (
            f"📜 Операции пользователя, страница {page + 1}\n\n"
            + "\n".join(lines)
    )

    await safe_edit_text(
        callback.message,
        text,
        reply_markup=_user_ledger_nav_kb(user_id, page, has_next),
    )
    await callback.answer()

@router.callback_query(F.data.startswith("adm:user:stats:"))
async def adm_user_stats(callback: CallbackQuery):
    try:
        user_id = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer("Некорректный user_id", show_alert=True)
        return

    parse_mode: Optional[str] = None
    try:
        result = await get_user_stats(user_id)
        text = result.get("text") or "Нет данных"
        parse_mode = ParseMode.HTML
    except ApiClientError as e:
        text = f"❌ Не удалось загрузить статистику из API.\n\n{e.detail}"

    try:
        await safe_edit_text(
            callback.message,
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⬅ Назад",
                            callback_data=f"adm:user:details:{user_id}",
                        )
                    ]
                ]
            ),
            parse_mode=parse_mode,
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise

    await callback.answer()


@router.callback_query(F.data.startswith("adm:user:battles:"))
async def adm_user_battles(callback: CallbackQuery):
    try:
        user_id = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer("Некорректный user_id", show_alert=True)
        return

    try:
        result = await get_user_battle_stats(user_id)
        text = result.get("text") or "Нет данных"
    except ApiClientError as e:
        text = f"❌ Не удалось загрузить статистику батлов из API.\n\n{e.detail}"

    try:
        await safe_edit_text(
            callback.message,
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⬅ Назад",
                            callback_data=f"adm:user:details:{user_id}",
                        )
                    ]
                ]
            ),
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise

    await callback.answer()


@router.callback_query(F.data.startswith("adm:user:thefts:"))
async def adm_user_thefts(callback: CallbackQuery):
    try:
        user_id = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer("Некорректный user_id", show_alert=True)
        return

    try:
        result = await get_user_theft_stats(user_id)
        text = result.get("text") or "Нет данных"
    except ApiClientError as e:
        text = f"❌ Не удалось загрузить статистику воровства из API.\n\n{e.detail}"

    try:
        await safe_edit_text(
            callback.message,
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⬅ Назад",
                            callback_data=f"adm:user:details:{user_id}",
                        )
                    ]
                ]
            ),
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise

    await callback.answer()


@router.callback_query(F.data.startswith("adm:user:risk:"))
async def adm_user_risk(callback: CallbackQuery):
    parts = (callback.data or "").split(":")

    try:
        user_id = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer("Некорректный user_id", show_alert=True)
        return

    page = 0
    if len(parts) >= 5:
        try:
            page = max(int(parts[4]), 0)
        except ValueError:
            page = 0

    try:
        result = await get_user_risk_page(
            user_id,
            page=page,
            page_size=LEDGER_PAGE_SIZE,
        )
    except ApiClientError as e:
        await callback.answer(f"❌ {e.detail}", show_alert=True)
        return

    history = result.get("items") or []
    risk_cases = result.get("risk_cases") or []
    total_score = float(result.get("total_score") or 0)
    score_cap = float(result.get("score_cap") or 100)

    if not history and page > 0:
        await callback.answer("Дальше записей нет")
        return

    has_next = bool(result.get("has_next") or False)
    summary_lines = []
    for i, row in enumerate(risk_cases, start=1):
        source = row.get("source") or "system"
        reason = row.get("reason") or "-"
        current_score = float(row.get("current_score") or 0)
        max_score = float(row.get("max_score") or 0)
        line = f"{i}. {source}: {reason} — {current_score:g}/{max_score:g}"
        formatted_meta = _format_risk_meta(row.get("meta"))
        if formatted_meta:
            line += f"\n{formatted_meta}"
        summary_lines.append(line)

    summary_block = (
        "\n".join(summary_lines)
        if summary_lines
        else "кейсы риска не настроены"
    )

    lines = []
    start_n = page * LEDGER_PAGE_SIZE + 1

    for i, row in enumerate(history, start=start_n):
        created_at = row["created_at"]
        delta = float(row.get("delta") or 0)
        score_after = float(row.get("score_after") or 0)
        source = row.get("source") or "system"
        reason = row.get("reason") or "-"
        meta = row.get("meta")
        sign = "+" if delta >= 0 else ""
        line = (
            f"{i}. {created_at}: {sign}{delta:g} риска → {score_after:g}\n"
            f"{source}: {reason}"
        )
        formatted_meta = _format_risk_meta(meta)
        if formatted_meta:
            line += f"\n{formatted_meta}"
        lines.append(line)

    if not lines:
        lines = ["нет событий риска"]

    text = (
        f"🛡 Риск-профиль пользователя\n"
        f"Текущий риск: {total_score:g}/{score_cap:g}\n\n"
        f"Все кейсы риска:\n{summary_block}\n\n"
        f"История изменений, страница {page + 1}\n\n"
        + "\n\n".join(lines)
    )

    await safe_edit_text(
        callback.message,
        text,
        reply_markup=_user_risk_nav_kb(user_id, page, has_next),
    )
    await callback.answer()

@router.callback_query(F.data == "adm:fee_refund_menu")
async def adm_fee_refund_menu(callback: CallbackQuery):
    await callback.answer()

    try:
        result = await list_recent_fee_payments_via_api(limit=10)
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            "↩️ Возврат комиссии\n\n"
            f"Не удалось загрузить оплаты комиссии из API.\n\n{e.detail}",
            reply_markup=admin_fee_refund_kb(),
        )
        return

    rows = result.get("items") or []

    if not rows:
        await safe_edit_text(
            callback.message,
            "↩️ Возврат комиссии\n\n"
            "Пока нет последних оплат комиссии.",
            reply_markup=admin_fee_refund_kb(),
        )
        return

    lines = ["↩️ Возврат комиссии\n", "Последние 10 оплат:\n"]

    for i, row in enumerate(reversed(rows), start=1):
        withdrawal_id = row["withdrawal_id"]
        user_id = row["user_id"]
        username = row["username"]
        fee_xtr = row["fee_xtr"]
        fee_paid = int(row["fee_paid"] or 0)
        fee_refunded = int(row["fee_refunded"] or 0)
        charge_id = row["fee_telegram_charge_id"] or "-"
        created_at = row["created_at"]

        status = "возвращено" if fee_refunded else ("оплачено" if fee_paid else "не оплачено")
        uname_line = f"@{username}" if username else "без username"

        lines.append(
            f"wid={withdrawal_id} {uname_line}\n"
            f"fee={fee_xtr}⭐\n"
            f"status={status}\n"
            f"created_at={created_at}\n"
            f"<code>{user_id} {charge_id}</code>\n"
        )

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=admin_fee_refund_kb(),
    )

@router.callback_query(F.data == "adm:fee_refund_manual")
async def adm_fee_refund_manual(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminRefundFee.waiting_manual_data)

    await callback.message.answer(
        "Введи параметры для возврата в таком формате:\n\n"
        "user_id charge_id\n"
        )

@router.message(AdminRefundFee.waiting_manual_data)
async def adm_fee_refund_manual_finish(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)

    if len(parts) != 2:
        await message.answer(
            "❌ Неверный формат.\n\n"
            "Нужно так:\n"
            "user_id charge_id"
        )
        return

    user_id_raw, charge_id = parts

    try:
        user_id = int(user_id_raw)
    except ValueError:
        await message.answer("❌ user_id должен быть числом.")
        return

    try:
        ok = await message.bot(
            RefundStarPayment(
                user_id=user_id,
                telegram_payment_charge_id=charge_id,
            )
        )
    except TelegramBadRequest as e:
        await message.answer(f"❌ TelegramBadRequest: {e}")
        return
    except Exception as e:
        await message.answer(f"❌ Ошибка возврата: {type(e).__name__}: {e}")
        return

    if not ok:
        await message.answer("❌ Telegram вернул неуспешный результат.")
        return

    try:
        result = await record_fee_refund_by_charge_id(
            charge_id,
            meta="status=manual_refund",
        )
    except ApiClientError as e:
        await state.clear()
        await message.answer(
            "⚠️ Refund в Telegram выполнен, но не удалось записать его в API.\n"
            f"{e.detail}"
        )
        return

    if result.get("status") == "not_found":
        await message.answer(
            "⚠️ Refund в Telegram выполнен, но заявка по charge_id не найдена. "
            "В xtr_ledger запись не добавлена."
        )

    await state.clear()
    await message.answer(
        "✅ Комиссия успешно возвращена.\n"
        f"user_id={user_id}\n"
        f"charge_id={charge_id}"
    )


@router.callback_query(F.data == "adm:sub:list")
async def adm_subscription_tasks_list(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()

    try:
        result = await list_subscription_tasks_via_api()
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить задания подписок.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    rows = result.get("items") or []
    if not rows:
        await safe_edit_text(
            callback.message,
            "📢 Подписки\n\n"
            "Пока нет заданий подписаться на канал.",
            reply_markup=admin_subscription_tasks_kb([]),
        )
        return

    await safe_edit_text(
        callback.message,
        "📢 Подписки\n\n"
        "Выбери задание:",
        reply_markup=admin_subscription_tasks_kb(rows),
    )


@router.callback_query(F.data == "adm:sub:new")
async def adm_subscription_task_new_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await state.set_state(SubscriptionTaskCreate.chat_id)
    await safe_edit_text(
        callback.message,
        "➕ Новое задание подписки\n\n"
        "Пришли chat_id канала.\n"
        "Пример: -1001234567890\n\n"
        "Бот должен быть в канале, иначе проверка подписки не сработает.",
        reply_markup=admin_back_kb("adm:sub:list"),
    )


@router.message(SubscriptionTaskCreate.chat_id)
async def adm_subscription_task_new_chat_id(message: Message, state: FSMContext):
    chat_id = (message.text or "").strip()
    if not chat_id:
        await message.answer("❌ Нужен chat_id канала.")
        return

    bot = message.bot
    title = await _get_channel_title_for_admin(bot, chat_id) if bot is not None else None
    await state.update_data(chat_id=chat_id, title=title)
    await state.set_state(SubscriptionTaskCreate.owner_type)
    channel_label = f"Канал: {title}" if title else (
        "Название канала пока не определилось.\n"
        "Задание создадим выключенным, а при включении проверим, что бот есть в канале."
    )
    await message.answer(
        f"{channel_label}\n\n"
        "Выбери, это клиентская или партнерская подписка:",
        reply_markup=admin_owner_type_kb(
            client_callback="adm:sub:new:owner:client",
            partner_callback="adm:sub:new:owner:partner",
            back_callback="adm:sub:list",
        ),
    )


@router.callback_query(F.data.startswith("adm:sub:new:owner:"))
async def adm_subscription_task_new_owner_type(callback: CallbackQuery, state: FSMContext):
    owner_type = _normalize_owner_type((callback.data or "").rsplit(":", 1)[1])
    await callback.answer()
    await state.update_data(owner_type=owner_type)
    await state.set_state(SubscriptionTaskCreate.client_ref)
    await safe_edit_text(
        callback.message,
        f"Тип подписки выбран: {_owner_type_label(owner_type)}\n\n"
        f"Теперь пришли @username или user_id {_owner_type_label(owner_type)}.",
        reply_markup=admin_back_kb("adm:sub:list"),
    )


@router.message(SubscriptionTaskCreate.client_ref)
async def adm_subscription_task_new_client_ref(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    if not query:
        await message.answer("❌ Нужен @username или user_id пользователя")
        return

    try:
        profile = await lookup_user(query)
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    client_user_id = int(profile["user_id"])
    client_username = (profile.get("username") or "").strip()
    client_name = (profile.get("first_name") or "").strip()
    owner_type = _normalize_owner_type((await state.get_data()).get("owner_type"))
    client_label = _owner_user_label(
        user_id=client_user_id,
        username=client_username,
        first_name=client_name,
    )

    await state.update_data(client_user_id=client_user_id)
    await state.set_state(SubscriptionTaskCreate.channel_url)
    await message.answer(
        f"{_owner_type_title(owner_type)} привязан: {client_label}\n\n"
        "Теперь пришли ссылку, которую пользователь будет открывать для подписки.\n"
        "Например: https://t.me/... или invite-link."
    )


@router.message(SubscriptionTaskCreate.channel_url)
async def adm_subscription_task_new_channel_url(message: Message, state: FSMContext):
    channel_url = (message.text or "").strip()
    if not channel_url:
        await message.answer("❌ Нужна ссылка на канал.")
        return
    if channel_url.startswith("t.me/"):
        channel_url = f"https://{channel_url}"

    await state.update_data(channel_url=channel_url)
    await state.set_state(SubscriptionTaskCreate.instant_reward)
    await message.answer(
        "Сколько звезд дать сразу после проверки подписки?\n"
        "Можно 0. Пример: 1 или 0.5"
    )


@router.message(SubscriptionTaskCreate.instant_reward)
async def adm_subscription_task_new_instant_reward(message: Message, state: FSMContext):
    try:
        instant_reward = round(float((message.text or "").strip().replace(",", ".")), 2)
        if instant_reward < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи число 0 или больше.")
        return

    await state.update_data(instant_reward=instant_reward)
    await state.set_state(SubscriptionTaskCreate.daily_reward_total)
    await message.answer(
        "Сколько звезд распределить на ежедневный клейм?\n"
        "Можно 0, если награда только одноразовая."
    )


@router.message(SubscriptionTaskCreate.daily_reward_total)
async def adm_subscription_task_new_daily_reward_total(message: Message, state: FSMContext):
    try:
        daily_reward_total = round(float((message.text or "").strip().replace(",", ".")), 2)
        if daily_reward_total < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи число 0 или больше.")
        return

    await state.update_data(daily_reward_total=daily_reward_total)
    await state.set_state(SubscriptionTaskCreate.daily_claim_days)
    await message.answer(
        "На сколько дней растянуть ежедневный клейм?\n"
        "Если ежедневный фонд 0, введи 0."
    )


@router.message(SubscriptionTaskCreate.daily_claim_days)
async def adm_subscription_task_new_daily_claim_days(message: Message, state: FSMContext):
    try:
        daily_claim_days = int((message.text or "").strip())
        if daily_claim_days < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое число 0 или больше.")
        return

    await state.update_data(daily_claim_days=daily_claim_days)
    await state.set_state(SubscriptionTaskCreate.max_subscribers)
    await message.answer("Теперь введи лимит подписчиков для задания. Пример: 120")


@router.message(SubscriptionTaskCreate.max_subscribers)
async def adm_subscription_task_new_max_subscribers(message: Message, state: FSMContext):
    try:
        max_subscribers = int((message.text or "").strip())
        if max_subscribers <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое число больше 0.")
        return

    data = await state.get_data()
    instant_reward = float(data.get("instant_reward") or 0)
    daily_reward_total = float(data.get("daily_reward_total") or 0)
    if instant_reward <= 0 and daily_reward_total <= 0:
        await message.answer("❌ Нельзя создать задание с нулевой наградой. Вернись и укажи награду.")
        return

    try:
        detail = await create_subscription_task_via_api(
            chat_id=str(data["chat_id"]),
            title=data.get("title"),
            client_user_id=_to_optional_int(data.get("client_user_id")),
            owner_type=_normalize_owner_type(data.get("owner_type")),
            channel_url=str(data["channel_url"]),
            instant_reward=instant_reward,
            daily_reward_total=daily_reward_total,
            daily_claim_days=int(data.get("daily_claim_days") or 0),
            max_subscribers=max_subscribers,
        )
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    await state.clear()
    text, is_active, task_id = _build_subscription_task_card_text(detail)
    await message.answer(
        "✅ Задание подписки создано\n\n" + text,
        reply_markup=admin_subscription_task_card_kb(task_id, is_active),
    )


@router.callback_query(F.data.startswith("adm:sub:open:"))
async def adm_subscription_task_open(callback: CallbackQuery):
    await callback.answer()
    task_id = int((callback.data or "").rsplit(":", 1)[1])

    try:
        detail = await get_subscription_task_via_api(task_id)
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось открыть задание подписки.\n\n{e.detail}",
            reply_markup=admin_subscription_tasks_kb([]),
        )
        return

    text, is_active, resolved_task_id = _build_subscription_task_card_text(detail)
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=admin_subscription_task_card_kb(resolved_task_id, is_active),
    )


@router.callback_query(F.data.startswith("adm:sub:toggle:"))
async def adm_subscription_task_toggle(callback: CallbackQuery):
    await callback.answer()
    parts = (callback.data or "").split(":")
    task_id = int(parts[3])
    next_active = bool(int(parts[4]))

    try:
        detail = await set_subscription_task_status_via_api(task_id, is_active=next_active)
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось обновить задание подписки.\n\n{e.detail}",
            reply_markup=admin_subscription_tasks_kb([]),
        )
        return

    text, is_active, resolved_task_id = _build_subscription_task_card_text(detail)
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=admin_subscription_task_card_kb(resolved_task_id, is_active),
    )


@router.callback_query(F.data.startswith("adm:sub:client:"))
async def adm_subscription_task_bind_client_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    task_id = int((callback.data or "").rsplit(":", 1)[1])

    try:
        detail = await get_subscription_task_via_api(task_id)
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось открыть задание подписки.\n\n{e.detail}",
            reply_markup=admin_subscription_tasks_kb([]),
        )
        return

    await state.clear()
    await state.update_data(subscription_task_id=task_id)
    text, _, _ = _build_subscription_task_card_text(detail)
    await state.set_state(SubscriptionTaskBindClient.owner_type)
    await safe_edit_text(
        callback.message,
        f"{text}\n\nВыбери, это клиент или партнер:",
        reply_markup=admin_owner_type_kb(
            client_callback=f"adm:sub:bind_owner:{task_id}:client",
            partner_callback=f"adm:sub:bind_owner:{task_id}:partner",
            back_callback=f"adm:sub:open:{task_id}",
        ),
    )


@router.callback_query(F.data.startswith("adm:sub:bind_owner:"))
async def adm_subscription_task_bind_owner_type(callback: CallbackQuery, state: FSMContext):
    parts = (callback.data or "").split(":")
    task_id = int(parts[3])
    owner_type = _normalize_owner_type(parts[4] if len(parts) > 4 else OWNER_TYPE_CLIENT)
    await callback.answer()
    await state.update_data(subscription_task_id=task_id, owner_type=owner_type)
    await state.set_state(SubscriptionTaskBindClient.client_ref)
    await safe_edit_text(
        callback.message,
        f"Пришли @username или user_id {_owner_type_label(owner_type)} для этого задания:",
        reply_markup=admin_back_kb(f"adm:sub:open:{task_id}"),
    )


@router.message(SubscriptionTaskBindClient.client_ref)
async def adm_subscription_task_bind_client_value(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = _to_optional_int(data.get("subscription_task_id"))
    if task_id is None:
        await state.clear()
        await message.answer("❌ Не удалось определить задание, открой его заново.")
        return

    query = (message.text or "").strip()
    if not query:
        await message.answer("❌ Нужен @username или user_id пользователя")
        return

    try:
        profile = await lookup_user(query)
        owner_type = _normalize_owner_type(data.get("owner_type"))
        detail = await bind_subscription_task_client_via_api(
            int(task_id),
            client_user_id=int(profile["user_id"]),
            owner_type=owner_type,
        )
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    await state.clear()
    text, is_active, resolved_task_id = _build_subscription_task_card_text(detail)
    await message.answer(
        f"✅ {_owner_type_title(owner_type)} привязан к подписке\n\n" + text,
        reply_markup=admin_subscription_task_card_kb(resolved_task_id, is_active),
    )


@router.callback_query(F.data.startswith("adm:sub:archive:ask:"))
async def adm_subscription_task_archive_ask(callback: CallbackQuery):
    await callback.answer()
    task_id = int((callback.data or "").rsplit(":", 1)[1])

    try:
        detail = await get_subscription_task_via_api(task_id)
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось открыть задание подписки.\n\n{e.detail}",
            reply_markup=admin_subscription_tasks_kb([]),
        )
        return

    text, _, resolved_task_id = _build_subscription_task_card_text(detail)
    await safe_edit_text(
        callback.message,
        f"{text}\n\n"
        "⚠️ Заархивировать это задание подписки?\n\n"
        "Оно исчезнет из админского списка и новых заданий для пользователей. "
        "Те, кто уже вошел в задание, смогут доклеймить ежедневные награды.",
        reply_markup=admin_subscription_task_archive_confirm_kb(resolved_task_id),
    )


@router.callback_query(F.data.startswith("adm:sub:archive:do:"))
async def adm_subscription_task_archive_do(callback: CallbackQuery):
    await callback.answer()
    task_id = int((callback.data or "").rsplit(":", 1)[1])

    try:
        await archive_subscription_task_via_api(task_id)
        result = await list_subscription_tasks_via_api()
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось заархивировать задание подписки.\n\n{e.detail}",
            reply_markup=admin_subscription_tasks_kb([]),
        )
        return

    rows = result.get("items") or []
    if not rows:
        await safe_edit_text(
            callback.message,
            "✅ Задание подписки отправлено в архив.\n\n"
            "📢 Подписки\n\n"
            "Пока нет заданий подписаться на канал.",
            reply_markup=admin_subscription_tasks_kb([]),
        )
        return

    await safe_edit_text(
        callback.message,
        "✅ Задание подписки отправлено в архив.\n\n"
        "📢 Подписки\n\n"
        "Выбери задание:",
        reply_markup=admin_subscription_tasks_kb(rows),
    )


async def _render_task_channel_card(callback: CallbackQuery, channel_id: int):
    try:
        detail = await get_task_channel_via_api(channel_id)
    except ApiClientError as e:
        if e.status_code == 404:
            await safe_edit_text(callback.message, "❌ Канал не найден.", reply_markup=admin_back_kb())
            return

        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить канал из API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    bot = callback.bot
    if bot is not None:
        detail = {
            **detail,
            "channel": await _refresh_task_channel_title_if_missing(bot, detail["channel"]),
        }

    text, is_active, resolved_channel_id, can_partner_views_accrual, can_add_client_views = _build_task_channel_card_text(detail)
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=admin_task_channel_card_kb(
            resolved_channel_id,
            is_active,
            can_partner_views_accrual=can_partner_views_accrual,
            can_add_client_views=can_add_client_views,
        ),
    )

@router.callback_query(F.data == "adm:tch:list")
async def adm_task_channels_list(callback: CallbackQuery):
    await callback.answer()

    try:
        result = await list_task_channels_via_api()
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить каналы из API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    rows = result.get("items") or []
    bot = callback.bot
    if rows and bot is not None:
        rows = [
            await _refresh_task_channel_title_if_missing(bot, row)
            for row in rows
        ]

    if not rows:
        await safe_edit_text(
            callback.message,
            "📺 Каналы просмотров\n\n"
            "Пока нет подключенных каналов.",
            reply_markup=admin_task_channels_kb([]),
        )
        return

    await safe_edit_text(
        callback.message,
        "📺 Каналы просмотров\n\n"
        "Выбери канал:",
        reply_markup=admin_task_channels_kb(rows),
    )


@router.callback_query(F.data == "adm:tch:new")
async def adm_task_channel_new_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(TaskChannelCreate.chat_id)
    await safe_edit_text(
        callback.message,
        "➕ Подключение канала\n\n"
        "Пришли chat_id канала.\n"
        "Пример: -1001234567890",
        reply_markup=admin_back_kb(),
    )


@router.message(TaskChannelCreate.chat_id)
async def adm_task_channel_new_chat_id(message: Message, state: FSMContext):
    chat_id = (message.text or "").strip()

    if not chat_id.startswith("-100"):
        await message.answer("❌ Нужен channel id в формате -100...")
        return

    await state.update_data(chat_id=chat_id)
    await state.set_state(TaskChannelCreate.owner_type)
    await message.answer(
        "Выбери, кому принадлежит этот канал:",
        reply_markup=admin_owner_type_kb(
            client_callback="adm:tch:new:owner:client",
            partner_callback="adm:tch:new:owner:partner",
            back_callback="adm:tch:list",
        ),
    )


@router.callback_query(F.data.startswith("adm:tch:new:owner:"))
async def adm_task_channel_new_owner_type(callback: CallbackQuery, state: FSMContext):
    owner_type = _normalize_owner_type((callback.data or "").rsplit(":", 1)[1])
    await callback.answer()
    await state.update_data(owner_type=owner_type)
    await state.set_state(TaskChannelCreate.client_ref)
    await safe_edit_text(
        callback.message,
        f"Тип выбран: {_owner_type_label(owner_type)}\n\n"
        f"Теперь пришли @username или user_id {_owner_type_label(owner_type)}.",
        reply_markup=admin_back_kb("adm:tch:list"),
    )


@router.message(TaskChannelCreate.client_ref)
async def adm_task_channel_new_client_ref(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    if not query:
        await message.answer("❌ Нужен @username или user_id пользователя")
        return

    try:
        profile = await lookup_user(query)
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    data = await state.get_data()
    owner_type = _normalize_owner_type(data.get("owner_type"))
    client_user_id = int(profile["user_id"])
    client_username = (profile.get("username") or "").strip()
    client_name = (profile.get("first_name") or "").strip()
    client_label = _owner_user_label(
        user_id=client_user_id,
        username=client_username,
        first_name=client_name,
    )

    await state.update_data(client_user_id=client_user_id)
    if owner_type == OWNER_TYPE_PARTNER:
        await state.update_data(total_bought_views=0)
        await state.set_state(TaskChannelCreate.views_per_post)
        await message.answer(
            f"{_owner_type_title(owner_type)} привязан: {client_label}\n\n"
            "Теперь введи, сколько просмотров выделять на 1 пост из доп. начислений:"
        )
        return

    await state.set_state(TaskChannelCreate.total_bought_views)
    await message.answer(
        f"{_owner_type_title(owner_type)} привязан: {client_label}\n\n"
        "Теперь введи, сколько просмотров куплено всего для этого канала:"
    )


@router.message(TaskChannelCreate.total_bought_views)
async def adm_task_channel_new_total_views(message: Message, state: FSMContext):
    try:
        total_bought_views = int((message.text or "").strip())
        if total_bought_views <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое число больше 0.")
        return

    await state.update_data(total_bought_views=total_bought_views)
    await state.set_state(TaskChannelCreate.views_per_post)
    await message.answer("Теперь введи, сколько просмотров выделять на 1 пост:")


@router.message(TaskChannelCreate.views_per_post)
async def adm_task_channel_new_views_per_post(message: Message, state: FSMContext):
    try:
        views_per_post = int((message.text or "").strip())
        if views_per_post <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое число больше 0.")
        return

    data = await state.get_data()
    owner_type = _normalize_owner_type(data.get("owner_type"))
    total_bought_views = int(data["total_bought_views"])

    if owner_type == OWNER_TYPE_CLIENT and views_per_post > total_bought_views:
        await message.answer("❌ Просмотров на 1 пост не может быть больше общего лимита.")
        return

    await state.update_data(views_per_post=views_per_post)
    await state.set_state(TaskChannelCreate.view_seconds)
    await message.answer("Теперь введи, сколько секунд держать пост перед засчитыванием просмотра:")


@router.callback_query(F.data.startswith("adm:tch:open:"))
async def adm_task_channel_open(callback: CallbackQuery):
    await callback.answer()
    channel_id = int(callback.data.split(":")[3])
    await _render_task_channel_card(callback, channel_id)


@router.callback_query(F.data.startswith("adm:tch:toggle:"))
async def adm_task_channel_toggle(callback: CallbackQuery):
    await callback.answer()
    channel_id = int(callback.data.split(":")[3])

    try:
        detail = await toggle_task_channel_via_api(channel_id)
    except ApiClientError as e:
        if e.status_code == 404:
            await safe_edit_text(callback.message, "❌ Канал не найден.", reply_markup=admin_back_kb())
            return

        await safe_edit_text(
            callback.message,
            f"❌ Не удалось обновить канал через API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    text, is_active, resolved_channel_id, can_partner_views_accrual, can_add_client_views = _build_task_channel_card_text(detail)
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=admin_task_channel_card_kb(
            resolved_channel_id,
            is_active,
            can_partner_views_accrual=can_partner_views_accrual,
            can_add_client_views=can_add_client_views,
        ),
    )


@router.callback_query(F.data.startswith("adm:tch:edit:"))
async def adm_task_channel_edit_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    channel_id = int(callback.data.split(":")[3])

    try:
        detail = await get_task_channel_via_api(channel_id)
    except ApiClientError as e:
        if e.status_code == 404:
            await safe_edit_text(callback.message, "❌ Канал не найден.", reply_markup=admin_back_kb())
            return
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить канал из API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    channel = detail["channel"]
    owner_type = _normalize_owner_type(channel.get("owner_type"))
    await state.clear()
    choice_keyboard = []
    if owner_type == OWNER_TYPE_CLIENT:
        choice_keyboard.append([InlineKeyboardButton(
            text="💰 Параметры покупки клиента",
            callback_data=f"adm:tch:edit_pool:{channel_id}:main",
        )])
    if owner_type == OWNER_TYPE_PARTNER or _to_optional_int(channel.get("client_user_id")) is not None:
        choice_keyboard.append([InlineKeyboardButton(
            text="🚀 Параметры доп. начислений",
            callback_data=f"adm:tch:edit_pool:{channel_id}:partner",
        )])

    await safe_edit_text(
        callback.message,
        "⚙️ Редактирование параметров канала\n\n"
        f"Канал: {(channel.get('title') or channel['chat_id'])}\n"
        "Выбери, для какого пула нужно изменить параметры:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                *choice_keyboard,
                [InlineKeyboardButton(text="⬅ Назад", callback_data=f"adm:tch:open:{channel_id}")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("adm:tch:edit_pool:"))
async def adm_task_channel_edit_pool_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = (callback.data or "").split(":")
    channel_id = int(parts[3])
    edit_pool = str(parts[4] if len(parts) > 4 else "").strip().lower()
    if edit_pool not in {"main", "partner"}:
        await safe_edit_text(
            callback.message,
            "❌ Не удалось определить пул для редактирования.",
            reply_markup=admin_back_kb(f"adm:tch:open:{channel_id}"),
        )
        return

    try:
        detail = await get_task_channel_via_api(channel_id)
    except ApiClientError as e:
        if e.status_code == 404:
            await safe_edit_text(callback.message, "❌ Канал не найден.", reply_markup=admin_back_kb())
            return
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить канал из API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    channel = detail["channel"]
    partner_accruals = detail.get("partner_accruals") or {}
    owner_type = _normalize_owner_type(channel.get("owner_type"))
    has_bound_user = _to_optional_int(channel.get("client_user_id")) is not None
    if edit_pool == "partner" and not has_bound_user:
        await safe_edit_text(
            callback.message,
            "❌ Сначала привяжи пользователя к каналу, чтобы настраивать партнерский пул.",
            reply_markup=admin_back_kb(f"adm:tch:open:{channel_id}"),
        )
        return

    total_bought_views = int(channel.get("total_bought_views") or 0)
    partner_views_promised = int(partner_accruals.get("views_promised") or 0)
    if edit_pool == "partner":
        pool_title = "доп. партнерских начислений"
        current_views_per_post = int(channel.get("partner_views_per_post") or 0)
        current_view_seconds = int(channel.get("partner_view_seconds") or 0)
        pool_total_limit = partner_views_promised
        total_label = "Сейчас начислено отдельно"
    else:
        pool_title = "покупки клиента"
        current_views_per_post = int(channel.get("views_per_post") or 0)
        current_view_seconds = int(channel.get("view_seconds") or 0)
        pool_total_limit = total_bought_views
        total_label = "Сейчас куплено просмотров"

    await state.set_state(TaskChannelEdit.views_per_post)
    await state.update_data(
        channel_id=channel_id,
        total_bought_views=total_bought_views,
        edit_pool=edit_pool,
        edit_pool_title=pool_title,
        pool_total_limit=pool_total_limit,
    )
    await safe_edit_text(
        callback.message,
        "⚙️ Редактирование параметров канала\n\n"
        f"Канал: {(channel.get('title') or channel['chat_id'])}\n"
        f"Пул: {pool_title}\n"
        f"{total_label}: {pool_total_limit if edit_pool == 'partner' else total_bought_views}\n"
        f"Сейчас просмотров на 1 пост: {current_views_per_post}\n"
        f"Сейчас секунд просмотра: {current_view_seconds}\n\n"
        "Объём здесь не меняется.\n"
        "Для этого используй кнопку «Добавить лимит» и выбери нужное направление.\n\n"
        "Теперь введи новое количество просмотров на 1 пост:",
        reply_markup=admin_back_kb(f"adm:tch:open:{channel_id}"),
    )


@router.callback_query(F.data.startswith("adm:tch:credit_views:"))
async def adm_task_channel_credit_views_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    channel_id = int(callback.data.split(":")[3])

    try:
        detail = await get_task_channel_via_api(channel_id)
    except ApiClientError as e:
        if e.status_code == 404:
            await safe_edit_text(callback.message, "❌ Канал не найден.", reply_markup=admin_back_kb())
            return
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить канал из API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    channel = detail["channel"]
    client_user_id = _to_optional_int(channel.get("client_user_id"))
    owner_type = _normalize_owner_type(channel.get("owner_type"))
    if client_user_id is None:
        await safe_edit_text(
            callback.message,
            "❌ Сначала привяжи пользователя к этому каналу, чтобы зачислять просмотры без ручного ввода.",
            reply_markup=admin_back_kb(f"adm:tch:open:{channel_id}"),
        )
        return

    owner_label = _owner_user_label(
        user_id=client_user_id,
        username=(channel.get("client_username") or "").strip(),
        first_name=(channel.get("client_first_name") or "").strip(),
    )
    await state.clear()
    await state.update_data(
        channel_id=channel_id,
        channel_owner_type=owner_type,
        channel_user_id=client_user_id,
        channel_username=(channel.get("client_username") or "").strip(),
        channel_first_name=(channel.get("client_first_name") or "").strip(),
        channel_title=(channel.get("title") or "").strip(),
        channel_chat_id=str(channel["chat_id"]),
    )
    choice_keyboard = [
        [InlineKeyboardButton(text="💰 В покупку клиенту", callback_data=f"adm:tch:credit_target:{channel_id}:client")]
    ]
    if owner_type == OWNER_TYPE_CLIENT:
        choice_keyboard.append([InlineKeyboardButton(text="🚀 В начисление партнеру", callback_data=f"adm:tch:credit_target:{channel_id}:partner")])
    else:
        choice_keyboard = [
            [InlineKeyboardButton(text="🚀 В начисление партнеру", callback_data=f"adm:tch:credit_target:{channel_id}:partner")]
        ]
    await safe_edit_text(
        callback.message,
        "➕ Добавить лимит\n\n"
        f"Пользователь: {owner_label}\n"
        f"Канал: {(channel.get('title') or channel['chat_id'])}\n\n"
        "Куда добавить просмотры?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                *choice_keyboard,
                [InlineKeyboardButton(text="⬅ Назад", callback_data=f"adm:tch:open:{channel_id}")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("adm:tch:credit_target:"))
async def adm_task_channel_credit_views_target(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    parts = (callback.data or "").split(":")
    channel_id = int(parts[3])
    target = str(parts[4] if len(parts) > 4 else "").strip().lower()
    if target not in {"client", "partner"}:
        await safe_edit_text(
            callback.message,
            "❌ Не удалось определить тип зачисления.",
            reply_markup=admin_back_kb(f"adm:tch:open:{channel_id}"),
        )
        return

    data = await state.get_data()
    owner_type = _normalize_owner_type(data.get("channel_owner_type"))
    if target == "client" and owner_type != OWNER_TYPE_CLIENT:
        await safe_edit_text(
            callback.message,
            "❌ В покупку клиента можно зачислить только на клиентский канал.",
            reply_markup=admin_back_kb(f"adm:tch:open:{channel_id}"),
        )
        return

    await state.update_data(credit_target=target)
    await state.set_state(TaskChannelAddViews.amount)
    prompt = (
        "Сколько просмотров добавить в покупку клиента?"
        if target == "client"
        else "Сколько просмотров добавить в доп. начисления партнеру?"
    )
    await safe_edit_text(
        callback.message,
        "➕ Добавить лимит\n\n"
        f"Канал: {(data.get('channel_title') or data.get('channel_chat_id'))}\n"
        f"Направление: {'покупка клиента' if target == 'client' else 'доп. начисления партнеру'}\n\n"
        f"{prompt}",
        reply_markup=admin_back_kb(f"adm:tch:open:{channel_id}"),
    )


@router.message(TaskChannelAddViews.amount)
async def adm_task_channel_add_views_amount(message: Message, state: FSMContext):
    try:
        amount = int((message.text or "").strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое число больше 0.")
        return

    data = await state.get_data()
    channel_id = int(data["channel_id"])
    credit_target = str(data.get("credit_target") or "").strip().lower()

    try:
        if credit_target == "partner":
            await create_partner_views_accrual_via_api(
                partner_user_id=int(data["channel_user_id"]),
                channel_chat_id=str(data["channel_chat_id"]),
                channel_title=(str(data.get("channel_title") or "").strip() or None),
                views_promised=amount,
            )
            detail = await get_task_channel_via_api(channel_id)
        else:
            detail = await add_task_channel_views_via_api(channel_id, amount=amount)
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    await state.clear()
    text, is_active, resolved_channel_id, can_partner_views_accrual, can_add_client_views = _build_task_channel_card_text(detail)
    success_text = (
        f"✅ Просмотры добавлены в доп. начисления партнеру: {amount}\n\n"
        if credit_target == "partner"
        else f"✅ Просмотры добавлены в покупку клиента: {amount}\n\n"
    )
    await message.answer(
        success_text + text,
        reply_markup=admin_task_channel_card_kb(
            resolved_channel_id,
            is_active,
            can_partner_views_accrual=can_partner_views_accrual,
            can_add_client_views=can_add_client_views,
        ),
    )

@router.message(TaskChannelEdit.views_per_post)
async def adm_task_channel_edit_views_per_post(message: Message, state: FSMContext):
    try:
        views_per_post = int((message.text or "").strip())
        if views_per_post <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое число больше 0.")
        return

    data = await state.get_data()
    pool_total_limit = int(data.get("pool_total_limit") or 0)
    pool_title = str(data.get("edit_pool_title") or "выбранного пула")

    if pool_total_limit > 0 and views_per_post > pool_total_limit:
        await message.answer(
            f"❌ Просмотров на 1 пост не может быть больше, чем весь объём {pool_title}."
        )
        return

    await state.update_data(views_per_post=views_per_post)
    await state.set_state(TaskChannelEdit.view_seconds)
    await message.answer("Теперь введи новое количество секунд просмотра:")


@router.callback_query(F.data.startswith("adm:tch:manual_post_start:"))
async def adm_task_channel_manual_post_start(callback: CallbackQuery, state: FSMContext):
    data = callback.data or ""
    await callback.answer()
    channel_id = int(data.rsplit(":", 1)[1])

    try:
        detail = await get_task_channel_via_api(channel_id)
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить канал из API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    channel = detail["channel"]
    title = channel.get("title") or channel["chat_id"]

    await state.clear()
    await state.update_data(channel_id=channel_id)
    await state.set_state(TaskChannelManualPost.post_url)
    await safe_edit_text(
        callback.message,
        "➕ Добавить пост вручную\n\n"
        f"Канал: {title}\n\n"
        "Пришли ссылку на пост:\n"
        "https://t.me/.../123\n\n"
        "Для приватного канала можно так:\n"
        "https://t.me/c/1234567890/123\n\n"
        "Если пост из этого же канала, можно просто прислать номер поста.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅ Назад к каналу", callback_data=f"adm:tch:manual_post:cancel:{channel_id}")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("adm:tch:manual_post:cancel:"))
async def adm_task_channel_manual_post_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Отменено")
    channel_id = int((callback.data or "").rsplit(":", 1)[1])
    await state.clear()
    await _render_task_channel_card(callback, channel_id)


@router.message(TaskChannelManualPost.post_url)
async def adm_task_channel_manual_post_link(message: Message, bot: Bot, state: FSMContext):
    data = await state.get_data()
    channel_id = _to_optional_int(data.get("channel_id"))
    if channel_id is None:
        await state.clear()
        await message.answer("❌ Не удалось определить канал, открой его заново.")
        return

    try:
        detail = await get_task_channel_via_api(channel_id)
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    channel = detail["channel"]
    selected_chat_id = str(channel["chat_id"])
    try:
        raw_chat_id, username, channel_post_id = _parse_task_post_reference(message.text or "")
        resolved_chat_id, copy_from_chat_id = await _resolve_task_post_chat_id(
            bot,
            raw_chat_id=raw_chat_id,
            username=username,
            fallback_chat_id=selected_chat_id,
        )
    except (ValueError, TelegramAPIError) as e:
        await message.answer(f"❌ {e}")
        return

    if str(resolved_chat_id) != selected_chat_id:
        await message.answer(
            "❌ Эта ссылка ведет на другой канал.\n\n"
            f"Выбранный канал: {selected_chat_id}\n"
            f"Канал из ссылки: {resolved_chat_id}"
        )
        return

    try:
        await bot.copy_message(
            chat_id=message.chat.id,
            from_chat_id=int(copy_from_chat_id),
            message_id=int(channel_post_id),
        )
    except TelegramAPIError as e:
        await message.answer(
            "❌ Не удалось показать пост.\n"
            "Проверь, что бот есть в канале и видит этот пост.\n\n"
            f"Детали: {e.message}"
        )
        return

    title = channel.get("title") or selected_chat_id
    await state.update_data(channel_post_id=int(channel_post_id))
    await message.answer(
        "Пост найден ✅\n\n"
        f"Канал: {title}\n"
        f"Post ID: {int(channel_post_id)}\n"
        f"Будет выделено просмотров: {int(channel.get('views_per_post') or 0)}\n"
        "Награда: 0.01⭐\n\n"
        "Добавить этот пост в просмотры?",
        reply_markup=admin_task_channel_manual_post_confirm_kb(int(channel_id)),
    )


@router.callback_query(F.data == "adm:tch:manual_post:add")
async def adm_task_channel_manual_post_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    channel_id = _to_optional_int(data.get("channel_id"))
    channel_post_id = _to_optional_int(data.get("channel_post_id"))
    if channel_id is None or channel_post_id is None:
        await state.clear()
        await safe_edit_text(
            callback.message,
            "❌ Не удалось определить пост. Начни добавление заново.",
            reply_markup=admin_back_kb(),
        )
        return

    try:
        detail = await add_task_channel_manual_post_via_api(
            int(channel_id),
            channel_post_id=int(channel_post_id),
            added_by_admin_id=int(callback.from_user.id),
        )
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось добавить пост.\n\n{e.detail}",
            reply_markup=admin_back_kb(f"adm:tch:open:{channel_id}"),
        )
        return

    await state.clear()
    post = detail["post"]
    text, is_active, resolved_channel_id, can_partner_views_accrual, can_add_client_views = _build_task_channel_card_text(detail)
    await safe_edit_text(
        callback.message,
        "✅ Пост добавлен вручную\n\n"
        f"Post ID: {int(post['channel_post_id'])}\n"
        f"Просмотры: 0/{int(post['required_views'])}\n\n"
        + text,
        reply_markup=admin_task_channel_card_kb(
            resolved_channel_id,
            is_active,
            can_partner_views_accrual=can_partner_views_accrual,
            can_add_client_views=can_add_client_views,
        ),
    )


@router.callback_query(F.data.startswith("adm:tch:posts:"))
async def adm_task_channel_posts(callback: CallbackQuery):
    await callback.answer()
    parts = (callback.data or "").split(":")
    channel_id = int(parts[3])
    page = 0
    if len(parts) > 4:
        try:
            page = max(int(parts[4]), 0)
        except ValueError:
            await safe_edit_text(callback.message, "❌ Страница не найдена.", reply_markup=admin_back_kb())
            return

    try:
        result = await get_task_channel_posts_via_api(channel_id, limit=5, page=page)
    except ApiClientError as e:
        if e.status_code == 404:
            await safe_edit_text(callback.message, "❌ Канал не найден.", reply_markup=admin_back_kb())
            return
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить посты канала из API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    channel = result["channel"]
    rows = result.get("items") or []
    current_page = int(result.get("page") or 0)
    has_next = bool(result.get("has_next") or False)
    title = channel.get("title") or channel["chat_id"]

    if not rows:
        await safe_edit_text(
            callback.message,
            "📊 Статус по постам\n\n"
            f"Канал: {title}\n\n"
            "Пока нет добавленных постов.",
            reply_markup=_task_channel_posts_nav_kb(channel_id, current_page, has_next),
        )
        return

    lines = []
    for row in rows:
        post_id = int(row["channel_post_id"])
        current_views = int(row["current_views"] or 0)
        required_views = int(row["required_views"] or 0)
        source_label = "ручной" if row.get("source") == "manual" else "авто"

        done = current_views >= required_views and required_views > 0
        status = "✅" if done else "🔄"

        created_at = row["created_at"] or "-"
        lines.append(
            f"📝 Пост #{post_id} ({source_label}, {created_at}) — {current_views}/{required_views} {status}\n"
        )

    text = (
            "📊 Статус по постам\n\n"
            f"Канал: {title}\n\n"
            + "\n".join(lines)
    )

    await safe_edit_text(
        callback.message,
        text,
        reply_markup=_task_channel_posts_nav_kb(channel_id, current_page, has_next),
    )

@router.message(TaskChannelEdit.view_seconds)
async def adm_task_channel_edit_view_seconds(message: Message, state: FSMContext):
    try:
        view_seconds = int((message.text or "").strip())
        if view_seconds <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое число больше 0.")
        return

    data = await state.get_data()
    channel_id = int(data["channel_id"])
    total_bought_views = int(data["total_bought_views"])
    views_per_post = int(data["views_per_post"])
    edit_pool = str(data.get("edit_pool") or "main").strip().lower()
    pool_title = str(data.get("edit_pool_title") or "канала")

    try:
        detail = await update_task_channel_params_via_api(
            channel_id,
            total_bought_views=total_bought_views,
            views_per_post=views_per_post,
            view_seconds=view_seconds,
            pool=edit_pool,
        )
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    await state.clear()
    text, is_active, resolved_channel_id, can_partner_views_accrual, can_add_client_views = _build_task_channel_card_text(detail)
    await message.answer(
        f"✅ Параметры {pool_title} обновлены\n\n" + text,
        reply_markup=admin_task_channel_card_kb(
            resolved_channel_id,
            is_active,
            can_partner_views_accrual=can_partner_views_accrual,
            can_add_client_views=can_add_client_views,
        ),
    )

@router.message(TaskChannelCreate.view_seconds)
async def adm_task_channel_new_view_seconds(message: Message, state: FSMContext):
    try:
        view_seconds = int((message.text or "").strip())
        if view_seconds <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое число больше 0.")
        return

    data = await state.get_data()
    chat_id = data["chat_id"]
    client_user_id = int(data["client_user_id"])
    owner_type = _normalize_owner_type(data.get("owner_type"))
    total_bought_views = int(data["total_bought_views"])
    views_per_post = int(data["views_per_post"])
    bot = message.bot
    channel_title = await _get_channel_title_for_admin(bot, str(chat_id)) if bot is not None else None

    try:
        detail = await create_task_channel_via_api(
            chat_id=chat_id,
            title=channel_title,
            client_user_id=client_user_id,
            owner_type=owner_type,
            total_bought_views=total_bought_views,
            views_per_post=views_per_post,
            view_seconds=view_seconds,
        )
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    await state.clear()
    new_id = int(detail["channel"]["id"])
    bought_views_line = (
        ""
        if owner_type == OWNER_TYPE_PARTNER
        else f"Куплено просмотров: {total_bought_views}\n"
    )

    await message.answer(
        "✅ Канал подключен\n\n"
        f"Название: {channel_title or 'не удалось определить'}\n"
        f"chat_id: {chat_id}\n"
        f"Тип: {_owner_type_label(owner_type)}\n"
        f"Пользователь user_id: {client_user_id}\n"
        f"{bought_views_line}"
        f"На 1 пост: {views_per_post}\n"
        f"Секунд просмотра: {view_seconds}\n"
        "Статус: 🔴 Отключен"
    )

    await message.answer(
        "Открой канал:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📺 Открыть канал", callback_data=f"adm:tch:open:{new_id}")],
                [InlineKeyboardButton(text="📺 Все каналы", callback_data="adm:tch:list")],
            ]
        )
    )


@router.callback_query(F.data.startswith("adm:tch:client:"))
async def adm_task_channel_bind_client(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.rsplit(":", 1)[1])
    await callback.answer()
    await state.clear()
    await state.update_data(channel_id=channel_id)
    await state.set_state(TaskChannelBindClient.owner_type)
    await safe_edit_text(
        callback.message,
        "Выбери, это клиент или партнер:",
        reply_markup=admin_owner_type_kb(
            client_callback=f"adm:tch:bind_owner:{channel_id}:client",
            partner_callback=f"adm:tch:bind_owner:{channel_id}:partner",
            back_callback=f"adm:tch:open:{channel_id}",
        ),
    )


@router.callback_query(F.data.startswith("adm:tch:bind_owner:"))
async def adm_task_channel_bind_owner_type(callback: CallbackQuery, state: FSMContext):
    parts = (callback.data or "").split(":")
    channel_id = int(parts[3])
    owner_type = _normalize_owner_type(parts[4] if len(parts) > 4 else OWNER_TYPE_CLIENT)
    await callback.answer()
    await state.update_data(channel_id=channel_id, owner_type=owner_type)
    await state.set_state(TaskChannelBindClient.client_ref)
    await safe_edit_text(
        callback.message,
        f"Пришли @username или user_id {_owner_type_label(owner_type)} для этого канала:",
        reply_markup=admin_back_kb(f"adm:tch:open:{channel_id}"),
    )


@router.message(TaskChannelBindClient.client_ref)
async def adm_task_channel_bind_client_value(message: Message, state: FSMContext):
    data = await state.get_data()
    channel_id = _to_optional_int(data.get("channel_id"))
    if channel_id is None:
        await state.clear()
        await message.answer("❌ Не удалось определить канал, попробуй открыть его заново")
        return

    query = (message.text or "").strip()
    if not query:
        await message.answer("❌ Нужен @username или user_id пользователя")
        return

    try:
        profile = await lookup_user(query)
        owner_type = _normalize_owner_type(data.get("owner_type"))
        detail = await bind_task_channel_client_via_api(
            int(channel_id),
            client_user_id=int(profile["user_id"]),
            owner_type=owner_type,
        )
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    await state.clear()

    text, is_active, channel_id_value, can_partner_views_accrual, can_add_client_views = _build_task_channel_card_text(detail)
    await message.answer(
        f"✅ {_owner_type_title(owner_type)} привязан\n\n" + text,
        reply_markup=admin_task_channel_card_kb(
            channel_id_value,
            is_active,
            can_partner_views_accrual=can_partner_views_accrual,
            can_add_client_views=can_add_client_views,
        ),
    )

@router.callback_query(F.data.startswith("adm:growth_back:"))
async def adm_growth_back(callback: CallbackQuery):
    await callback.answer()

    origin_message_id = int(callback.data.rsplit(":", 1)[1])

    try:
        await callback.message.delete()
    except Exception:
        pass

    try:
        await callback.bot.edit_message_text(
            chat_id=callback.from_user.id,
            message_id=origin_message_id,
            text="🔐 Админ-панель",
            reply_markup=admin_menu_kb(),
        )
    except TelegramBadRequest as e:
        error_text = str(e)
        if "message is not modified" in error_text:
            return
        if "there is no text in the message to edit" in error_text:
            try:
                await callback.bot.edit_message_caption(
                    chat_id=callback.from_user.id,
                    message_id=origin_message_id,
                    caption="🔐 Админ-панель",
                    reply_markup=admin_menu_kb(),
                )
                return
            except TelegramBadRequest as caption_error:
                if "message is not modified" in str(caption_error):
                    return

        await callback.bot.send_message(
            chat_id=callback.from_user.id,
            text="🔐 Админ-панель",
            reply_markup=admin_menu_kb(),
        )

@router.message(_is_myrole_command)
async def adm_my_role(message: Message):
    try:
        profile = await get_user_profile(message.from_user.id)
    except ApiClientError as e:
        await message.answer(f"❌ Не удалось загрузить роль из API.\n\n{e.detail}")
        return

    role_level = int(profile.get("role_level") or 0)
    role_name = profile.get("role") or "пользователь"

    await message.answer(
        f"Твоя роль: <b>{role_name}</b>\n"
        f"Уровень: <b>{role_level}</b>",
        parse_mode=ParseMode.HTML,
    )

@router.callback_query(F.data.startswith("adm:user:role:"))
async def adm_choose_role(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[-1])

    await callback.answer()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 Пользователь", callback_data=f"adm:setrole:{user_id}:0")],
            [InlineKeyboardButton(text="💼 Клиент", callback_data=f"adm:setrole:{user_id}:3")],
            [InlineKeyboardButton(text="🤝 Партнер", callback_data=f"adm:setrole:{user_id}:6")],
            [InlineKeyboardButton(text="🛠 Админ", callback_data=f"adm:setrole:{user_id}:9")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data=f"adm:user:details:{user_id}")]
        ]
    )

    await safe_edit_text(
        callback.message,
        f"Выбери новую роль для пользователя {user_id}",
        reply_markup=kb
    )

@router.callback_query(F.data.startswith("adm:setrole:"))
async def adm_set_role(callback: CallbackQuery):
    _, _, user_id, level = callback.data.split(":")

    user_id = int(user_id)
    level = int(level)

    try:
        result = await set_user_role(user_id, level)
    except ApiClientError as e:
        await callback.answer(f"❌ {e.detail}", show_alert=True)
        return

    final_role_name = result.get("role") or "пользователь"

    await callback.answer("✅ Роль изменена")

    await callback.message.edit_text(
        f"✅ Роль пользователя <code>{user_id}</code> изменена.\n\n"
        f"Новая роль: <b>{final_role_name}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅ Назад",
                        callback_data=f"adm:user:details:{user_id}",
                    )
                ]
            ]
        ),
    )
