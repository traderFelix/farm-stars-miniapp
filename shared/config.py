import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=False)

# def _parse_ids(env_name: str) -> set[int]:
#     raw = (os.getenv(env_name) or "").strip()
#     if not raw:
#         return set()
#
#     result: set[int] = set()
#     for part in raw.split(","):
#         part = part.strip()
#         if not part:
#             continue
#         result.add(int(part))
#     return result
#
# OWNER_ID = _parse_ids("OWNER_ID")
# ADMIN_IDS = _parse_ids("ADMIN_IDS")
OWNER_ID = os.getenv("OWNER_ID", "")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}

API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

WEB_ORIGIN_DEV = os.getenv("WEB_ORIGIN_DEV", "http://localhost:3000")
WEB_ORIGIN_NGROK = os.getenv("WEB_ORIGIN_NGROK", "")

DB_PATH = os.getenv("DB_PATH")

JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "30"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOW_DEV_AUTH = os.getenv("ALLOW_DEV_AUTH", "false").lower() == "true"

CHANNEL_LINK = os.getenv("CHANNEL_LINK", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")

ROLE_USER = 0
ROLE_CLIENT = 3
ROLE_PARTNER = 6
ROLE_ADMIN = 9
ROLE_OWNER = 10

MIN_WITHDRAW = 100.0
MIN_WITHDRAW_PERCENT = 0.5
LEDGER_PAGE_SIZE = 20
REFERRAL_PERCENT = 0.10

SYSTEM_REASONS = {
    "withdraw_hold",
    "withdraw_paid",
    "withdraw_release",
}
GOOD_ACTIVITY_REASONS = {
    "view_post_bonus",
    "daily_bonus",
    "referral_bonus",
    "task_bonus",
}
BAD_ACTIVITY_REASONS = {
    "admin_adjust",
    "contest_bonus",
    "promo_bonus",
}

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
API_TIMEOUT = float(os.getenv("API_TIMEOUT", "10"))
