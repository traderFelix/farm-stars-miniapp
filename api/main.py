import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from typing import Any, AsyncIterator, Optional, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.config import WEB_ORIGIN_DEV, WEB_ORIGIN_NGROK

from api.routes.admin.analytics import router as analytics_admin_router
from api.routes.admin.campaigns import router as campaigns_admin_router
from api.routes.admin.promos import router as promos_admin_router
from api.routes.admin.subscriptions import router as subscriptions_admin_router
from api.routes.admin.users import router as users_router
from api.routes.admin.task_channels import router as task_channels_router
from api.routes.admin.withdrawals import router as withdrawals_admin_router
from api.routes.auth import router as auth_router
from api.routes.battles import router as battles_router
from api.routes.campaigns import router as campaigns_router
from api.routes.health import router as health_router
from api.routes.internal_users import router as internal_users_router
from api.routes.miniapp_compat import router as miniapp_compat_router
from api.routes.profile import router as profile_router
from api.routes.promos import router as promos_router
from api.routes.referrals import router as referrals_router
from api.routes.tasks import router as tasks_router
from api.routes.thefts import router as thefts_router
from api.routes.subscriptions import router as subscriptions_router
from api.routes.ledger import router as ledger_router
from api.routes.checkin import router as checkin_router
from api.routes.withdrawals import router as withdrawals_router
from api.services.thefts import sync_expired_thefts_and_notify

logger = logging.getLogger(__name__)
_THEFT_RESOLUTION_POLL_SECONDS = 5
_theft_resolution_task: Optional[asyncio.Task] = None

allowed_origins: list[str] = [
    origin
    for origin in (WEB_ORIGIN_DEV, WEB_ORIGIN_NGROK)
    if origin
]


async def _theft_resolution_watcher() -> None:
    while True:
        try:
            await sync_expired_thefts_and_notify()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to sync expired thefts")

        await asyncio.sleep(_THEFT_RESOLUTION_POLL_SECONDS)


async def start_theft_resolution_watcher() -> None:
    global _theft_resolution_task
    if _theft_resolution_task is None or _theft_resolution_task.done():
        _theft_resolution_task = asyncio.create_task(_theft_resolution_watcher())


async def stop_theft_resolution_watcher() -> None:
    global _theft_resolution_task
    if _theft_resolution_task is None:
        return

    _theft_resolution_task.cancel()
    with suppress(asyncio.CancelledError):
        await _theft_resolution_task
    _theft_resolution_task = None


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await start_theft_resolution_watcher()
    try:
        yield
    finally:
        await stop_theft_resolution_watcher()


app = FastAPI(title="Farm Stars", lifespan=lifespan)

app.add_middleware(
    cast(Any, CORSMiddleware),
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(battles_router)
app.include_router(campaigns_router)
app.include_router(promos_router)
app.include_router(internal_users_router)
app.include_router(profile_router)
app.include_router(referrals_router)
app.include_router(tasks_router)
app.include_router(thefts_router)
app.include_router(subscriptions_router)
app.include_router(miniapp_compat_router)
app.include_router(users_router)
app.include_router(analytics_admin_router)
app.include_router(campaigns_admin_router)
app.include_router(promos_admin_router)
app.include_router(subscriptions_admin_router)
app.include_router(task_channels_router)
app.include_router(withdrawals_admin_router)
app.include_router(ledger_router)
app.include_router(checkin_router)
app.include_router(withdrawals_router)
