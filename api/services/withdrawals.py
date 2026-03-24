from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from api.db.connection import get_db
from api.schemas.withdrawals import (
    WithdrawalCreateRequest,
    WithdrawalCreateResponse,
    WithdrawalEligibilityResponse,
    WithdrawalItem,
    WithdrawalListResponse,
)
from shared.config import REQUIRED_ACCOUNT_AGE_HOURS, MIN_WITHDRAW, MIN_WITHDRAW_PERCENT
from shared.db.ledger import get_user_earnings_breakdown
from shared.db.users import get_user_by_id, user_created_hours_ago
from shared.db.withdrawals import (
    create_withdrawal,
    has_pending_withdrawal,
    user_withdrawals,
    wallet_used_by_another_user,
)


@dataclass
class EligibilityCheckResult:
    can_withdraw: bool
    message: str
    min_withdraw: float
    min_task_percent: float
    has_pending_withdrawal: bool
    account_age_hours: float
    required_account_age_hours: float
    task_earnings_percent: float
    available_balance: float


def _safe_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _extract_task_percent(breakdown: dict) -> float:
    total = _safe_float(breakdown.get("total"))
    if total <= 0:
        return 0.0

    tasks_amount = _safe_float(
        breakdown.get("view_post_bonus", 0)
    )

    return round((tasks_amount / total) * 100, 2)


async def _build_eligibility(user_id: int) -> EligibilityCheckResult:
    async with get_db() as db:
        user = await get_user_by_id(db, user_id)
        if not user:
            return EligibilityCheckResult(
                can_withdraw=False,
                message="Пользователь не найден.",
                min_withdraw=MIN_WITHDRAW,
                min_task_percent=MIN_WITHDRAW_PERCENT,
                has_pending_withdrawal=False,
                account_age_hours=0.0,
                required_account_age_hours=REQUIRED_ACCOUNT_AGE_HOURS,
                task_earnings_percent=0.0,
                available_balance=0.0,
            )

        balance = _safe_float(user["balance"])
        account_age_hours = _safe_float(await user_created_hours_ago(db, user_id))
        pending = await has_pending_withdrawal(db, user_id)

        breakdown = await get_user_earnings_breakdown(db, user_id)
        task_percent = _extract_task_percent(breakdown)

        if pending:
            return EligibilityCheckResult(
                can_withdraw=False,
                message="У тебя уже есть заявка на вывод в обработке.",
                min_withdraw=MIN_WITHDRAW,
                min_task_percent=MIN_WITHDRAW_PERCENT,
                has_pending_withdrawal=True,
                account_age_hours=round(account_age_hours, 2),
                required_account_age_hours=REQUIRED_ACCOUNT_AGE_HOURS,
                task_earnings_percent=task_percent,
                available_balance=balance,
            )

        if account_age_hours < REQUIRED_ACCOUNT_AGE_HOURS:
            return EligibilityCheckResult(
                can_withdraw=False,
                message="Вывод будет доступен после 24 часов с момента регистрации.",
                min_withdraw=MIN_WITHDRAW,
                min_task_percent=MIN_WITHDRAW_PERCENT,
                has_pending_withdrawal=False,
                account_age_hours=round(account_age_hours, 2),
                required_account_age_hours=REQUIRED_ACCOUNT_AGE_HOURS,
                task_earnings_percent=task_percent,
                available_balance=balance,
            )

        if balance < MIN_WITHDRAW:
            return EligibilityCheckResult(
                can_withdraw=False,
                message=f"Минимальная сумма вывода — {MIN_WITHDRAW:.0f}⭐️.",
                min_withdraw=MIN_WITHDRAW,
                min_task_percent=MIN_WITHDRAW_PERCENT,
                has_pending_withdrawal=False,
                account_age_hours=round(account_age_hours, 2),
                required_account_age_hours=REQUIRED_ACCOUNT_AGE_HOURS,
                task_earnings_percent=task_percent,
                available_balance=balance,
            )

        if task_percent < MIN_WITHDRAW_PERCENT:
            return EligibilityCheckResult(
                can_withdraw=False,
                message=(
                    f"Для вывода нужно минимум {MIN_WITHDRAW_PERCENT:.0f}% "
                    f"звезд, добытых через задания."
                ),
                min_withdraw=MIN_WITHDRAW,
                min_task_percent=MIN_WITHDRAW_PERCENT,
                has_pending_withdrawal=False,
                account_age_hours=round(account_age_hours, 2),
                required_account_age_hours=REQUIRED_ACCOUNT_AGE_HOURS,
                task_earnings_percent=task_percent,
                available_balance=balance,
            )

        return EligibilityCheckResult(
            can_withdraw=True,
            message="Вывод доступен.",
            min_withdraw=MIN_WITHDRAW,
            min_task_percent=MIN_WITHDRAW_PERCENT,
            has_pending_withdrawal=False,
            account_age_hours=round(account_age_hours, 2),
            required_account_age_hours=REQUIRED_ACCOUNT_AGE_HOURS,
            task_earnings_percent=task_percent,
            available_balance=balance,
        )


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
        task_earnings_percent=result.task_earnings_percent,
        available_balance=result.available_balance,
        message=result.message,
    )


def _normalize_wallet(method: str, wallet: Optional[str]) -> Optional[str]:
    if method != "ton":
        return None
    normalized = (wallet or "").strip()
    return normalized or None


async def create_withdrawal_for_user(
        user_id: int,
        payload: WithdrawalCreateRequest,
) -> WithdrawalCreateResponse:
    eligibility = await _build_eligibility(user_id)
    if not eligibility.can_withdraw:
        raise ValueError(eligibility.message)

    method = payload.method
    amount = _safe_float(payload.amount)
    wallet = _normalize_wallet(method, payload.wallet)

    if amount <= 0:
        raise ValueError("Сумма вывода должна быть больше нуля.")

    if amount < MIN_WITHDRAW:
        raise ValueError(f"Минимальная сумма вывода — {MIN_WITHDRAW:.0f}⭐️.")

    if amount > eligibility.available_balance:
        raise ValueError("Недостаточно средств для вывода.")

    if method == "ton":
        if not wallet:
            raise ValueError("Для вывода в TON нужно указать кошелек.")

        async with get_db() as db:
            wallet_in_use = await wallet_used_by_another_user(db, user_id, wallet)
            if wallet_in_use:
                raise ValueError("Этот TON-кошелек уже используется другим пользователем.")

            withdrawal_id = await create_withdrawal(
                db=db,
                user_id=user_id,
                amount=amount,
                method=method,
                wallet=wallet,
            )
            await db.commit()
    else:
        async with get_db() as db:
            withdrawal_id = await create_withdrawal(
                db=db,
                user_id=user_id,
                amount=amount,
                method=method,
                wallet=None,
            )
            await db.commit()

    return WithdrawalCreateResponse(
        ok=True,
        withdrawal_id=withdrawal_id,
        status="pending",
        message="Заявка на вывод создана.",
    )


async def get_my_withdrawals_for_user(
        user_id: int,
        limit: int = 20,
) -> WithdrawalListResponse:
    async with get_db() as db:
        rows = await user_withdrawals(db, user_id=user_id, limit=limit)

    items = [
        WithdrawalItem(
            id=int(row["id"]),
            amount=float(row["amount"]),
            method=row["method"],
            status=row["status"],
            wallet=row["wallet"] if "wallet" in row.keys() else None,
            created_at=row["created_at"],
            processed_at=row["processed_at"] if "processed_at" in row.keys() else None,
            fee_xtr=int(row["fee_xtr"]) if "fee_xtr" in row.keys() and row["fee_xtr"] is not None else 0,
            fee_paid=bool(row["fee_paid"]) if "fee_paid" in row.keys() and row["fee_paid"] is not None else False,
            fee_refunded=bool(row["fee_refunded"]) if "fee_refunded" in row.keys() and row["fee_refunded"] is not None else False,
        )
        for row in rows
    ]

    return WithdrawalListResponse(items=items)