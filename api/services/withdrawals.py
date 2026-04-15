from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from api.db.connection import get_db
from api.security.request_fingerprint import RequestFingerprint
from api.services.antiabuse import log_user_action_with_fingerprint
from api.schemas.withdrawals import (
    WithdrawalCreateRequest,
    WithdrawalCreateResponse,
    WithdrawalEligibilityResponse,
    WithdrawalFeeTier,
    WithdrawalItem,
    WithdrawalListResponse,
    WithdrawalPolicyResponse,
    WithdrawalPreviewRequest,
    WithdrawalPreviewResponse,
)
from shared.config import (
    REQUIRED_ACCOUNT_AGE_HOURS,
    MIN_WITHDRAW,
    MIN_WITHDRAW_PERCENT,
    RISK_SCORE_WITHDRAW_BLOCK_THRESHOLD,
)
from shared.db.abuse import (
    count_recent_abuse_events,
    sum_recent_abuse_amount,
)
from shared.db.ledger import (
    apply_balance_debit_if_enough,
    get_withdrawal_ability,
    get_user_earnings_breakdown,
)
from shared.db.users import add_user_risk_score, get_balance, get_user_by_id, user_created_hours_ago
from shared.db.withdrawals import (
    create_withdrawal,
    has_pending_withdrawal,
    is_first_withdraw,
    set_withdrawal_fee_info,
    user_withdrawals,
    wallet_used_by_another_user,
)
from shared.db.xtr_ledger import xtr_ledger_add

MIN_TASK_PERCENT_VALUE = min(round(MIN_WITHDRAW_PERCENT * 200, 2), 100.0)


@dataclass
class EligibilityCheckResult:
    can_withdraw: bool
    message: str
    min_withdraw: float
    min_task_percent: float
    has_pending_withdrawal: bool
    account_age_hours: float
    required_account_age_hours: float
    withdrawal_ability: float
    task_earnings_percent: float
    available_balance: float
    is_first_withdraw: bool


def _safe_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _extract_task_percent(breakdown: dict) -> float:
    total = _safe_float(breakdown.get("total"))
    if total <= 0:
        return 0.0
    tasks_amount = _safe_float(breakdown.get("view_post_bonus", 0))
    return round((tasks_amount / total) * 100, 2)


def _normalize_wallet(method: str, wallet: Optional[str]) -> Optional[str]:
    if method != "ton":
        return None
    normalized = (wallet or "").strip()
    return normalized or None


def get_withdraw_fee(amount: float, is_first: bool) -> int:
    if is_first:
        return 0
    if amount >= 500:
        return 0
    if amount >= 200:
        return 3
    return 5


def build_withdrawal_policy(*, is_first_withdraw: bool) -> WithdrawalPolicyResponse:
    return WithdrawalPolicyResponse(
        first_withdraw_free=True,
        is_first_withdraw=is_first_withdraw,
        rate_source_name="Fragment",
        rate_source_url="https://fragment.com",
        fee_currency="Telegram Stars",
        fee_balance_source="telegram_stars_balance",
        fee_tiers=[
            WithdrawalFeeTier(min_amount=100, fee_xtr=5),
            WithdrawalFeeTier(min_amount=200, fee_xtr=3),
            WithdrawalFeeTier(min_amount=500, fee_xtr=0),
        ],
    )


async def _build_eligibility(user_id: int) -> EligibilityCheckResult:
    db = await get_db()
    try:
        user = await get_user_by_id(db, user_id)
        if not user:
            return EligibilityCheckResult(
                can_withdraw=False,
                message="Пользователь не найден",
                min_withdraw=MIN_WITHDRAW,
                min_task_percent=MIN_TASK_PERCENT_VALUE,
                has_pending_withdrawal=False,
                account_age_hours=0.0,
                required_account_age_hours=REQUIRED_ACCOUNT_AGE_HOURS,
                withdrawal_ability=0.0,
                task_earnings_percent=0.0,
                available_balance=0.0,
                is_first_withdraw=True,
            )

        balance = _safe_float(user["balance"])
        risk_score = _safe_float(user["risk_score"])
        is_suspicious = bool(user["is_suspicious"] or 0)
        account_age_hours = _safe_float(await user_created_hours_ago(db, user_id))
        pending = await has_pending_withdrawal(db, user_id)
        withdrawal_ability = _safe_float(await get_withdrawal_ability(db, user_id))
        breakdown = await get_user_earnings_breakdown(db, user_id)
        task_percent = _extract_task_percent(breakdown)
        first_withdraw = await is_first_withdraw(db, user_id)

        if is_suspicious or risk_score >= RISK_SCORE_WITHDRAW_BLOCK_THRESHOLD:
            return EligibilityCheckResult(
                can_withdraw=False,
                message="Вывод временно недоступен, аккаунт отправлен на проверку",
                min_withdraw=MIN_WITHDRAW,
                min_task_percent=MIN_TASK_PERCENT_VALUE,
                has_pending_withdrawal=False,
                account_age_hours=round(account_age_hours, 2),
                required_account_age_hours=REQUIRED_ACCOUNT_AGE_HOURS,
                withdrawal_ability=withdrawal_ability,
                task_earnings_percent=task_percent,
                available_balance=balance,
                is_first_withdraw=first_withdraw,
            )

        if pending:
            return EligibilityCheckResult(
                can_withdraw=False,
                message="У тебя уже есть заявка на вывод в обработке",
                min_withdraw=MIN_WITHDRAW,
                min_task_percent=MIN_TASK_PERCENT_VALUE,
                has_pending_withdrawal=True,
                account_age_hours=round(account_age_hours, 2),
                required_account_age_hours=REQUIRED_ACCOUNT_AGE_HOURS,
                withdrawal_ability=withdrawal_ability,
                task_earnings_percent=task_percent,
                available_balance=balance,
                is_first_withdraw=first_withdraw,
            )

        if account_age_hours < REQUIRED_ACCOUNT_AGE_HOURS:
            return EligibilityCheckResult(
                can_withdraw=False,
                message="Вывод будет доступен после 24 часов с момента регистрации",
                min_withdraw=MIN_WITHDRAW,
                min_task_percent=MIN_TASK_PERCENT_VALUE,
                has_pending_withdrawal=False,
                account_age_hours=round(account_age_hours, 2),
                required_account_age_hours=REQUIRED_ACCOUNT_AGE_HOURS,
                withdrawal_ability=withdrawal_ability,
                task_earnings_percent=task_percent,
                available_balance=balance,
                is_first_withdraw=first_withdraw,
            )

        if balance < MIN_WITHDRAW:
            return EligibilityCheckResult(
                can_withdraw=False,
                message=f"Минимальная сумма вывода — {MIN_WITHDRAW:.0f}⭐️",
                min_withdraw=MIN_WITHDRAW,
                min_task_percent=MIN_TASK_PERCENT_VALUE,
                has_pending_withdrawal=False,
                account_age_hours=round(account_age_hours, 2),
                required_account_age_hours=REQUIRED_ACCOUNT_AGE_HOURS,
                withdrawal_ability=withdrawal_ability,
                task_earnings_percent=task_percent,
                available_balance=balance,
                is_first_withdraw=first_withdraw,
            )

        if withdrawal_ability < MIN_TASK_PERCENT_VALUE:
            return EligibilityCheckResult(
                can_withdraw=False,
                message=f"Для вывода нужно набить {MIN_TASK_PERCENT_VALUE:.0f}% доступности вывода",
                min_withdraw=MIN_WITHDRAW,
                min_task_percent=MIN_TASK_PERCENT_VALUE,
                has_pending_withdrawal=False,
                account_age_hours=round(account_age_hours, 2),
                required_account_age_hours=REQUIRED_ACCOUNT_AGE_HOURS,
                withdrawal_ability=withdrawal_ability,
                task_earnings_percent=task_percent,
                available_balance=balance,
                is_first_withdraw=first_withdraw,
            )

        return EligibilityCheckResult(
            can_withdraw=True,
            message="Вывод доступен",
            min_withdraw=MIN_WITHDRAW,
            min_task_percent=MIN_TASK_PERCENT_VALUE,
            has_pending_withdrawal=False,
            account_age_hours=round(account_age_hours, 2),
            required_account_age_hours=REQUIRED_ACCOUNT_AGE_HOURS,
            withdrawal_ability=withdrawal_ability,
            task_earnings_percent=task_percent,
            available_balance=balance,
            is_first_withdraw=first_withdraw,
        )
    finally:
        await db.close()


async def _validate_withdraw_rules(db, user_id: int, amount: float) -> Optional[str]:
    user = await get_user_by_id(db, user_id)
    balance = _safe_float(user["balance"] if user else 0)
    risk_score = _safe_float(user["risk_score"] if user else 0)
    is_suspicious = bool(user["is_suspicious"] or 0) if user else False

    if is_suspicious or risk_score >= RISK_SCORE_WITHDRAW_BLOCK_THRESHOLD:
        return "Вывод временно недоступен, аккаунт отправлен на проверку"

    if amount < MIN_WITHDRAW:
        return f"❌ Минимальная сумма вывода: {MIN_WITHDRAW:g}⭐"

    if amount > balance:
        return "❌ Недостаточно звезд на балансе"

    user_age_hours = await user_created_hours_ago(db, user_id)
    if user_age_hours < 24:
        return "⏳ Вывод доступен только через 24 часа после регистрации"

    if await has_pending_withdrawal(db, user_id):
        return "⏳ У тебя уже есть заявка на вывод в обработке"

    recent_withdraw_count = await count_recent_abuse_events(db, user_id, "withdraw_create", 1440)
    if recent_withdraw_count >= 3:
        return "Лимит: не более 3 заявок на вывод в сутки"

    recent_withdraw_sum = await sum_recent_abuse_amount(db, user_id, "withdraw_create", 24)
    if recent_withdraw_sum + amount > 1000:
        return "Суточный лимит вывода превышен"

    withdrawal_ability = await get_withdrawal_ability(db, user_id)
    if withdrawal_ability <= 0:
        return "❌ Вывод пока недоступен"

    if withdrawal_ability < MIN_TASK_PERCENT_VALUE:
        return (
            "❌ Вывод пока недоступен\n\n"
            f"Для вывода нужно набить {MIN_TASK_PERCENT_VALUE:.0f}% доступности вывода\n\n"
            f"• Доступность вывода: {withdrawal_ability:.2f}%"
        )

    return None


async def get_withdrawal_eligibility_for_user(
        user_id: int,
) -> WithdrawalEligibilityResponse:
    result = await _build_eligibility(user_id)

    return WithdrawalEligibilityResponse(
        can_withdraw=result.can_withdraw,
        min_withdraw=result.min_withdraw,
        min_task_percent=result.min_task_percent,
        has_pending_withdrawal=result.has_pending_withdrawal,
        account_age_hours=result.account_age_hours,
        required_account_age_hours=result.required_account_age_hours,
        withdrawal_ability=result.withdrawal_ability,
        task_earnings_percent=result.task_earnings_percent,
        available_balance=result.available_balance,
        message=result.message,
        policy=build_withdrawal_policy(is_first_withdraw=result.is_first_withdraw),
    )


async def preview_withdrawal_for_user(
        user_id: int,
        payload: WithdrawalPreviewRequest,
        *,
        fingerprint: Optional[RequestFingerprint] = None,
) -> WithdrawalPreviewResponse:
    method = payload.method
    amount = _safe_float(payload.amount)
    wallet = _normalize_wallet(method, payload.wallet)

    db = await get_db()
    try:
        await log_user_action_with_fingerprint(
            db,
            user_id=int(user_id),
            action="withdraw_preview",
            fingerprint=fingerprint,
            amount=amount,
            entity_type="withdrawal",
            entity_id=method,
        )
        recent_previews = await count_recent_abuse_events(db, int(user_id), "withdraw_preview", 60)
        if recent_previews >= 10:
            await add_user_risk_score(
                db,
                int(user_id),
                10,
                "Слишком много preview заявок на вывод",
                source="withdrawals",
            )
        user = await get_user_by_id(db, user_id)
        available_balance = _safe_float(user["balance"] if user else 0)

        if amount <= 0:
            raise ValueError("Сумма вывода должна быть больше нуля")

        error_text = await _validate_withdraw_rules(db, user_id, amount)
        if error_text:
            await log_user_action_with_fingerprint(
                db,
                user_id=int(user_id),
                action="withdraw_preview_fail",
                fingerprint=fingerprint,
                amount=amount,
                entity_type="withdrawal",
                entity_id=method,
                meta=error_text,
            )
            await db.commit()
            raise ValueError(error_text)

        if method == "ton":
            if not wallet:
                raise ValueError("Для вывода в TON нужно указать кошелек")

            wallet_in_use = await wallet_used_by_another_user(db, user_id, wallet)
            if wallet_in_use:
                await add_user_risk_score(
                    db,
                    int(user_id),
                    100,
                    "Общий TON-кошелек с другим аккаунтом",
                    source="withdrawals",
                    meta=f"wallet={wallet}",
                )
                await log_user_action_with_fingerprint(
                    db,
                    user_id=int(user_id),
                    action="withdraw_wallet_conflict",
                    fingerprint=fingerprint,
                    amount=amount,
                    entity_type="wallet",
                    entity_id=wallet,
                )
                await db.commit()
                raise ValueError("Этот TON-кошелек уже используется другим пользователем")

        first = await is_first_withdraw(db, user_id)
        expected_fee = get_withdraw_fee(amount, first)
        await db.commit()

        return WithdrawalPreviewResponse(
            ok=True,
            amount=amount,
            method=method,
            wallet=wallet,
            available_balance=available_balance,
            expected_fee=expected_fee,
            message="ok",
        )
    finally:
        await db.close()


async def create_withdrawal_for_user(
        user_id: int,
        payload: WithdrawalCreateRequest,
        *,
        fingerprint: Optional[RequestFingerprint] = None,
) -> WithdrawalCreateResponse:
    method = payload.method
    amount = _safe_float(payload.amount)
    wallet = _normalize_wallet(method, payload.wallet)

    paid_fee = int(payload.paid_fee or 0)
    fee_payment_charge_id = payload.fee_payment_charge_id
    fee_invoice_payload = payload.fee_invoice_payload

    if amount <= 0:
        raise ValueError("Сумма вывода должна быть больше нуля")

    db = await get_db()
    try:
        await log_user_action_with_fingerprint(
            db,
            user_id=int(user_id),
            action="withdraw_create_attempt",
            fingerprint=fingerprint,
            amount=amount,
            entity_type="withdrawal",
            entity_id=method,
        )
        error_text = await _validate_withdraw_rules(db, user_id, amount)
        if error_text:
            await log_user_action_with_fingerprint(
                db,
                user_id=int(user_id),
                action="withdraw_create_fail",
                fingerprint=fingerprint,
                amount=amount,
                entity_type="withdrawal",
                entity_id=method,
                meta=error_text,
            )
            recent_create_fails = await count_recent_abuse_events(db, int(user_id), "withdraw_create_fail", 60)
            if recent_create_fails >= 5:
                await add_user_risk_score(
                    db,
                    int(user_id),
                    15,
                    "Слишком много неудачных попыток вывода",
                    source="withdrawals",
                )
            await db.commit()
            raise ValueError(error_text)

        if method == "ton":
            if not wallet:
                raise ValueError("Для вывода в TON нужно указать кошелек")

            wallet_in_use = await wallet_used_by_another_user(db, user_id, wallet)
            if wallet_in_use:
                await add_user_risk_score(
                    db,
                    int(user_id),
                    100,
                    "Общий TON-кошелек с другим аккаунтом",
                    source="withdrawals",
                    meta=f"wallet={wallet}",
                )
                await log_user_action_with_fingerprint(
                    db,
                    user_id=int(user_id),
                    action="withdraw_wallet_conflict",
                    fingerprint=fingerprint,
                    amount=amount,
                    entity_type="wallet",
                    entity_id=wallet,
                )
                await db.commit()
                raise ValueError("Этот TON-кошелек уже используется другим пользователем")

        first = await is_first_withdraw(db, user_id)
        expected_fee = get_withdraw_fee(amount, first)
        if paid_fee != expected_fee:
            await log_user_action_with_fingerprint(
                db,
                user_id=int(user_id),
                action="withdraw_create_fail",
                fingerprint=fingerprint,
                amount=amount,
                entity_type="withdrawal",
                entity_id=method,
                meta="fee_mismatch",
            )
            await db.commit()
            raise ValueError("Сумма комиссии не совпадает с ожидаемой")

        withdrawal_id = await create_withdrawal(
            db=db,
            user_id=user_id,
            amount=amount,
            method=method,
            wallet=wallet,
        )

        await set_withdrawal_fee_info(
            db=db,
            withdrawal_id=withdrawal_id,
            fee_xtr=paid_fee,
            fee_paid=paid_fee > 0,
            fee_payment_charge_id=fee_payment_charge_id,
            fee_invoice_payload=fee_invoice_payload,
        )

        if paid_fee > 0:
            await xtr_ledger_add(
                db=db,
                user_id=user_id,
                withdrawal_id=withdrawal_id,
                delta_xtr=paid_fee,
                reason="withdraw_fee_paid",
                telegram_payment_charge_id=fee_payment_charge_id,
                invoice_payload=fee_invoice_payload,
                meta=f"method={method}",
            )

        await log_user_action_with_fingerprint(
            db,
            user_id=int(user_id),
            action="withdraw_create",
            fingerprint=fingerprint,
            amount=amount,
            entity_type="withdrawal",
            entity_id=str(withdrawal_id),
            meta=f"method={method}",
        )

        ok = await apply_balance_debit_if_enough(
            db=db,
            user_id=user_id,
            amount=amount,
            reason="withdraw_hold",
            withdrawal_id=withdrawal_id,
            meta=f"method={method};fee_xtr={paid_fee}",
        )
        if not ok:
            raise ValueError("insufficient_balance")

        balance = await get_balance(db, user_id)
        await db.commit()

        return WithdrawalCreateResponse(
            ok=True,
            withdrawal_id=withdrawal_id,
            status="pending",
            message="Заявка на вывод создана",
            balance=float(balance or 0),
            fee_xtr=paid_fee,
        )
    finally:
        await db.close()


async def get_my_withdrawals_for_user(
        user_id: int,
        limit: int = 20,
) -> WithdrawalListResponse:
    db = await get_db()
    try:
        rows = await user_withdrawals(db, user_id=user_id, limit=limit)
    finally:
        await db.close()

    items = []
    for row in rows:
        items.append(
            WithdrawalItem(
                id=int(row["id"]),
                amount=float(row["amount"]),
                method=row["method"],
                status=row["status"],
                wallet=row["wallet"],
                created_at=row["created_at"],
                processed_at=row["processed_at"],
                fee_xtr=int(row["fee_xtr"] or 0),
                fee_paid=bool(row["fee_paid"] or 0),
                fee_refunded=bool(row["fee_refunded"] or 0),
            )
        )

    return WithdrawalListResponse(items=items)
