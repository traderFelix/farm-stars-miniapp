import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=False)

def _get_env(name: str) -> Optional[str]:
    return os.getenv(name)


def _require_env(name: str) -> str:
    value = _get_env(name)
    if value is None:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


def _get_int_env(name: str) -> int:
    return int(_require_env(name))


def _get_float_env(name: str) -> float:
    return float(_require_env(name))


def _get_bool_env(name: str) -> bool:
    normalized = _require_env(name).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"Environment variable {name} must be a boolean")


def _resolve_base_path(value: str) -> str:
    path = Path(value)
    return str(path if path.is_absolute() else BASE_DIR / path)


BASE_DIR = Path(__file__).resolve().parent.parent
OWNER_ID = _get_int_env("OWNER_ID")
ADMIN_IDS = {int(x) for x in _require_env("ADMIN_IDS").split(",") if x.strip()}
API_HOST = _require_env("API_HOST")
API_PORT = _get_int_env("API_PORT")
WEB_ORIGIN_DEV = _get_env("WEB_ORIGIN_DEV")
WEB_ORIGIN_NGROK = _get_env("WEB_ORIGIN_NGROK")
DB_PATH = _require_env("DB_PATH")
JWT_SECRET = _require_env("JWT_SECRET")
JWT_ALG = _require_env("JWT_ALG")
JWT_EXPIRE_DAYS = _get_int_env("JWT_EXPIRE_DAYS")
BOT_INTERNAL_TOKEN = _require_env("BOT_INTERNAL_TOKEN")
TELEGRAM_BOT_TOKEN = _require_env("TELEGRAM_BOT_TOKEN")
TELEGRAM_BOT_USERNAME = _require_env("TELEGRAM_BOT_USERNAME")
ALLOW_DEV_AUTH = _get_bool_env("ALLOW_DEV_AUTH")
CHANNEL_LINK = _require_env("CHANNEL_LINK")
CHANNEL_ID = _require_env("CHANNEL_ID")
API_BASE_URL = _require_env("API_BASE_URL")
API_TIMEOUT = _get_float_env("API_TIMEOUT")
TELEGRAM_INIT_DATA_MAX_AGE_SECONDS = _get_int_env("TELEGRAM_INIT_DATA_MAX_AGE_SECONDS")
ANTIABUSE_HASH_SALT = _require_env("ANTIABUSE_HASH_SALT")
RISK_SCORE_SUSPICIOUS_THRESHOLD = _get_float_env("RISK_SCORE_SUSPICIOUS_THRESHOLD")
RISK_SCORE_WITHDRAW_BLOCK_THRESHOLD = _get_float_env("RISK_SCORE_WITHDRAW_BLOCK_THRESHOLD")
BOT_TASK_CHANNEL_POST_QUEUE_PATH = _resolve_base_path(_require_env("BOT_TASK_CHANNEL_POST_QUEUE_PATH"))

ROLE_USER = 0
ROLE_CLIENT = 3
ROLE_PARTNER = 6
ROLE_ADMIN = 9
ROLE_OWNER = 10

MIN_WITHDRAW = _get_float_env("MIN_WITHDRAW")
MIN_WITHDRAW_PERCENT = _get_float_env("MIN_WITHDRAW_PERCENT")
LEDGER_PAGE_SIZE = _get_int_env("LEDGER_PAGE_SIZE")
REFERRAL_PERCENT = _get_float_env("REFERRAL_PERCENT")
REQUIRED_ACCOUNT_AGE_HOURS = _get_float_env("REQUIRED_ACCOUNT_AGE_HOURS")
VIEW_BATTLE_ENTRY_FEE = _get_float_env("VIEW_BATTLE_ENTRY_FEE")
VIEW_BATTLE_TARGET_VIEWS = _get_int_env("VIEW_BATTLE_TARGET_VIEWS")
VIEW_BATTLE_DURATION_SECONDS = _get_int_env("VIEW_BATTLE_DURATION_SECONDS")
VIEW_BATTLE_WAITING_EXPIRE_SECONDS = _get_int_env("VIEW_BATTLE_WAITING_EXPIRE_SECONDS")
VIEW_BATTLE_HOLD_MIN_SECONDS = _get_int_env("VIEW_BATTLE_HOLD_MIN_SECONDS")
VIEW_BATTLE_HOLD_MAX_SECONDS = _get_int_env("VIEW_BATTLE_HOLD_MAX_SECONDS")
VIEW_THEFT_ATTACK_TARGET_VIEWS = _get_int_env("VIEW_THEFT_ATTACK_TARGET_VIEWS")
VIEW_THEFT_DEFENSE_TARGET_VIEWS = _get_int_env("VIEW_THEFT_DEFENSE_TARGET_VIEWS")
VIEW_THEFT_PROTECTION_TARGET_VIEWS = _get_int_env("VIEW_THEFT_PROTECTION_TARGET_VIEWS")
VIEW_THEFT_DURATION_SECONDS = _get_int_env("VIEW_THEFT_DURATION_SECONDS")
VIEW_THEFT_PROTECTION_SECONDS = _get_int_env("VIEW_THEFT_PROTECTION_SECONDS")
VIEW_THEFT_MIN_WITHDRAWAL_ABILITY = _get_float_env("VIEW_THEFT_MIN_WITHDRAWAL_ABILITY")
VIEW_THEFT_MIN_AMOUNT = _get_float_env("VIEW_THEFT_MIN_AMOUNT")
VIEW_THEFT_MAX_AMOUNT = _get_float_env("VIEW_THEFT_MAX_AMOUNT")
SUBSCRIPTION_ACTIVE_SLOT_LIMIT = _get_int_env("SUBSCRIPTION_ACTIVE_SLOT_LIMIT")
SUBSCRIPTION_ABANDON_COOLDOWN_DAYS = _get_int_env("SUBSCRIPTION_ABANDON_COOLDOWN_DAYS")

SYSTEM_REASONS = {
    "withdraw_hold",
    "withdraw_paid",
    "withdraw_release",
    "theft_hold",
    "theft_release",
}
NON_EARNING_REASONS = SYSTEM_REASONS.union({
    "battle_entry",
    "battle_refund",
})
GOOD_ACTIVITY_REASONS = {
    "view_post_bonus",
    "daily_bonus",
    "referral_bonus",
    "task_bonus",
    "battle_bonus",
    "subscription_bonus",
}
BAD_ACTIVITY_REASONS = {
    "admin_adjust",
    "contest_bonus",
    "promo_bonus",
}
