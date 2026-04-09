from __future__ import annotations

from typing import Optional

from api.db.connection import get_db
from api.schemas.campaigns import CampaignClaimResponse, CampaignItem, CampaignListResponse
from shared.db.abuse import count_recent_abuse_events, log_abuse_event
from shared.db.campaigns import get_campaign as get_shared_campaign
from shared.db.common import tx
from shared.db.ledger import apply_balance_delta
from shared.db.users import get_balance, get_user_by_id, register_user


async def _get_campaign(db, campaign_key: str):
    return await get_shared_campaign(db, campaign_key)


async def _list_active_campaign_rows(db):
    async with db.execute(
            """
        SELECT campaign_key, title, reward_amount, description AS post_url
        FROM campaigns
        WHERE status = 'active'
        ORDER BY datetime(created_at) DESC
        """
    ) as cur:
        return await cur.fetchall()


async def _attach_winner_user_id(db, campaign_key: str, username: Optional[str], user_id: int) -> None:
    normalized_username = (username or "").strip().lstrip("@")
    if not normalized_username:
        return

    await db.execute(
        """
        UPDATE campaign_winners
        SET user_id = ?
        WHERE campaign_key = ?
          AND username = ?
          AND user_id IS NULL
        """,
        (int(user_id), campaign_key, normalized_username),
    )


async def _is_winner(db, campaign_key: str, user_id: int, username: Optional[str]) -> bool:
    async with db.execute(
            """
        SELECT 1
        FROM campaign_winners
        WHERE campaign_key = ?
          AND user_id = ?
        LIMIT 1
        """,
            (campaign_key, int(user_id)),
    ) as cur:
        if await cur.fetchone() is not None:
            return True

    normalized_username = (username or "").strip().lstrip("@")
    if not normalized_username:
        return False

    async with db.execute(
            """
        SELECT 1
        FROM campaign_winners
        WHERE campaign_key = ?
          AND username = ?
        LIMIT 1
        """,
            (campaign_key, normalized_username),
    ) as cur:
        return await cur.fetchone() is not None


async def _add_claim(db, user_id: int, campaign_key: str, amount: float) -> None:
    await db.execute(
        """
        INSERT INTO claims (user_id, campaign_key, amount)
        VALUES (?, ?, ?)
        """,
        (int(user_id), campaign_key, float(amount)),
    )


async def get_active_campaigns_for_user() -> CampaignListResponse:
    db = await get_db()
    try:
        rows = await _list_active_campaign_rows(db)
    finally:
        await db.close()

    return CampaignListResponse(
        items=[
            CampaignItem(
                campaign_key=row["campaign_key"],
                title=row["title"],
                reward_amount=float(row["reward_amount"] or 0),
                post_url=row["post_url"] or None,
            )
            for row in rows
        ]
    )


async def claim_campaign_reward_for_user(
        user_id: int,
        campaign_key: str,
        *,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
) -> CampaignClaimResponse:
    user_id = int(user_id)
    normalized_campaign_key = (campaign_key or "").strip()

    db = await get_db()
    try:
        recent_claim_clicks = await count_recent_abuse_events(db, user_id, "claim_click", 1)
        if recent_claim_clicks >= 3:
            return CampaignClaimResponse(
                ok=False,
                message="Слишком частые попытки, попробуй через минуту",
                new_balance=0,
                code="rate_limited",
            )

        recent_claim_fails = await count_recent_abuse_events(db, user_id, "claim_fail", 10)
        if recent_claim_fails >= 10:
            return CampaignClaimResponse(
                ok=False,
                message="Слишком много неудачных попыток, попробуй позже",
                new_balance=0,
                code="too_many_failures",
            )

        async with tx(db, immediate=True):
            user_row = await get_user_by_id(db, user_id)
            resolved_username = username if username is not None else (user_row["username"] if user_row else None)
            resolved_first_name = first_name if first_name is not None else (
                user_row["tg_first_name"] if user_row else None
            )
            resolved_last_name = last_name if last_name is not None else (
                user_row["tg_last_name"] if user_row else None
            )

            await log_abuse_event(db, user_id, "claim_click")
            await register_user(db, user_id, resolved_username, resolved_first_name, resolved_last_name)

            row = await _get_campaign(db, normalized_campaign_key)
            if not row:
                await log_abuse_event(db, user_id, "claim_fail")
                return CampaignClaimResponse(
                    ok=False,
                    message="Конкурс не найден",
                    new_balance=0,
                    code="not_found",
                )

            reward_amount = float(row["reward_amount"] or 0)
            title = row["title"]
            status = row["status"]
            if status != "active":
                await log_abuse_event(db, user_id, "claim_fail")
                return CampaignClaimResponse(
                    ok=False,
                    message="Этот конкурс сейчас неактивен",
                    new_balance=0,
                    code="inactive",
                )

            if resolved_username:
                await _attach_winner_user_id(db, normalized_campaign_key, resolved_username, user_id)

            if not await _is_winner(db, normalized_campaign_key, user_id, resolved_username):
                await log_abuse_event(db, user_id, "claim_fail")
                return CampaignClaimResponse(
                    ok=False,
                    message="Тебя нет в списке победителей этого конкурса",
                    new_balance=0,
                    code="not_winner",
                )

            try:
                await _add_claim(db, user_id, normalized_campaign_key, reward_amount)
            except Exception:
                await log_abuse_event(db, user_id, "claim_fail")
                return CampaignClaimResponse(
                    ok=False,
                    message="Награда по этому конкурсу уже получена",
                    new_balance=0,
                    code="already_claimed",
                )

            await apply_balance_delta(
                db,
                user_id=user_id,
                delta=reward_amount,
                reason="contest_bonus",
                campaign_key=normalized_campaign_key,
                meta=title,
            )

            new_balance = await get_balance(db, user_id)
            return CampaignClaimResponse(
                ok=True,
                message=f"Награда за конкурс «{title}» зачислена",
                new_balance=float(new_balance),
                code="claimed",
            )
    finally:
        await db.close()
