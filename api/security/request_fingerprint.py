from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from fastapi import Request

from shared.config import ANTIABUSE_HASH_SALT


@dataclass(frozen=True)
class RequestFingerprint:
    ip_hash: Optional[str] = None
    ua_hash: Optional[str] = None
    session_id: Optional[str] = None


def _normalize_header_value(value: Optional[str], *, max_length: int = 256) -> Optional[str]:
    normalized = (value or "").strip()
    if not normalized:
        return None
    return normalized[:max_length]


def _hash_value(value: Optional[str]) -> Optional[str]:
    normalized = _normalize_header_value(value, max_length=512)
    if not normalized:
        return None

    raw = f"{ANTIABUSE_HASH_SALT}:{normalized}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _extract_client_ip(request: Request) -> Optional[str]:
    forwarded_for = _normalize_header_value(request.headers.get("x-forwarded-for"), max_length=512)
    if forwarded_for:
        first_ip = forwarded_for.split(",")[0].strip()
        if first_ip:
            return first_ip

    real_ip = _normalize_header_value(request.headers.get("x-real-ip"), max_length=128)
    if real_ip:
        return real_ip

    if request.client and request.client.host:
        return request.client.host

    return None


def build_request_fingerprint(request: Request) -> RequestFingerprint:
    return RequestFingerprint(
        ip_hash=_hash_value(_extract_client_ip(request)),
        ua_hash=_hash_value(request.headers.get("user-agent")),
        session_id=_normalize_header_value(request.headers.get("x-client-session"), max_length=128),
    )
