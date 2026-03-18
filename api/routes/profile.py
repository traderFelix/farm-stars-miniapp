from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from schemas.profile import ProfileResponse

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me", response_model=ProfileResponse)
async def get_my_profile(authorization: Optional[str] = Header(default=None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if authorization != "Bearer dev-token":
        raise HTTPException(status_code=401, detail="Invalid token")

    return ProfileResponse(
        user_id=144574240,
        username="vad_ym",
        first_name="Vadym",
        balance=0.15,
        role="user",
    )