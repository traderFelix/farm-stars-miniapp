from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from shared.config import WEB_ORIGIN_NGROK, ROLE_ADMIN, ROLE_CLIENT, ROLE_PARTNER

# ---------- USER KEYBOARDS ----------

MINIAPP_MENU_BUTTON_TEXT = "Запустить"


def _miniapp_button() -> InlineKeyboardButton:
    if not WEB_ORIGIN_NGROK:
        raise RuntimeError("Environment variable WEB_ORIGIN_NGROK is required")

    return InlineKeyboardButton(
        text="🚀 Открыть приложение",
        web_app=WebAppInfo(url=WEB_ORIGIN_NGROK),
    )


def miniapp_menu_button() -> MenuButtonWebApp:
    if not WEB_ORIGIN_NGROK:
        raise RuntimeError("Environment variable WEB_ORIGIN_NGROK is required")

    return MenuButtonWebApp(
        text=MINIAPP_MENU_BUTTON_TEXT,
        web_app=WebAppInfo(url=WEB_ORIGIN_NGROK),
    )


def main_menu(role_level: int = 0) -> InlineKeyboardMarkup:
    rows = [
        [_miniapp_button()],
        [InlineKeyboardButton(text="👁 Просмотр постов", callback_data="tasks")],
    ]
    if role_level >= ROLE_CLIENT:
        rows.append([InlineKeyboardButton(text="🤝 Кабинет клиента", callback_data="client:home")])
    if role_level >= ROLE_PARTNER:
        rows.append([InlineKeyboardButton(text="💼 Кабинет партнера", callback_data="partner:home")])
    if role_level >= ROLE_ADMIN:
        rows.append([InlineKeyboardButton(text="🔐 Админка", callback_data="adm:home")])

    return InlineKeyboardMarkup(inline_keyboard=rows)

def tasks_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👁 Смотреть пост", callback_data="task:view_post")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="back")],
        ]
    )

def task_after_view_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👁 Смотреть следующий пост", callback_data="task:view_post")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="back")],
        ]
    )


# ---------- ADMIN KEYBOARDS ----------

def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏆 Конкурсы", callback_data="adm:campaigns_menu")],
            [InlineKeyboardButton(text="🎟 Промокоды", callback_data="adm:promos_menu")],
            [InlineKeyboardButton(text="📢 Подписки", callback_data="adm:sub:list")],
            [InlineKeyboardButton(text="📺 Каналы просмотров", callback_data="adm:tch:list")],
            [InlineKeyboardButton(text="📈 Рост пользователей", callback_data="adm:growth_png")],
            [InlineKeyboardButton(text="📜 Леджер", callback_data="adm:ledger_last")],
            [InlineKeyboardButton(text="🔎 Детали пользователя", callback_data="adm:user_balance")],
            [InlineKeyboardButton(text="🏆 Топ по балансу", callback_data="adm:top")],
            [InlineKeyboardButton(text="💸 Заявки на вывод", callback_data="adm:wd:list")],
            [InlineKeyboardButton(text="↩️ Возврат комсы", callback_data="adm:fee_refund_menu")],
            [InlineKeyboardButton(text="🧮 Сверка балансов", callback_data="adm:audit")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="back")],
        ]
    )


def admin_campaigns_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Все конкурсы", callback_data="adm:list")],
            [InlineKeyboardButton(text="➕ Создать конкурс", callback_data="adm:new")],
            [InlineKeyboardButton(text="📊 Статистика конкурсов", callback_data="adm:stats_menu")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="adm:back")],
        ]
    )


def admin_promos_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎟 Все промокоды", callback_data="adm:promo:list")],
            [InlineKeyboardButton(text="➕ Создать промокод", callback_data="adm:promo:new")],
            [InlineKeyboardButton(text="📊 Статистика промокодов", callback_data="adm:promo:stats_menu")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="adm:back")],
        ]
    )

def admin_withdraw_list_kb(rows):
    kb = []
    for row in rows:
        if isinstance(row, dict):
            wid = int(row["id"])
            user_id = int(row["user_id"])
            username = row.get("username")
            amount = float(row.get("amount") or 0)
            method = row.get("method")
        else:
            wid, user_id, username, amount, method, wallet, status, created_at = row
        name = f"@{username}" if username else f"id:{user_id}"
        kb.append([InlineKeyboardButton(
            text=f"#{wid} {name} — {float(amount):g}⭐ ({method})",
            callback_data=f"adm:wd:open:{wid}"
        )])
    kb.append([InlineKeyboardButton(text="⬅ Назад", callback_data="adm:back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def admin_withdraw_actions_kb(withdrawal_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выплатил", callback_data=f"adm:wd:paid:{withdrawal_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm:wd:reject:{withdrawal_id}")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="adm:wd:list")],
    ])

def user_actions_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика ⭐", callback_data=f"adm:user:stats:{user_id}",)],
            [InlineKeyboardButton(text="⚔️ Батлы", callback_data=f"adm:user:battles:{user_id}",)],
            [InlineKeyboardButton(text="🕵️ Воровство", callback_data=f"adm:user:thefts:{user_id}",)],
            [InlineKeyboardButton(text="📜 Последние операции", callback_data=f"adm:user:ledger:{user_id}",)],
            [InlineKeyboardButton(text="🛡 Риск-история", callback_data=f"adm:user:risk:{user_id}",)],
            [InlineKeyboardButton(text="🔧 Изменить роль", callback_data=f"adm:user:role:{user_id}")],
            [InlineKeyboardButton(text="➕ Начислить ⭐", callback_data=f"adm:ub:add:{user_id}",)],
            [InlineKeyboardButton(text="➖ Списать ⭐", callback_data=f"adm:ub:sub:{user_id}",)],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="adm:back",)],
        ]
    )

def admin_back_kb(callback_data: str = "adm:back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅ Назад", callback_data=callback_data)]
        ]
    )


def _status_icon(status: str) -> str:
    if status == "active":
        return "🟢"
    if status == "ended":
        return "🔴"
    if status == "draft":
        return "🟡"
    return "⚪"

def campaigns_list_kb(rows, back_callback: str = "adm:back") -> InlineKeyboardMarkup:
    keyboard = []
    for row in rows[:50]:
        if isinstance(row, dict):
            key = row["campaign_key"]
            amount = row.get("reward_amount") or 0
            status = row.get("status") or "draft"
        else:
            key, amount, status, created_at = row
        icon = _status_icon(str(status))
        keyboard.append([
            InlineKeyboardButton(
                text=f"{icon} {key} — {float(amount):g}⭐",
                callback_data=f"adm:open:{key}"
            )
        ])

    keyboard.append([InlineKeyboardButton(text="⬅ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def stats_list_kb(rows, back_callback: str = "adm:back") -> InlineKeyboardMarkup:
    keyboard = []
    for row in rows:
        if isinstance(row, dict):
            key = row["campaign_key"]
            status = row.get("status") or "draft"
        else:
            key, amount, status, created_at = row
        icon = _status_icon(str(status))
        keyboard.append([
            InlineKeyboardButton(
                text=f"{icon} {key}",
                callback_data=f"adm:stats:{key}"
            )
        ])

    keyboard.append([InlineKeyboardButton(text="⬅ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def campaign_manage_kb(key: str, status: str) -> InlineKeyboardMarkup:
    keyboard = []

    if status == "active":
        keyboard.append([InlineKeyboardButton(text="🔴 Выключить", callback_data=f"adm:off:{key}")])
    else:
        keyboard.append([InlineKeyboardButton(text="🟢 Включить", callback_data=f"adm:on:{key}")])

    keyboard.append([
        InlineKeyboardButton(text="➕ Добавить победителей", callback_data=f"adm:add_winners:{key}"),
        InlineKeyboardButton(text="👥 Победители", callback_data=f"adm:show_winners:{key}"),
    ])

    keyboard.append([
        InlineKeyboardButton(text="➖ Удалить победителя", callback_data=f"adm:winner_del:{key}"),
        InlineKeyboardButton(text="🗑 Удалить конкурс", callback_data=f"adm:del:ask:{key}"),
    ])

    keyboard.append([
        InlineKeyboardButton(text="⬅ Назад", callback_data="adm:list"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def campaign_delete_confirm_kb(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"adm:del:do:{key}")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data=f"adm:open:{key}")],
        ]
    )

def campaign_created_kb(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📂 Открыть конкурс", callback_data=f"adm:open:{key}")],
            [InlineKeyboardButton(text="📋 Все конкурсы", callback_data="adm:list")],
        ]
    )


def promos_list_kb(rows, back_callback: str = "adm:back") -> InlineKeyboardMarkup:
    keyboard = []
    for row in rows[:50]:
        icon = _status_icon(str(row.get("status") or "draft"))
        code = row["promo_code"]
        amount = float(row.get("reward_amount") or 0)
        uses = int(row.get("remaining_uses") or 0)
        keyboard.append([
            InlineKeyboardButton(
                text=f"{icon} {code} — {amount:g}⭐ × {uses}",
                callback_data=f"adm:promo:open:{code}",
            )
        ])

    keyboard.append([InlineKeyboardButton(text="⬅ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def promo_manage_kb(code: str, status: str) -> InlineKeyboardMarkup:
    keyboard = []

    if status == "active":
        keyboard.append([InlineKeyboardButton(text="🔴 Выключить", callback_data=f"adm:promo:off:{code}")])
    else:
        keyboard.append([InlineKeyboardButton(text="🟢 Включить", callback_data=f"adm:promo:on:{code}")])

    keyboard.append([InlineKeyboardButton(text="📊 Статистика", callback_data=f"adm:promo:stats:{code}")])
    keyboard.append([InlineKeyboardButton(text="🗑 Удалить промокод", callback_data=f"adm:promo:del:ask:{code}")])
    keyboard.append([InlineKeyboardButton(text="⬅ Назад", callback_data="adm:promo:list")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def promo_delete_confirm_kb(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"adm:promo:del:do:{code}")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data=f"adm:promo:open:{code}")],
        ]
    )


def promo_created_kb(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📂 Открыть промокод", callback_data=f"adm:promo:open:{code}")],
            [InlineKeyboardButton(text="🎟 Все промокоды", callback_data="adm:promo:list")],
        ]
    )


def promo_stats_list_kb(rows, back_callback: str = "adm:back") -> InlineKeyboardMarkup:
    keyboard = []
    for row in rows[:50]:
        icon = _status_icon(str(row.get("status") or "draft"))
        code = row["promo_code"]
        keyboard.append([
            InlineKeyboardButton(
                text=f"{icon} {code}",
                callback_data=f"adm:promo:stats:{code}",
            )
        ])

    keyboard.append([InlineKeyboardButton(text="⬅ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def user_details_kb(user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Детали пользователя", callback_data=f"adm:user:details:{user_id}")
    builder.button(text="⬅️ Назад", callback_data="adm:users")
    builder.adjust(1)
    return builder.as_markup()


def admin_fee_refund_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Вернуть вручную", callback_data="adm:fee_refund_manual")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="adm:back")],
        ]
    )

def admin_task_channels_kb(rows) -> InlineKeyboardMarkup:
    kb = []

    for row in rows:
        channel_id = int(row["id"])
        title = row["title"] or row["chat_id"]
        is_active = int(row["is_active"] or 0)
        remaining = int(row["remaining_views"] or 0)
        status = "🟢" if is_active else "🔴"
        kb.append([
            InlineKeyboardButton(
                text=f"{status} {title} • остаток {remaining}",
                callback_data=f"adm:tch:open:{channel_id}",
            )
        ])

    kb.append([InlineKeyboardButton(text="➕ Подключить канал", callback_data="adm:tch:new")])
    kb.append([InlineKeyboardButton(text="⬅ Назад", callback_data="adm:back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def admin_task_channel_card_kb(channel_id: int, is_active: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить пост вручную", callback_data=f"adm:tch:manual_post_start:{channel_id}")],
            [InlineKeyboardButton(text="📊 Статус по постам", callback_data=f"adm:tch:posts:{channel_id}")],
            [InlineKeyboardButton(text="👤 Привязать клиента", callback_data=f"adm:tch:client:{channel_id}")],
            [InlineKeyboardButton(text="⚙️ Редактировать параметры", callback_data=f"adm:tch:edit:{channel_id}")],
            [InlineKeyboardButton(
                text="🔴 Отключить канал" if is_active else "🟢 Включить канал",
                callback_data=f"adm:tch:toggle:{channel_id}",
            )],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="adm:tch:list")],
        ]
    )


def admin_task_channel_manual_post_confirm_kb(channel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Добавить пост", callback_data="adm:tch:manual_post:add")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"adm:tch:manual_post:cancel:{int(channel_id)}")],
        ]
    )


def admin_subscription_tasks_kb(rows) -> InlineKeyboardMarkup:
    kb = []

    for row in rows:
        task_id = int(row["id"])
        title = row.get("title") or row.get("chat_id") or f"#{task_id}"
        is_active = bool(row.get("is_active"))
        participants = int(row.get("participants_count") or 0)
        max_subscribers = int(row.get("max_subscribers") or 0)
        total_reward = float(row.get("total_reward") or 0)
        status = "🟢" if is_active else "🔴"
        kb.append([
            InlineKeyboardButton(
                text=f"{status} {title} • {participants}/{max_subscribers} • {total_reward:g}⭐",
                callback_data=f"adm:sub:open:{task_id}",
            )
        ])

    kb.append([InlineKeyboardButton(text="➕ Создать подписку", callback_data="adm:sub:new")])
    kb.append([InlineKeyboardButton(text="⬅ Назад", callback_data="adm:back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def admin_subscription_task_card_kb(task_id: int, is_active: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔴 Отключить" if is_active else "🟢 Включить",
                callback_data=f"adm:sub:toggle:{int(task_id)}:{0 if is_active else 1}",
            )],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="adm:sub:list")],
        ]
    )

def admin_growth_photo_kb(origin_message_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="⬅ Назад",
                callback_data=f"adm:growth_back:{origin_message_id}"
            )]
        ]
    )
