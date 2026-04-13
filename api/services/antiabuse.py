from __future__ import annotations

from typing import Optional

from api.security.request_fingerprint import RequestFingerprint
from shared.db.abuse import (
    count_distinct_users_for_fingerprint,
    count_distinct_users_for_session,
    list_related_users_for_fingerprint,
    list_related_users_for_session,
    log_abuse_event,
)
from shared.db.users import add_user_risk_score, get_referrer_id


async def log_user_action_with_fingerprint(
        db,
        *,
        user_id: int,
        action: str,
        fingerprint: Optional[RequestFingerprint],
        amount: float = 0,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        meta: Optional[str] = None,
) -> None:
    await log_abuse_event(
        db,
        int(user_id),
        action,
        amount=float(amount),
        ip_hash=fingerprint.ip_hash if fingerprint else None,
        ua_hash=fingerprint.ua_hash if fingerprint else None,
        session_id=fingerprint.session_id if fingerprint else None,
        entity_type=entity_type,
        entity_id=entity_id,
        meta=meta,
    )


async def apply_auth_fingerprint_risk(
        db,
        *,
        user_id: int,
        fingerprint: Optional[RequestFingerprint],
) -> None:
    await log_user_action_with_fingerprint(
        db,
        user_id=int(user_id),
        action="auth_success",
        fingerprint=fingerprint,
    )

    if not fingerprint:
        return

    def _format_related_users(rows) -> Optional[str]:
        labels: list[str] = []
        for row in rows:
            username = (row["username"] or "").strip() if row["username"] is not None else ""
            first_name = (row["tg_first_name"] or "").strip() if row["tg_first_name"] is not None else ""
            if username:
                labels.append(f"@{username}")
            elif first_name:
                labels.append(first_name)
            else:
                labels.append(f"id:{int(row['user_id'])}")

        if not labels:
            return None
        return ", ".join(labels)

    session_cluster = 0
    if fingerprint.session_id:
        session_cluster = await count_distinct_users_for_session(
            db,
            user_id=int(user_id),
            session_id=fingerprint.session_id,
            hours=24 * 30,
        )
        if session_cluster >= 1:
            related_users = await list_related_users_for_session(
                db,
                user_id=int(user_id),
                session_id=fingerprint.session_id,
                hours=24 * 30,
                limit=10,
            )
            related_users_meta = _format_related_users(related_users)
            await add_user_risk_score(
                db,
                int(user_id),
                45,
                "Один browser session используется на нескольких аккаунтах",
                source="auth",
                meta=(
                    f"related_users={related_users_meta};cluster_size={session_cluster}"
                    if related_users_meta
                    else f"cluster_size={session_cluster}"
                ),
            )

    fingerprint_cluster = 0
    if fingerprint.ip_hash and fingerprint.ua_hash:
        fingerprint_cluster = await count_distinct_users_for_fingerprint(
            db,
            user_id=int(user_id),
            ip_hash=fingerprint.ip_hash,
            ua_hash=fingerprint.ua_hash,
            hours=24,
        )
        if fingerprint_cluster >= 2:
            related_users = await list_related_users_for_fingerprint(
                db,
                user_id=int(user_id),
                ip_hash=fingerprint.ip_hash,
                ua_hash=fingerprint.ua_hash,
                hours=24,
                limit=10,
            )
            related_users_meta = _format_related_users(related_users)
            await add_user_risk_score(
                db,
                int(user_id),
                20,
                "Зафиксирован кластер аккаунтов с одинаковым устройством/сетью",
                source="auth",
                meta=(
                    f"related_users={related_users_meta};cluster_size={fingerprint_cluster}"
                    if related_users_meta
                    else f"cluster_size={fingerprint_cluster}"
                ),
            )

    referrer_id = await get_referrer_id(db, int(user_id))
    if referrer_id and (session_cluster >= 1 or fingerprint_cluster >= 2):
        await add_user_risk_score(
            db,
            int(user_id),
            30,
            "Подозрительный реферальный кластер по fingerprint",
            source="auth",
            meta=(
                f"session_cluster={session_cluster};fingerprint_cluster={fingerprint_cluster}"
            ),
        )
