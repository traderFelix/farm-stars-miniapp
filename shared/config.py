import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=False)


OWNER_ID = os.getenv("OWNER_ID")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS").split(",") if x.strip()}
API_HOST = os.getenv("API_HOST")
API_PORT = int(os.getenv("API_PORT"))
WEB_ORIGIN_DEV = os.getenv("WEB_ORIGIN_DEV")
WEB_ORIGIN_NGROK = os.getenv("WEB_ORIGIN_NGROK")
DB_PATH = os.getenv("DB_PATH")
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALG = os.getenv("JWT_ALG")
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOW_DEV_AUTH = os.getenv("ALLOW_DEV_AUTH", "false").lower() == "true"
CHANNEL_LINK = os.getenv("CHANNEL_LINK")
CHANNEL_ID = os.getenv("CHANNEL_ID")
API_BASE_URL = os.getenv("API_BASE_URL")
API_TIMEOUT = float(os.getenv("API_TIMEOUT"))

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
