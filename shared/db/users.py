import aiosqlite
from typing import Optional, Any

from shared.config import (
    OWNER_ID,
    ADMIN_IDS,
    ROLE_USER,
    ROLE_CLIENT,
    ROLE_PARTNER,
    ROLE_ADMIN,
    ROLE_OWNER,
    SYSTEM_REASONS,
    GOOD_ACTIVITY_REASONS,
)


def normalize_role_level(role_level: int) -> int:
    value = int(role_level)
    if value < ROLE_USER:
        return ROLE_USER
    if value > ROLE_OWNER:
        return ROLE_OWNER
    return value


def role_title_from_level(role_level: int) -> str:
    value = normalize_role_level(role_level)

    if value >= ROLE_OWNER:
        return "владелец"
    if value >= ROLE_ADMIN:
        return "админ"
    if value >= ROLE_PARTNER:
        return "партнер"
    if value >= ROLE_CLIENT:
        return "клиент"
    return "пользователь"


def bootstrap_role_level_for_user_id(user_id: int) -> int:
    uid = int(user_id)

    if uid == OWNER_ID:
        return ROLE_OWNER
    if uid in ADMIN_IDS:
        return ROLE_ADMIN
    return ROLE_USER


def has_role_level(current_level: int, required_level: int) -> bool:
    return int(current_level) >= int(required_level)


async def get_user_by_id(db: aiosqlite.Connection, user_id: int):
    async with db.execute(
            """
        SELECT user_id, username, tg_first_name, tg_last_name, balance, role_level,
               is_suspicious, suspicious_reason, created_at, last_seen_at
        FROM users
        WHERE user_id = ?
        """,
            (int(user_id),),
    ) as cur:
        return await cur.fetchone()


async def register_user(
        db: aiosqlite.Connection,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
) -> None:
    u = (username or "").strip().lstrip("@") or None
    fn = (first_name or "").strip() or None
    ln = (last_name or "").strip() or None

    bootstrap_level = bootstrap_role_level_for_user_id(user_id)

    async with db.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            (int(user_id),),
    ) as cur:
        exists = await cur.fetchone() is not None

    if not exists:
        await db.execute(
            """
            INSERT INTO users (
                user_id, username, tg_first_name, tg_last_name,
                balance, role_level, created_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, 0, ?, datetime('now'), datetime('now'))
            """,
            (int(user_id), u, fn, ln, bootstrap_level),
        )
        return

    await db.execute(
        """
        UPDATE users
        SET username = COALESCE(?, username),
            tg_first_name = COALESCE(?, tg_first_name),
            tg_last_name = COALESCE(?, tg_last_name),
            role_level = CASE
                WHEN COALESCE(role_level, 0) < ? THEN ?
                ELSE role_level
            END,
            last_seen_at = datetime('now')
        WHERE user_id = ?
        """,
        (u, fn, ln, bootstrap_level, bootstrap_level, int(user_id)),
    )


async def update_user_telegram_fields(
        db: aiosqlite.Connection,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
) -> None:
    """
    Удобная обертка для API-сервиса.
    По сути использует ту же логику, что и register_user.
    """
    await register_user(
        db=db,
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
    )


async def get_user_role_level(db: aiosqlite.Connection, user_id: int) -> int:
    async with db.execute(
            """
        SELECT COALESCE(role_level, ?) AS role_level
        FROM users
        WHERE user_id = ?
        """,
            (ROLE_USER, int(user_id)),
    ) as cur:
        row = await cur.fetchone()

    db_level = int(row["role_level"]) if row else ROLE_USER
    bootstrap_level = bootstrap_role_level_for_user_id(user_id)
    return max(db_level, bootstrap_level)


async def get_user_role_name(db: aiosqlite.Connection, user_id: int) -> str:
    return role_title_from_level(await get_user_role_level(db, user_id))


async def user_has_role(
        db: aiosqlite.Connection,
        user_id: int,
        required_level: int,
) -> bool:
    current_level = await get_user_role_level(db, user_id)
    return has_role_level(current_level, required_level)


async def set_user_role_level(
        db: aiosqlite.Connection,
        user_id: int,
        role_level: int,
) -> bool:
    target_level = normalize_role_level(role_level)

    async with db.execute(
            "SELECT 1 FROM users WHERE user_id = ?",
            (int(user_id),),
    ) as cur:
        exists = await cur.fetchone()

    if not exists:
        return False

    if target_level >= ROLE_OWNER:
        target_level = ROLE_ADMIN

    target_level = max(target_level, bootstrap_role_level_for_user_id(user_id))

    await db.execute(
        """
        UPDATE users
        SET role_level = ?
        WHERE user_id = ?
        """,
        (target_level, int(user_id)),
    )
    return True


async def get_balance(db: aiosqlite.Connection, user_id: int) -> float:
    async with db.execute(
            "SELECT balance FROM users WHERE user_id = ?",
            (int(user_id),),
    ) as cur:
        row = await cur.fetchone()
    return float(row["balance"]) if row else 0.0


async def get_user_earnings_breakdown(db: aiosqlite.Connection, user_id: int) -> dict[str, float]:
    system_placeholders = ",".join("?" for _ in SYSTEM_REASONS)

    query = f"""
        SELECT
            COALESCE(SUM(CASE WHEN reason = 'view_post_bonus' THEN delta ELSE 0 END), 0) AS view_post_bonus,
            COALESCE(SUM(CASE WHEN reason = 'daily_bonus' THEN delta ELSE 0 END), 0) AS daily_bonus,
            COALESCE(SUM(CASE WHEN reason = 'contest_bonus' THEN delta ELSE 0 END), 0) AS contest_bonus,
            COALESCE(SUM(CASE WHEN reason = 'referral_bonus' THEN delta ELSE 0 END), 0) AS referral_bonus,
            COALESCE(SUM(CASE WHEN reason = 'admin_adjust' THEN delta ELSE 0 END), 0) AS admin_adjust,
            COALESCE(
                SUM(
                    CASE
                        WHEN reason NOT IN ({system_placeholders})
                        THEN delta ELSE 0
                    END
                ),
                0
            ) AS total_earned
        FROM ledger
        WHERE user_id = ?
    """

    params = (*SYSTEM_REASONS, int(user_id))
    async with db.execute(query, params) as cursor:
        row = await cursor.fetchone()

    view_post_bonus = float(row["view_post_bonus"] or 0)
    daily_bonus = float(row["daily_bonus"] or 0)
    contest_bonus = float(row["contest_bonus"] or 0)
    referral_bonus = float(row["referral_bonus"] or 0)
    admin_adjust = float(row["admin_adjust"] or 0)
    total = float(row["total_earned"] or 0)

    def pct(value: float, total_value: float) -> float:
        if total_value == 0:
            return 0.0
        return value * 100 / total_value

    return {
        "total": total,
        "view_post_bonus": view_post_bonus,
        "view_post_bonus_pct": pct(view_post_bonus, total),
        "daily_bonus": daily_bonus,
        "daily_bonus_pct": pct(daily_bonus, total),
        "contest_bonus": contest_bonus,
        "contest_bonus_pct": pct(contest_bonus, total),
        "referral_bonus": referral_bonus,
        "referral_bonus_pct": pct(referral_bonus, total),
        "admin_adjust": admin_adjust,
        "admin_adjust_pct": pct(admin_adjust, total),
    }


async def get_user_admin_details(db: aiosqlite.Connection, user_id: int):
    async with db.execute(
            """
        SELECT user_id, username, balance, is_suspicious, suspicious_reason
        FROM users
        WHERE user_id = ?
        """,
            (int(user_id),),
    ) as cursor:
        return await cursor.fetchone()


def _fmt_stars(value: float) -> str:
    text = f"{float(value):.2f}"
    text = text.rstrip("0").rstrip(".")
    return text if text else "0"


async def build_user_stats_text(db: aiosqlite.Connection, user_id: int) -> str:
    stats = await get_user_earnings_breakdown(db, user_id)

    return (
        f"⭐ Всего заработано: {_fmt_stars(stats['total'])}⭐\n"
        f"{_fmt_stars(stats['view_post_bonus'])} ({stats['view_post_bonus_pct']:.1f}%) — просмотр постов\n"
        f"{_fmt_stars(stats['daily_bonus'])} ({stats['daily_bonus_pct']:.1f}%) — ежедневный бонус\n"
        f"{_fmt_stars(stats['contest_bonus'])} ({stats['contest_bonus_pct']:.1f}%) — конкурсы\n"
        f"{_fmt_stars(stats['referral_bonus'])} ({stats['referral_bonus_pct']:.1f}%) — рефералы\n"
        f"{_fmt_stars(stats['admin_adjust'])} ({stats['admin_adjust_pct']:.1f}%) — начисления от админа"
    )


async def get_activity_index(db, user_id: int) -> float:
    system_placeholders = ",".join("?" for _ in SYSTEM_REASONS)
    good_placeholders = ",".join("?" for _ in GOOD_ACTIVITY_REASONS)

    sql = f"""
    SELECT
        COALESCE(SUM(CASE
            WHEN delta > 0 AND reason IN ({good_placeholders}) THEN delta
            ELSE 0
        END), 0) AS good_total,
        COALESCE(SUM(CASE
            WHEN delta > 0 THEN delta
            ELSE 0
        END), 0) AS total_earned
    FROM ledger
    WHERE user_id = ?
      AND reason NOT IN ({system_placeholders})
    """

    params = [*GOOD_ACTIVITY_REASONS, int(user_id), *SYSTEM_REASONS]

    async with db.execute(sql, params) as cur:
        row = await cur.fetchone()

    good_total = float(row["good_total"] or 0)
    total_earned = float(row["total_earned"] or 0)

    if total_earned <= 0:
        return 0.0

    return (good_total / total_earned) * 100.0


async def build_user_profile(db: aiosqlite.Connection, user_id: int) -> Optional[dict[str, Any]]:
    row = await get_user_by_id(db, user_id)
    if not row:
        return None

    role_level = await get_user_role_level(db, user_id)

    return {
        "user_id": int(row["user_id"]),
        "username": row["username"],
        "first_name": row["tg_first_name"],
        "last_name": row["tg_last_name"],
        "balance": float(row["balance"] or 0),
        "role_level": int(role_level),
        "role": role_title_from_level(role_level),
        "activity_index": get_activity_index(db, user_id),
        "is_suspicious": bool(row["is_suspicious"]) if "is_suspicious" in row.keys() else False,
        "suspicious_reason": row["suspicious_reason"] if "suspicious_reason" in row.keys() else None,
        "created_at": row["created_at"] if "created_at" in row.keys() else None,
        "last_seen_at": row["last_seen_at"] if "last_seen_at" in row.keys() else None,
    }