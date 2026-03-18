import os, secrets

from fastapi import APIRouter, HTTPException

from .schemas import MiniAppAuthRequest, MiniAppAuthResponse, MiniAppUser
from .telegram_auth import TelegramInitDataError, validate_telegram_init_data

router = APIRouter()

# Потом вынесешь в нормальное хранилище / redis / db
SESSIONS: dict[str, dict] = {}

BOT_TOKEN = os.environ["BOT_TOKEN"]


@router.post("/api/miniapp/auth", response_model=MiniAppAuthResponse)
async def miniapp_auth(payload: MiniAppAuthRequest):
    try:
        result = validate_telegram_init_data(
            init_data=payload.init_data,
            bot_token=BOT_TOKEN,
            max_age_seconds=3600,
        )
    except TelegramInitDataError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    tg_user = result["user"]

    session_token = secrets.token_urlsafe(32)

    SESSIONS[session_token] = {
        "user_id": tg_user["id"],
        "username": tg_user.get("username"),
        "first_name": tg_user.get("first_name"),
        "last_name": tg_user.get("last_name"),
    }

    return MiniAppAuthResponse(
        ok=True,
        session_token=session_token,
        user=MiniAppUser(
            id=tg_user["id"],
            username=tg_user.get("username"),
            first_name=tg_user.get("first_name"),
            last_name=tg_user.get("last_name"),
        ),
    )
