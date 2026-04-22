import aiosqlite, json, re, secrets
from typing import Optional, Any
from datetime import datetime, timedelta, timezone

from shared.db.common import (
    tx,
    normalize_daily_cycle_day,
    daily_checkin_reward,
    daily_checkin_schedule,
    daily_checkin_season_length,
)
from shared.formatting import fmt_stars
from shared.config import (
    OWNER_ID, ADMIN_IDS, ROLE_USER, ROLE_CLIENT, ROLE_PARTNER, ROLE_ADMIN, ROLE_OWNER,
    RISK_SCORE_SUSPICIOUS_THRESHOLD,
)

_RISK_SCORE_CAP = 100.0
_GAME_NICKNAME_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_LEGACY_AUTO_GAME_NICKNAME_RE = re.compile(r"^Шахтер [0-9A-F]{6}$")


def default_game_nickname_for_user_id(user_id: int) -> str:
    return f"Шахтер {int(user_id) % 100000:05d}"


def normalize_game_nickname(value: Optional[str]) -> str:
    return " ".join((value or "").strip().split())


def _is_legacy_auto_game_nickname(value: Optional[str]) -> bool:
    normalized = normalize_game_nickname(value)
    return bool(_LEGACY_AUTO_GAME_NICKNAME_RE.fullmatch(normalized))


async def _is_game_nickname_taken(
        db: aiosqlite.Connection,
        nickname: str,
        *,
        exclude_user_id: Optional[int] = None,
) -> bool:
    normalized_nickname = normalize_game_nickname(nickname)
    if not normalized_nickname:
        return False

    query = """
        SELECT 1
        FROM users
        WHERE game_nickname = ? COLLATE NOCASE
    """
    params: list[Any] = [normalized_nickname]
    if exclude_user_id is not None:
        query += " AND user_id != ?"
        params.append(int(exclude_user_id))
    query += " LIMIT 1"

    async with db.execute(query, tuple(params)) as cur:
        row = await cur.fetchone()
    return row is not None


async def _generate_unique_game_nickname(db: aiosqlite.Connection) -> str:
    for _ in range(128):
        suffix = "".join(secrets.choice(_GAME_NICKNAME_ALPHABET) for _ in range(5))
        candidate = f"Шахтер {suffix}"
        if not await _is_game_nickname_taken(db, candidate):
            return candidate

    raise RuntimeError("Не удалось сгенерировать уникальный игровой ник")


async def _backfill_game_nicknames(db: aiosqlite.Connection) -> None:
    async with db.execute(
            """
        SELECT user_id, game_nickname
        FROM users
        WHERE game_nickname IS NULL
           OR TRIM(game_nickname) = ''
           OR game_nickname GLOB 'Шахтер [0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F]'
        ORDER BY user_id ASC
        """
    ) as cur:
        rows = await cur.fetchall()

    for row in rows:
        current_nickname = row["game_nickname"] if "game_nickname" in row.keys() else None
        if current_nickname and not _is_legacy_auto_game_nickname(current_nickname):
            continue

        next_nickname = await _generate_unique_game_nickname(db)
        await db.execute(
            """
            UPDATE users
            SET game_nickname = COALESCE(NULLIF(TRIM(game_nickname), ''), ?)
            WHERE user_id = ?
            """,
            (next_nickname, int(row["user_id"])),
        )
        if current_nickname and _is_legacy_auto_game_nickname(current_nickname):
            await db.execute(
                """
                UPDATE users
                SET game_nickname = ?
                WHERE user_id = ?
                """,
                (next_nickname, int(row["user_id"])),
            )


async def _column_exists(db: aiosqlite.Connection, table_name: str, column_name: str) -> bool:
    async with db.execute(f"PRAGMA table_info({table_name})") as cur:
        rows = await cur.fetchall()

    for row in rows:
        name = row["name"] if isinstance(row, aiosqlite.Row) else row[1]
        if name == column_name:
            return True
    return False


async def ensure_users_risk_schema(db: aiosqlite.Connection) -> None:
    if not await _column_exists(db, "users", "risk_score"):
        await db.execute("ALTER TABLE users ADD COLUMN risk_score REAL NOT NULL DEFAULT 0")

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS risk_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            delta REAL NOT NULL,
            score_after REAL NOT NULL DEFAULT 0,
            reason TEXT,
            source TEXT,
            meta TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS risk_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            risk_key TEXT NOT NULL,
            score REAL NOT NULL DEFAULT 0,
            reason TEXT,
            source TEXT,
            meta TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(user_id, risk_key)
        )
        """
    )


async def ensure_users_profile_schema(db: aiosqlite.Connection) -> None:
    if not await _column_exists(db, "users", "game_nickname"):
        await db.execute("ALTER TABLE users ADD COLUMN game_nickname TEXT")
    if not await _column_exists(db, "users", "game_nickname_change_count"):
        await db.execute("ALTER TABLE users ADD COLUMN game_nickname_change_count INTEGER NOT NULL DEFAULT 0")

    await db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_game_nickname_unique
        ON users(game_nickname COLLATE NOCASE)
        WHERE game_nickname IS NOT NULL AND TRIM(game_nickname) != ''
        """
    )
    await db.execute(
        """
        UPDATE users
        SET game_nickname_change_count = COALESCE(game_nickname_change_count, 0)
        """
    )
    await _backfill_game_nicknames(db)


def _risk_flag_key(source: Optional[str], reason: Optional[str]) -> str:
    normalized_source = (source or "system").strip().lower() or "system"
    normalized_reason = " ".join((reason or "unknown").strip().lower().split()) or "unknown"
    return f"{normalized_source}::{normalized_reason}"


_RISK_CASE_WEIGHTS = (
    {"source": "auth", "reason": "Зафиксирован кластер аккаунтов с одинаковым устройством/сетью", "weight": 45.0},
    {"source": "auth", "reason": "Подозрительный реферальный кластер по fingerprint", "weight": 30.0},
    {"source": "withdrawals", "reason": "Общий TON-кошелек с другим аккаунтом", "weight": 100.0},
    {"source": "withdrawals", "reason": "Слишком много неудачных попыток вывода", "weight": 15.0},
    {"source": "withdrawals", "reason": "Слишком много preview заявок на вывод", "weight": 10.0},
    {"source": "battles", "reason": "Подозрительная серия побед над одним и тем же соперником", "weight": 35.0},
    {"source": "battles", "reason": "Подозрительная серия поражений от одного и того же соперника", "weight": 35.0},
    {"source": "battles", "reason": "Слишком частые батлы против одного и того же соперника", "weight": 20.0},
    {"source": "campaigns", "reason": "Много неудачных попыток клейма конкурсов", "weight": 12.0},
    {"source": "tasks", "reason": "Слишком частые попытки открыть просмотры", "weight": 10.0},
    {"source": "promos", "reason": "Много неудачных попыток активации промокодов", "weight": 8.0},
    {"source": "checkin", "reason": "Подозрительно частые попытки ежедневного бонуса", "weight": 8.0},
)


def _build_known_risk_cases(weights: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    total_weight = sum(float(item["weight"]) for item in weights)
    if total_weight <= 0:
        return tuple()

    ranked_cases: list[dict[str, Any]] = []
    assigned_score = 0
    for index, item in enumerate(weights):
        exact_score = float(item["weight"]) * _RISK_SCORE_CAP / total_weight
        base_score = int(exact_score)
        assigned_score += base_score
        ranked_cases.append(
            {
                **item,
                "max_score": float(base_score),
                "_remainder": exact_score - base_score,
                "_index": index,
            }
        )

    remaining = int(_RISK_SCORE_CAP - assigned_score)
    if remaining > 0:
        ranked_cases.sort(
            key=lambda item: (float(item["_remainder"]), -int(item["_index"])),
            reverse=True,
        )
        for item in ranked_cases[:remaining]:
            item["max_score"] += 1.0

    ranked_cases.sort(key=lambda item: int(item["_index"]))
    for item in ranked_cases:
        item.pop("_remainder", None)
        item.pop("_index", None)

    return tuple(ranked_cases)


_KNOWN_RISK_CASES = _build_known_risk_cases(_RISK_CASE_WEIGHTS)

_KNOWN_RISK_CASES_BY_KEY = {
    _risk_flag_key(item["source"], item["reason"]): item
    for item in _KNOWN_RISK_CASES
}


def _get_known_risk_case(source: Optional[str], reason: Optional[str]) -> Optional[dict[str, Any]]:
    return _KNOWN_RISK_CASES_BY_KEY.get(_risk_flag_key(source, reason))


def _get_risk_case_weight(source: Optional[str], reason: Optional[str], fallback: float) -> float:
    known_case = _get_known_risk_case(source, reason)
    if known_case:
        return float(known_case["weight"])
    return float(fallback)


def _risk_flag_score_to_percent(
        source: Optional[str],
        reason: Optional[str],
        raw_score: float,
) -> float:
    known_case = _get_known_risk_case(source, reason)
    normalized_raw_score = max(float(raw_score or 0), 0.0)
    if not known_case:
        return min(normalized_raw_score, _RISK_SCORE_CAP)

    weight = float(known_case["weight"] or 0)
    max_score = float(known_case["max_score"] or 0)
    if weight <= 0 or max_score <= 0:
        return 0.0

    score_ratio = min(normalized_raw_score, weight) / weight
    return min(max_score, score_ratio * max_score)


async def _recalculate_user_risk_score(
        db: aiosqlite.Connection,
        user_id: int,
        *,
        suspicious_threshold: float = RISK_SCORE_SUSPICIOUS_THRESHOLD,
) -> float:
    async with db.execute(
            """
        SELECT score, source, reason
        FROM risk_flags
        WHERE user_id = ?
        """,
            (int(user_id),),
    ) as cur:
        rows = await cur.fetchall()

    total_score = 0.0
    for row in rows:
        total_score += _risk_flag_score_to_percent(
            row["source"],
            row["reason"],
            float(row["score"] or 0),
        )

    total_score = min(max(float(total_score), 0.0), _RISK_SCORE_CAP)
    await db.execute(
        """
        UPDATE users
        SET risk_score = ?
        WHERE user_id = ?
        """,
        (float(total_score), int(user_id)),
    )

    if total_score >= float(suspicious_threshold):
        await _mark_user_suspicious(
            db,
            int(user_id),
            "Автофлаг риска",
            commit=False,
        )

    return float(total_score)


async def _ensure_user_risk_state(
        db: aiosqlite.Connection,
        user_id: int,
        *,
        suspicious_threshold: float = RISK_SCORE_SUSPICIOUS_THRESHOLD,
) -> None:
    await ensure_users_risk_schema(db)

    async with db.execute(
            "SELECT 1 FROM users WHERE user_id = ? LIMIT 1",
            (int(user_id),),
    ) as cur:
        user_exists = await cur.fetchone()

    if not user_exists:
        return

    async with db.execute(
            "SELECT 1 FROM risk_flags WHERE user_id = ? LIMIT 1",
            (int(user_id),),
    ) as cur:
        has_flags = await cur.fetchone()

    if not has_flags:
        async with db.execute(
                """
            SELECT
                COALESCE(source, 'system') AS source,
                COALESCE(reason, 'unknown') AS reason,
                COALESCE(MAX(CASE WHEN delta > 0 THEN delta ELSE 0 END), 0) AS score,
                MAX(meta) AS meta
            FROM risk_events
            WHERE user_id = ?
            GROUP BY COALESCE(source, 'system'), COALESCE(reason, 'unknown')
            HAVING score > 0
            """,
                (int(user_id),),
        ) as cur:
            grouped_rows = await cur.fetchall()

        for row in grouped_rows:
            source = row["source"]
            reason = row["reason"]
            score = min(
                max(float(row["score"] or 0), 0.0),
                _get_risk_case_weight(source, reason, _RISK_SCORE_CAP),
            )
            await db.execute(
                """
                INSERT OR IGNORE INTO risk_flags (
                    user_id, risk_key, score, reason, source, meta
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(user_id),
                    _risk_flag_key(source, reason),
                    score,
                    reason,
                    source,
                    row["meta"],
                ),
            )

    await _recalculate_user_risk_score(
        db,
        int(user_id),
        suspicious_threshold=suspicious_threshold,
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
    await ensure_users_profile_schema(db)
    await _ensure_user_risk_state(db, int(user_id))
    async with db.execute(
            """
        SELECT user_id, username, tg_first_name, tg_last_name, game_nickname,
               COALESCE(game_nickname_change_count, 0) AS game_nickname_change_count,
               balance, role_level,
               is_suspicious, suspicious_reason, COALESCE(risk_score, 0) AS risk_score,
               created_at, last_seen_at
        FROM users
        WHERE user_id = ?
        """,
            (int(user_id),),
    ) as cur:
        return await cur.fetchone()


async def get_user_id_by_username(
        db: aiosqlite.Connection,
        username: Optional[str],
) -> Optional[int]:
    normalized_username = (username or "").strip().lstrip("@")
    if not normalized_username:
        return None

    async with db.execute(
            "SELECT user_id FROM users WHERE username = ? LIMIT 1",
            (normalized_username,),
    ) as cur:
        row = await cur.fetchone()

    if not row:
        return None

    return int(row["user_id"])


async def register_user(
        db: aiosqlite.Connection,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
) -> None:
    await ensure_users_profile_schema(db)
    await ensure_users_risk_schema(db)
    u = (username or "").strip().lstrip("@") or None
    fn = (first_name or "").strip() or None
    ln = (last_name or "").strip() or None
    game_nickname = default_game_nickname_for_user_id(user_id)

    bootstrap_level = bootstrap_role_level_for_user_id(user_id)

    async with db.execute(
            """
            SELECT user_id, game_nickname
            FROM users
            WHERE user_id = ?
            """,
            (int(user_id),),
    ) as cur:
        existing_row = await cur.fetchone()

    if not existing_row:
        game_nickname = await _generate_unique_game_nickname(db)
        await db.execute(
            """
            INSERT INTO users (
                user_id, username, tg_first_name, tg_last_name, game_nickname,
                game_nickname_change_count, balance, role_level, created_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, 0, 0, ?, datetime('now'), datetime('now'))
            """,
            (int(user_id), u, fn, ln, game_nickname, bootstrap_level),
        )
        return

    replacement_game_nickname: Optional[str] = None
    current_game_nickname = existing_row["game_nickname"] if "game_nickname" in existing_row.keys() else None
    if not normalize_game_nickname(current_game_nickname):
        replacement_game_nickname = await _generate_unique_game_nickname(db)

    await db.execute(
        """
        UPDATE users
        SET username = COALESCE(?, username),
            tg_first_name = COALESCE(?, tg_first_name),
            tg_last_name = COALESCE(?, tg_last_name),
            game_nickname = COALESCE(game_nickname, ?),
            role_level = CASE
                WHEN COALESCE(role_level, 0) < ? THEN ?
                ELSE role_level
            END,
            last_seen_at = datetime('now')
        WHERE user_id = ?
        """,
        (u, fn, ln, replacement_game_nickname, bootstrap_level, bootstrap_level, int(user_id)),
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


async def is_game_nickname_taken(
        db: aiosqlite.Connection,
        nickname: str,
        *,
        exclude_user_id: Optional[int] = None,
) -> bool:
    return await _is_game_nickname_taken(
        db,
        nickname,
        exclude_user_id=exclude_user_id,
    )


async def set_user_game_nickname_once(
        db: aiosqlite.Connection,
        user_id: int,
        nickname: str,
) -> bool:
    normalized_nickname = normalize_game_nickname(nickname)
    cur = await db.execute(
        """
        UPDATE users
        SET
            game_nickname = ?,
            game_nickname_change_count = COALESCE(game_nickname_change_count, 0) + 1
        WHERE user_id = ?
          AND COALESCE(game_nickname_change_count, 0) < 1
        """,
        (normalized_nickname, int(user_id)),
    )
    return cur.rowcount == 1


async def get_user_admin_details(db: aiosqlite.Connection, user_id: int):
    await ensure_users_profile_schema(db)
    await ensure_users_risk_schema(db)
    async with db.execute(
            """
        SELECT user_id, username, balance, is_suspicious, suspicious_reason, COALESCE(risk_score, 0) AS risk_score
        FROM users
        WHERE user_id = ?
        """,
            (int(user_id),),
    ) as cursor:
        return await cursor.fetchone()

async def build_user_stats_text(db: aiosqlite.Connection, user_id: int) -> str:
    from shared.db.ledger import get_user_earnings_breakdown

    stats = await get_user_earnings_breakdown(db, user_id)
    withdrawal_ability_total = (
        float(stats["view_post_bonus"])
        + float(stats["daily_bonus"])
        + float(stats["battle_net"])
        + float(stats["theft_net"])
        + float(stats["referral_bonus"])
        + float(stats["subscription_bonus"])
    )
    withdrawal_ability_total_pct = (
        float(stats["view_post_bonus_pct"])
        + float(stats["daily_bonus_pct"])
        + float(stats["battle_net_pct"])
        + float(stats["theft_net_pct"])
        + float(stats["referral_bonus_pct"])
        + float(stats["subscription_bonus_pct"])
    )
    bonus_total = (
        float(stats["contest_bonus"])
        + float(stats["promo_bonus"])
        + float(stats["admin_adjust"])
    )
    bonus_total_pct = (
        float(stats["contest_bonus_pct"])
        + float(stats["promo_bonus_pct"])
        + float(stats["admin_adjust_pct"])
    )

    def fmt_pct(value: float) -> str:
        return f"{float(value):.2f}".replace(".", ",")

    def fmt_pct_total(value: float) -> str:
        return f"{float(value):.2f}"

    return (
        f"<b>Всего заработано: {fmt_stars(stats['total'])}⭐</b>\n\n"
        f"{fmt_stars(stats['view_post_bonus'])} ({fmt_pct(stats['view_post_bonus_pct'])}%) — просмотр постов\n"
        f"{fmt_stars(stats['daily_bonus'])} ({fmt_pct(stats['daily_bonus_pct'])}%) — ежедневный бонус\n"
        f"{fmt_stars(stats['battle_net'])} ({fmt_pct(stats['battle_net_pct'])}%) — батлы\n"
        f"{fmt_stars(stats['theft_net'])} ({fmt_pct(stats['theft_net_pct'])}%) — воровство\n"
        f"{fmt_stars(stats['subscription_bonus'])} ({fmt_pct(stats['subscription_bonus_pct'])}%) — подписки\n"
        f"{fmt_stars(stats['referral_bonus'])} ({fmt_pct(stats['referral_bonus_pct'])}%) — рефералы\n"
        f"<b>Итого: {fmt_stars(withdrawal_ability_total)} ({fmt_pct_total(withdrawal_ability_total_pct)}%)</b>\n\n"
        f"{fmt_stars(stats['contest_bonus'])} ({fmt_pct(stats['contest_bonus_pct'])}%) — конкурсы\n"
        f"{fmt_stars(stats['promo_bonus'])} ({fmt_pct(stats['promo_bonus_pct'])}%) — промокоды\n"
        f"{fmt_stars(stats['admin_adjust'])} ({fmt_pct(stats['admin_adjust_pct'])}%) — начисления от админа\n"
        f"<b>Итого: {fmt_stars(bonus_total)} ({fmt_pct_total(bonus_total_pct)}%)</b>"
    )


async def build_user_profile(db: aiosqlite.Connection, user_id: int) -> Optional[dict[str, Any]]:
    from shared.db.ledger import get_withdrawal_ability

    row = await get_user_by_id(db, user_id)
    if not row:
        return None

    role_level = await get_user_role_level(db, user_id)

    return {
        "user_id": int(row["user_id"]),
        "username": row["username"],
        "first_name": row["tg_first_name"],
        "last_name": row["tg_last_name"],
        "game_nickname": row["game_nickname"] or default_game_nickname_for_user_id(int(row["user_id"])),
        "game_nickname_change_count": int(row["game_nickname_change_count"] or 0),
        "can_change_game_nickname": int(row["game_nickname_change_count"] or 0) < 1,
        "balance": float(row["balance"] or 0),
        "risk_score": float(row["risk_score"] or 0),
        "role_level": int(role_level),
        "role": role_title_from_level(role_level),
        "withdrawal_ability": await get_withdrawal_ability(db, user_id),
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


async def list_related_referral_users(
        db: aiosqlite.Connection,
        *,
        user_id: int,
        candidate_user_ids: list[int],
        limit: int = 10,
):
    normalized_ids = sorted({int(item) for item in candidate_user_ids if int(item) != int(user_id)})
    if not normalized_ids:
        return []

    placeholders = ",".join("?" for _ in normalized_ids)
    query = f"""
        SELECT user_id, username, tg_first_name
        FROM users
        WHERE user_id IN ({placeholders})
          AND referred_by = ?
        ORDER BY user_id ASC
        LIMIT ?
    """
    params: list[Any] = [*normalized_ids, int(user_id), int(limit)]
    async with db.execute(query, tuple(params)) as cur:
        return await cur.fetchall()


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
    await ensure_users_risk_schema(db)
    return await _mark_user_suspicious(db, user_id, reason, commit=True)


async def _mark_user_suspicious(db, user_id: int, reason: str, *, commit: bool) -> None:
    async with db.execute(
            "SELECT is_suspicious, suspicious_reason FROM users WHERE user_id = ?",
            (user_id,),
    ) as cur:
        row = await cur.fetchone()
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
    if commit:
        await db.commit()


async def clear_user_suspicious(db, user_id: int):
    await ensure_users_risk_schema(db)
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


async def get_user_risk_score(db: aiosqlite.Connection, user_id: int) -> float:
    await _ensure_user_risk_state(db, int(user_id))
    async with db.execute(
            "SELECT COALESCE(risk_score, 0) AS risk_score FROM users WHERE user_id = ?",
            (int(user_id),),
    ) as cur:
        row = await cur.fetchone()
    return float(row["risk_score"] or 0.0) if row else 0.0


async def add_user_risk_score(
        db: aiosqlite.Connection,
        user_id: int,
        delta: float,
        reason: str,
        *,
        source: Optional[str] = None,
        meta: Optional[str] = None,
        suspicious_threshold: float = RISK_SCORE_SUSPICIOUS_THRESHOLD,
) -> float:
    await _ensure_user_risk_state(
        db,
        int(user_id),
        suspicious_threshold=suspicious_threshold,
    )
    delta_value = float(delta)
    if delta_value <= 0:
        return await get_user_risk_score(db, int(user_id))

    previous_total = await get_user_risk_score(db, int(user_id))
    risk_key = _risk_flag_key(source, reason)

    async with db.execute(
            """
        SELECT score, reason, source, meta
        FROM risk_flags
        WHERE user_id = ? AND risk_key = ?
        LIMIT 1
        """,
            (int(user_id), risk_key),
    ) as cur:
        existing_row = await cur.fetchone()

    previous_flag_score = float(existing_row["score"] or 0) if existing_row else 0.0
    max_flag_score = _get_risk_case_weight(source, reason, _RISK_SCORE_CAP)
    next_flag_score = max(previous_flag_score, min(delta_value, max_flag_score))

    if next_flag_score <= previous_flag_score:
        if existing_row:
            existing_reason = existing_row["reason"]
            existing_source = existing_row["source"]
            existing_meta = existing_row["meta"]
            next_meta = meta if meta is not None else existing_meta
            if (
                existing_reason != reason
                or existing_source != source
                or existing_meta != next_meta
            ):
                await db.execute(
                    """
                    UPDATE risk_flags
                    SET reason = ?,
                        source = ?,
                        meta = ?,
                        updated_at = datetime('now')
                    WHERE user_id = ? AND risk_key = ?
                    """,
                    (
                        reason,
                        source,
                        next_meta,
                        int(user_id),
                        risk_key,
                    ),
                )
        return previous_total

    if existing_row:
        cur = await db.execute(
            """
            UPDATE risk_flags
            SET score = ?,
                reason = ?,
                source = ?,
                meta = ?,
                updated_at = datetime('now')
            WHERE user_id = ? AND risk_key = ?
            """,
            (
                float(next_flag_score),
                reason,
                source,
                meta,
                int(user_id),
                risk_key,
            ),
        )
    else:
        cur = await db.execute(
            """
            INSERT INTO risk_flags (user_id, risk_key, score, reason, source, meta)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(user_id),
                risk_key,
                float(next_flag_score),
                reason,
                source,
                meta,
            ),
        )

    if cur.rowcount != 1:
        return previous_total

    current_score = await _recalculate_user_risk_score(
        db,
        int(user_id),
        suspicious_threshold=suspicious_threshold,
    )
    effective_delta = float(current_score) - float(previous_total)
    if effective_delta <= 0:
        return current_score

    await db.execute(
        """
        INSERT INTO risk_events (user_id, delta, score_after, reason, source, meta)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            int(user_id),
            effective_delta,
            float(current_score),
            reason,
            source,
            meta,
        ),
    )

    return current_score


async def list_user_risk_events(
        db: aiosqlite.Connection,
        user_id: int,
        *,
        limit: int,
        offset: int,
):
    await _ensure_user_risk_state(db, int(user_id))
    async with db.execute(
            """
        SELECT id, delta, score_after, reason, source, meta, created_at
        FROM risk_events
        WHERE user_id = ?
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT ? OFFSET ?
        """,
            (int(user_id), int(limit), int(offset)),
    ) as cur:
        return await cur.fetchall()


async def list_user_risk_flags(
        db: aiosqlite.Connection,
        user_id: int,
):
    await _ensure_user_risk_state(db, int(user_id))
    async with db.execute(
            """
        SELECT risk_key, score, reason, source, meta, created_at, updated_at
        FROM risk_flags
        WHERE user_id = ?
          AND score > 0
        ORDER BY score DESC, datetime(updated_at) DESC, id DESC
        """,
            (int(user_id),),
    ) as cur:
        return await cur.fetchall()


async def list_user_risk_case_progress(
        db: aiosqlite.Connection,
        user_id: int,
):
    await _ensure_user_risk_state(db, int(user_id))
    flags = await list_user_risk_flags(db, int(user_id))
    flags_by_key = {
        row["risk_key"]: row
        for row in flags
    }

    items: list[dict[str, Any]] = []
    known_keys = set()
    for case in _KNOWN_RISK_CASES:
        risk_key = _risk_flag_key(case["source"], case["reason"])
        known_keys.add(risk_key)
        current_flag = flags_by_key.get(risk_key)
        items.append(
            {
                "risk_key": risk_key,
                "source": case["source"],
                "reason": case["reason"],
                "current_score": (
                    _risk_flag_score_to_percent(
                        case["source"],
                        case["reason"],
                        float(current_flag["score"] or 0),
                    )
                    if current_flag
                    else 0.0
                ),
                "max_score": float(case["max_score"]),
                "meta": current_flag["meta"] if current_flag else None,
                "created_at": current_flag["created_at"] if current_flag else None,
                "updated_at": current_flag["updated_at"] if current_flag else None,
            }
        )

    for row in flags:
        risk_key = row["risk_key"]
        if risk_key in known_keys:
            continue
        score = float(row["score"] or 0)
        items.append(
            {
                "risk_key": risk_key,
                "source": row["source"],
                "reason": row["reason"],
                "current_score": score,
                "max_score": score,
                "meta": row["meta"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )

    return items


def _build_daily_checkin_state(
        cycle_day: int,
        last_checkin_raw: Optional[str],
        now: datetime,
) -> dict[str, Any]:
    today = now.date()
    yesterday = today - timedelta(days=1)

    last_date = None
    if last_checkin_raw:
        last_date = datetime.fromisoformat(last_checkin_raw).date()

    already_claimed_today = last_date == today
    claimed_yesterday = last_date == yesterday

    if already_claimed_today:
        current_cycle_day = normalize_daily_cycle_day(cycle_day if cycle_day > 0 else 1)
        can_claim = False
    elif claimed_yesterday:
        current_cycle_day = normalize_daily_cycle_day(cycle_day + 1)
        can_claim = True
    else:
        current_cycle_day = 1
        can_claim = True

    reward_today = daily_checkin_reward(current_cycle_day)
    next_cycle_day = normalize_daily_cycle_day(current_cycle_day + 1)
    next_reward = daily_checkin_reward(next_cycle_day)
    claimed_days_count = current_cycle_day if already_claimed_today else max(current_cycle_day - 1, 0)
    claimed_total_reward = sum(
        daily_checkin_reward(day)
        for day in range(1, claimed_days_count + 1)
    )

    return {
        "already_claimed_today": already_claimed_today,
        "claimed_yesterday": claimed_yesterday,
        "can_claim": can_claim,
        "current_cycle_day": current_cycle_day,
        "claimed_days_count": claimed_days_count,
        "claimed_total_reward": float(claimed_total_reward),
        "reward_today": reward_today,
        "next_cycle_day": next_cycle_day,
        "next_reward": next_reward,
        "last_checkin_at": last_checkin_raw,
    }


async def get_daily_checkin_status(
        db: aiosqlite.Connection,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
) -> dict[str, Any]:
    uid = int(user_id)
    now = datetime.now(timezone.utc)

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

    cycle_day = int(row["daily_checkin_cycle_day"] or 0) if row else 0
    last_checkin_raw = row["last_daily_checkin_at"] if row else None

    state = _build_daily_checkin_state(
        cycle_day=cycle_day,
        last_checkin_raw=last_checkin_raw,
        now=now,
    )

    return {
        "can_claim": state["can_claim"],
        "already_claimed_today": state["already_claimed_today"],
        "current_cycle_day": state["current_cycle_day"],
        "claimed_days_count": state["claimed_days_count"],
        "claimed_total_reward": state["claimed_total_reward"],
        "season_length": daily_checkin_season_length(),
        "cycle_rewards": daily_checkin_schedule(),
        "reward_today": float(state["reward_today"]),
        "next_cycle_day": state["next_cycle_day"],
        "next_reward": float(state["next_reward"]),
        "last_checkin_at": state["last_checkin_at"],
        "server_time": now.isoformat(),
    }


async def claim_daily_checkin(
        db,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
):
    uid = int(user_id)
    now = datetime.now(timezone.utc)

    async with tx(db, immediate=True):
        from shared.db.ledger import apply_balance_delta

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

        cycle_day = int(row["daily_checkin_cycle_day"] or 0) if row else 0
        last_checkin_raw = row["last_daily_checkin_at"] if row else None

        state = _build_daily_checkin_state(
            cycle_day=cycle_day,
            last_checkin_raw=last_checkin_raw,
            now=now,
        )

        if not state["can_claim"]:
            balance = await get_balance(db, uid)
            return False, "🎁 Бонус за сегодня уже получен", balance

        new_cycle_day = state["current_cycle_day"]
        reward = state["reward_today"]
        next_reward = state["next_reward"]

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
