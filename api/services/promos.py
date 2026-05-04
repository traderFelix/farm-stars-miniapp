from __future__ import annotations

from typing import Optional

from api.db.connection import get_db
from api.security.request_fingerprint import RequestFingerprint
from api.schemas.promos import PromoRedeemResponse
from api.services.antiabuse import log_user_action_with_fingerprint
from shared.db.abuse import count_recent_abuse_events
from shared.db.common import tx
from shared.db.ledger import apply_balance_delta
from shared.db.promos import (
    add_promo_claim,
    get_promo,
    get_promo_claims_count,
    has_promo_claim,
)
from shared.db.users import add_user_risk_score, get_balance


def _normalize_promo_code(value: str) -> str:
    return "".join((value or "").strip().upper().split())


async def redeem_promo_for_user(
        user_id: int,
        code: str,
        *,
        fingerprint: Optional[RequestFingerprint] = None,
) -> PromoRedeemResponse:
    user_id = int(user_id)
    normalized_code = _normalize_promo_code(code)

    if len(normalized_code) < 3:
        return PromoRedeemResponse(
            ok=False,
            message="Промокод слишком короткий",
            code="invalid_code",
        )

    db = await get_db()
    try:
        recent_attempts = await count_recent_abuse_events(db, user_id, "promo_redeem_attempt", 1)
        if recent_attempts >= 8:
            return PromoRedeemResponse(
                ok=False,
                message="Слишком частые попытки, попробуй через минуту",
                code="rate_limited",
            )

        recent_fails = await count_recent_abuse_events(db, user_id, "promo_redeem_fail", 10)
        if recent_fails >= 12:
            return PromoRedeemResponse(
                ok=False,
                message="Слишком много неудачных попыток, попробуй позже",
                code="too_many_failures",
            )

        async with tx(db, immediate=True):
            await log_user_action_with_fingerprint(
                db,
                user_id=user_id,
                action="promo_redeem_attempt",
                fingerprint=fingerprint,
                entity_type="promo",
                entity_id=normalized_code,
            )

            row = await get_promo(db, normalized_code)
            if not row:
                await log_user_action_with_fingerprint(
                    db,
                    user_id=user_id,
                    action="promo_redeem_fail",
                    fingerprint=fingerprint,
                    entity_type="promo",
                    entity_id=normalized_code,
                    meta="not_found",
                )
                if recent_fails >= 5:
                    await add_user_risk_score(
                        db,
                        user_id,
                        8,
                        "Много неудачных попыток активации промокодов",
                        source="promos",
                        meta=f"promo={normalized_code}",
                    )
                return PromoRedeemResponse(
                    ok=False,
                    message="Промокод не найден",
                    code="not_found",
                )

            title = row["title"] or None
            reward_amount = float(row["reward_amount"] or 0)
            total_uses = int(row["total_uses"] or 0)
            status = row["status"] or "draft"
            partner_user_id = int(row["partner_user_id"]) if row["partner_user_id"] is not None else None

            if status != "active":
                await log_user_action_with_fingerprint(
                    db,
                    user_id=user_id,
                    action="promo_redeem_fail",
                    fingerprint=fingerprint,
                    entity_type="promo",
                    entity_id=normalized_code,
                    meta="inactive",
                )
                return PromoRedeemResponse(
                    ok=False,
                    message="Этот промокод сейчас неактивен",
                    code="inactive",
                )

            if partner_user_id is not None and partner_user_id == user_id:
                await log_user_action_with_fingerprint(
                    db,
                    user_id=user_id,
                    action="promo_redeem_fail",
                    fingerprint=fingerprint,
                    entity_type="promo",
                    entity_id=normalized_code,
                    meta="own_partner_promo",
                )
                return PromoRedeemResponse(
                    ok=False,
                    message="Нельзя активировать свой промокод",
                    code="own_promo",
                )

            if await has_promo_claim(db, normalized_code, user_id):
                await log_user_action_with_fingerprint(
                    db,
                    user_id=user_id,
                    action="promo_redeem_fail",
                    fingerprint=fingerprint,
                    entity_type="promo",
                    entity_id=normalized_code,
                    meta="already_claimed",
                )
                return PromoRedeemResponse(
                    ok=False,
                    message="Этот промокод уже активирован",
                    code="already_claimed",
                )

            claims_count = await get_promo_claims_count(db, normalized_code)
            if claims_count >= total_uses:
                await log_user_action_with_fingerprint(
                    db,
                    user_id=user_id,
                    action="promo_redeem_fail",
                    fingerprint=fingerprint,
                    entity_type="promo",
                    entity_id=normalized_code,
                    meta="exhausted",
                )
                return PromoRedeemResponse(
                    ok=False,
                    message="Лимит активаций этого промокода уже исчерпан",
                    code="exhausted",
                )

            await add_promo_claim(db, normalized_code, user_id, reward_amount)
            await apply_balance_delta(
                db,
                user_id=user_id,
                delta=reward_amount,
                reason="promo_bonus",
                campaign_key=normalized_code,
                meta=title or f"promo:{normalized_code}",
            )
            await log_user_action_with_fingerprint(
                db,
                user_id=user_id,
                action="promo_redeem_success",
                fingerprint=fingerprint,
                amount=reward_amount,
                entity_type="promo",
                entity_id=normalized_code,
            )

            new_balance = await get_balance(db, user_id)
            return PromoRedeemResponse(
                ok=True,
                message="Промокод активирован",
                new_balance=float(new_balance),
                reward_amount=reward_amount,
                promo_code=normalized_code,
                title=title,
                code="claimed",
            )
    finally:
        await db.close()
