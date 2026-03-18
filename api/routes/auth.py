from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])


class TelegramAuthRequest(BaseModel):
    init_data: Optional[str] = None


@router.post("/telegram")
async def telegram_auth(payload: TelegramAuthRequest):
    if payload.init_data is None:
        raise HTTPException(status_code=400, detail="init_data is required")

    return {
        "ok": True,
        "token": "dev-token",
        "session": {
            "user_id": 144574240,
            "username": "vad_ym",
            "first_name": "Vadym",
        },
    }