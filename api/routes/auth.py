from fastapi import APIRouter, HTTPException, Request

from shared.config import ALLOW_DEV_AUTH, TELEGRAM_BOT_TOKEN
from api.db.connection import get_db
from api.schemas.auth import TelegramAuthRequest, TelegramAuthResponse
from api.security.request_fingerprint import build_request_fingerprint
from api.services.antiabuse import apply_auth_fingerprint_risk
from api.services.telegram_auth import make_access_token, validate_init_data
from api.services.users import get_or_create_telegram_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/telegram", response_model=TelegramAuthResponse)
async def telegram_auth(payload: TelegramAuthRequest, request: Request):
    if not payload.init_data:
        if not ALLOW_DEV_AUTH:
            raise HTTPException(status_code=400, detail="init_data is required")

        tg_user = {
            "user_id": 144574240,
            "username": "vad_ym",
            "first_name": "Vadym",
            "last_name": None,
        }
    else:
        tg_user = validate_init_data(payload.init_data, TELEGRAM_BOT_TOKEN)

    db = await get_db()
    try:
        profile = await get_or_create_telegram_user(db, tg_user)
        await apply_auth_fingerprint_risk(
            db,
            user_id=int(profile["user_id"]),
            fingerprint=build_request_fingerprint(request),
        )
        await db.commit()
    finally:
        await db.close()

    token = make_access_token(profile["user_id"])

    return TelegramAuthResponse(
        ok=True,
        token=token,
        session={
            "user_id": profile["user_id"],
            "username": profile.get("username"),
            "first_name": profile.get("first_name"),
        },
    )
