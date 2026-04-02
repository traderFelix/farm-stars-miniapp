from fastapi import APIRouter, Depends

from api.db.connection import get_db
from api.dependencies.internal import require_internal_token
from api.schemas.users import (
    UserBootstrapRequest,
    UserBootstrapResponse,
    UserMainMenuRequest,
    UserMainMenuResponse,
    UserReferralsRequest,
    UserReferralsResponse,
)
from api.services.users import (
    bootstrap_bot_user,
    get_bot_main_menu_by_user_id,
    touch_bot_user_and_get_referrals,
    touch_bot_user_and_get_main_menu,
)

router = APIRouter(
    prefix="/bot/users",
    tags=["internal-users"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("/bootstrap", response_model=UserBootstrapResponse)
async def internal_user_bootstrap(payload: UserBootstrapRequest):
    db = await get_db()
    try:
        return await bootstrap_bot_user(
            db=db,
            tg_user=payload.user.dict(),
            start_referrer_id=payload.start_referrer_id,
        )
    finally:
        await db.close()


@router.post("/main-menu", response_model=UserMainMenuResponse)
async def internal_user_main_menu(payload: UserMainMenuRequest):
    db = await get_db()
    try:
        return await touch_bot_user_and_get_main_menu(
            db=db,
            tg_user=payload.user.dict(),
        )
    finally:
        await db.close()


@router.post("/referrals", response_model=UserReferralsResponse)
async def internal_user_referrals(payload: UserReferralsRequest):
    db = await get_db()
    try:
        return await touch_bot_user_and_get_referrals(
            db=db,
            tg_user=payload.user.dict(),
        )
    finally:
        await db.close()


@router.get("/{user_id}/main-menu", response_model=UserMainMenuResponse)
async def internal_user_main_menu_by_user_id(user_id: int):
    db = await get_db()
    try:
        return await get_bot_main_menu_by_user_id(
            db=db,
            user_id=user_id,
        )
    finally:
        await db.close()
