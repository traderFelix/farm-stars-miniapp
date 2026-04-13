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


BASE_DIR = Path(__file__).resolve().parent.parent
OWNER_ID = _get_env("OWNER_ID")
ADMIN_IDS = {int(x) for x in _require_env("ADMIN_IDS").split(",") if x.strip()}
API_HOST = _get_env("API_HOST")
API_PORT = _get_int_env("API_PORT")
WEB_ORIGIN_DEV = _get_env("WEB_ORIGIN_DEV")
WEB_ORIGIN_NGROK = _get_env("WEB_ORIGIN_NGROK")
DB_PATH = _get_env("DB_PATH")
JWT_SECRET = _get_env("JWT_SECRET")
JWT_ALG = _get_env("JWT_ALG")
JWT_EXPIRE_DAYS = _get_int_env("JWT_EXPIRE_DAYS")
BOT_INTERNAL_TOKEN = _get_env("BOT_INTERNAL_TOKEN") or JWT_SECRET
TELEGRAM_BOT_TOKEN = _get_env("TELEGRAM_BOT_TOKEN")
TELEGRAM_BOT_USERNAME = _get_env("TELEGRAM_BOT_USERNAME")
ALLOW_DEV_AUTH = os.getenv("ALLOW_DEV_AUTH", "false").lower() == "true"
CHANNEL_LINK = _get_env("CHANNEL_LINK")
CHANNEL_ID = _get_env("CHANNEL_ID")
API_BASE_URL = _get_env("API_BASE_URL")
API_TIMEOUT = _get_float_env("API_TIMEOUT")
TELEGRAM_INIT_DATA_MAX_AGE_SECONDS = int(os.getenv("TELEGRAM_INIT_DATA_MAX_AGE_SECONDS", "3600"))
ANTIABUSE_HASH_SALT = _get_env("ANTIABUSE_HASH_SALT") or (JWT_SECRET or "farmstars")
RISK_SCORE_SUSPICIOUS_THRESHOLD = float(os.getenv("RISK_SCORE_SUSPICIOUS_THRESHOLD", "100"))
RISK_SCORE_WITHDRAW_BLOCK_THRESHOLD = float(os.getenv("RISK_SCORE_WITHDRAW_BLOCK_THRESHOLD", "80"))
BOT_TASK_CHANNEL_POST_QUEUE_PATH = (
    _get_env("BOT_TASK_CHANNEL_POST_QUEUE_PATH")
    or str(BASE_DIR / "bot" / ".runtime" / "pending_task_channel_posts.jsonl")
)

ROLE_USER = 0
ROLE_CLIENT = 3
ROLE_PARTNER = 6
ROLE_ADMIN = 9
ROLE_OWNER = 10

MIN_WITHDRAW = 100.0
MIN_WITHDRAW_PERCENT = 0.5
LEDGER_PAGE_SIZE = 20
REFERRAL_PERCENT = 0.10
REQUIRED_ACCOUNT_AGE_HOURS = 24.0
VIEW_BATTLE_ENTRY_FEE = float(os.getenv("VIEW_BATTLE_ENTRY_FEE", "1"))
VIEW_BATTLE_TARGET_VIEWS = int(os.getenv("VIEW_BATTLE_TARGET_VIEWS", "20"))
VIEW_BATTLE_DURATION_SECONDS = int(os.getenv("VIEW_BATTLE_DURATION_SECONDS", "300"))
VIEW_BATTLE_WAITING_EXPIRE_SECONDS = int(os.getenv("VIEW_BATTLE_WAITING_EXPIRE_SECONDS", "600"))
VIEW_BATTLE_HOLD_MIN_SECONDS = int(os.getenv("VIEW_BATTLE_HOLD_MIN_SECONDS", "5"))
VIEW_BATTLE_HOLD_MAX_SECONDS = int(os.getenv("VIEW_BATTLE_HOLD_MAX_SECONDS", "8"))

SYSTEM_REASONS = {
    "withdraw_hold",
    "withdraw_paid",
    "withdraw_release",
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
}
BAD_ACTIVITY_REASONS = {
    "admin_adjust",
    "contest_bonus",
    "promo_bonus",
}
