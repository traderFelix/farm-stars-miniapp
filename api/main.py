from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.config import WEB_ORIGIN_DEV, WEB_ORIGIN_NGROK

from api.routes.admin_users import router as admin_users_router
from api.routes.auth import router as auth_router
from api.routes.health import router as health_router
from api.routes.miniapp_compat import router as miniapp_compat_router
from api.routes.profile import router as profile_router
from api.routes.tasks import router as tasks_router
from api.routes.ledger import router as ledger_router
from api.routes.checkin import router as checkin_router
from api.routes.withdrawals import router as withdrawals_router

app = FastAPI(title="Farm Stars")

allowed_origins = [WEB_ORIGIN_DEV]
if WEB_ORIGIN_NGROK:
    allowed_origins.append(WEB_ORIGIN_NGROK)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(tasks_router)
app.include_router(miniapp_compat_router)
app.include_router(admin_users_router)
app.include_router(ledger_router)
app.include_router(checkin_router)
app.include_router(withdrawals_router)