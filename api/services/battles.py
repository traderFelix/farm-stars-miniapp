from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timezone
from typing import Optional, Protocol, cast
from urllib import error as urllib_error
from urllib import request as urllib_request

from api.db.connection import get_db
from api.schemas.battles import BattleRecentResult, BattleResult, BattleState, BattleStatusResponse
from api.schemas.tasks import TaskBattleResult, TaskBattleSnapshot, TaskBattleState
from api.security.request_fingerprint import RequestFingerprint
from api.services.antiabuse import log_user_action_with_fingerprint
from shared.config import (
    TELEGRAM_BOT_TOKEN,
    VIEW_BATTLE_DURATION_SECONDS,
    VIEW_BATTLE_ENTRY_FEE,
    VIEW_BATTLE_HOLD_MAX_SECONDS,
    VIEW_BATTLE_HOLD_MIN_SECONDS,
    VIEW_BATTLE_TARGET_VIEWS,
    VIEW_BATTLE_WAITING_EXPIRE_SECONDS,
)
from shared.db.abuse import count_recent_abuse_events_for_actions
from shared.db.battles import (
    activate_battle,
    cancel_waiting_battle,
    count_finished_battles_between_users,
    count_wins_over_opponent,
    create_waiting_battle,
    ensure_view_battles_schema,
    finish_battle,
    get_battle_by_id,
    get_user_latest_finished_battle,
    get_user_open_battle,
    get_waiting_battle_for_match,
    increment_battle_progress,
    list_expired_waiting_battles,
)
from shared.db.common import tx
from shared.db.ledger import (
    apply_balance_debit_if_enough,
    apply_balance_delta,
    has_battle_entry_lock,
    has_battle_refund_record,
)
from shared.db.tasks import count_completed_task_views_for_user
from shared.db.users import add_user_risk_score, default_game_nickname_for_user_id, get_balance

logger = logging.getLogger(__name__)

_SQLITE_DT_FORMAT = "%Y-%m-%d %H:%M:%S"
_BATTLE_JOIN_CANCEL_MAX_CYCLES_PER_MINUTE = 3


class BattleRowLike(Protocol):
    def __getitem__(self, key: str) -> object:
        ...


def _row_optional_str(row: BattleRowLike, key: str) -> Optional[str]:
    value = row[key]
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    normalized = str(value).strip()
    return normalized or None


def _row_str(row: BattleRowLike, key: str, default: str = "") -> str:
    return _row_optional_str(row, key) or default


def _row_optional_int(row: BattleRowLike, key: str) -> Optional[int]:
    value = row[key]
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    return int(str(value))


def _row_int(row: BattleRowLike, key: str, default: int = 0) -> int:
    value = row[key]
    if value is None or value == "":
        return int(default)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    return int(str(value))


def _row_float(row: BattleRowLike, key: str, default: float = 0.0) -> float:
    value = row[key]
    if value is None or value == "":
        return float(default)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    return float(str(value))


def _parse_db_datetime(value: Optional[str]) -> Optional[datetime]:
    normalized = (value or "").strip()
    if not normalized:
        return None

    try:
        return datetime.strptime(normalized, _SQLITE_DT_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _seconds_left(battle_row: BattleRowLike) -> int:
    ends_at = _parse_db_datetime(_row_optional_str(battle_row, "ends_at"))
    if not ends_at:
        return 0
    return max(int((ends_at - _utc_now()).total_seconds()), 0)


def _display_name(*, game_nickname: Optional[str], user_id: Optional[int]) -> Optional[str]:
    normalized_game_nickname = (game_nickname or "").strip()
    if normalized_game_nickname:
        return normalized_game_nickname
    if user_id is not None:
        return default_game_nickname_for_user_id(int(user_id))
    return None


def _battle_side(battle_row: BattleRowLike, user_id: int) -> str:
    if _row_int(battle_row, "creator_user_id") == int(user_id):
        return "creator"
    opponent_user_id = _row_optional_int(battle_row, "opponent_user_id")
    if opponent_user_id is not None and opponent_user_id == int(user_id):
        return "opponent"
    raise ValueError(f"User {user_id} is not a participant of battle {_row_int(battle_row, 'id')}")


def _opponent_name(battle_row: BattleRowLike, user_id: int) -> Optional[str]:
    side = _battle_side(battle_row, user_id)
    if side == "creator":
        return _display_name(
            game_nickname=_row_optional_str(battle_row, "opponent_game_nickname"),
            user_id=_row_optional_int(battle_row, "opponent_user_id"),
        )
    return _display_name(
        game_nickname=_row_optional_str(battle_row, "creator_game_nickname"),
        user_id=_row_int(battle_row, "creator_user_id"),
    )


def _battle_progress_tuple(battle_row: BattleRowLike, user_id: int) -> tuple[int, int]:
    side = _battle_side(battle_row, user_id)
    creator_views = _row_int(battle_row, "creator_views")
    opponent_views = _row_int(battle_row, "opponent_views")
    if side == "creator":
        return creator_views, opponent_views
    return opponent_views, creator_views


def _battle_recent_result_from_row(
        battle_row: Optional[BattleRowLike],
        user_id: int,
) -> Optional[BattleRecentResult]:
    if not battle_row or _row_str(battle_row, "state") != "finished":
        return None

    result = _row_str(battle_row, "result")
    normalized_result: BattleResult
    if result == "draw":
        normalized_result = "draw"
        delta = 0.0
    elif _row_optional_int(battle_row, "winner_user_id") == int(user_id):
        normalized_result = "won"
        delta = _row_float(battle_row, "stake_amount")
    else:
        normalized_result = "lost"
        delta = -_row_float(battle_row, "stake_amount")

    finished_at = _row_optional_str(battle_row, "resolved_at") or _row_optional_str(battle_row, "created_at") or ""
    if not finished_at:
        return None

    return BattleRecentResult(
        result=normalized_result,
        finished_at=finished_at,
        delta=delta,
        stake_amount=_row_float(battle_row, "stake_amount"),
        opponent_name=_opponent_name(battle_row, user_id),
    )


def _build_status_response(
        *,
        user_id: int,
        current_balance: float,
        total_completed_views: int,
        open_battle: Optional[BattleRowLike],
        latest_finished_battle: Optional[BattleRowLike] = None,
        message: Optional[str] = None,
) -> BattleStatusResponse:
    if open_battle:
        my_progress, opponent_progress = _battle_progress_tuple(open_battle, user_id)
        raw_state = _row_str(open_battle, "state")
        state: BattleState = "waiting" if raw_state == "waiting" else "active"
        default_message = (
            "Ищу соперника для дуэли"
            if state == "waiting"
            else "Кто первым добьет 20 просмотров, тот забирает банк"
        )
        return BattleStatusResponse(
            state=state,
            battle_id=_row_int(open_battle, "id"),
            target_views=_row_int(open_battle, "target_views", VIEW_BATTLE_TARGET_VIEWS),
            entry_fee=_row_float(open_battle, "stake_amount", VIEW_BATTLE_ENTRY_FEE),
            duration_seconds=_row_int(open_battle, "duration_seconds", VIEW_BATTLE_DURATION_SECONDS),
            seconds_left=_seconds_left(open_battle) if state == "active" else 0,
            my_progress=my_progress,
            opponent_progress=opponent_progress,
            opponent_name=_opponent_name(open_battle, user_id),
            current_balance=float(current_balance),
            total_completed_views=int(total_completed_views),
            can_join=False,
            can_cancel=state == "waiting",
            can_open_tasks=state == "active",
            hold_seconds_min=VIEW_BATTLE_HOLD_MIN_SECONDS,
            hold_seconds_max=VIEW_BATTLE_HOLD_MAX_SECONDS,
            message=message or default_message,
            last_result=None,
        )

    return BattleStatusResponse(
        state="idle",
        battle_id=None,
        target_views=VIEW_BATTLE_TARGET_VIEWS,
        entry_fee=VIEW_BATTLE_ENTRY_FEE,
        duration_seconds=VIEW_BATTLE_DURATION_SECONDS,
        seconds_left=0,
        my_progress=0,
        opponent_progress=0,
        opponent_name=None,
        current_balance=float(current_balance),
        total_completed_views=int(total_completed_views),
        can_join=float(current_balance) >= VIEW_BATTLE_ENTRY_FEE,
        can_cancel=False,
        can_open_tasks=False,
        hold_seconds_min=VIEW_BATTLE_HOLD_MIN_SECONDS,
        hold_seconds_max=VIEW_BATTLE_HOLD_MAX_SECONDS,
        message=message or "",
        last_result=_battle_recent_result_from_row(latest_finished_battle, user_id),
    )


def build_battle_snapshot_for_task(
        battle_row: BattleRowLike,
        user_id: int,
        *,
        result: Optional[TaskBattleResult] = None,
) -> TaskBattleSnapshot:
    my_progress, opponent_progress = _battle_progress_tuple(battle_row, user_id)
    normalized_result: Optional[TaskBattleResult] = result
    if normalized_result is None and _row_str(battle_row, "state") == "finished":
        if _row_str(battle_row, "result") == "draw":
            normalized_result = "draw"
        elif _row_optional_int(battle_row, "winner_user_id") == int(user_id):
            normalized_result = "won"
        else:
            normalized_result = "lost"

    snapshot_state: TaskBattleState = (
        "active" if _row_str(battle_row, "state") == "active" and result is None else "finished"
    )
    return TaskBattleSnapshot(
        state=snapshot_state,
        result=normalized_result,
        my_progress=my_progress,
        opponent_progress=opponent_progress,
        target_views=_row_int(battle_row, "target_views", VIEW_BATTLE_TARGET_VIEWS),
        seconds_left=_seconds_left(battle_row),
        opponent_name=_opponent_name(battle_row, user_id),
    )


def _telegram_api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def _build_battle_started_reply_markup() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "👁 Перейти к просмотру постов", "callback_data": "task:view_post"}],
        ]
    }


def _send_telegram_message(*, user_id: int, text: str, reply_markup: Optional[dict] = None) -> None:
    if not TELEGRAM_BOT_TOKEN:
        return

    payload_data: dict[str, object] = {
        "chat_id": int(user_id),
        "text": text,
    }
    if reply_markup is not None:
        payload_data["reply_markup"] = reply_markup

    payload = json.dumps(payload_data, ensure_ascii=False).encode("utf-8")

    request = urllib_request.Request(
        _telegram_api_url("sendMessage"),
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    with urllib_request.urlopen(request, timeout=15) as response:
        response_payload = json.loads(response.read().decode("utf-8"))

    if not response_payload.get("ok"):
        raise RuntimeError(response_payload.get("description") or "Telegram API request failed")


def _build_battle_started_text(*, battle_row: BattleRowLike, user_id: int) -> str:
    opponent_name = _opponent_name(battle_row, user_id) or "соперник"
    return (
        "⚔️ Дуэль началась\n\n"
        f"Твой соперник: {opponent_name}\n"
        "Начинайте просмотры, удачи\n\n"
        f"Цель: {_row_int(battle_row, 'target_views', VIEW_BATTLE_TARGET_VIEWS)} просмотров\n"
        f"Время: {_row_int(battle_row, 'duration_seconds', VIEW_BATTLE_DURATION_SECONDS) // 60} минут\n"
        f"Ставка: {_row_float(battle_row, 'stake_amount', VIEW_BATTLE_ENTRY_FEE):g}⭐\n\n"
        "Открывай поток постов и добивай 20 первым"
    )


def _build_battle_resolved_text(*, battle_row: BattleRowLike, user_id: int) -> str:
    result = _row_str(battle_row, "result")
    stake_amount = _row_float(battle_row, "stake_amount", VIEW_BATTLE_ENTRY_FEE)
    if result == "draw":
        return (
            "🤝 Дуэль завершилась вничью\n\n"
            f"За 5 минут никто не успел добить {_row_int(battle_row, 'target_views', VIEW_BATTLE_TARGET_VIEWS)} просмотров\n"
            f"{stake_amount:g}⭐ возвращена на баланс"
        )

    if _row_optional_int(battle_row, "winner_user_id") == int(user_id):
        return (
            "🏆 Ты выиграл дуэль\n\n"
            f"Ты первым добил {_row_int(battle_row, 'target_views', VIEW_BATTLE_TARGET_VIEWS)} просмотров\n"
            f"Ставка {stake_amount:g}⭐ возвращена\n"
            f"Боевой бонус: +{stake_amount:g}⭐"
        )

    opponent_name = _opponent_name(battle_row, user_id) or "соперник"
    return (
        "💥 Дуэль проиграна\n\n"
        f"{opponent_name} первым добил {_row_int(battle_row, 'target_views', VIEW_BATTLE_TARGET_VIEWS)} просмотров\n"
        f"Ставка {stake_amount:g}⭐ списана"
    )


def _safe_notify_battle_start(battle_row: BattleRowLike) -> None:
    opponent_user_id = _row_optional_int(battle_row, "opponent_user_id")
    if opponent_user_id is None:
        return

    for participant_user_id in (
            _row_int(battle_row, "creator_user_id"),
            opponent_user_id,
    ):
        try:
            _send_telegram_message(
                user_id=participant_user_id,
                text=_build_battle_started_text(
                    battle_row=battle_row,
                    user_id=participant_user_id,
                ),
                reply_markup=_build_battle_started_reply_markup(),
            )
        except (urllib_error.HTTPError, urllib_error.URLError, RuntimeError) as exc:
            logger.warning(
                "Failed to notify user about battle start battle_id=%s user_id=%s detail=%s",
                _row_int(battle_row, "id"),
                participant_user_id,
                exc,
            )


def _safe_notify_battle_resolution(battle_row: BattleRowLike) -> None:
    participant_ids = [_row_int(battle_row, "creator_user_id")]
    opponent_user_id = _row_optional_int(battle_row, "opponent_user_id")
    if opponent_user_id is not None:
        participant_ids.append(opponent_user_id)

    for participant_user_id in participant_ids:
        try:
            _send_telegram_message(
                user_id=participant_user_id,
                text=_build_battle_resolved_text(
                    battle_row=battle_row,
                    user_id=participant_user_id,
                ),
            )
        except (urllib_error.HTTPError, urllib_error.URLError, RuntimeError) as exc:
            logger.warning(
                "Failed to notify user about battle resolution battle_id=%s user_id=%s detail=%s",
                _row_int(battle_row, "id"),
                participant_user_id,
                exc,
            )


async def _resolve_finished_battle(
        db,
        *,
        battle_row: BattleRowLike,
        result: str,
        winner_user_id: Optional[int],
) -> Optional[dict]:
    battle_id = _row_int(battle_row, "id")
    stake_amount = _row_float(battle_row, "stake_amount", VIEW_BATTLE_ENTRY_FEE)

    updated = await finish_battle(
        db,
        battle_id=battle_id,
        result=result,
        winner_user_id=winner_user_id,
    )
    if not updated:
        return None

    creator_user_id = _row_int(battle_row, "creator_user_id")
    opponent_user_id = _row_optional_int(battle_row, "opponent_user_id")

    if result == "draw":
        await apply_balance_delta(
            db,
            user_id=creator_user_id,
            delta=stake_amount,
            reason="battle_refund",
            meta=f"battle_id={battle_id};result=draw",
        )
        if opponent_user_id is not None:
            await apply_balance_delta(
                db,
                user_id=opponent_user_id,
                delta=stake_amount,
                reason="battle_refund",
                meta=f"battle_id={battle_id};result=draw",
            )
    elif winner_user_id is not None:
        await apply_balance_delta(
            db,
            user_id=int(winner_user_id),
            delta=stake_amount,
            reason="battle_refund",
            meta=f"battle_id={battle_id};result={result}",
        )
        await apply_balance_delta(
            db,
            user_id=int(winner_user_id),
            delta=stake_amount,
            reason="battle_bonus",
            meta=f"battle_id={battle_id};result={result}",
        )

        loser_user_id = None
        if opponent_user_id is not None:
            loser_user_id = creator_user_id if int(winner_user_id) == opponent_user_id else opponent_user_id

        if loser_user_id is not None:
            pair_total_24h = await count_finished_battles_between_users(
                db,
                user_a=int(winner_user_id),
                user_b=int(loser_user_id),
                hours=24,
            )
            same_winner_24h = await count_wins_over_opponent(
                db,
                user_id=int(winner_user_id),
                opponent_user_id=int(loser_user_id),
                hours=24,
            )

            if pair_total_24h >= 5:
                await add_user_risk_score(
                    db,
                    int(winner_user_id),
                    20,
                    "Слишком частые батлы против одного и того же соперника",
                    source="battles",
                    meta=f"opponent_user_id={loser_user_id};pair_total_24h={pair_total_24h}",
                )
                await add_user_risk_score(
                    db,
                    int(loser_user_id),
                    20,
                    "Слишком частые батлы против одного и того же соперника",
                    source="battles",
                    meta=f"opponent_user_id={winner_user_id};pair_total_24h={pair_total_24h}",
                )

            if same_winner_24h >= 4:
                await add_user_risk_score(
                    db,
                    int(winner_user_id),
                    35,
                    "Подозрительная серия побед над одним и тем же соперником",
                    source="battles",
                    meta=f"opponent_user_id={loser_user_id};wins_24h={same_winner_24h}",
                )
                await add_user_risk_score(
                    db,
                    int(loser_user_id),
                    35,
                    "Подозрительная серия поражений от одного и того же соперника",
                    source="battles",
                    meta=f"opponent_user_id={winner_user_id};losses_24h={same_winner_24h}",
                )

    return {
        "battle_id": battle_id,
        "result": result,
        "winner_user_id": int(winner_user_id) if winner_user_id is not None else None,
    }


async def _refund_waiting_battle_stake_if_locked(
        db,
        *,
        battle_id: int,
        user_id: int,
        stake_amount: float,
        result: str,
) -> bool:
    if not await has_battle_entry_lock(db, user_id=int(user_id), battle_id=int(battle_id)):
        return False

    if await has_battle_refund_record(db, user_id=int(user_id), battle_id=int(battle_id)):
        return False

    await apply_balance_delta(
        db,
        user_id=int(user_id),
        delta=float(stake_amount),
        reason="battle_refund",
        meta=f"battle_id={int(battle_id)};result={result}",
    )
    return True


async def _expire_waiting_battles_with_refund(db) -> None:
    expired_battles = await list_expired_waiting_battles(
        db,
        older_than_seconds=VIEW_BATTLE_WAITING_EXPIRE_SECONDS,
    )
    for battle_row in expired_battles:
        battle_id = _row_int(battle_row, "id")
        creator_user_id = _row_int(battle_row, "creator_user_id")
        cancelled = await cancel_waiting_battle(
            db,
            battle_id=battle_id,
            user_id=creator_user_id,
        )
        if not cancelled:
            continue

        await _refund_waiting_battle_stake_if_locked(
            db,
            battle_id=battle_id,
            user_id=creator_user_id,
            stake_amount=_row_float(battle_row, "stake_amount", VIEW_BATTLE_ENTRY_FEE),
            result="expired",
        )


async def _sync_user_battle_resolution(db, *, user_id: int) -> Optional[dict]:
    await ensure_view_battles_schema(db)
    await _expire_waiting_battles_with_refund(db)

    battle_row = cast(Optional[BattleRowLike], await get_user_open_battle(db, user_id))
    if not battle_row or _row_str(battle_row, "state") != "active":
        return None

    if _seconds_left(battle_row) > 0:
        return None

    return await _resolve_finished_battle(
        db,
        battle_row=battle_row,
        result="draw",
        winner_user_id=None,
    )


async def get_active_battle_for_user_db(
        db,
        *,
        user_id: int,
) -> Optional[BattleRowLike]:
    await _sync_user_battle_resolution(db, user_id=user_id)
    battle_row = cast(Optional[BattleRowLike], await get_user_open_battle(db, user_id))
    if not battle_row or _row_str(battle_row, "state") != "active":
        return None
    return battle_row


async def get_battle_hold_seconds_for_user(
        db,
        *,
        user_id: int,
        default_seconds: int,
) -> int:
    battle_row = await get_active_battle_for_user_db(db, user_id=user_id)
    if not battle_row:
        return int(default_seconds)

    return random.randint(VIEW_BATTLE_HOLD_MIN_SECONDS, VIEW_BATTLE_HOLD_MAX_SECONDS)


async def get_battle_status_for_user(
        user_id: int,
) -> BattleStatusResponse:
    db = await get_db()
    resolution_to_notify = None
    try:
        async with tx(db, immediate=True):
            resolution_to_notify = await _sync_user_battle_resolution(db, user_id=user_id)
            open_battle = cast(Optional[BattleRowLike], await get_user_open_battle(db, user_id))
            latest_finished = (
                None
                if open_battle
                else cast(Optional[BattleRowLike], await get_user_latest_finished_battle(db, user_id))
            )
            current_balance = await get_balance(db, user_id)
            total_completed_views = await count_completed_task_views_for_user(db, user_id)

            response = _build_status_response(
                user_id=user_id,
                current_balance=current_balance,
                total_completed_views=total_completed_views,
                open_battle=open_battle,
                latest_finished_battle=latest_finished,
            )
    finally:
        await db.close()

    if resolution_to_notify:
        db = await get_db()
        try:
            battle_row = cast(Optional[BattleRowLike], await get_battle_by_id(db, int(resolution_to_notify["battle_id"])))
        finally:
            await db.close()
        if battle_row:
            _safe_notify_battle_resolution(battle_row)

    return response


async def join_battle_for_user(
        user_id: int,
        *,
        fingerprint: Optional[RequestFingerprint] = None,
) -> BattleStatusResponse:
    db = await get_db()
    started_battle_id: Optional[int] = None
    resolution_to_notify = None
    response: Optional[BattleStatusResponse] = None
    try:
        async with tx(db, immediate=True):
            await log_user_action_with_fingerprint(
                db,
                user_id=user_id,
                action="battle_join_attempt",
                fingerprint=fingerprint,
            )

            recent_cancel_count = await count_recent_abuse_events_for_actions(
                db,
                user_id=int(user_id),
                actions=["battle_cancel_success"],
                minutes=1,
            )
            if recent_cancel_count >= _BATTLE_JOIN_CANCEL_MAX_CYCLES_PER_MINUTE:
                current_balance = await get_balance(db, user_id)
                total_completed_views = await count_completed_task_views_for_user(db, user_id)
                response = _build_status_response(
                    user_id=user_id,
                    current_balance=current_balance,
                    total_completed_views=total_completed_views,
                    open_battle=None,
                    latest_finished_battle=cast(Optional[BattleRowLike], await get_user_latest_finished_battle(db, user_id)),
                    message="Слишком частые перезапуски поиска, попробуй через минуту",
                )

            resolution_to_notify = await _sync_user_battle_resolution(db, user_id=user_id)
            open_battle = cast(Optional[BattleRowLike], await get_user_open_battle(db, user_id))
            if response is None and open_battle:
                current_balance = await get_balance(db, user_id)
                total_completed_views = await count_completed_task_views_for_user(db, user_id)
                response = _build_status_response(
                    user_id=user_id,
                    current_balance=current_balance,
                    total_completed_views=total_completed_views,
                    open_battle=open_battle,
                    message="У тебя уже есть активная дуэль",
                )
            if response is None:
                candidate = cast(Optional[BattleRowLike], await get_waiting_battle_for_match(db, user_id))
                if candidate:
                    battle_id = _row_int(candidate, "id")
                    creator_user_id = _row_int(candidate, "creator_user_id")
                    creator_stake_locked = await has_battle_entry_lock(
                        db,
                        user_id=creator_user_id,
                        battle_id=battle_id,
                    )
                    if not creator_stake_locked:
                        creator_debited = await apply_balance_debit_if_enough(
                            db,
                            user_id=creator_user_id,
                            amount=VIEW_BATTLE_ENTRY_FEE,
                            reason="battle_entry",
                            meta=f"battle_id={battle_id}",
                        )
                        if not creator_debited:
                            await cancel_waiting_battle(
                                db,
                                battle_id=battle_id,
                                user_id=creator_user_id,
                            )
                        else:
                            creator_stake_locked = True

                    if creator_stake_locked:
                        my_balance = await get_balance(db, user_id)
                        if my_balance < VIEW_BATTLE_ENTRY_FEE:
                            total_completed_views = await count_completed_task_views_for_user(db, user_id)
                            response = _build_status_response(
                                user_id=user_id,
                                current_balance=my_balance,
                                total_completed_views=total_completed_views,
                                open_battle=None,
                                latest_finished_battle=cast(Optional[BattleRowLike], await get_user_latest_finished_battle(db, user_id)),
                                message="Для входа в дуэль нужна 1⭐ на игровом балансе",
                            )
                        else:
                            opponent_debited = await apply_balance_debit_if_enough(
                                db,
                                user_id=user_id,
                                amount=VIEW_BATTLE_ENTRY_FEE,
                                reason="battle_entry",
                                meta=f"battle_id={battle_id}",
                            )
                            if not opponent_debited:
                                current_balance = await get_balance(db, user_id)
                                total_completed_views = await count_completed_task_views_for_user(db, user_id)
                                response = _build_status_response(
                                    user_id=user_id,
                                    current_balance=current_balance,
                                    total_completed_views=total_completed_views,
                                    open_battle=None,
                                    latest_finished_battle=cast(Optional[BattleRowLike], await get_user_latest_finished_battle(db, user_id)),
                                    message="Для входа в дуэль нужна 1⭐ на игровом балансе",
                                )
                            else:
                                activated = await activate_battle(
                                    db,
                                    battle_id=battle_id,
                                    opponent_user_id=user_id,
                                )
                                if not activated:
                                    raise RuntimeError("Failed to activate battle after stake debit")

                                await log_user_action_with_fingerprint(
                                    db,
                                    user_id=user_id,
                                    action="battle_join_success",
                                    fingerprint=fingerprint,
                                    amount=VIEW_BATTLE_ENTRY_FEE,
                                    entity_type="battle",
                                    entity_id=str(battle_id),
                                )
                                started_battle_id = battle_id
                                open_battle = cast(Optional[BattleRowLike], await get_battle_by_id(db, battle_id))
                                current_balance = await get_balance(db, user_id)
                                total_completed_views = await count_completed_task_views_for_user(db, user_id)
                                response = _build_status_response(
                                    user_id=user_id,
                                    current_balance=current_balance,
                                    total_completed_views=total_completed_views,
                                    open_battle=open_battle,
                                    message="Соперник найден, дуэль началась",
                                )

            if response is None:
                current_balance = await get_balance(db, user_id)
                if current_balance < VIEW_BATTLE_ENTRY_FEE:
                    total_completed_views = await count_completed_task_views_for_user(db, user_id)
                    response = _build_status_response(
                        user_id=user_id,
                        current_balance=current_balance,
                        total_completed_views=total_completed_views,
                        open_battle=None,
                        latest_finished_battle=await get_user_latest_finished_battle(db, user_id),
                        message="Для входа в дуэль нужна 1⭐ на игровом балансе",
                    )

            if response is None:
                battle_id = await create_waiting_battle(
                    db,
                    creator_user_id=user_id,
                    target_views=VIEW_BATTLE_TARGET_VIEWS,
                    stake_amount=VIEW_BATTLE_ENTRY_FEE,
                    duration_seconds=VIEW_BATTLE_DURATION_SECONDS,
                )
                creator_debited = await apply_balance_debit_if_enough(
                    db,
                    user_id=user_id,
                    amount=VIEW_BATTLE_ENTRY_FEE,
                    reason="battle_entry",
                    meta=f"battle_id={battle_id}",
                )
                if not creator_debited:
                    raise RuntimeError("Failed to reserve battle entry fee for waiting battle")
                open_battle = cast(Optional[BattleRowLike], await get_battle_by_id(db, battle_id))
                current_balance = await get_balance(db, user_id)
                total_completed_views = await count_completed_task_views_for_user(db, user_id)
                response = _build_status_response(
                    user_id=user_id,
                    current_balance=current_balance,
                    total_completed_views=total_completed_views,
                    open_battle=open_battle,
                    message="Ищу соперника для дуэли",
                )
    finally:
        await db.close()

    if resolution_to_notify:
        db = await get_db()
        try:
            battle_row = cast(Optional[BattleRowLike], await get_battle_by_id(db, int(resolution_to_notify["battle_id"])))
        finally:
            await db.close()
        if battle_row:
            _safe_notify_battle_resolution(battle_row)

    if started_battle_id is not None:
        db = await get_db()
        try:
            started_battle_id_int = int(started_battle_id)
            battle_row = cast(Optional[BattleRowLike], await get_battle_by_id(db, started_battle_id_int))
        finally:
            await db.close()
        if battle_row:
            _safe_notify_battle_start(battle_row)

    if response is not None:
        return response

    return await get_battle_status_for_user(user_id)


async def cancel_battle_for_user(
        user_id: int,
        *,
        fingerprint: Optional[RequestFingerprint] = None,
) -> BattleStatusResponse:
    db = await get_db()
    response: Optional[BattleStatusResponse] = None
    try:
        async with tx(db, immediate=True):
            await log_user_action_with_fingerprint(
                db,
                user_id=user_id,
                action="battle_cancel_attempt",
                fingerprint=fingerprint,
            )

            await _sync_user_battle_resolution(db, user_id=user_id)
            open_battle = cast(Optional[BattleRowLike], await get_user_open_battle(db, user_id))
            if not open_battle or _row_str(open_battle, "state") != "waiting":
                current_balance = await get_balance(db, user_id)
                total_completed_views = await count_completed_task_views_for_user(db, user_id)
                response = _build_status_response(
                    user_id=user_id,
                    current_balance=current_balance,
                    total_completed_views=total_completed_views,
                    open_battle=open_battle,
                    latest_finished_battle=(
                        None
                        if open_battle
                        else cast(Optional[BattleRowLike], await get_user_latest_finished_battle(db, user_id))
                    ),
                    message="Нечего отменять",
                )
            else:
                cancelled = await cancel_waiting_battle(
                    db,
                    battle_id=_row_int(open_battle, "id"),
                    user_id=user_id,
                )
                if cancelled:
                    await log_user_action_with_fingerprint(
                        db,
                        user_id=user_id,
                        action="battle_cancel_success",
                        fingerprint=fingerprint,
                        entity_type="battle",
                        entity_id=str(_row_int(open_battle, "id")),
                    )
                    await _refund_waiting_battle_stake_if_locked(
                        db,
                        battle_id=_row_int(open_battle, "id"),
                        user_id=user_id,
                        stake_amount=_row_float(open_battle, "stake_amount", VIEW_BATTLE_ENTRY_FEE),
                        result="cancelled",
                    )
                current_balance = await get_balance(db, user_id)
                total_completed_views = await count_completed_task_views_for_user(db, user_id)
                response = _build_status_response(
                    user_id=user_id,
                    current_balance=current_balance,
                    total_completed_views=total_completed_views,
                    open_battle=None,
                    latest_finished_battle=cast(Optional[BattleRowLike], await get_user_latest_finished_battle(db, user_id)),
                    message=None,
                )
    finally:
        await db.close()

    if response is not None:
        return response

    return await get_battle_status_for_user(user_id)


async def register_battle_view_completion(
        db,
        *,
        user_id: int,
) -> dict:
    resolution_to_notify = await _sync_user_battle_resolution(db, user_id=user_id)
    battle_row = cast(Optional[BattleRowLike], await get_user_open_battle(db, user_id))
    if not battle_row or _row_str(battle_row, "state") != "active":
        return {
            "battle": None,
            "resolved_battle_id": int(resolution_to_notify["battle_id"]) if resolution_to_notify else None,
        }

    updated = await increment_battle_progress(
        db,
        battle_id=_row_int(battle_row, "id"),
        user_id=user_id,
    )
    if not updated:
        battle_row = cast(Optional[BattleRowLike], await get_battle_by_id(db, _row_int(battle_row, "id")))
        if battle_row and _row_str(battle_row, "state") == "finished":
            resolution_to_notify = {
                "battle_id": _row_int(battle_row, "id"),
            }
        return {
            "battle": build_battle_snapshot_for_task(battle_row, user_id) if battle_row else None,
            "resolved_battle_id": int(resolution_to_notify["battle_id"]) if resolution_to_notify else None,
        }

    battle_row = cast(Optional[BattleRowLike], await get_battle_by_id(db, _row_int(battle_row, "id")))
    if not battle_row:
        return {
            "battle": None,
            "resolved_battle_id": int(resolution_to_notify["battle_id"]) if resolution_to_notify else None,
        }
    my_progress, _ = _battle_progress_tuple(battle_row, user_id)
    target_views = _row_int(battle_row, "target_views", VIEW_BATTLE_TARGET_VIEWS)

    if my_progress >= target_views:
        resolution_to_notify = await _resolve_finished_battle(
            db,
            battle_row=battle_row,
            result="winner_reached_target",
            winner_user_id=user_id,
        )
        battle_row = cast(Optional[BattleRowLike], await get_battle_by_id(db, _row_int(battle_row, "id")))
        if not battle_row:
            return {
                "battle": None,
                "resolved_battle_id": int(resolution_to_notify["battle_id"]) if resolution_to_notify else None,
            }
        return {
            "battle": build_battle_snapshot_for_task(battle_row, user_id, result="won"),
            "resolved_battle_id": int(resolution_to_notify["battle_id"]) if resolution_to_notify else None,
        }

    return {
        "battle": build_battle_snapshot_for_task(battle_row, user_id),
        "resolved_battle_id": int(resolution_to_notify["battle_id"]) if resolution_to_notify else None,
    }


async def notify_battle_resolution_by_id(
        battle_id: Optional[int],
) -> None:
    if battle_id is None:
        return

    db = await get_db()
    try:
        battle_row = await get_battle_by_id(db, int(battle_id))
    finally:
        await db.close()

    if battle_row:
        _safe_notify_battle_resolution(battle_row)
