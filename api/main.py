from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.miniapp_compat import router as miniapp_compat_router

from config import WEB_ORIGIN_DEV, WEB_ORIGIN_NGROK
from routes.health import router as health_router
from routes.auth import router as auth_router
from routes.profile import router as profile_router

app = FastAPI(title="Farm Stars API")

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
app.include_router(miniapp_compat_router)