from typing import Any


def format_admin_user_profile_card(profile: dict[str, Any]) -> str:
    user_id = profile["user_id"]
    username = profile.get("username")
    balance = float(profile.get("balance") or 0)
    role = profile.get("role") or "пользователь"
    activity_index = float(profile.get("activity_index") or 0)
    is_suspicious = bool(profile.get("is_suspicious") or False)
    suspicious_reason = profile.get("suspicious_reason") or "-"

    uname_line = f"@{username}" if username else "без username"

    if is_suspicious:
        suspicious_block = (
            f"⚠️ Подозрительный\n"
            f"Причина: {suspicious_reason}"
        )
    else:
        suspicious_block = "✅ Не подозрительный"

    if activity_index <= 1:
        activity_text = f"{activity_index * 100:.1f}%"
    else:
        activity_text = f"{activity_index:.1f}%"

    return (
        f"👤 Пользователь: {user_id}\n"
        f"Username: {uname_line}\n"
        f"Баланс: {balance:.2f}⭐\n\n"
        f"Роль: {role}\n"
        f"Индекс активности: {activity_text}\n\n"
        f"{suspicious_block}"
    )