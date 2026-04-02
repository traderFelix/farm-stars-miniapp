import asyncio, logging

from typing import Optional

from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, PreCheckoutQuery, LabeledPrice
)

from shared.config import (
    CHANNEL_ID, ADMIN_IDS, MIN_WITHDRAW, MIN_WITHDRAW_PERCENT, ROLE_CLIENT, ROLE_PARTNER
)

from bot.db import (
    tx,
)

from shared.db.users import (
    fmt_stars, user_has_role,
    get_referrals_count,
)
from shared.db.tasks import allocate_task_post_from_channel_post

from bot.keyboards import (
    subscribe_keyboard, main_menu, tasks_menu, bottom_menu_kb, withdraw_stars_amount_kb, task_after_view_kb,
    withdraw_method_kb, withdraw_menu_kb, withdraw_back_kb, referrals_kb, daily_checkin_kb
)

from bot.states import WithdrawCreate

from bot.api_client import (
    ApiClientError,
    bootstrap_bot_user_via_api,
    claim_campaign_reward_via_api,
    get_next_task,
    open_task,
    check_task,
    get_active_campaigns_via_api,
    get_bot_main_menu_for_user_context_via_api,
    get_bot_main_menu_via_api,
    get_daily_checkin_status,
    claim_daily_checkin_via_api,
    get_withdrawal_eligibility_via_api,
    preview_withdrawal_via_api,
    get_my_withdrawals_via_api,
    create_withdrawal_via_api,
)

router = Router()

logger = logging.getLogger(__name__)

LAST_TASK_POST_MSG_ID_KEY = "last_task_post_message_id"

WITHDRAW_TEXT = f"""
💰 <b>Вывод и обмен звезд</b>

🔷 Минимальная сумма вывода и обмена <b>{MIN_WITHDRAW}⭐</b>
🔷 Конвертация звезд в TON производится по курсу на сайте <b>Fragment</b>
🔷 Для вывода необходимо, чтобы минимум <b>{MIN_WITHDRAW_PERCENT * 100:.0f}%</b> звезд на балансе были добыты путем выполнения заданий

<blockquote>
<b>Первый вывод бесплатный 🔥</b>

Последующие выводы:
▪️ 100⭐ — комиссия <b>5 Telegram Stars</b>
▪️ 200⭐ — комиссия <b>3 Telegram Stars</b>
▪️ 500⭐ — <b>без комиссии</b>

💡 Комиссия списывается <b>только с баланса Telegram Stars</b>, а не с игрового баланса звезд
</blockquote>

Выберите нужный вариант ниже! 👇
"""


def _build_tg_user_payload(user) -> dict[str, Optional[str]]:
    return {
        "user_id": int(user.id),
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }

@router.channel_post()
async def ingest_task_channel_post(message: Message, db):
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

    async with tx(db, immediate=True):
        await allocate_task_post_from_channel_post(
            db=db,
            chat_id=str(message.chat.id),
            channel_post_id=int(message.message_id),
            title=message.chat.title,
            reward=0.01,
        )

@router.message(StateFilter("*"), F.text == "🏠 Главное меню")
async def open_main_menu_from_bottom_button(message: Message, state: FSMContext):
    await state.clear()

    menu_payload = await get_bot_main_menu_for_user_context_via_api(
        **_build_tg_user_payload(message.from_user),
    )
    role_level = int(menu_payload.get("role_level") or 0)

    await message.answer(
        menu_payload["text"],
        reply_markup=main_menu(role_level)
    )


@router.message(CommandStart())
async def start(message: Message, bot: Bot):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    start_arg = None
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1:
        start_arg = parts[1].strip()

    logger.info("START user_id=%s text=%r start_arg=%r", user_id, message.text, start_arg)

    start_referrer_id = int(start_arg) if start_arg and start_arg.isdigit() else None
    menu_payload = await bootstrap_bot_user_via_api(
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        start_referrer_id=start_referrer_id,
    )

    if start_referrer_id is not None:
        logger.info(
            "bind_referrer user_id=%s referrer_id=%s bound=%s",
            user_id,
            start_referrer_id,
            bool(menu_payload.get("referrer_bound")),
        )

    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
    except Exception:
        try:
            await message.answer("Ошибка проверки канала.")
        except TelegramForbiddenError:
            logger.warning("User %s blocked bot during channel check error reply", user_id)
        return

    try:
        if member.status in ("member", "administrator", "creator"):
            role_level = int(menu_payload.get("role_level") or 0)

            await message.answer(
                "Нажми кнопку снизу, чтобы открыть меню 👇",
                reply_markup=bottom_menu_kb()
            )

            await message.answer(
                menu_payload["text"],
                reply_markup=main_menu(role_level)
            )
        else:
            await message.answer(
                "Чтобы продолжить, подпишись на канал 👇",
                reply_markup=subscribe_keyboard()
            )
    except TelegramForbiddenError:
        logger.warning("User %s blocked bot", user_id)


@router.callback_query(F.data == "check_sub")
async def check_subscription(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id

    menu_payload = await get_bot_main_menu_for_user_context_via_api(
        **_build_tg_user_payload(callback.from_user),
    )

    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
    except Exception:
        await callback.answer("Ошибка проверки канала", show_alert=True)
        return

    if member.status in ("member", "administrator", "creator"):
        role_level = int(menu_payload.get("role_level") or 0)

        await callback.message.answer(
            "Нажми кнопку снизу, чтобы открыть меню 👇",
            reply_markup=bottom_menu_kb()
        )

        await safe_edit_text(
            callback.message,
            menu_payload["text"],
            reply_markup=main_menu(role_level)
        )
    else:
        await callback.answer("❌ Ты еще не подписан!", show_alert=True)


@router.callback_query(F.data == "tasks")
async def show_tasks(callback: CallbackQuery):
    await callback.answer()

    user_id = callback.from_user.id
    menu_payload = await get_bot_main_menu_via_api(user_id)
    balance = float(menu_payload.get("balance") or 0)

    try:
        next_task = await get_next_task(user_id)
    except Exception:
        next_task = None

    if next_task:
        tasks_status_text = "Сейчас есть доступные посты для просмотра."
    else:
        tasks_status_text = "Сейчас доступных постов нет."

    await safe_edit_text(
        callback.message,
        "📋 Задания\n\n"
        "👁 Просмотр постов из каналов\n"
        "За каждый просмотр начисляется награда.\n"
        f"{tasks_status_text}\n\n"
        f"Баланс: {fmt_stars(balance)}⭐️",
        reply_markup=tasks_menu(),
    )


@router.callback_query(F.data == "task:view_post")
async def task_view_post(callback: CallbackQuery, bot: Bot, state: FSMContext):
    user_id = callback.from_user.id
    task = await get_next_task(user_id)
    if not task:
        await callback.answer("❌ Доступных постов пока нет.", show_alert=True)
        return

    task_id = int(task["id"])
    chat_id = task.get("chat_id")
    channel_post_id = task.get("channel_post_id")

    try:
        open_result = await open_task(user_id, task_id)
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
        await callback.message.delete()
    except Exception:
        pass

    if not chat_id or not channel_post_id:
        await bot.send_message(
            chat_id=user_id,
            text="❌ У задания нет данных поста.",
            reply_markup=task_after_view_kb(),
        )
        return

    try:
        sent = await bot.forward_message(
            chat_id=user_id,
            from_chat_id=chat_id,
            message_id=int(channel_post_id),
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

    try:
        next_task = await get_next_task(user_id)
    except Exception:
        next_task = None

    has_more_tasks = next_task is not None
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
    menu_payload = await get_bot_main_menu_via_api(user_id)
    role_level = int(menu_payload.get("role_level") or 0)

    await _delete_last_task_post(bot, user_id, state)

    await callback.answer()
    await safe_edit_text(
        callback.message,
        menu_payload["text"],
        reply_markup=main_menu(role_level)
    )


@router.callback_query(F.data == "claim")
async def claim_menu(callback: CallbackQuery):
    data = await get_active_campaigns_via_api()
    campaigns = data.get("items", [])

    if not campaigns:
        await callback.answer("❌ Сейчас нет активных конкурсов", show_alert=True)
        return

    await callback.answer()

    keyboard = []
    for item in campaigns:
        key = item["campaign_key"]
        title = item["title"]
        amount = float(item["reward_amount"])
        keyboard.append([
            InlineKeyboardButton(
                text=f"🎁 {title} • {amount}⭐",
                callback_data=f"claim:{key}"
            )
        ])

    keyboard.append([InlineKeyboardButton(text="⬅ Назад", callback_data="back")])

    text = "Выбери конкурс для получения награды:"
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    if callback.message.text == text:
        await safe_edit_reply_markup(callback.message, reply_markup=markup)
        return

    await safe_edit_text(
        callback.message,
        text,
        reply_markup=markup,
    )


@router.callback_query(F.data.startswith("claim:"))
async def claim_for_campaign(callback: CallbackQuery):
    user_id = callback.from_user.id
    campaign_key = callback.data.split(":", 1)[1]

    result = await claim_campaign_reward_via_api(
        user_id=user_id,
        campaign_key=campaign_key,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name,
    )

    ok = bool(result.get("ok"))
    msg = result.get("message") or "Готово"
    new_balance = float(result.get("new_balance") or 0)

    if not ok:
        await callback.answer(msg, show_alert=True)
        return

    await callback.answer(
        f"{msg}\nБаланс: {fmt_stars(new_balance)}⭐️",
        show_alert=True
    )

@router.callback_query(F.data == "withdraw")
async def withdraw_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()

    eligibility = await get_withdrawal_eligibility_via_api(callback.from_user.id)
    balance = float(eligibility.get("available_balance") or 0)

    await safe_edit_text(
        callback.message,
        "Меню заявок на вывод\n\n"
        f"Доступно: {fmt_stars(balance)}⭐",
        reply_markup=withdraw_menu_kb()
    )


@router.callback_query(F.data == "withdraw:new")
async def withdraw_new(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()

    await callback.message.edit_text(
        WITHDRAW_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=withdraw_method_kb()
    )


async def finalize_withdraw_request(
        message: Message,
        state: FSMContext,
        user_id: int,
        amount: float,
        method: str,
        wallet: Optional[str] = None,
        paid_fee: int = 0,
        fee_payment_charge_id: Optional[str] = None,
        fee_invoice_payload: Optional[str] = None,
):
    result = await create_withdrawal_via_api(
        user_id=user_id,
        payload={
            "method": method,
            "amount": amount,
            "wallet": wallet,
            "paid_fee": paid_fee,
            "fee_payment_charge_id": fee_payment_charge_id,
            "fee_invoice_payload": fee_invoice_payload,
        },
    )

    wid = int(result["withdrawal_id"])
    new_balance = float(result.get("balance") or 0)

    username = message.from_user.username
    name = f"@{username}" if username else f"id:{user_id}"

    admin_text = (
        f"📤 Новая заявка на вывод\n\n"
        f"👤 {name}\n"
        f"⭐ {amount:g}\n"
        f"💸 {method.upper()}\n"
    )

    if wallet:
        admin_text += f"🏦 {wallet}\n"

    if paid_fee > 0:
        admin_text += f"💳 Комиссия оплачена: {paid_fee} XTR\n"

    admin_text += f"\nID заявки: #{wid}"

    bot: Bot = message.bot
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_text)
        except Exception:
            pass

    await state.clear()

    success_text = (
        f"✅ Заявка на вывод создана\n"
        f"ID: #{wid}\n"
        f"Сумма: {amount:g}⭐\n"
        f"Способ: {'Telegram Stars' if method == 'stars' else 'TON'}\n"
    )

    if wallet:
        success_text += f"Кошелек: {wallet}\n"

    if paid_fee > 0:
        success_text += f"Комиссия оплачена: {paid_fee} XTR\n"

    success_text += f"\nБаланс: {fmt_stars(new_balance)}⭐"

    await message.answer(success_text)


async def start_fee_payment_or_create(
        message: Message,
        state: FSMContext,
        user_id: int,
        amount: float,
        method: str,
        wallet: Optional[str] = None,
):
    try:
        preview = await preview_withdrawal_via_api(
            user_id=user_id,
            payload={
                "method": method,
                "amount": amount,
                "wallet": wallet,
            },
        )
    except ApiClientError as e:
        await safe_edit_text(
            message,
            e.detail,
            reply_markup=withdraw_back_kb(),
        )
        return

    fee = int(preview.get("expected_fee") or 0)

    if fee <= 0:
        try:
            await finalize_withdraw_request(
                message=message,
                state=state,
                user_id=user_id,
                amount=amount,
                method=method,
                wallet=wallet,
                paid_fee=0,
                fee_payment_charge_id=None,
                fee_invoice_payload=None,
            )
        except ApiClientError as e:
            if e.detail == "insufficient_balance":
                await message.answer("❌ Недостаточно звезд на балансе")
                return
            await message.answer(f"❌ Ошибка создания заявки: {e.detail}")
        return

    await state.update_data(
        amount=amount,
        method=method,
        wallet=wallet,
        withdraw_fee=fee,
    )
    await state.set_state(WithdrawCreate.fee_payment)

    await message.answer_invoice(
        title="Комиссия за вывод",
        description=f"Оплата комиссии {fee} Telegram Stars за вывод {amount:g}⭐",
        payload=f"withdraw_fee:{user_id}",
        currency="XTR",
        prices=[LabeledPrice(label="Комиссия за вывод", amount=fee)],
        provider_token="",
        start_parameter=f"withdraw-fee-{user_id}",
    )

    await message.answer(
        f"💳 Для продолжения оплати комиссию: {fee} Telegram Stars.\n"
        "После успешной оплаты заявка создастся автоматически."
    )


@router.callback_query(F.data.startswith("withdraw:method:"))
async def withdraw_choose_method(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    method = callback.data.split(":")[2]  # ton | stars
    await state.update_data(method=method)
    await state.set_state(WithdrawCreate.amount)

    eligibility = await get_withdrawal_eligibility_via_api(callback.from_user.id)
    balance = float(eligibility.get("available_balance") or 0)

    await state.clear()
    await state.update_data(method=method)

    if method == "stars":
        await safe_edit_text(
            callback.message,
            "Выбери сумму вывода ⭐:\n\n"
            f"Доступно: {fmt_stars(balance)}⭐\n"
            f"Минимум: {MIN_WITHDRAW:g}⭐",
            reply_markup=withdraw_stars_amount_kb(),
        )
        return

    await state.set_state(WithdrawCreate.amount)
    await callback.message.answer(
        f"Введи сумму обмена ⭐ в TON:\n"
        f"Доступно: {fmt_stars(balance)}⭐\n"
        f"Минимум: {MIN_WITHDRAW:g}⭐"
    )


@router.callback_query(F.data.startswith("withdraw:stars_amount:"))
async def withdraw_stars_fixed_amount(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    user_id = callback.from_user.id
    amount = float(callback.data.split(":")[2])

    await state.update_data(method="stars", amount=amount)

    try:
        preview = await preview_withdrawal_via_api(
            user_id=user_id,
            payload={
                "method": "stars",
                "amount": amount,
                "wallet": None,
            },
        )
    except ApiClientError as e:
        await safe_edit_text(
            callback.message,
            e.detail,
            reply_markup=withdraw_back_kb(),
        )
        return

    fee = int(preview.get("expected_fee") or 0)

    if fee <= 0:
        try:
            await finalize_withdraw_request(
                message=callback.message,
                state=state,
                user_id=user_id,
                amount=amount,
                method="stars",
                wallet=None,
                paid_fee=0,
                fee_payment_charge_id=None,
                fee_invoice_payload=None,
            )
        except ApiClientError as e:
            if e.detail == "insufficient_balance":
                await callback.message.answer("❌ Недостаточно звезд на балансе")
                return
            await callback.message.answer(f"❌ Ошибка создания заявки: {e.detail}")
        return

    await state.update_data(
        amount=amount,
        method="stars",
        wallet=None,
        withdraw_fee=fee,
    )
    await state.set_state(WithdrawCreate.fee_payment)

    await callback.message.answer_invoice(
        title="Комиссия за вывод",
        description=f"Оплата комиссии {fee} Telegram Stars за вывод {amount:g}⭐",
        payload=f"withdraw_fee:{user_id}",
        currency="XTR",
        prices=[LabeledPrice(label="Комиссия за вывод", amount=fee)],
        provider_token="",
        start_parameter=f"withdraw-fee-{user_id}",
    )

    await callback.message.answer(
        f"Для продолжения оплати комиссию: {fee} Telegram Stars.\n"
        "После успешной оплаты заявка создастся автоматически."
    )

@router.message(WithdrawCreate.amount)
async def withdraw_enter_amount(message: Message, state: FSMContext):
    data = await state.get_data()
    method = data.get("method")

    if method != "ton":
        await state.clear()
        await message.answer("❌ Для вывода в звездах используй кнопки с фиксированной суммой.")
        return

    try:
        amount = float(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи число > 0, например 50")
        return

    await state.update_data(amount=amount)
    await state.set_state(WithdrawCreate.wallet)
    await message.answer("Введи TON-адрес кошелька для выплаты:")

@router.message(WithdrawCreate.wallet)
async def withdraw_enter_details(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    amount = float(data["amount"])
    wallet = message.text.strip()

    if len(wallet) < 10:
        await message.answer("❌ Похоже на неправильный TON-адрес. Введи еще раз.")
        return

    await state.update_data(wallet=wallet)

    await start_fee_payment_or_create(
        message=message,
        state=state,
        user_id=user_id,
        amount=amount,
        method="ton",
        wallet=wallet,
    )


@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery, state: FSMContext):
    data = await state.get_data()
    fee = int(data.get("withdraw_fee") or 0)
    expected_payload = f"withdraw_fee:{pre_checkout_query.from_user.id}"

    if pre_checkout_query.invoice_payload != expected_payload:
        await pre_checkout_query.answer(
            ok=False,
            error_message="Некорректный payload оплаты."
        )
        return

    if pre_checkout_query.currency != "XTR":
        await pre_checkout_query.answer(
            ok=False,
            error_message="Некорректная валюта оплаты."
        )
        return

    if fee <= 0 or pre_checkout_query.total_amount != fee:
        await pre_checkout_query.answer(
            ok=False,
            error_message="Сумма комиссии изменилась. Открой вывод заново."
        )
        return

    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, state: FSMContext):
    payment = message.successful_payment

    print("PAYMENT:", payment)
    print("CHARGE_ID:", payment.telegram_payment_charge_id)

    if not payment:
        return

    if payment.currency != "XTR":
        return

    user_id = message.from_user.id
    data = await state.get_data()

    expected_payload = f"withdraw_fee:{user_id}"
    if payment.invoice_payload != expected_payload:
        return

    amount = float(data.get("amount") or 0)
    method = data.get("method")
    wallet = data.get("wallet")
    fee = int(data.get("withdraw_fee") or 0)

    if amount <= 0 or method not in {"stars", "ton"}:
        await message.answer(
            "⚠️ Оплата прошла, но данные заявки не найдены. Напиши администратору."
        )
        return

    if payment.total_amount != fee:
        await message.answer(
            "⚠️ Оплата прошла, но сумма комиссии не совпала. Напиши администратору."
        )
        return

    try:
        await finalize_withdraw_request(
            message=message,
            state=state,
            user_id=user_id,
            amount=amount,
            method=method,
            wallet=wallet,
            paid_fee=fee,
            fee_payment_charge_id=payment.telegram_payment_charge_id,
            fee_invoice_payload=payment.invoice_payload,
        )
    except ApiClientError as e:
        if e.detail == "insufficient_balance":
            await message.answer(
                "⚠️ Комиссия оплачена, но на момент создания заявки на балансе уже не хватило звезд.\n\n"
                "Напишите администратору."
            )
            return

        await message.answer(
            "⚠️ Комиссия оплачена, но заявка не может быть создана автоматически.\n\n"
            f"{e.detail}\n\n"
            "Напиши администратору."
        )


@router.callback_query(F.data == "withdraw:my")
async def withdraw_my(callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    data = await get_my_withdrawals_via_api(user_id=user_id, limit=20)
    items = data.get("items", [])

    if not items:
        await safe_edit_text(
            callback.message,
            "📜 Мои заявки\n\n"
            "📭 У тебя пока нет заявок на вывод.",
            reply_markup=withdraw_back_kb()
        )
        return

    status_map = {
        "pending": "⏳ В обработке",
        "paid": "✅ Выплачено",
        "approved": "✅ Одобрено",
        "rejected": "❌ Отклонено",
        "cancelled": "🚫 Отменено",
    }

    lines = []
    for item in items:
        wid = item["id"]
        amount = float(item["amount"])
        method = item["method"]
        status = item["status"]
        created = item["created_at"]

        line = (
            f"#{wid} • {amount:g}⭐ • {str(method).upper()} • {status_map.get(status, status)}\n"
            f"{created}"
        )

        fee_xtr = int(item.get("fee_xtr") or 0)
        fee_paid = bool(item.get("fee_paid") or False)
        fee_refunded = bool(item.get("fee_refunded") or False)

        if fee_paid and fee_xtr > 0:
            line += f"\nКомиссия: {fee_xtr} XTR"
            if fee_refunded:
                line += " (возвращена)"

        wallet = item.get("wallet")
        if wallet and method == "ton":
            line += f"\nКошелек: {wallet}"

        lines.append(line)

    await safe_edit_text(
        callback.message,
        "📜 Мои заявки\n\n" + "\n\n".join(lines),
        reply_markup=withdraw_back_kb()
    )

@router.callback_query(F.data == "referrals")
async def show_referrals(callback: CallbackQuery, db):
    await callback.answer()

    user_id = callback.from_user.id
    invited_count = await get_referrals_count(db, user_id)

    me = await callback.bot.get_me()
    invite_link = f"https://t.me/{me.username}?start={user_id}"

    text = (
        "🫂 <b>Приглашайте друзей и получайте до 10% рефбека ⭐ с каждого их вывода!</b>\n\n"
        f"Ваша ссылка 👉🏻\n<code>{invite_link}</code>\n\n"
        f"👥 Всего приглашено: {invited_count}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=referrals_kb(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
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

async def safe_edit_text(message, text: str, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        raise

async def safe_edit_reply_markup(message, reply_markup=None):
    try:
        await message.edit_reply_markup(reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        raise

@router.callback_query(F.data == "client:home")
async def client_home(callback: CallbackQuery, db):
    user_id = callback.from_user.id

    if not await user_has_role(db, user_id, ROLE_CLIENT):
        await callback.answer("❌ Раздел клиента тебе пока недоступен.", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text(
        "🤝 <b>Кабинет клиента</b>\n\n"
        "Тут потом будут:\n"
        "• мои заказы\n"
        "• запуск просмотров\n"
        "• запуск подписок\n"
        "• статистика заказов",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
            ]
        )
    )


@router.callback_query(F.data == "partner:home")
async def partner_home(callback: CallbackQuery, db):
    user_id = callback.from_user.id

    if not await user_has_role(db, user_id, ROLE_PARTNER):
        await callback.answer("❌ Партнерский раздел тебе пока недоступен.", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text(
        "💼 <b>Кабинет партнера</b>\n\n"
        "Тут потом будут:\n"
        "• приглашенные клиенты\n"
        "• приглашенные юзеры\n"
        "• проценты / бонусы\n"
        "• партнерская статистика",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
            ]
        )
    )

def daily_checkin_text(current_day: int, already_claimed_today: bool) -> str:
    current_day = max(1, min(current_day, 30))
    next_day = 1 if current_day >= 30 else current_day + 1

    current_reward = round(current_day * 0.05, 2)
    next_reward = round(next_day * 0.05, 2)

    status = "✅ Ежедневный бонус уже получен" if already_claimed_today else "🎁 Ежедневный бонус доступен"

    return (
        f"{status}\n\n"
        f"🔥 День цикла: {current_day}/30\n"
        f"💰 Сегодня: {fmt_stars(current_reward)}⭐\n"
        f"📅 Завтра: {fmt_stars(next_reward)}⭐\n\n"
        "Заходите каждый день, чтобы не сбросился прогресс"
    )

@router.callback_query(F.data == "daily_checkin")
async def daily_checkin_open(callback: CallbackQuery):
    await callback.answer()

    status = await get_daily_checkin_status(callback.from_user.id)

    current_day = int(status["current_cycle_day"])
    already_claimed_today = bool(status["already_claimed_today"])

    await safe_edit_text(
        callback.message,
        daily_checkin_text(
            current_day=current_day,
            already_claimed_today=already_claimed_today,
        ),
        reply_markup=daily_checkin_kb(
            current_day=current_day,
            already_claimed_today=already_claimed_today,
        ),
    )

@router.callback_query(F.data == "daily_checkin:noop")
async def daily_checkin_noop(callback: CallbackQuery):
    await callback.answer()

@router.callback_query(F.data == "daily_checkin:claim")
async def daily_checkin_claim(callback: CallbackQuery):
    result = await claim_daily_checkin_via_api(callback.from_user.id)

    alert_text = result.get("message") or "Готово"
    await callback.answer(alert_text, show_alert=True)

    status = await get_daily_checkin_status(callback.from_user.id)

    current_day = int(status["current_cycle_day"])
    already_claimed_today = bool(status["already_claimed_today"])

    await safe_edit_text(
        callback.message,
        daily_checkin_text(
            current_day=current_day,
            already_claimed_today=already_claimed_today,
        ),
        reply_markup=daily_checkin_kb(
            current_day=current_day,
            already_claimed_today=already_claimed_today,
        ),
    )
