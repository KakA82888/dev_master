"""FastAPI 应用入口：装配路由、CORS、启动种子账号、前端静态托管。"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import SEED_PASSWORD, SEED_USERNAME
from .db import SessionLocal, init_db
from .models import User
from .routers import auth, reports
from .security import hash_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(User(username=SEED_USERNAME, hashed_password=hash_password(SEED_PASSWORD)))
            db.commit()
    finally:
        db.close()
    yield


app = FastAPI(title="电商运营报表自动化 Agent", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(reports.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# 前端静态托管：vite build 产物存在时挂载（单端口访问 http://host:8000 即完整应用）
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
