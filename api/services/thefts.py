from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from typing import Optional, Protocol, cast
from urllib import error as urllib_error
from urllib import request as urllib_request

from api.db.connection import get_db
from api.schemas.thefts import (
    TheftActionResponse,
    TheftActivitySnapshot,
    TheftRecentResult,
    TheftResult,
    TheftRole,
    TheftStatusResponse,
)
from api.services.antiabuse import log_user_action_with_fingerprint
from api.security.request_fingerprint import RequestFingerprint
from shared.config import (
    TELEGRAM_BOT_TOKEN,
    VIEW_BATTLE_HOLD_MAX_SECONDS,
    VIEW_BATTLE_HOLD_MIN_SECONDS,
    VIEW_THEFT_ATTACK_TARGET_VIEWS,
    VIEW_THEFT_DAILY_LIMIT_SECONDS,
    VIEW_THEFT_DEFENSE_TARGET_VIEWS,
    VIEW_THEFT_DURATION_SECONDS,
    VIEW_THEFT_MAX_AMOUNT,
    VIEW_THEFT_MIN_AMOUNT,
    VIEW_THEFT_MIN_WITHDRAWAL_ABILITY,
    VIEW_THEFT_PROTECTION_SECONDS,
    VIEW_THEFT_PROTECTION_TARGET_VIEWS,
)
from shared.db.abuse import log_abuse_event
from shared.db.battles import get_user_open_battle
from shared.db.common import tx
from shared.db.ledger import apply_balance_debit_if_enough, apply_balance_delta
from shared.db.ledger import get_withdrawal_ability
from shared.db.tasks import count_completed_task_views_for_user
from shared.db.thefts import (
    create_theft_attempt,
    create_theft_protection_attempt,
    ensure_view_thefts_schema,
    finish_theft,
    finish_theft_protection_attempt,
    get_theft_by_id,
    get_user_active_protection_attempt,
    get_user_active_theft,
    get_user_current_protection,
    get_user_latest_finished_theft,
    has_recent_theft_attack,
    increment_theft_progress,
    increment_theft_protection_progress,
    list_expired_active_thefts,
    list_expired_theft_protection_attempts,
    list_theft_victim_candidates,
    upsert_theft_protection,
)
from shared.db.users import default_game_nickname_for_user_id, get_balance

logger = logging.getLogger(__name__)

_SQLITE_DT_FORMAT = "%Y-%m-%d %H:%M:%S"


class TheftRowLike(Protocol):
    def __getitem__(self, key: str) -> object:
        ...


def _optional_theft_row(row: object) -> Optional[TheftRowLike]:
    if row is None:
        return None
    return cast(TheftRowLike, row)


def _row_optional_str(row: TheftRowLike, key: str) -> Optional[str]:
    value = row[key]
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    normalized = str(value).strip()
    return normalized or None


def _row_str(row: TheftRowLike, key: str, default: str = "") -> str:
    return _row_optional_str(row, key) or default


def _row_optional_int(row: TheftRowLike, key: str) -> Optional[int]:
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


def _row_int(row: TheftRowLike, key: str, default: int = 0) -> int:
    return _row_optional_int(row, key) if _row_optional_int(row, key) is not None else int(default)


def _row_float(row: TheftRowLike, key: str, default: float = 0.0) -> float:
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


def _format_api_datetime(value: Optional[str]) -> Optional[str]:
    parsed = _parse_db_datetime(value)
    if not parsed:
        return value
    return parsed.isoformat().replace("+00:00", "Z")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _seconds_left(row: TheftRowLike) -> int:
    ends_at = _parse_db_datetime(_row_optional_str(row, "ends_at"))
    if not ends_at:
        return 0
    return max(int((ends_at - _utc_now()).total_seconds()), 0)


def _display_name(*, game_nickname: Optional[str], username: Optional[str], user_id: Optional[int]) -> Optional[str]:
    normalized_game_nickname = (game_nickname or "").strip()
    if normalized_game_nickname:
        return normalized_game_nickname
    normalized_username = (username or "").strip()
    if normalized_username:
        return f"@{normalized_username}"
    if user_id is not None:
        return default_game_nickname_for_user_id(int(user_id))
    return None


def _opponent_name(theft_row: TheftRowLike, user_id: int) -> Optional[str]:
    if _row_int(theft_row, "attacker_user_id") == int(user_id):
        return _display_name(
            game_nickname=_row_optional_str(theft_row, "victim_game_nickname"),
            username=_row_optional_str(theft_row, "victim_username"),
            user_id=_row_int(theft_row, "victim_user_id"),
        )
    return _display_name(
        game_nickname=_row_optional_str(theft_row, "attacker_game_nickname"),
        username=_row_optional_str(theft_row, "attacker_username"),
        user_id=_row_int(theft_row, "attacker_user_id"),
    )


def _theft_role(theft_row: TheftRowLike, user_id: int) -> str:
    if _row_int(theft_row, "attacker_user_id") == int(user_id):
        return "attacker"
    if _row_int(theft_row, "victim_user_id") == int(user_id):
        return "victim"
    raise ValueError(f"User {user_id} is not a participant of theft {_row_int(theft_row, 'id')}")


def _build_theft_snapshot(
        theft_row: TheftRowLike,
        user_id: int,
        *,
        result: Optional[str] = None,
) -> TheftActivitySnapshot:
    role = _theft_role(theft_row, user_id)
    is_attacker = role == "attacker"
    my_progress = _row_int(theft_row, "attacker_views" if is_attacker else "victim_views")
    opponent_progress = _row_int(theft_row, "victim_views" if is_attacker else "attacker_views")
    target_views = _row_int(
        theft_row,
        "attacker_target_views" if is_attacker else "victim_target_views",
    )
    opponent_target_views = _row_int(
        theft_row,
        "victim_target_views" if is_attacker else "attacker_target_views",
    )

    normalized_result = result
    if normalized_result is None and _row_str(theft_row, "state") == "finished":
        normalized_result = _row_optional_str(theft_row, "result")
    snapshot_state = "active" if _row_str(theft_row, "state") == "active" and normalized_result is None else "finished"
    amount = _row_float(theft_row, "amount")
    if role == "attacker" and snapshot_state == "active":
        amount = 0

    return TheftActivitySnapshot(
        state=snapshot_state,
        kind="attack" if is_attacker else "defense",
        result=cast(Optional[TheftResult], normalized_result),
        role=cast(TheftRole, role),
        my_progress=my_progress,
        target_views=target_views,
        opponent_progress=opponent_progress,
        opponent_target_views=opponent_target_views,
        seconds_left=_seconds_left(theft_row),
        amount=amount,
        opponent_name=_opponent_name(theft_row, user_id),
    )


def _theft_recent_result_from_row(row: Optional[TheftRowLike], user_id: int) -> Optional[TheftRecentResult]:
    if not row:
        return None

    result = _row_optional_str(row, "result")
    if result not in {"stolen", "defended", "expired", "protected"}:
        return None

    finished_at = _row_optional_str(row, "resolved_at") or _row_optional_str(row, "created_at") or ""
    if not finished_at:
        return None

    return TheftRecentResult(
        result=cast(TheftResult, result),
        role=cast(TheftRole, _theft_role(row, user_id)),
        finished_at=_format_api_datetime(finished_at) or finished_at,
        amount=_row_float(row, "amount"),
        opponent_name=_opponent_name(row, user_id),
    )


def _build_protection_snapshot(row, *, result: Optional[str] = None) -> TheftActivitySnapshot:
    normalized_result = result or row["result"]
    return TheftActivitySnapshot(
        state="active" if row["state"] == "active" and normalized_result is None else "finished",
        kind="protection",
        result=cast(Optional[TheftResult], normalized_result),
        role="protector",
        my_progress=int(row["views"] or 0),
        target_views=int(row["target_views"] or VIEW_THEFT_PROTECTION_TARGET_VIEWS),
        seconds_left=_seconds_left(cast(TheftRowLike, row)),
    )


def _telegram_api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def _task_reply_markup() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "👁 Смотреть посты", "callback_data": "task:view_post"}],
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


def _safe_notify_theft_started(theft_row: TheftRowLike) -> None:
    victim_user_id = _row_int(theft_row, "victim_user_id")
    attacker_name = _opponent_name(theft_row, victim_user_id) or "кто-то"
    try:
        _send_telegram_message(
            user_id=victim_user_id,
            text=(
                "🚨 На тебя напали\n\n"
                f"{attacker_name} пытается украсть {_row_float(theft_row, 'amount'):g}⭐\n"
                f"Чтобы отбить атаку, сделай {VIEW_THEFT_DEFENSE_TARGET_VIEWS} просмотра за "
                f"{VIEW_THEFT_DURATION_SECONDS // 60} минуты быстрее, чем вор сделает "
                f"{VIEW_THEFT_ATTACK_TARGET_VIEWS} просмотров."
            ),
            reply_markup=_task_reply_markup(),
        )
    except (urllib_error.HTTPError, urllib_error.URLError, RuntimeError) as exc:
        logger.warning(
            "Failed to notify victim about theft start theft_id=%s user_id=%s detail=%s",
            _row_int(theft_row, "id"),
            victim_user_id,
            exc,
        )


def _build_theft_resolved_text(*, theft_row: TheftRowLike, user_id: int) -> str:
    result = _row_str(theft_row, "result")
    amount = _row_float(theft_row, "amount")
    role = _theft_role(theft_row, user_id)
    opponent_name = _opponent_name(theft_row, user_id) or "соперник"

    if result == "stolen":
        if role == "attacker":
            return (
                "🕵️ Кража удалась\n\n"
                f"Ты украл у {opponent_name} {amount:g}⭐"
            )
        return (
            "💥 Кража прошла\n\n"
            f"{opponent_name} успел сделать просмотры и украл {amount:g}⭐"
        )

    if result == "defended":
        if role == "victim":
            return (
                "🛡 Атака отбита\n\n"
                f"Ты защитился от {opponent_name}, заблокированные {amount:g}⭐ вернулись на баланс"
            )
        return (
            "🛡 Кражу отбили\n\n"
            f"{opponent_name} успел защититься быстрее"
        )

    return (
        "⌛ Кража сорвалась\n\n"
        f"Время вышло, заблокированные {amount:g}⭐ вернулись владельцу"
    )


def _safe_notify_theft_resolution(theft_row: TheftRowLike) -> None:
    for participant_user_id in (
        _row_int(theft_row, "attacker_user_id"),
        _row_int(theft_row, "victim_user_id"),
    ):
        try:
            _send_telegram_message(
                user_id=participant_user_id,
                text=_build_theft_resolved_text(
                    theft_row=theft_row,
                    user_id=participant_user_id,
                ),
            )
        except (urllib_error.HTTPError, urllib_error.URLError, RuntimeError) as exc:
            logger.warning(
                "Failed to notify user about theft resolution theft_id=%s user_id=%s detail=%s",
                _row_int(theft_row, "id"),
                participant_user_id,
                exc,
            )


async def _resolve_theft(db, theft_row: TheftRowLike, *, result: str, winner_user_id: Optional[int]) -> Optional[int]:
    theft_id = _row_int(theft_row, "id")
    amount = round(_row_float(theft_row, "amount"), 2)
    attacker_user_id = _row_int(theft_row, "attacker_user_id")
    victim_user_id = _row_int(theft_row, "victim_user_id")

    updated = await finish_theft(
        db,
        theft_id=theft_id,
        result=result,
        winner_user_id=winner_user_id,
    )
    if not updated:
        return None

    if result == "stolen":
        await apply_balance_delta(
            db,
            user_id=victim_user_id,
            delta=amount,
            reason="theft_release",
            meta=f"theft_id={theft_id};result=stolen",
        )
        await apply_balance_delta(
            db,
            user_id=victim_user_id,
            delta=-amount,
            reason="theft_loss",
            meta=f"theft_id={theft_id};attacker_user_id={attacker_user_id}",
        )
        await apply_balance_delta(
            db,
            user_id=attacker_user_id,
            delta=amount,
            reason="theft_win",
            meta=f"theft_id={theft_id};victim_user_id={victim_user_id}",
        )
    else:
        await apply_balance_delta(
            db,
            user_id=victim_user_id,
            delta=amount,
            reason="theft_release",
            meta=f"theft_id={theft_id};result={result}",
        )

    await log_abuse_event(
        db,
        attacker_user_id,
        f"theft_{result}",
        amount=amount,
        entity_type="theft",
        entity_id=str(theft_id),
    )
    await log_abuse_event(
        db,
        victim_user_id,
        f"theft_{result}",
        amount=amount,
        entity_type="theft",
        entity_id=str(theft_id),
    )
    return theft_id


async def _sync_theft_resolution(db) -> list[int]:
    await ensure_view_thefts_schema(db)
    resolved_ids: list[int] = []

    for theft_row in await list_expired_active_thefts(db):
        resolved_id = await _resolve_theft(
            db,
            cast(TheftRowLike, theft_row),
            result="expired",
            winner_user_id=None,
        )
        if resolved_id is not None:
            resolved_ids.append(resolved_id)

    for protection_row in await list_expired_theft_protection_attempts(db):
        updated = await finish_theft_protection_attempt(
            db,
            attempt_id=int(protection_row["id"]),
            result="expired",
        )
        if updated:
            await log_abuse_event(
                db,
                int(protection_row["user_id"]),
                "theft_protection_expired",
                entity_type="theft_protection",
                entity_id=str(protection_row["id"]),
            )

    return resolved_ids


async def sync_theft_resolution_db(db) -> list[int]:
    return await _sync_theft_resolution(db)


async def get_active_theft_activity_for_user_db(
        db,
        *,
        user_id: int,
        sync_resolution: bool = True,
) -> Optional[dict[str, object]]:
    if sync_resolution:
        await _sync_theft_resolution(db)

    theft_row = await get_user_active_theft(db, user_id)
    if theft_row:
        role = _theft_role(cast(TheftRowLike, theft_row), user_id)
        return {
            "activity_type": "theft_attack" if role == "attacker" else "theft_defense",
            "activity_id": int(theft_row["id"]),
            "snapshot": _build_theft_snapshot(cast(TheftRowLike, theft_row), user_id),
        }

    protection_row = await get_user_active_protection_attempt(db, user_id)
    if protection_row:
        return {
            "activity_type": "theft_protection",
            "activity_id": int(protection_row["id"]),
            "snapshot": _build_protection_snapshot(protection_row),
        }

    return None


async def _get_status_response(db, user_id: int) -> TheftStatusResponse:
    await _sync_theft_resolution(db)

    active = await get_active_theft_activity_for_user_db(db, user_id=user_id, sync_resolution=False)
    latest_finished_theft = _optional_theft_row(await get_user_latest_finished_theft(db, user_id))
    current_balance = await get_balance(db, user_id)
    total_completed_views = await count_completed_task_views_for_user(db, user_id)
    _ = (current_balance, total_completed_views)

    if active:
        snapshot = cast(TheftActivitySnapshot, active["snapshot"])
        return TheftStatusResponse(
            state="active",
            message=(
                "Идет кража"
                if snapshot.kind in {"attack", "defense"}
                else "Заряжаешь защиту от воровства"
            ),
            theft_id=int(active["activity_id"]) if snapshot.kind in {"attack", "defense"} else None,
            protection_attempt_id=int(active["activity_id"]) if snapshot.kind == "protection" else None,
            role=snapshot.role,
            amount=snapshot.amount,
            my_progress=snapshot.my_progress,
            target_views=snapshot.target_views,
            opponent_progress=snapshot.opponent_progress,
            opponent_target_views=snapshot.opponent_target_views,
            seconds_left=snapshot.seconds_left,
            opponent_name=snapshot.opponent_name,
            can_attack=False,
            can_protect=False,
        )

    protection = await get_user_current_protection(db, user_id)
    if protection:
        can_attack = not await has_recent_theft_attack(
            db,
            attacker_user_id=user_id,
            seconds=VIEW_THEFT_DAILY_LIMIT_SECONDS,
        )
        return TheftStatusResponse(
            state="protected",
            message="Защита от воровства активна",
            protected_until=_format_api_datetime(_row_optional_str(protection, "protected_until")),
            can_attack=can_attack,
            can_protect=False,
            last_result=_theft_recent_result_from_row(latest_finished_theft, user_id),
        )

    return TheftStatusResponse(
        state="idle",
        message="Можно начать кражу или зарядить защиту",
        can_attack=not await has_recent_theft_attack(
            db,
            attacker_user_id=user_id,
            seconds=VIEW_THEFT_DAILY_LIMIT_SECONDS,
        ),
        can_protect=True,
        last_result=_theft_recent_result_from_row(latest_finished_theft, user_id),
    )


async def get_theft_status_for_user(user_id: int) -> TheftStatusResponse:
    db = await get_db()
    notify_ids: list[int] = []
    try:
        async with tx(db, immediate=True):
            notify_ids = await _sync_theft_resolution(db)
            response = await _get_status_response(db, user_id)
    finally:
        await db.close()

    for theft_id in notify_ids:
        schedule_theft_resolution_notification(theft_id)

    return response


async def start_theft_for_user(
        user_id: int,
        *,
        fingerprint: Optional[RequestFingerprint] = None,
) -> TheftActionResponse:
    db = await get_db()
    notify_started_id: Optional[int] = None
    notify_resolved_ids: list[int] = []
    response: Optional[TheftActionResponse] = None
    try:
        async with tx(db, immediate=True):
            notify_resolved_ids = await _sync_theft_resolution(db)
            await log_user_action_with_fingerprint(
                db,
                user_id=user_id,
                action="theft_start_attempt",
                fingerprint=fingerprint,
            )

            if await get_user_open_battle(db, user_id):
                response = TheftActionResponse(
                    ok=False,
                    message="Сначала заверши дуэль, потом можно воровать.",
                    status=await _get_status_response(db, user_id),
                )
            elif await get_active_theft_activity_for_user_db(db, user_id=user_id, sync_resolution=False):
                response = TheftActionResponse(
                    ok=False,
                    message="У тебя уже есть активная активность.",
                    status=await _get_status_response(db, user_id),
                )
            elif await has_recent_theft_attack(
                    db,
                    attacker_user_id=user_id,
                    seconds=VIEW_THEFT_DAILY_LIMIT_SECONDS,
            ):
                response = TheftActionResponse(
                    ok=False,
                    message="Воровать можно только 1 раз в сутки.",
                    status=await _get_status_response(db, user_id),
                )
            else:
                candidates = await list_theft_victim_candidates(db, attacker_user_id=user_id)
                eligible_candidates = []
                for candidate in candidates:
                    ability = await get_withdrawal_ability(db, int(candidate["user_id"]))
                    if ability > VIEW_THEFT_MIN_WITHDRAWAL_ABILITY:
                        eligible_candidates.append(candidate)

                if not eligible_candidates:
                    response = TheftActionResponse(
                        ok=False,
                        message="Пока что не у кого воровать, попробуй чуть позже.",
                        status=await _get_status_response(db, user_id),
                    )
                else:
                    victim = random.choice(eligible_candidates)
                    victim_balance = float(victim["balance"] or 0)
                    raw_amount = round(
                        random.uniform(VIEW_THEFT_MIN_AMOUNT, VIEW_THEFT_MAX_AMOUNT),
                        2,
                    )
                    amount = round(min(raw_amount, victim_balance), 2)
                    if amount < VIEW_THEFT_MIN_AMOUNT:
                        response = TheftActionResponse(
                            ok=False,
                            message="Пока что не у кого воровать, попробуй чуть позже.",
                            status=await _get_status_response(db, user_id),
                        )
                    else:
                        theft_id = await create_theft_attempt(
                            db,
                            attacker_user_id=user_id,
                            victim_user_id=int(victim["user_id"]),
                            amount=amount,
                            attacker_target_views=VIEW_THEFT_ATTACK_TARGET_VIEWS,
                            victim_target_views=VIEW_THEFT_DEFENSE_TARGET_VIEWS,
                            duration_seconds=VIEW_THEFT_DURATION_SECONDS,
                        )
                        locked = await apply_balance_debit_if_enough(
                            db,
                            user_id=int(victim["user_id"]),
                            amount=amount,
                            reason="theft_hold",
                            meta=f"theft_id={theft_id}",
                        )
                        if not locked:
                            await finish_theft(
                                db,
                                theft_id=theft_id,
                                result="cancelled",
                                winner_user_id=None,
                            )
                            response = TheftActionResponse(
                                ok=False,
                                message="Пока что не у кого воровать, попробуй чуть позже.",
                                status=await _get_status_response(db, user_id),
                            )
                        else:
                            notify_started_id = theft_id
                            await log_abuse_event(
                                db,
                                user_id,
                                "theft_started",
                                amount=amount,
                                entity_type="theft",
                                entity_id=str(theft_id),
                            )
                            await log_abuse_event(
                                db,
                                int(victim["user_id"]),
                                "theft_targeted",
                                amount=amount,
                                entity_type="theft",
                                entity_id=str(theft_id),
                            )
                            response = TheftActionResponse(
                                ok=True,
                                message=(
                                    f"Цель найдена. Нужно сделать {VIEW_THEFT_ATTACK_TARGET_VIEWS} "
                                    f"просмотров за {VIEW_THEFT_DURATION_SECONDS // 60} минуты, "
                                    "чтобы украсть звезды."
                                ),
                                status=await _get_status_response(db, user_id),
                            )
    finally:
        await db.close()

    for theft_id in notify_resolved_ids:
        schedule_theft_resolution_notification(theft_id)
    if notify_started_id is not None:
        schedule_theft_started_notification(notify_started_id)

    if response is None:
        raise RuntimeError("Theft action response was not built")
    return response


async def start_theft_protection_for_user(
        user_id: int,
        *,
        fingerprint: Optional[RequestFingerprint] = None,
) -> TheftActionResponse:
    db = await get_db()
    notify_resolved_ids: list[int] = []
    response: Optional[TheftActionResponse] = None
    try:
        async with tx(db, immediate=True):
            notify_resolved_ids = await _sync_theft_resolution(db)
            await log_user_action_with_fingerprint(
                db,
                user_id=user_id,
                action="theft_protection_start_attempt",
                fingerprint=fingerprint,
            )

            if await get_user_current_protection(db, user_id):
                response = TheftActionResponse(
                    ok=False,
                    message="Защита уже активна.",
                    status=await _get_status_response(db, user_id),
                )
            elif await get_user_open_battle(db, user_id):
                response = TheftActionResponse(
                    ok=False,
                    message="Сначала заверши дуэль, потом можно поставить защиту.",
                    status=await _get_status_response(db, user_id),
                )
            elif await get_active_theft_activity_for_user_db(db, user_id=user_id, sync_resolution=False):
                response = TheftActionResponse(
                    ok=False,
                    message="У тебя уже есть активная активность.",
                    status=await _get_status_response(db, user_id),
                )
            else:
                attempt_id = await create_theft_protection_attempt(
                    db,
                    user_id=user_id,
                    target_views=VIEW_THEFT_PROTECTION_TARGET_VIEWS,
                    duration_seconds=VIEW_THEFT_DURATION_SECONDS,
                )
                await log_abuse_event(
                    db,
                    user_id,
                    "theft_protection_started",
                    entity_type="theft_protection",
                    entity_id=str(attempt_id),
                )
                response = TheftActionResponse(
                    ok=True,
                    message=(
                        f"Сделай {VIEW_THEFT_PROTECTION_TARGET_VIEWS} просмотров за "
                        f"{VIEW_THEFT_DURATION_SECONDS // 60} минуты, чтобы включить защиту на сутки."
                    ),
                    status=await _get_status_response(db, user_id),
                )
    finally:
        await db.close()

    for theft_id in notify_resolved_ids:
        schedule_theft_resolution_notification(theft_id)

    if response is None:
        raise RuntimeError("Theft protection response was not built")
    return response


async def register_theft_view_completion(
        db,
        *,
        user_id: int,
        activity_type: Optional[str],
        activity_id: Optional[int],
) -> dict[str, object]:
    if not activity_type or activity_id is None:
        return {"theft": None, "resolved_theft_id": None}

    resolved_ids = await _sync_theft_resolution(db)
    if activity_type in {"theft_attack", "theft_defense"}:
        theft_row = await get_theft_by_id(db, int(activity_id))
        if not theft_row or theft_row["state"] != "active":
            return {
                "theft": (
                    _build_theft_snapshot(cast(TheftRowLike, theft_row), user_id)
                    if theft_row
                    else None
                ),
                "resolved_theft_id": resolved_ids[0] if resolved_ids else None,
            }

        updated = await increment_theft_progress(
            db,
            theft_id=int(activity_id),
            user_id=user_id,
        )
        theft_row = await get_theft_by_id(db, int(activity_id))
        if not updated or not theft_row:
            return {"theft": None, "resolved_theft_id": resolved_ids[0] if resolved_ids else None}

        theft_like = cast(TheftRowLike, theft_row)
        if _row_int(theft_like, "attacker_views") >= _row_int(theft_like, "attacker_target_views"):
            resolved_id = await _resolve_theft(
                db,
                theft_like,
                result="stolen",
                winner_user_id=_row_int(theft_like, "attacker_user_id"),
            )
            theft_row = await get_theft_by_id(db, int(activity_id))
            return {
                "theft": _build_theft_snapshot(cast(TheftRowLike, theft_row), user_id, result="stolen") if theft_row else None,
                "resolved_theft_id": resolved_id,
            }

        if _row_int(theft_like, "victim_views") >= _row_int(theft_like, "victim_target_views"):
            resolved_id = await _resolve_theft(
                db,
                theft_like,
                result="defended",
                winner_user_id=_row_int(theft_like, "victim_user_id"),
            )
            theft_row = await get_theft_by_id(db, int(activity_id))
            return {
                "theft": _build_theft_snapshot(cast(TheftRowLike, theft_row), user_id, result="defended") if theft_row else None,
                "resolved_theft_id": resolved_id,
            }

        return {
            "theft": _build_theft_snapshot(theft_like, user_id),
            "resolved_theft_id": resolved_ids[0] if resolved_ids else None,
        }

    if activity_type == "theft_protection":
        protection_row = await get_user_active_protection_attempt(db, user_id)
        if not protection_row or int(protection_row["id"]) != int(activity_id):
            return {"theft": None, "resolved_theft_id": resolved_ids[0] if resolved_ids else None}

        updated = await increment_theft_protection_progress(
            db,
            attempt_id=int(activity_id),
            user_id=user_id,
        )
        protection_row = await get_user_active_protection_attempt(db, user_id)
        if not updated or not protection_row:
            return {"theft": None, "resolved_theft_id": resolved_ids[0] if resolved_ids else None}

        if int(protection_row["views"] or 0) >= int(protection_row["target_views"] or VIEW_THEFT_PROTECTION_TARGET_VIEWS):
            await finish_theft_protection_attempt(
                db,
                attempt_id=int(activity_id),
                result="protected",
                protected_seconds=VIEW_THEFT_PROTECTION_SECONDS,
            )
            await upsert_theft_protection(
                db,
                user_id=user_id,
                protected_seconds=VIEW_THEFT_PROTECTION_SECONDS,
            )
            await log_abuse_event(
                db,
                user_id,
                "theft_protection_activated",
                entity_type="theft_protection",
                entity_id=str(activity_id),
            )
            return {
                "theft": _build_protection_snapshot(
                    {
                        "state": "finished",
                        "result": "protected",
                        "views": int(protection_row["views"] or 0),
                        "target_views": int(protection_row["target_views"] or VIEW_THEFT_PROTECTION_TARGET_VIEWS),
                        "ends_at": protection_row["ends_at"],
                    },
                    result="protected",
                ),
                "resolved_theft_id": resolved_ids[0] if resolved_ids else None,
            }

        return {
            "theft": _build_protection_snapshot(protection_row),
            "resolved_theft_id": resolved_ids[0] if resolved_ids else None,
        }

    return {"theft": None, "resolved_theft_id": resolved_ids[0] if resolved_ids else None}


async def notify_theft_started_by_id(theft_id: Optional[int]) -> None:
    if theft_id is None:
        return
    db = await get_db()
    try:
        theft_row = await get_theft_by_id(db, int(theft_id))
    finally:
        await db.close()
    if theft_row:
        await asyncio.to_thread(_safe_notify_theft_started, cast(TheftRowLike, theft_row))


async def notify_theft_resolution_by_id(theft_id: Optional[int]) -> None:
    if theft_id is None:
        return
    db = await get_db()
    try:
        theft_row = await get_theft_by_id(db, int(theft_id))
    finally:
        await db.close()
    if theft_row:
        await asyncio.to_thread(_safe_notify_theft_resolution, cast(TheftRowLike, theft_row))


def _schedule(coro_factory, theft_id: Optional[int], log_message: str) -> None:
    if theft_id is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("No running event loop for theft notification theft_id=%s", theft_id)
        return

    async def _notify() -> None:
        try:
            await coro_factory(theft_id)
        except Exception:
            logger.exception(log_message, theft_id)

    loop.create_task(_notify())


def schedule_theft_started_notification(theft_id: Optional[int]) -> None:
    _schedule(
        notify_theft_started_by_id,
        theft_id,
        "Failed to notify victim about theft start theft_id=%s",
    )


def schedule_theft_resolution_notification(theft_id: Optional[int]) -> None:
    _schedule(
        notify_theft_resolution_by_id,
        theft_id,
        "Failed to notify users about resolved theft theft_id=%s",
    )
