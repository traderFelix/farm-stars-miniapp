from typing import Any

import aiosqlite

from shared.db.ledger import (
    balances_audit,
    get_balance_adjusts_by_admin,
    ledger_count_by_reason,
    ledger_sum_battle_net,
    ledger_sum_by_reason,
    list_global_ledger_page,
)
from shared.db.users import (
    top_users_by_balance,
    total_balances,
    users_active_since_days,
    users_growth_by_day,
    users_new_since_days,
    users_new_since_hours,
    users_total_count,
)
from shared.db.withdrawals import pending_withdrawn_amount, total_withdrawn_amount


def _serialize_top_balance(row: Any) -> dict[str, Any]:
    return {
        "username": row["username"],
        "balance": float(row["balance"] or 0),
    }


def _serialize_growth_point(row: Any) -> dict[str, Any]:
    return {
        "date": str(row[0]),
        "count": int(row[1] or 0),
    }


def _serialize_ledger_entry(row: Any) -> dict[str, Any]:
    return {
        "created_at": row["created_at"],
        "username": row["username"],
        "delta": float(row["delta"] or 0),
        "reason": row["reason"],
        "campaign_key": row["campaign_key"],
    }


def _serialize_audit_mismatch(row: Any) -> dict[str, Any]:
    return {
        "user_id": int(row["user_id"]),
        "username": row["username"],
        "users_balance": float(row["users_balance"] or 0),
        "ledger_sum": float(row["ledger_sum"] or 0),
        "diff": float(row["diff"] or 0),
    }


async def get_top_balances(
        db: aiosqlite.Connection,
        *,
        limit: int = 10,
) -> dict[str, Any]:
    rows = await top_users_by_balance(db, int(limit))
    return {
        "items": [_serialize_top_balance(row) for row in rows],
    }


async def get_growth(
        db: aiosqlite.Connection,
        *,
        days: int = 30,
) -> dict[str, Any]:
    return {
        "days": int(days),
        "total_users": int(await users_total_count(db)),
        "new_1d": int(await users_new_since_hours(db, 24)),
        "new_7d": int(await users_new_since_days(db, 7)),
        "new_30d": int(await users_new_since_days(db, 30)),
        "active_1d": int(await users_active_since_days(db, 1)),
        "active_7d": int(await users_active_since_days(db, 7)),
        "active_30d": int(await users_active_since_days(db, 30)),
        "points": [_serialize_growth_point(row) for row in await users_growth_by_day(db, int(days))],
    }


async def get_admin_ledger_page(
        db: aiosqlite.Connection,
        *,
        page: int,
        page_size: int,
) -> dict[str, Any]:
    safe_page = max(int(page), 0)
    safe_page_size = max(int(page_size), 1)
    offset = safe_page * safe_page_size

    rows = await list_global_ledger_page(
        db,
        limit=safe_page_size + 1,
        offset=offset,
    )

    has_next = len(rows) > safe_page_size
    rows = rows[:safe_page_size]

    return {
        "page": safe_page,
        "page_size": safe_page_size,
        "has_next": has_next,
        "items": [_serialize_ledger_entry(row) for row in rows],
    }


async def get_audit(
        db: aiosqlite.Connection,
        *,
        limit: int = 10,
) -> dict[str, Any]:
    mismatches = await balances_audit(db, limit=int(limit))
    total_balances_sum = await total_balances(db)
    admin_added, admin_removed = await get_balance_adjusts_by_admin(db)
    total_withdrawn_sum = await total_withdrawn_amount(db)
    pending_withdrawn_sum = await pending_withdrawn_amount(db)
    campaign_claimed_total = await ledger_sum_by_reason(db, "contest_bonus")
    promo_claimed_total = await ledger_sum_by_reason(db, "promo_bonus")
    claims_count_from_ledger = await ledger_count_by_reason(db, "contest_bonus")
    promo_claims_count_from_ledger = await ledger_count_by_reason(db, "promo_bonus")
    referral_bonus = await ledger_sum_by_reason(db, "referral_bonus")
    view_post_bonus = await ledger_sum_by_reason(db, "view_post_bonus")
    daily_bonus = await ledger_sum_by_reason(db, "daily_bonus")
    subscription_bonus = await ledger_sum_by_reason(db, "subscription_bonus")
    battle_bonus = await ledger_sum_battle_net(db)

    return {
        "total_balances": float(total_balances_sum),
        "campaign_claims_count": int(claims_count_from_ledger),
        "campaign_claimed_total": float(campaign_claimed_total),
        "promo_claims_count": int(promo_claims_count_from_ledger),
        "promo_claimed_total": float(promo_claimed_total),
        "referral_bonus": float(referral_bonus),
        "view_post_bonus": float(view_post_bonus),
        "daily_bonus": float(daily_bonus),
        "subscription_bonus": float(subscription_bonus),
        "battle_bonus": float(battle_bonus),
        "admin_adjust_net": float(admin_added - admin_removed),
        "total_withdrawn": float(total_withdrawn_sum),
        "pending_withdrawn": float(pending_withdrawn_sum),
        "mismatch_count": len(mismatches),
        "mismatches": [_serialize_audit_mismatch(row) for row in mismatches],
    }
