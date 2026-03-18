from typing import Optional

from fastapi import APIRouter, Header, HTTPException

router = APIRouter(prefix="/api", tags=["miniapp-compat"])


@router.post("/miniapp/auth")
async def miniapp_auth():
    return {
        "ok": True,
        "token": "dev-token",
        "user": {
            "id": 144574240,
            "username": "vad_ym",
            "first_name": "Vadym",
            "role": "user",
            "balance": 0.15,
        },
    }


@router.get("/me")
async def get_me(authorization: Optional[str] = Header(default=None)):
    if authorization and authorization != "Bearer dev-token":
        raise HTTPException(status_code=401, detail="Invalid token")

    return {
        "id": 144574240,
        "username": "vad_ym",
        "first_name": "Vadym",
        "role": "user",
        "balance": 0.15,
    }


@router.get("/history")
async def get_history(authorization: Optional[str] = Header(default=None)):
    if authorization and authorization != "Bearer dev-token":
        raise HTTPException(status_code=401, detail="Invalid token")

    return {
        "items": [
            {
                "id": 1,
                "delta": 0.03,
                "reason": "view_post_bonus",
                "created_at": "2026-03-18 12:00:00",
            },
            {
                "id": 2,
                "delta": 0.05,
                "reason": "daily_bonus",
                "created_at": "2026-03-18 13:00:00",
            },
        ]
    }


@router.get("/tasks/next")
async def get_next_task(authorization: Optional[str] = Header(default=None)):
    if authorization and authorization != "Bearer dev-token":
        raise HTTPException(status_code=401, detail="Invalid token")

    return {
        "task": {
            "id": 1,
            "type": "view_post",
            "title": "Посмотреть пост",
            "reward": 0.03,
            "seconds": 3,
            "url": "https://t.me/example/1",
        }
    }