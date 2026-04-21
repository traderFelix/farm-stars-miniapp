from typing import Any, Optional

import aiosqlite
from fastapi import HTTPException

from shared.config import ROLE_OWNER
from shared.db.common import tx
from shared.db.battles import list_battle_opponent_stats
from shared.db.ledger import list_user_ledger_page
from shared.db.ledger import apply_balance_delta
from shared.db.thefts import list_theft_opponent_stats
from shared.db.users import (
    build_user_stats_text,
    build_user_profile,
    clear_user_suspicious,
    get_balance,
    get_user_by_id,
    get_user_id_by_username,
    get_user_role_level,
    get_user_risk_score,
    list_user_risk_case_progress,
    list_user_risk_events,
    list_user_risk_flags,
    mark_user_suspicious,
    role_title_from_level,
    set_user_role_level,
)


async def get_profile(
        db: aiosqlite.Connection,
        user_id: int,
) -> dict[str, Any]:
    profile = await build_user_profile(db, int(user_id))
    if not profile:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return profile


async def _ensure_user_exists(
        db: aiosqlite.Connection,
        user_id: int,
) -> None:
    if not await get_user_by_id(db, int(user_id)):
        raise HTTPException(status_code=404, detail="Пользователь не найден")


async def lookup_profile(
        db: aiosqlite.Connection,
        query: str,
) -> dict[str, Any]:
    value = (query or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="Пустой запрос")

    if value.isdigit():
        return await get_profile(db, int(value))

    user_id = await get_user_id_by_username(db, value)
    if user_id is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return await get_profile(db, user_id)


async def update_role(
        db: aiosqlite.Connection,
        user_id: int,
        role_level: int,
) -> dict[str, Any]:
    target_level = int(role_level)
    if target_level >= ROLE_OWNER:
        raise HTTPException(status_code=400, detail="Роль владельца назначить нельзя.")

    async with tx(db, immediate=False):
        ok = await set_user_role_level(db, int(user_id), target_level)
        if not ok:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

    final_level = await get_user_role_level(db, int(user_id))
    return {
        "user_id": int(user_id),
        "role_level": int(final_level),
        "role": role_title_from_level(final_level),
    }


async def adjust_balance(
        db: aiosqlite.Connection,
        user_id: int,
        amount: float,
        mode: str,
) -> dict[str, Any]:
    value = float(amount)
    if value <= 0:
        raise HTTPException(status_code=400, detail="Сумма должна быть больше 0")

    normalized_mode = (mode or "").strip().lower()
    if normalized_mode not in {"add", "sub"}:
        raise HTTPException(status_code=400, detail="Некорректный режим операции")

    if not await get_user_by_id(db, int(user_id)):
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    delta = value if normalized_mode == "add" else -value

    async with tx(db):
        await apply_balance_delta(
            db,
            user_id=int(user_id),
            delta=delta,
            reason="admin_adjust",
            meta=f"mode={normalized_mode}",
        )

    balance = await get_balance(db, int(user_id))
    return {
        "user_id": int(user_id),
        "delta": float(delta),
        "balance": float(balance or 0),
    }


async def mark_suspicious(
        db: aiosqlite.Connection,
        user_id: int,
        reason: Optional[str],
) -> dict[str, Any]:
    if not await get_user_by_id(db, int(user_id)):
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    await mark_user_suspicious(
        db,
        int(user_id),
        (reason or "").strip() or "Помечен администратором",
    )
    return await get_profile(db, int(user_id))


async def get_stats(
        db: aiosqlite.Connection,
        user_id: int,
) -> dict[str, Any]:
    await _ensure_user_exists(db, int(user_id))

    return {
        "text": await build_user_stats_text(db, int(user_id)),
    }


async def get_battle_stats(
        db: aiosqlite.Connection,
        user_id: int,
) -> dict[str, Any]:
    await _ensure_user_exists(db, int(user_id))

    rows = await list_battle_opponent_stats(db, user_id=int(user_id), limit=50)
    if not rows:
        return {
            "text": "⚔️ Батлы\n\nУ пользователя пока нет завершенных дуэлей",
        }

    lines = ["⚔️ Батлы\n"]
    for index, row in enumerate(rows, start=1):
        opponent_username = (row["opponent_username"] or "").strip()
        opponent_first_name = (row["opponent_first_name"] or "").strip()
        opponent_name = f"@{opponent_username}" if opponent_username else opponent_first_name or f"id:{int(row['opponent_user_id'])}"
        wins = int(row["wins"] or 0)
        losses = int(row["losses"] or 0)
        draws = int(row["draws"] or 0)
        total = int(row["total"] or 0)
        line = f"{index}. {opponent_name} — счет {wins}:{losses}"
        if draws:
            line += f", ничьих {draws}"
        line += f" · всего {total}"
        lines.append(line)

    return {
        "text": "\n".join(lines),
    }


async def get_theft_stats(
        db: aiosqlite.Connection,
        user_id: int,
) -> dict[str, Any]:
    await _ensure_user_exists(db, int(user_id))

    rows = await list_theft_opponent_stats(db, user_id=int(user_id), limit=50)
    if not rows:
        return {
            "text": "🕵️ Воровство\n\nУ пользователя пока нет завершенных краж",
        }

    lines = ["🕵️ Воровство\n"]
    for index, row in enumerate(rows, start=1):
        opponent_username = (row["opponent_username"] or "").strip()
        opponent_nickname = (row["opponent_game_nickname"] or "").strip()
        opponent_first_name = (row["opponent_first_name"] or "").strip()
        opponent_name = (
            opponent_nickname
            or (f"@{opponent_username}" if opponent_username else "")
            or opponent_first_name
            or f"id:{int(row['opponent_user_id'])}"
        )
        stolen_amount = float(row["stolen_amount"] or 0)
        lost_amount = float(row["lost_amount"] or 0)
        net_amount = stolen_amount - lost_amount
        defended_count = int(row["defended_count"] or 0)
        failed_count = int(row["failed_count"] or 0)
        total = int(row["total"] or 0)
        line = (
            f"{index}. {opponent_name} — украл +{stolen_amount:g}⭐, "
            f"потерял -{lost_amount:g}⭐, итог {net_amount:+g}⭐"
        )
        if defended_count or failed_count:
            line += f" · отбил {defended_count}, неудачных атак {failed_count}"
        line += f" · всего {total}"
        lines.append(line)

    return {
        "text": "\n".join(lines),
    }


async def get_user_ledger(
        db: aiosqlite.Connection,
        user_id: int,
        *,
        page: int,
        page_size: int,
) -> dict[str, Any]:
    await _ensure_user_exists(db, int(user_id))

    safe_page = max(int(page), 0)
    safe_page_size = max(int(page_size), 1)
    offset = safe_page * safe_page_size

    history = await list_user_ledger_page(
        db,
        int(user_id),
        limit=safe_page_size + 1,
        offset=offset,
    )

    has_next = len(history) > safe_page_size
    history = history[:safe_page_size]

    return {
        "user_id": int(user_id),
        "page": safe_page,
        "page_size": safe_page_size,
        "has_next": has_next,
        "items": [
            {
                "created_at": row["created_at"],
                "delta": float(row["delta"] or 0),
                "reason": row["reason"],
                "campaign_key": row["campaign_key"],
            }
            for row in history
        ],
    }


async def get_user_risk_history(
        db: aiosqlite.Connection,
        user_id: int,
        *,
        page: int,
        page_size: int,
) -> dict[str, Any]:
    await _ensure_user_exists(db, int(user_id))

    safe_page = max(int(page), 0)
    safe_page_size = max(int(page_size), 1)
    offset = safe_page * safe_page_size

    total_score = await get_user_risk_score(db, int(user_id))
    flags = await list_user_risk_flags(db, int(user_id))
    risk_cases = await list_user_risk_case_progress(db, int(user_id))
    history = await list_user_risk_events(
        db,
        int(user_id),
        limit=safe_page_size + 1,
        offset=offset,
    )

    has_next = len(history) > safe_page_size
    history = history[:safe_page_size]

    return {
        "user_id": int(user_id),
        "total_score": float(total_score),
        "score_cap": 100.0,
        "page": safe_page,
        "page_size": safe_page_size,
        "has_next": has_next,
        "flags": [
            {
                "risk_key": row["risk_key"],
                "score": float(row["score"] or 0),
                "reason": row["reason"],
                "source": row["source"],
                "meta": row["meta"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in flags
        ],
        "risk_cases": risk_cases,
        "items": [
            {
                "id": int(row["id"]),
                "created_at": row["created_at"],
                "delta": float(row["delta"] or 0),
                "score_after": float(row["score_after"] or 0),
                "reason": row["reason"],
                "source": row["source"],
                "meta": row["meta"],
            }
            for row in history
        ],
    }


async def clear_suspicious(
        db: aiosqlite.Connection,
        user_id: int,
) -> dict[str, Any]:
    if not await get_user_by_id(db, int(user_id)):
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    await clear_user_suspicious(db, int(user_id))
    return await get_profile(db, int(user_id))
