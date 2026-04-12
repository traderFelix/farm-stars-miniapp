import io, logging
from datetime import date, timedelta
from typing import Any, Literal, Optional
from urllib.parse import urlparse

import matplotlib

from bot.api_client import (
    ApiClientError,
    add_campaign_winners_via_api,
    adjust_user_balance,
    bind_task_channel_client_via_api,
    clear_user_suspicious,
    create_campaign_via_api,
    create_task_channel_via_api,
    delete_campaign_via_api,
    delete_campaign_winner_via_api,
    get_admin_ledger_page_via_api,
    get_audit_via_api,
    get_campaign_stats_via_api,
    get_campaign_via_api,
    get_campaign_winners_via_api,
    get_campaigns_summary_via_api,
    get_growth_via_api,
    get_top_balances_via_api,
    get_withdrawal_details,
    get_task_channel_posts_via_api,
    get_task_channel_via_api,
    get_user_ledger_page,
    get_user_profile,
    get_user_risk_page,
    get_user_stats,
    list_campaigns_via_api,
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
    set_user_role,
    toggle_task_channel_via_api,
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
from aiogram.exceptions import TelegramBadRequest

from shared.config import ADMIN_IDS, LEDGER_PAGE_SIZE, OWNER_ID, ROLE_ADMIN

from bot.handlers.user import safe_edit_text

from shared.formatting import fmt_stars

from bot.keyboards import (
    admin_menu_kb, admin_back_kb, campaigns_list_kb, campaign_manage_kb, stats_list_kb, admin_fee_refund_kb,
    campaign_created_kb, user_actions_kb, admin_withdraw_list_kb, admin_withdraw_actions_kb, campaign_delete_confirm_kb,
    admin_task_channels_kb, admin_task_channel_card_kb, admin_growth_photo_kb,
)

from bot.states import (
    CampaignCreate, AddWinners, DeleteWinner, UserLookup, AdminAdjust, AdminRefundFee, TaskChannelBindClient, TaskChannelCreate, TaskChannelEdit,
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


@fallback_router.message(F.text.startswith("/myrole"))
async def admin_api_unavailable_myrole(message: Message):
    await message.answer(ADMIN_API_UNAVAILABLE_TEXT)


@fallback_router.message(
    StateFilter(
        AddWinners.usernames,
        CampaignCreate.key,
        CampaignCreate.amount,
        CampaignCreate.title,
        CampaignCreate.post_url,
        DeleteWinner.username,
        UserLookup.user,
        AdminAdjust.amount,
        AdminRefundFee.waiting_manual_data,
        TaskChannelCreate.chat_id,
        TaskChannelCreate.client_ref,
        TaskChannelCreate.total_bought_views,
        TaskChannelCreate.views_per_post,
        TaskChannelCreate.view_seconds,
        TaskChannelBindClient.client_ref,
        TaskChannelEdit.total_bought_views,
        TaskChannelEdit.views_per_post,
        TaskChannelEdit.view_seconds,
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


async def _get_user_card_text(user_id: int) -> str:
    profile = await get_user_profile(user_id)
    return format_user_profile_card(profile)


def _build_task_channel_card_text(detail: dict) -> tuple[str, bool, int]:
    channel = detail["channel"]
    stats = detail["stats"]

    channel_id = int(channel["id"])
    title = channel.get("title") or "Без названия"
    chat_id = channel["chat_id"]
    is_active = bool(channel.get("is_active") or False)
    total_bought = int(channel.get("total_bought_views") or 0)
    views_per_post = int(channel.get("views_per_post") or 0)
    allocated = int(channel.get("allocated_views") or 0)
    remaining = int(channel.get("remaining_views") or 0)
    view_seconds = int(channel.get("view_seconds") or 0)
    total_posts = int(stats.get("total_posts") or 0)
    total_required = int(stats.get("total_required") or 0)
    total_current = int(stats.get("total_current") or 0)
    active_posts = int(stats.get("active_posts") or 0)
    client_user_id = _to_optional_int(channel.get("client_user_id"))
    client_username = (channel.get("client_username") or "").strip()
    client_first_name = (channel.get("client_first_name") or "").strip()

    status_text = "🟢 Включен" if is_active else "🔴 Отключен"
    client_label = "не привязан"
    if client_user_id is not None:
        client_label = f"id:{client_user_id}"
        if client_username:
            client_label = f"@{client_username}"
        elif client_first_name:
            client_label = f"{client_first_name} ({client_label})"

    text = (
        "📺 Канал просмотров\n\n"
        f"Название: {title}\n"
        f"ID канала: {chat_id}\n"
        f"Клиент: {client_label}\n"
        f"Статус: {status_text}\n\n"
        f"Куплено просмотров: {total_bought}\n"
        f"На один пост: {views_per_post}\n"
        f"Секунд просмотра: {view_seconds}\n"
        f"Уже распределено: {allocated}\n"
        f"Осталось распределить: {remaining}\n\n"
        f"Постов в системе: {total_posts}\n"
        f"Активных постов: {active_posts}\n"
        f"Всего нужно просмотров по постам: {total_required}\n"
        f"Фактически набрано: {total_current}"
    )
    return text, is_active, channel_id


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


def _is_valid_post_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


async def _render_campaign_card(callback: CallbackQuery, key: str):
    try:
        detail = await get_campaign_via_api(key)
    except ApiClientError as e:
        if e.status_code == 404:
            await safe_edit_text(callback.message, "❌ Конкурс не найден.", reply_markup=admin_back_kb())
            return

        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить конкурс из API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    text, status = _build_campaign_card_text(detail)
    await safe_edit_text(callback.message, text, reply_markup=campaign_manage_kb(key, status))


@router.callback_query(F.data == "adm:back")
async def adm_back(callback: CallbackQuery):
    await callback.answer()
    await safe_edit_text(callback.message, "🛠 Админ-панель", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "adm:list")
async def adm_list(callback: CallbackQuery):
    await callback.answer()

    try:
        result = await list_campaigns_via_api()
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить конкурсы из API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    rows = result.get("items") or []
    if not rows:
        await safe_edit_text(callback.message, "Пока нет конкурсов.", reply_markup=admin_back_kb())
        return

    await safe_edit_text(callback.message, "📋 Список всех конкурсов:", reply_markup=campaigns_list_kb(rows))


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
            await safe_edit_text(callback.message, "❌ Конкурс не найден.", reply_markup=admin_back_kb())
            return
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось обновить статус конкурса через API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
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
            await safe_edit_text(callback.message, "❌ Конкурс не найден.", reply_markup=admin_back_kb())
            return
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось обновить статус конкурса через API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
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
                reply_markup=admin_back_kb()
            )
            return
        await safe_edit_text(
            callback.message,
            f"❌ Не удалось загрузить конкурс из API.\n\n{e.detail}",
            reply_markup=admin_back_kb(),
        )
        return

    title = detail.get("title") or ""
    amount = float(detail.get("reward_amount") or 0)
    status = detail.get("status") or "draft"

    await safe_edit_text(
        callback.message,
        f"⚠️ Ты точно хочешь удалить конкурс?\n\n"
        f"KEY: {key}\n"
        f"Название: {title}\n"
        f"Награда: {amount}⭐\n"
        f"Статус: {status}",
        reply_markup=campaign_delete_confirm_kb(key),
    )


@router.callback_query(F.data.startswith("adm:del:do:"))
async def adm_delete_do(callback: CallbackQuery):
    await callback.answer()
    key = callback.data.split(":", 3)[3]

    try:
        await delete_campaign_via_api(key)
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
        reply_markup=admin_back_kb(),
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
            reply_markup=admin_back_kb(),
        )
        return

    rows = summary.get("latest_items") or []
    if not rows:
        await safe_edit_text(callback.message, "Нет конкурсов", reply_markup=admin_back_kb())
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
        reply_markup=stats_list_kb(rows)
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
            reply_markup=admin_back_kb(),
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
        reply_markup=admin_back_kb()
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

        ax.bar(xs, ys)
        ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
        ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%d"))

        ax.set_ylim(bottom=0)
        ax.set_xticks(xs[::max(1, len(xs) // 15)])
        ax.set_xlabel("Date")
        ax.set_ylabel("New users")
        ax.set_title(f"User growth (last {days} days)")

        fig.autofmt_xdate(rotation=45)
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
    admin_adjust_net = float(audit.get("admin_adjust_net") or 0)
    total_withdrawn_sum = float(audit.get("total_withdrawn") or 0)
    pending_withdrawn_sum = float(audit.get("pending_withdrawn") or 0)
    claimed_from_ledger = float(audit.get("campaign_claimed_from_ledger") or 0)
    referral_bonus = float(audit.get("referral_bonus") or 0)
    view_post_bonus = float(audit.get("view_post_bonus") or 0)
    daily_bonus = float(audit.get("daily_bonus") or 0)

    lines = [
        "🧮 Сверка балансов\n",
        f"Баланс пользователей: {fmt_stars(total_balances_sum)}⭐\n",
        f"Получено в конкурсах (база): {fmt_stars(total_claimed_all)}⭐",
        f"Получено в конкурсах (леджер): {fmt_stars(claimed_from_ledger)}⭐",
        f"Получено за рефералов: {fmt_stars(referral_bonus)}⭐\n"
        f"Получено за просмотры постов: {fmt_stars(view_post_bonus)}⭐\n"
        f"Получено за ежедневный бонус: {fmt_stars(daily_bonus)}⭐\n"
        f"Получено от админа: {fmt_stars(admin_adjust_net)}⭐\n",
        f"Выведено: {fmt_stars(total_withdrawn_sum)}⭐",
        f"В обработке: {fmt_stars(pending_withdrawn_sum)}⭐\n",
    ]

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

    try:
        result = await get_user_stats(user_id)
        text = result.get("text") or "Нет данных"
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

    if not history and page > 0:
        await callback.answer("Дальше записей нет")
        return

    has_next = bool(result.get("has_next") or False)
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
        if meta:
            line += f"\nmeta: {meta}"
        lines.append(line)

    if not lines:
        lines = ["нет событий риска"]

    text = (
        f"🛡 Риск-история пользователя, страница {page + 1}\n\n"
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

    text, is_active, resolved_channel_id = _build_task_channel_card_text(detail)
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=admin_task_channel_card_kb(resolved_channel_id, is_active),
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
    await state.set_state(TaskChannelCreate.client_ref)
    await message.answer("Теперь пришли @username или user_id клиента, которому принадлежит этот канал:")


@router.message(TaskChannelCreate.client_ref)
async def adm_task_channel_new_client_ref(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    if not query:
        await message.answer("❌ Нужен @username или user_id клиента")
        return

    try:
        profile = await lookup_user(query)
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    client_user_id = int(profile["user_id"])
    client_username = (profile.get("username") or "").strip()
    client_name = (profile.get("first_name") or "").strip()
    client_label = f"id:{client_user_id}"
    if client_username:
        client_label = f"@{client_username}"
    elif client_name:
        client_label = f"{client_name} ({client_label})"

    await state.update_data(client_user_id=client_user_id)
    await state.set_state(TaskChannelCreate.total_bought_views)
    await message.answer(
        f"Клиент привязан: {client_label}\n\n"
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
    total_bought_views = int(data["total_bought_views"])

    if views_per_post > total_bought_views:
        await message.answer("❌ Просмотров на 1 пост не может быть больше, чем куплено всего.")
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

    text, is_active, resolved_channel_id = _build_task_channel_card_text(detail)
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=admin_task_channel_card_kb(resolved_channel_id, is_active),
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

    await state.set_state(TaskChannelEdit.total_bought_views)
    await state.update_data(channel_id=channel_id)

    await safe_edit_text(
        callback.message,
        "⚙️ Редактирование параметров канала\n\n"
        f"Текущий chat_id: {channel['chat_id']}\n"
        f"Сейчас куплено просмотров: {int(channel.get('total_bought_views') or 0)}\n"
        f"Сейчас просмотров на 1 пост: {int(channel.get('views_per_post') or 0)}\n"
        f"Сейчас секунд просмотра: {int(channel.get('view_seconds') or 0)}\n"
        f"Уже распределено по постам: {int(channel.get('allocated_views') or 0)}\n\n"
        "Введи новое общее количество купленных просмотров:",
        reply_markup=admin_back_kb(),
    )

@router.message(TaskChannelEdit.total_bought_views)
async def adm_task_channel_edit_total_views(message: Message, state: FSMContext):
    try:
        total_bought_views = int((message.text or "").strip())
        if total_bought_views <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое число больше 0.")
        return

    data = await state.get_data()
    channel_id = int(data["channel_id"])

    try:
        detail = await get_task_channel_via_api(channel_id)
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    allocated_views = int(detail["channel"].get("allocated_views") or 0)
    if total_bought_views < allocated_views:
        await message.answer(
            "❌ Нельзя поставить меньше, чем уже распределено по постам.\n\n"
            f"Уже распределено: {allocated_views}"
        )
        return

    await state.update_data(total_bought_views=total_bought_views)
    await state.set_state(TaskChannelEdit.views_per_post)
    await message.answer("Теперь введи новое количество просмотров на 1 пост:")

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
    channel_id = int(data["channel_id"])
    total_bought_views = int(data["total_bought_views"])

    if views_per_post > total_bought_views:
        await message.answer("❌ Просмотров на 1 пост не может быть больше, чем куплено всего.")
        return

    await state.update_data(views_per_post=views_per_post)
    await state.set_state(TaskChannelEdit.view_seconds)
    await message.answer("Теперь введи новое количество секунд просмотра:")


@router.callback_query(F.data.startswith("adm:tch:posts:"))
async def adm_task_channel_posts(callback: CallbackQuery):
    await callback.answer()
    channel_id = int(callback.data.split(":")[3])

    try:
        result = await get_task_channel_posts_via_api(channel_id, limit=20)
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
    title = channel.get("title") or channel["chat_id"]

    if not rows:
        await safe_edit_text(
            callback.message,
            "📊 Статус по постам\n\n"
            f"Канал: {title}\n\n"
            "Пока нет добавленных постов.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⬅ Назад к каналу", callback_data=f"adm:tch:open:{channel_id}")],
                    [InlineKeyboardButton(text="📺 Все каналы", callback_data="adm:tch:list")],
                ]
            )
        )
        return

    lines = []
    for row in rows:
        post_id = int(row["channel_post_id"])
        current_views = int(row["current_views"] or 0)
        required_views = int(row["required_views"] or 0)

        done = current_views >= required_views and required_views > 0
        status = "✅" if done else "🔄"

        created_at = row["created_at"] or "-"
        lines.append(
            f"📝 Пост #{post_id} ({created_at}) — {current_views}/{required_views} {status}\n"
        )

    text = (
            "📊 Статус по постам\n\n"
            f"Канал: {title}\n\n"
            + "\n".join(lines)
    )

    await safe_edit_text(
        callback.message,
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅ Назад к каналу", callback_data=f"adm:tch:open:{channel_id}")],
                [InlineKeyboardButton(text="📺 Все каналы", callback_data="adm:tch:list")],
            ]
        )
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

    try:
        detail = await update_task_channel_params_via_api(
            channel_id,
            total_bought_views=total_bought_views,
            views_per_post=views_per_post,
            view_seconds=view_seconds,
        )
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    await state.clear()
    channel = detail["channel"]
    stats = detail["stats"]

    title = channel.get("title") or "Без названия"
    chat_id = channel["chat_id"]
    is_active = bool(channel.get("is_active") or False)
    allocated = int(channel.get("allocated_views") or 0)
    remaining = int(channel.get("remaining_views") or 0)

    total_posts = int(stats.get("total_posts") or 0)
    active_posts = int(stats.get("active_posts") or 0)
    total_required = int(stats.get("total_required") or 0)
    total_current = int(stats.get("total_current") or 0)

    status_text = "🟢 Включен" if is_active else "🔴 Отключен"

    await message.answer(
        "✅ Параметры канала обновлены\n\n"
        f"Название: {title}\n"
        f"chat_id: {chat_id}\n"
        f"Статус: {status_text}\n\n"
        f"Куплено просмотров: {int(channel.get('total_bought_views') or 0)}\n"
        f"На 1 пост: {int(channel.get('views_per_post') or 0)}\n"
        f"Секунд просмотра: {int(channel.get('view_seconds') or 0)}\n"
        f"Уже распределено: {allocated}\n"
        f"Осталось распределить: {remaining}\n\n"
        f"Постов в системе: {total_posts}\n"
        f"Активных постов: {active_posts}\n"
        f"Всего нужно просмотров по постам: {total_required}\n"
        f"Фактически набрано: {total_current}",
        reply_markup=admin_task_channel_card_kb(channel_id, is_active),
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
    total_bought_views = int(data["total_bought_views"])
    views_per_post = int(data["views_per_post"])

    try:
        detail = await create_task_channel_via_api(
            chat_id=chat_id,
            title=None,
            client_user_id=client_user_id,
            total_bought_views=total_bought_views,
            views_per_post=views_per_post,
            view_seconds=view_seconds,
        )
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    await state.clear()
    new_id = int(detail["channel"]["id"])

    await message.answer(
        "✅ Канал подключен\n\n"
        f"chat_id: {chat_id}\n"
        f"Клиент user_id: {client_user_id}\n"
        f"Куплено просмотров: {total_bought_views}\n"
        f"На 1 пост: {views_per_post}\n"
        f"Секунд просмотра: {view_seconds}"
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
    await state.set_state(TaskChannelBindClient.client_ref)
    await callback.message.answer(
        "Пришли @username или user_id клиента для этого канала:"
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
        await message.answer("❌ Нужен @username или user_id клиента")
        return

    try:
        profile = await lookup_user(query)
        detail = await bind_task_channel_client_via_api(
            int(channel_id),
            client_user_id=int(profile["user_id"]),
        )
    except ApiClientError as e:
        await message.answer(f"❌ {e.detail}")
        return

    await state.clear()

    text, is_active, channel_id_value = _build_task_channel_card_text(detail)
    await message.answer(
        "✅ Клиент привязан\n\n" + text,
        reply_markup=admin_task_channel_card_kb(channel_id_value, is_active),
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
        if "message is not modified" not in str(e):
            raise

@router.message(F.text.startswith("/myrole"))
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
