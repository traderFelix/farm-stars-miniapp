from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from fastapi import HTTPException

from api.db.connection import get_db
from api.schemas.subscriptions import (
    SubscriptionActionResponse,
    SubscriptionAssignmentItem,
    SubscriptionStatusResponse,
    SubscriptionTaskItem,
)
from api.security.request_fingerprint import RequestFingerprint
from api.services.antiabuse import log_user_action_with_fingerprint
from shared.config import (
    ADMIN_IDS,
    OWNER_ID,
    SUBSCRIPTION_ABANDON_COOLDOWN_DAYS,
    SUBSCRIPTION_ACTIVE_SLOT_LIMIT,
    TELEGRAM_BOT_TOKEN,
)
from shared.db.abuse import log_abuse_event
from shared.db.common import tx
from shared.db.ledger import apply_balance_delta
from shared.db.subscriptions import (
    abandon_subscription_assignment,
    count_user_active_subscription_slots,
    create_subscription_assignment,
    current_utc_day,
    current_utc_timestamp,
    ensure_subscription_tasks_schema,
    get_subscription_abandon_available_at,
    get_subscription_assignment_with_task,
    get_subscription_task,
    get_user_subscription_assignment_for_task,
    increment_subscription_task_participants,
    list_available_subscription_tasks_for_user,
    list_user_active_subscription_assignments,
    mark_subscription_task_unavailable_for_admin,
    mark_subscription_daily_claimed,
    set_subscription_abandon_cooldown,
    set_subscription_task_title,
)
from shared.db.users import get_user_by_id

logger = logging.getLogger(__name__)

SUBSCRIPTION_BONUS_REASON = "subscription_bonus"
_MEMBER_STATUSES = {"creator", "administrator", "member"}


def _telegram_api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def _get_chat_member_sync(*, chat_id: str, user_id: int) -> dict[str, Any]:
    query = urllib_parse.urlencode({"chat_id": str(chat_id), "user_id": int(user_id)})
    request = urllib_request.Request(
        f"{_telegram_api_url('getChatMember')}?{query}",
        method="GET",
    )

    with urllib_request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not payload.get("ok"):
        raise RuntimeError(str(payload.get("description") or "Telegram API request failed"))

    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("Telegram API returned an empty member result")

    return result


def _get_chat_title_sync(chat_id: str) -> str:
    query = urllib_parse.urlencode({"chat_id": str(chat_id)})
    request = urllib_request.Request(
        f"{_telegram_api_url('getChat')}?{query}",
        method="GET",
    )

    with urllib_request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not payload.get("ok"):
        raise RuntimeError(str(payload.get("description") or "Telegram API request failed"))

    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("Telegram API returned an empty chat result")

    title = str(result.get("title") or result.get("username") or "").strip()
    return title or "Канал подписки"


def _send_telegram_message_sync(*, user_id: int, text: str) -> None:
    payload = json.dumps(
        {
            "chat_id": int(user_id),
            "text": text,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib_request.Request(
        _telegram_api_url("sendMessage"),
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    with urllib_request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not payload.get("ok"):
        raise RuntimeError(str(payload.get("description") or "Telegram API request failed"))


def _admin_notification_user_ids() -> list[int]:
    ids = {int(admin_id) for admin_id in ADMIN_IDS}
    if OWNER_ID:
        ids.add(int(OWNER_ID))
    return sorted(ids)


async def _notify_admins_subscription_unavailable_once(
        db,
        *,
        task_id: int,
        chat_id: str,
        title: str,
        channel_url: str,
        source_user_id: int,
) -> None:
    should_notify = await mark_subscription_task_unavailable_for_admin(db, task_id=int(task_id))
    if not should_notify:
        return

    title_label = (title or "").strip() or "без названия"
    text = (
        "⚠️ Подписка временно недоступна\n\n"
        f"Задание #{int(task_id)}: {title_label}\n"
        f"chat_id: {chat_id}\n"
        f"Ссылка: {channel_url or '-'}\n"
        f"Первый user_id: {int(source_user_id)}\n\n"
        "Пользователь не смог забрать награду, потому что бот не видит канал/участников. "
        "Я автоматически выключил задание. Добавь бота в канал и включи задание заново."
    )

    for admin_id in _admin_notification_user_ids():
        try:
            await asyncio.to_thread(
                _send_telegram_message_sync,
                user_id=int(admin_id),
                text=text,
            )
        except (urllib_error.HTTPError, urllib_error.URLError, RuntimeError, json.JSONDecodeError) as exc:
            logger.warning(
                "Failed to notify admin about unavailable subscription task_id=%s admin_id=%s detail=%s",
                task_id,
                admin_id,
                exc,
            )


async def _is_user_subscribed(
        *,
        chat_id: str,
        user_id: int,
        db=None,
        task_id: Optional[int] = None,
        title: str = "",
        channel_url: str = "",
) -> bool:
    try:
        member = await asyncio.to_thread(_get_chat_member_sync, chat_id=chat_id, user_id=user_id)
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        logger.warning(
            "Failed to check subscription membership user_id=%s chat_id=%s http=%s detail=%s",
            user_id,
            chat_id,
            exc.code,
            detail,
        )
        if db is not None and task_id is not None:
            await _notify_admins_subscription_unavailable_once(
                db,
                task_id=int(task_id),
                chat_id=str(chat_id),
                title=title,
                channel_url=channel_url,
                source_user_id=int(user_id),
            )
        raise HTTPException(
            status_code=400,
            detail="Это задание временно недоступно. Попробуй другое.",
        ) from exc
    except (urllib_error.URLError, RuntimeError, json.JSONDecodeError) as exc:
        logger.warning(
            "Failed to check subscription membership user_id=%s chat_id=%s detail=%s",
            user_id,
            chat_id,
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail="Проверка подписки временно недоступна. Попробуй чуть позже.",
        ) from exc

    return str(member.get("status") or "").lower() in _MEMBER_STATUSES


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_sqlite_utc(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    elif "+" not in normalized and normalized.count("-") >= 2:
        normalized = normalized.replace(" ", "T")
        normalized = f"{normalized}+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _cooldown_days_left(available_at: Optional[str]) -> int:
    available_dt = _parse_sqlite_utc(available_at)
    if available_dt is None:
        return 0

    seconds_left = max((available_dt - _utc_now()).total_seconds(), 0)
    if seconds_left <= 0:
        return 0
    return max(1, int(math.ceil(seconds_left / 86_400)))


def _total_reward(row: Any) -> float:
    return round(float(row["instant_reward"] or 0) + float(row["daily_reward_total"] or 0), 2)


def _task_title(row: Any) -> str:
    title = str(row["title"] or "").strip()
    if title:
        return title
    return "Канал подписки"


def _assignment_title(row: Any) -> str:
    title = str(row["title_snapshot"] or row["task_title"] or "").strip()
    if title:
        return title
    return "Канал подписки"


async def _fill_missing_task_titles(
        db,
        rows: list[Any],
        *,
        task_title_key: str = "title",
) -> list[Any]:
    prepared: list[Any] = []

    for row in rows:
        title = str(row[task_title_key] or "").strip()
        if title:
            prepared.append(row)
            continue

        task_id = int(row["id"] if task_title_key == "title" else row["task_id"])
        chat_id = str(row["chat_id"])
        try:
            fetched_title = await asyncio.to_thread(_get_chat_title_sync, chat_id)
        except (urllib_error.HTTPError, urllib_error.URLError, RuntimeError, json.JSONDecodeError) as exc:
            logger.warning(
                "Skipping subscription task with missing title task_id=%s chat_id=%s detail=%s",
                task_id,
                chat_id,
                exc,
            )
            if task_title_key == "title":
                continue
            prepared.append(row)
            continue

        await set_subscription_task_title(db, task_id=task_id, title=fetched_title)

        row_dict = {key: row[key] for key in row.keys()}
        row_dict[task_title_key] = fetched_title
        if task_title_key != "title":
            row_dict["task_title"] = fetched_title
        prepared.append(row_dict)

    return prepared


async def _filter_available_tasks_user_is_not_subscribed(
        db,
        rows: list[Any],
        *,
        user_id: int,
) -> list[Any]:
    filtered: list[Any] = []

    for row in rows:
        try:
            subscribed = await _is_user_subscribed(
                chat_id=str(row["chat_id"]),
                user_id=int(user_id),
                db=db,
                task_id=int(row["id"]),
                title=_task_title(row),
                channel_url=str(row["channel_url"] or ""),
            )
        except HTTPException as exc:
            logger.info(
                "Skipping subscription task in available list user_id=%s task_id=%s status=%s detail=%s",
                user_id,
                row["id"],
                exc.status_code,
                exc.detail,
            )
            continue

        if not subscribed:
            filtered.append(row)

    return filtered


def _assignment_url(row: Any) -> str:
    return _normalize_subscription_channel_url(str(row["channel_url_snapshot"] or row["task_channel_url"] or ""))


def _normalize_subscription_channel_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return raw

    if raw.startswith("@"):
        username = raw.lstrip("@").strip("/")
        return f"https://t.me/{username}" if username else raw

    if raw.startswith("t.me/") or raw.startswith("telegram.me/") or raw.startswith("telegram.dog/"):
        raw = f"https://{raw}"

    if raw.startswith("tg://"):
        return raw

    try:
        parsed = urllib_parse.urlparse(raw)
    except ValueError:
        return raw

    if parsed.scheme in {"http", "https"} and parsed.netloc:
        host = parsed.netloc.lower()
        if host in {"t.me", "www.t.me", "telegram.me", "telegram.dog"}:
            path = parsed.path.rstrip("/")
            if path.startswith("/s/"):
                path = path[2:]
            query = f"?{parsed.query}" if parsed.query else ""
            return f"https://t.me{path}{query}"
        return raw

    username = raw.strip().strip("/")
    if username:
        return f"https://t.me/{username.lstrip('@')}"
    return raw


def _remaining_daily_reward(row: Any) -> float:
    total = float(row["daily_reward_total"] or 0)
    claimed = float(row["daily_reward_claimed"] or 0)
    return round(max(total - claimed, 0), 2)


def _has_daily_claims(row: Any) -> bool:
    return float(row["daily_reward_total"] or 0) > 0 and int(row["daily_claim_days"] or 0) > 0


def _is_first_daily_claim_blocked_today(row: Any, today: str) -> bool:
    if int(row["daily_claims_done"] or 0) > 0:
        return False

    created_day = str(row["created_at"] or "")[:10]
    return bool(created_day and created_day == str(today))


def _next_daily_claim_amount(row: Any) -> float:
    total = round(float(row["daily_reward_total"] or 0), 2)
    days = int(row["daily_claim_days"] or 0)
    done = int(row["daily_claims_done"] or 0)
    claimed = round(float(row["daily_reward_claimed"] or 0), 2)
    remaining_days = max(days - done, 0)

    if total <= 0 or remaining_days <= 0:
        return 0.0

    if remaining_days == 1:
        return round(max(total - claimed, 0), 2)

    return round(total / days, 2)


def _serialize_task(row: Any) -> SubscriptionTaskItem:
    return SubscriptionTaskItem(
        id=int(row["id"]),
        title=_task_title(row),
        channel_url=_normalize_subscription_channel_url(str(row["channel_url"])),
        total_reward=_total_reward(row),
        participants_count=int(row["participants_count"] or 0),
        max_subscribers=int(row["max_subscribers"] or 0),
    )


def _serialize_assignment(
        row: Any,
        *,
        today: str,
        abandon_available_at: Optional[str],
) -> SubscriptionAssignmentItem:
    cooldown_days_left = _cooldown_days_left(abandon_available_at)
    daily_days = int(row["daily_claim_days"] or 0)
    claims_done = int(row["daily_claims_done"] or 0)
    can_claim_today = (
        _has_daily_claims(row)
        and claims_done < daily_days
        and str(row["last_daily_claim_day"] or "") != today
        and not _is_first_daily_claim_blocked_today(row, today)
    )

    return SubscriptionAssignmentItem(
        id=int(row["id"]),
        task_id=int(row["task_id"]),
        title=_assignment_title(row),
        channel_url=_assignment_url(row),
        daily_claims_done=claims_done,
        daily_claim_days=daily_days,
        daily_reward_claimed=round(float(row["daily_reward_claimed"] or 0), 2),
        daily_reward_total=round(float(row["daily_reward_total"] or 0), 2),
        remaining_reward=_remaining_daily_reward(row),
        can_claim_today=can_claim_today,
        last_daily_claim_day=row["last_daily_claim_day"],
        can_abandon=_has_daily_claims(row) and cooldown_days_left == 0,
        abandon_available_at=abandon_available_at if cooldown_days_left > 0 else None,
        abandon_cooldown_days_left=cooldown_days_left,
    )


async def get_subscription_status_for_user(user_id: int) -> SubscriptionStatusResponse:
    db = await get_db()
    try:
        await ensure_subscription_tasks_schema(db)
        today = await current_utc_day(db)
        server_time = await current_utc_timestamp(db)
        abandon_available_at = await get_subscription_abandon_available_at(db, int(user_id))
        available_rows = await list_available_subscription_tasks_for_user(db, int(user_id))
        active_rows = await list_user_active_subscription_assignments(db, int(user_id))
        available_rows = await _fill_missing_task_titles(db, available_rows)
        available_rows = await _filter_available_tasks_user_is_not_subscribed(
            db,
            available_rows,
            user_id=int(user_id),
        )
        active_rows = await _fill_missing_task_titles(db, active_rows, task_title_key="task_title")
        slots_used = await count_user_active_subscription_slots(db, int(user_id))

        return SubscriptionStatusResponse(
            available=[_serialize_task(row) for row in available_rows],
            active=[
                _serialize_assignment(
                    row,
                    today=today,
                    abandon_available_at=abandon_available_at,
                )
                for row in active_rows
            ],
            slots_used=int(slots_used),
            slot_limit=int(SUBSCRIPTION_ACTIVE_SLOT_LIMIT),
            abandon_available_at=(
                abandon_available_at if _cooldown_days_left(abandon_available_at) > 0 else None
            ),
            abandon_cooldown_days_left=_cooldown_days_left(abandon_available_at),
            server_time=server_time,
        )
    finally:
        await db.close()


async def join_subscription_task_for_user(
        *,
        user_id: int,
        task_id: int,
        fingerprint: Optional[RequestFingerprint],
) -> SubscriptionActionResponse:
    db = await get_db()
    try:
        await ensure_subscription_tasks_schema(db)
        task = await get_subscription_task(db, int(task_id))
        if not task:
            raise HTTPException(status_code=404, detail="Задание подписки не найдено.")
        if int(task["is_archived"] or 0) == 1:
            raise HTTPException(status_code=404, detail="Задание подписки не найдено.")

        await log_user_action_with_fingerprint(
            db,
            user_id=int(user_id),
            action="subscription_join_attempt",
            fingerprint=fingerprint,
            entity_type="subscription_task",
            entity_id=str(task_id),
        )

        if not await get_user_by_id(db, int(user_id)):
            raise HTTPException(status_code=404, detail="Пользователь не найден.")

        existing = await get_user_subscription_assignment_for_task(
            db,
            user_id=int(user_id),
            task_id=int(task_id),
        )
        if existing:
            return await _action_response(
                db,
                user_id=int(user_id),
                ok=False,
                message="Ты уже заходил в это задание подписки.",
                reward_granted=0,
                remaining_reward=_remaining_daily_reward(existing),
            )

        if int(task["is_active"] or 0) != 1:
            raise HTTPException(status_code=400, detail="Это задание сейчас отключено.")

        if int(task["participants_count"] or 0) >= int(task["max_subscribers"] or 0):
            raise HTTPException(status_code=400, detail="Лимит подписчиков уже заполнен.")

        has_daily = float(task["daily_reward_total"] or 0) > 0 and int(task["daily_claim_days"] or 0) > 0
        slots_used = await count_user_active_subscription_slots(db, int(user_id))
        if slots_used >= int(SUBSCRIPTION_ACTIVE_SLOT_LIMIT):
            raise HTTPException(
                status_code=400,
                detail="Все слоты подписок заняты. Забери награды или удали одно задание.",
            )

        subscribed = await _is_user_subscribed(
            chat_id=str(task["chat_id"]),
            user_id=int(user_id),
            db=db,
            task_id=int(task["id"]),
            title=str(task["title"] or ""),
            channel_url=str(task["channel_url"] or ""),
        )
        if not subscribed:
            await log_user_action_with_fingerprint(
                db,
                user_id=int(user_id),
                action="subscription_join_fail",
                fingerprint=fingerprint,
                entity_type="subscription_task",
                entity_id=str(task_id),
                meta="not_subscribed",
            )
            raise HTTPException(status_code=400, detail="Подписка не найдена. Подпишись на канал и попробуй снова.")

        instant_reward = round(float(task["instant_reward"] or 0), 2)
        daily_reward_total = round(float(task["daily_reward_total"] or 0), 2)
        status = "active" if has_daily else "completed"

        async with tx(db, immediate=True):
            locked_task = await get_subscription_task(db, int(task_id))
            if not locked_task:
                raise HTTPException(status_code=404, detail="Задание подписки не найдено.")
            if int(locked_task["is_archived"] or 0) == 1:
                raise HTTPException(status_code=404, detail="Задание подписки не найдено.")
            if int(locked_task["is_active"] or 0) != 1:
                raise HTTPException(status_code=400, detail="Это задание сейчас отключено.")
            if int(locked_task["participants_count"] or 0) >= int(locked_task["max_subscribers"] or 0):
                raise HTTPException(status_code=400, detail="Лимит подписчиков уже заполнен.")
            if await get_user_subscription_assignment_for_task(
                db,
                user_id=int(user_id),
                task_id=int(task_id),
            ):
                raise HTTPException(status_code=409, detail="Ты уже заходил в это задание подписки.")
            locked_slots_used = await count_user_active_subscription_slots(db, int(user_id))
            if locked_slots_used >= int(SUBSCRIPTION_ACTIVE_SLOT_LIMIT):
                raise HTTPException(
                    status_code=400,
                    detail="Все слоты подписок заняты. Забери награды или удали одно задание.",
                )
            locked_has_daily = (
                float(locked_task["daily_reward_total"] or 0) > 0
                and int(locked_task["daily_claim_days"] or 0) > 0
            )
            assignment_id = await create_subscription_assignment(
                db,
                task=locked_task,
                user_id=int(user_id),
                status="active" if locked_has_daily else "completed",
                instant_claimed_at=True,
                first_daily_available_next_utc_day=locked_has_daily,
            )
            await increment_subscription_task_participants(db, int(task_id))
            if instant_reward > 0:
                await apply_balance_delta(
                    db,
                    user_id=int(user_id),
                    delta=instant_reward,
                    reason=SUBSCRIPTION_BONUS_REASON,
                    meta=f"subscription_task_id={int(task_id)};assignment_id={assignment_id};kind=instant",
                )

            await log_abuse_event(
                db,
                int(user_id),
                "subscription_join_success",
                amount=instant_reward,
                ip_hash=fingerprint.ip_hash if fingerprint else None,
                ua_hash=fingerprint.ua_hash if fingerprint else None,
                session_id=fingerprint.session_id if fingerprint else None,
                entity_type="subscription_task",
                entity_id=str(task_id),
                meta=f"assignment_id={assignment_id}",
            )

        remaining = daily_reward_total if has_daily else 0
        message = "Подписка засчитана."
        if remaining > 0:
            message = (
                f"Получено {instant_reward:g}⭐. "
                f"Клейми каждый день, чтобы забрать оставшиеся {remaining:g}⭐."
            )
        elif instant_reward > 0:
            message = f"Получено {instant_reward:g}⭐."

        return await _action_response(
            db,
            user_id=int(user_id),
            ok=True,
            message=message,
            reward_granted=instant_reward,
            remaining_reward=remaining,
        )
    finally:
        await db.close()


async def claim_subscription_daily_for_user(
        *,
        user_id: int,
        assignment_id: int,
        fingerprint: Optional[RequestFingerprint],
) -> SubscriptionActionResponse:
    db = await get_db()
    try:
        await ensure_subscription_tasks_schema(db)
        assignment = await get_subscription_assignment_with_task(
            db,
            int(assignment_id),
            user_id=int(user_id),
        )
        if not assignment:
            raise HTTPException(status_code=404, detail="Задание подписки не найдено.")
        if str(assignment["status"]) != "active":
            raise HTTPException(status_code=400, detail="Это задание уже завершено.")
        if not _has_daily_claims(assignment):
            raise HTTPException(status_code=400, detail="У этого задания нет ежедневных наград.")

        today = await current_utc_day(db)
        if _is_first_daily_claim_blocked_today(assignment, today):
            return await _action_response(
                db,
                user_id=int(user_id),
                ok=False,
                message="Первую награду за подписку можно забрать завтра.",
                reward_granted=0,
                remaining_reward=_remaining_daily_reward(assignment),
            )

        if str(assignment["last_daily_claim_day"] or "") == today:
            return await _action_response(
                db,
                user_id=int(user_id),
                ok=False,
                message="Сегодняшняя награда уже забрана.",
                reward_granted=0,
                remaining_reward=_remaining_daily_reward(assignment),
            )

        if int(assignment["daily_claims_done"] or 0) >= int(assignment["daily_claim_days"] or 0):
            raise HTTPException(status_code=400, detail="Все награды уже забраны.")

        subscribed = await _is_user_subscribed(
            chat_id=str(assignment["chat_id"]),
            user_id=int(user_id),
            db=db,
            task_id=int(assignment["task_id"]),
            title=_assignment_title(assignment),
            channel_url=_assignment_url(assignment),
        )
        if not subscribed:
            await log_user_action_with_fingerprint(
                db,
                user_id=int(user_id),
                action="subscription_claim_fail",
                fingerprint=fingerprint,
                entity_type="subscription_assignment",
                entity_id=str(assignment_id),
                meta="not_subscribed",
            )
            raise HTTPException(status_code=400, detail="Ты отписался от канала. Подпишись обратно, чтобы забрать награду.")

        amount = _next_daily_claim_amount(assignment)
        next_done = int(assignment["daily_claims_done"] or 0) + 1
        completed = next_done >= int(assignment["daily_claim_days"] or 0)

        async with tx(db, immediate=True):
            locked_assignment = await get_subscription_assignment_with_task(
                db,
                int(assignment_id),
                user_id=int(user_id),
            )
            if not locked_assignment or str(locked_assignment["status"]) != "active":
                raise HTTPException(status_code=400, detail="Это задание уже завершено.")
            if _is_first_daily_claim_blocked_today(locked_assignment, today):
                raise HTTPException(status_code=409, detail="Первую награду за подписку можно забрать завтра.")
            if str(locked_assignment["last_daily_claim_day"] or "") == today:
                raise HTTPException(status_code=409, detail="Сегодняшняя награда уже забрана.")

            amount = _next_daily_claim_amount(locked_assignment)
            next_done = int(locked_assignment["daily_claims_done"] or 0) + 1
            completed = next_done >= int(locked_assignment["daily_claim_days"] or 0)

            if amount > 0:
                await apply_balance_delta(
                    db,
                    user_id=int(user_id),
                    delta=amount,
                    reason=SUBSCRIPTION_BONUS_REASON,
                    meta=(
                        f"subscription_task_id={int(locked_assignment['task_id'])};"
                        f"assignment_id={int(assignment_id)};kind=daily;day={next_done}"
                    ),
                )

            await mark_subscription_daily_claimed(
                db,
                assignment_id=int(assignment_id),
                amount=amount,
                claim_day=today,
                completed=completed,
            )

            await log_abuse_event(
                db,
                int(user_id),
                "subscription_daily_claim_success",
                amount=amount,
                ip_hash=fingerprint.ip_hash if fingerprint else None,
                ua_hash=fingerprint.ua_hash if fingerprint else None,
                session_id=fingerprint.session_id if fingerprint else None,
                entity_type="subscription_assignment",
                entity_id=str(assignment_id),
                meta=f"completed={int(completed)}",
            )

        remaining = round(max(_remaining_daily_reward(assignment) - amount, 0), 2)
        message = f"Получено {amount:g}⭐."
        if remaining > 0:
            message += f" Осталось забрать {remaining:g}⭐."
        else:
            message += " Все награды по подписке забраны."

        return await _action_response(
            db,
            user_id=int(user_id),
            ok=True,
            message=message,
            reward_granted=amount,
            remaining_reward=remaining,
        )
    finally:
        await db.close()


async def abandon_subscription_for_user(
        *,
        user_id: int,
        assignment_id: int,
        fingerprint: Optional[RequestFingerprint],
) -> SubscriptionActionResponse:
    db = await get_db()
    try:
        await ensure_subscription_tasks_schema(db)
        assignment = await get_subscription_assignment_with_task(
            db,
            int(assignment_id),
            user_id=int(user_id),
        )
        if not assignment:
            raise HTTPException(status_code=404, detail="Задание подписки не найдено.")
        if str(assignment["status"]) != "active":
            raise HTTPException(status_code=400, detail="Это задание уже не активно.")
        if not _has_daily_claims(assignment):
            raise HTTPException(status_code=400, detail="Это задание не занимает слот.")

        abandon_available_at = await get_subscription_abandon_available_at(db, int(user_id))
        days_left = _cooldown_days_left(abandon_available_at)
        if days_left > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Удаление доступно через {days_left}д.",
            )

        async with tx(db, immediate=True):
            await abandon_subscription_assignment(db, assignment_id=int(assignment_id))
            await set_subscription_abandon_cooldown(
                db,
                user_id=int(user_id),
                days=int(SUBSCRIPTION_ABANDON_COOLDOWN_DAYS),
            )
            await log_abuse_event(
                db,
                int(user_id),
                "subscription_abandoned",
                amount=0,
                ip_hash=fingerprint.ip_hash if fingerprint else None,
                ua_hash=fingerprint.ua_hash if fingerprint else None,
                session_id=fingerprint.session_id if fingerprint else None,
                entity_type="subscription_assignment",
                entity_id=str(assignment_id),
                meta=f"task_id={int(assignment['task_id'])}",
            )

        return await _action_response(
            db,
            user_id=int(user_id),
            ok=True,
            message="Задание удалено. Слот освобожден.",
            reward_granted=0,
            remaining_reward=0,
        )
    finally:
        await db.close()


async def _action_response(
        db,
        *,
        user_id: int,
        ok: bool,
        message: str,
        reward_granted: float,
        remaining_reward: float,
) -> SubscriptionActionResponse:
    profile = await get_user_by_id(db, int(user_id))
    status = await _status_with_existing_db(db, int(user_id))
    return SubscriptionActionResponse(
        ok=ok,
        message=message,
        reward_granted=round(float(reward_granted or 0), 2),
        remaining_reward=round(float(remaining_reward or 0), 2),
        balance=float(profile["balance"] or 0) if profile else 0,
        status=status,
    )


async def _status_with_existing_db(db, user_id: int) -> SubscriptionStatusResponse:
    today = await current_utc_day(db)
    server_time = await current_utc_timestamp(db)
    abandon_available_at = await get_subscription_abandon_available_at(db, int(user_id))
    available_rows = await list_available_subscription_tasks_for_user(db, int(user_id))
    active_rows = await list_user_active_subscription_assignments(db, int(user_id))
    available_rows = await _fill_missing_task_titles(db, available_rows)
    available_rows = await _filter_available_tasks_user_is_not_subscribed(
        db,
        available_rows,
        user_id=int(user_id),
    )
    active_rows = await _fill_missing_task_titles(db, active_rows, task_title_key="task_title")
    slots_used = await count_user_active_subscription_slots(db, int(user_id))
    cooldown_days_left = _cooldown_days_left(abandon_available_at)
    return SubscriptionStatusResponse(
        available=[_serialize_task(row) for row in available_rows],
        active=[
            _serialize_assignment(
                row,
                today=today,
                abandon_available_at=abandon_available_at,
            )
            for row in active_rows
        ],
        slots_used=int(slots_used),
        slot_limit=int(SUBSCRIPTION_ACTIVE_SLOT_LIMIT),
        abandon_available_at=abandon_available_at if cooldown_days_left > 0 else None,
        abandon_cooldown_days_left=cooldown_days_left,
        server_time=server_time,
    )
