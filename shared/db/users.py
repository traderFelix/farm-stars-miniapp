import aiosqlite, json
from typing import Optional, Any
from datetime import datetime, timedelta, timezone

from bot.db import daily_checkin_reward, normalize_daily_cycle_day, tx # todo felix
from shared.config import (
    OWNER_ID, ADMIN_IDS, ROLE_USER, ROLE_CLIENT, ROLE_PARTNER, ROLE_ADMIN, ROLE_OWNER,
)

from shared.db.ledger import get_user_earnings_breakdown, get_activity_index, apply_balance_delta


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


def fmt_stars(value: float) -> str:
    text = f"{float(value):.2f}"
    text = text.rstrip("0").rstrip(".")
    return text if text else "0"


async def build_user_stats_text(db: aiosqlite.Connection, user_id: int) -> str:
    stats = await get_user_earnings_breakdown(db, user_id)

    return (
        f"⭐ Всего заработано: {fmt_stars(stats['total'])}⭐\n"
        f"{fmt_stars(stats['view_post_bonus'])} ({stats['view_post_bonus_pct']:.1f}%) — просмотр постов\n"
        f"{fmt_stars(stats['daily_bonus'])} ({stats['daily_bonus_pct']:.1f}%) — ежедневный бонус\n"
        f"{fmt_stars(stats['contest_bonus'])} ({stats['contest_bonus_pct']:.1f}%) — конкурсы\n"
        f"{fmt_stars(stats['referral_bonus'])} ({stats['referral_bonus_pct']:.1f}%) — рефералы\n"
        f"{fmt_stars(stats['admin_adjust'])} ({stats['admin_adjust_pct']:.1f}%) — начисления от админа"
    )


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
        "activity_index": await get_activity_index(db, user_id),
        "is_suspicious": bool(row["is_suspicious"]) if "is_suspicious" in row.keys() else False,
        "suspicious_reason": row["suspicious_reason"] if "suspicious_reason" in row.keys() else None,
        "created_at": row["created_at"] if "created_at" in row.keys() else None,
        "last_seen_at": row["last_seen_at"] if "last_seen_at" in row.keys() else None,
    }


async def get_referrer_id(db: aiosqlite.Connection, user_id: int) -> Optional[int]:
    async with db.execute(
            "SELECT referred_by FROM users WHERE user_id = ?",
            (int(user_id),),
    ) as cur:
        row = await cur.fetchone()

    if not row or row["referred_by"] is None:
        return None

    return int(row["referred_by"])


async def total_balances(db: aiosqlite.Connection) -> float:
    async with db.execute("SELECT COALESCE(SUM(balance), 0) AS s FROM users") as cur:
        row = await cur.fetchone()
    return float(row["s"] or 0.0)

async def top_users_by_balance(db: aiosqlite.Connection, limit: int = 10):
    async with db.execute(
            """
        SELECT username, balance
        FROM users
        ORDER BY balance DESC
        LIMIT ?
        """,
            (int(limit),),
    ) as cur:
        return await cur.fetchall()


async def bind_referrer(
        db: aiosqlite.Connection,
        user_id: int,
        referrer_id: int,
) -> bool:
    user_id = int(user_id)
    referrer_id = int(referrer_id)

    if user_id == referrer_id:
        return False

    async with db.execute(
            "SELECT referred_by FROM users WHERE user_id = ?",
            (user_id,),
    ) as cur:
        row = await cur.fetchone()

    if not row:
        return False

    if row["referred_by"] is not None:
        return False

    async with db.execute(
            "SELECT 1 FROM users WHERE user_id = ?",
            (referrer_id,),
    ) as cur:
        ref_exists = await cur.fetchone()

    if not ref_exists:
        return False

    await db.execute(
        """
        UPDATE users
        SET referred_by = ?
        WHERE user_id = ? AND referred_by IS NULL
        """,
        (referrer_id, user_id),
    )
    return True


async def get_referrals_count(db: aiosqlite.Connection, user_id: int) -> int:
    async with db.execute(
            "SELECT COUNT(*) AS c FROM users WHERE referred_by = ?",
            (int(user_id),),
    ) as cur:
        row = await cur.fetchone()
    return int(row["c"] or 0)


async def users_total_count(db: aiosqlite.Connection) -> int:
    async with db.execute("SELECT COUNT(*) AS c FROM users") as cur:
        row = await cur.fetchone()
    return int(row["c"])


async def users_new_since_hours(db: aiosqlite.Connection, hours: int) -> int:
    async with db.execute(
            "SELECT COUNT(*) AS c FROM users WHERE created_at >= datetime('now', ?)",
            (f"-{int(hours)} hours",),
    ) as cur:
        row = await cur.fetchone()
    return int(row["c"])


async def users_new_since_days(db: aiosqlite.Connection, days: int) -> int:
    async with db.execute(
            "SELECT COUNT(*) AS c FROM users WHERE created_at >= datetime('now', ?)",
            (f"-{int(days)} days",),
    ) as cur:
        row = await cur.fetchone()
    return int(row["c"])


async def users_active_since_days(db: aiosqlite.Connection, days: int) -> int:
    async with db.execute(
            "SELECT COUNT(*) AS c FROM users WHERE last_seen_at >= datetime('now', ?)",
            (f"-{int(days)} days",),
    ) as cur:
        row = await cur.fetchone()
    return int(row["c"])


async def users_growth_by_day(db: aiosqlite.Connection, days: int = 30):
    async with db.execute(
            """
        SELECT date(created_at) AS d, COUNT(*) AS cnt
        FROM users
        WHERE created_at >= datetime('now', ?)
        GROUP BY d
        ORDER BY d ASC
        """,
            (f"-{int(days)} days",),
    ) as cur:
        rows = await cur.fetchall()
    return [(r["d"], int(r["cnt"])) for r in rows]


async def user_created_hours_ago(db: aiosqlite.Connection, user_id: int) -> float:
    async with db.execute(
            """
        SELECT COALESCE((julianday('now') - julianday(created_at)) * 24.0, 0)
        FROM users
        WHERE user_id = ?
        """,
            (int(user_id),),
    ) as cur:
        row = await cur.fetchone()
        return float(row[0] or 0.0)


async def mark_user_suspicious(db, user_id: int, reason: str):
    row = await db.execute_fetchone(
        "SELECT is_suspicious, suspicious_reason FROM users WHERE user_id = ?",
        (user_id,),
    )
    if not row:
        return

    if row["is_suspicious"]:
        old_reason = row["suspicious_reason"] or ""
        if reason and reason not in old_reason:
            new_reason = f"{old_reason}; {reason}" if old_reason else reason
        else:
            new_reason = old_reason
    else:
        new_reason = reason

    await db.execute(
        """
        UPDATE users
        SET is_suspicious = 1,
            suspicious_reason = ?
        WHERE user_id = ?
        """,
        (new_reason, user_id),
    )
    await db.commit()


async def clear_user_suspicious(db, user_id: int):
    await db.execute(
        """
        UPDATE users
        SET is_suspicious = 0,
            suspicious_reason = NULL
        WHERE user_id = ?
        """,
        (user_id,),
    )
    await db.commit()


async def claim_daily_checkin(
        db,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
):
    uid = int(user_id)

    now = datetime.now(timezone.utc)
    today = now.date()
    yesterday = today - timedelta(days=1)

    async with tx(db, immediate=True):
        await register_user(db, uid, username, first_name, last_name)

        async with db.execute(
                """
            SELECT daily_checkin_cycle_day, last_daily_checkin_at
            FROM users
            WHERE user_id = ?
            """,
                (uid,),
        ) as cur:
            row = await cur.fetchone()

        cycle_day = int(row["daily_checkin_cycle_day"] or 0)
        last_checkin_raw = row["last_daily_checkin_at"]

        last_date = None
        if last_checkin_raw:
            last_date = datetime.fromisoformat(last_checkin_raw).date()

        if last_date == today:
            balance = await get_balance(db, uid)
            return False, "", balance

        if last_date == yesterday:
            new_cycle_day = normalize_daily_cycle_day(cycle_day + 1)
        else:
            new_cycle_day = 1

        reward = daily_checkin_reward(new_cycle_day)
        next_cycle_day = normalize_daily_cycle_day(new_cycle_day + 1)
        next_reward = daily_checkin_reward(next_cycle_day)

        await db.execute(
            """
            UPDATE users
            SET daily_checkin_cycle_day = ?, last_daily_checkin_at = ?
            WHERE user_id = ?
            """,
            (new_cycle_day, now.isoformat(), uid),
        )

        await apply_balance_delta(
            db=db,
            user_id=uid,
            delta=reward,
            reason="daily_bonus",
            meta=json.dumps(
                {
                    "type": "daily_bonus",
                    "cycle_day": new_cycle_day,
                    "reward": reward,
                },
                ensure_ascii=False,
            ),
        )

        balance = await get_balance(db, uid)

        text = (
            f"🎁 Вы получили {fmt_stars(reward)}⭐\n\n"
            f"📅 Приходите завтра и забирайте {fmt_stars(next_reward)}⭐"
        )

        return True, text, balance


async def _column_exists(db: aiosqlite.Connection, table_name: str, column_name: str) -> bool:
    async with db.execute(f"PRAGMA table_info({table_name})") as cur:
        rows = await cur.fetchall()

    for row in rows:
        name = row["name"] if isinstance(row, aiosqlite.Row) else row[1]
        if name == column_name:
            return True
    return False


async def ensure_users_role_schema(db: aiosqlite.Connection) -> None:
    if not await _column_exists(db, "users", "role_level"):
        await db.execute(
            f"ALTER TABLE users ADD COLUMN role_level INTEGER NOT NULL DEFAULT {ROLE_USER}"
        )

    await db.execute(
        f"""
        UPDATE users
        SET role_level = COALESCE(role_level, {ROLE_USER})
        """
    )

    await db.execute(
        """
            UPDATE users
            SET role_level = CASE
                WHEN COALESCE(role_level, 0) < ? THEN ?
                ELSE role_level
            END
            WHERE user_id = ?
            """,
        (ROLE_OWNER, ROLE_OWNER, OWNER_ID),
    )

    for admin_id in ADMIN_IDS:
        await db.execute(
            """
            UPDATE users
            SET role_level = CASE
                WHEN COALESCE(role_level, 0) < ? THEN ?
                ELSE role_level
            END
            WHERE user_id = ?
            """,
            (ROLE_ADMIN, ROLE_ADMIN, int(admin_id)),
        )

