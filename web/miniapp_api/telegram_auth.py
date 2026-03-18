import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

class TelegramInitDataError(ValueError):
    pass


def validate_telegram_init_data(init_data: str, bot_token: str, max_age_seconds: int = 3600) -> dict:
    if not init_data:
        raise TelegramInitDataError("Empty init_data")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise TelegramInitDataError("Missing hash")

    auth_date_raw = pairs.get("auth_date")
    if not auth_date_raw:
        raise TelegramInitDataError("Missing auth_date")

    try:
        auth_date = int(auth_date_raw)
    except ValueError as exc:
        raise TelegramInitDataError("Invalid auth_date") from exc

    now = int(time.time())
    if now - auth_date > max_age_seconds:
        raise TelegramInitDataError("init_data is too old")

    data_check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(pairs.items(), key=lambda item: item[0])
    )

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
        raise TelegramInitDataError("Invalid Telegram signature")

    user_raw = pairs.get("user")
    if not user_raw:
        raise TelegramInitDataError("Missing user")

    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise TelegramInitDataError("Invalid user JSON") from exc

    return {
        "user": user,
        "auth_date": auth_date,
        "query_id": pairs.get("query_id"),
        "raw": pairs,
    }
