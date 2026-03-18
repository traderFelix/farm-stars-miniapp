from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes_auth import router as auth_router
from .routes_me import router as me_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(me_router)


@app.get("/")
async def root():
    return {"ok": True, "service": "backend"}


@app.get("/health")
async def health():
    return {"ok": True}
