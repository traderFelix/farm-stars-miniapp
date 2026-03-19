from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])


class TelegramAuthRequest(BaseModel):
    init_data: Optional[str] = None


@router.post("/telegram")
async def telegram_auth(payload: TelegramAuthRequest):
    print("AUTH HIT:", {
        "has_init_data": payload.init_data is not None,
        "init_data_len": len(payload.init_data or ""),
        "init_data_preview": (payload.init_data or "")[:120],
    })

    if not payload.init_data:
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