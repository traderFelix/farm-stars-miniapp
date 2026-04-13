import secrets
from typing import TypedDict

from fastapi import APIRouter, HTTPException

from shared.config import TELEGRAM_BOT_TOKEN
from .schemas import MiniAppAuthRequest, MiniAppAuthResponse, MiniAppUser
from .telegram_auth import TelegramInitDataError, validate_telegram_init_data

router = APIRouter()

# Потом вынесешь в нормальное хранилище / redis / db
class MiniAppSessionData(TypedDict):
    user_id: int


SESSIONS: dict[str, MiniAppSessionData] = {}


@router.post("/api/miniapp/auth", response_model=MiniAppAuthResponse)
async def miniapp_auth(payload: MiniAppAuthRequest):
    try:
        result = validate_telegram_init_data(
            init_data=payload.init_data,
            bot_token=TELEGRAM_BOT_TOKEN,
            max_age_seconds=3600,
        )
    except TelegramInitDataError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    tg_user = result["user"]

    session_token = secrets.token_urlsafe(32)

    SESSIONS[session_token] = {
        "user_id": tg_user["id"],
    }

    return MiniAppAuthResponse(
        ok=True,
        session_token=session_token,
        user=MiniAppUser(
            id=tg_user["id"],
        ),
    )
