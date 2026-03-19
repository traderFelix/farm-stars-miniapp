import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl

import jwt
from fastapi import HTTPException

from shared.config import JWT_ALG, JWT_EXPIRE_DAYS, JWT_SECRET


def parse_init_data(init_data: str) -> dict[str, Any]:
    if not init_data or not init_data.strip():
        raise HTTPException(status_code=400, detail="init_data is empty")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))

    if not pairs:
        raise HTTPException(status_code=400, detail="init_data is invalid")

    return pairs


def validate_init_data(init_data: str, bot_token: str) -> dict[str, Any]:
    if not bot_token:
        raise HTTPException(status_code=500, detail="TELEGRAM_BOT_TOKEN is not configured")

    parsed = parse_init_data(init_data)

    received_hash = parsed.get("hash")
    if not received_hash:
        raise HTTPException(status_code=400, detail="init_data hash is missing")

    data_check_items = []
    for key, value in parsed.items():
        if key == "hash":
            continue
        data_check_items.append(f"{key}={value}")

    data_check_string = "\n".join(sorted(data_check_items))

    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()

    calculated_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid Telegram init_data hash")

    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(status_code=400, detail="Telegram user is missing in init_data")

    try:
        user_data = json.loads(user_raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Telegram user payload is invalid")

    user_id = user_data.get("id")
    if not user_id:
        raise HTTPException(status_code=400, detail="Telegram user id is missing")

    return {
        "user_id": int(user_id),
        "username": user_data.get("username"),
        "first_name": user_data.get("first_name"),
        "last_name": user_data.get("last_name"),
    }


def make_access_token(user_id: int) -> str:
    now = int(time.time())
    exp = now + JWT_EXPIRE_DAYS * 24 * 60 * 60

    payload = {
        "sub": str(int(user_id)),
        "iat": now,
        "exp": exp,
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token payload is invalid")

    return payload
