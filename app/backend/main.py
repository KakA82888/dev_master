"""FastAPI 应用入口：装配路由、CORS、启动种子账号、前端静态托管。"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# 加载项目根目录 .env（不入库，含 LLM Key 等敏感配置）
ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import SEED_PASSWORD, SEED_USERNAME
from .db import SessionLocal, engine, init_db
from .models import User
from .routers import auth, reports
from .security import hash_password


def _ensure_columns() -> None:
    """轻量列迁移：SQLite 的 create_all 不会为已存在的表补列。

    开发库/生产库可能是旧版本创建的，缺少后加的 reports.error_code，
    升级后直接查询会报 no such column，故此处按需要 ALTER 补列（幂等）。
    """
    with engine.connect() as con:
        cols = {row[1] for row in con.exec_driver_sql("PRAGMA table_info(reports)")}
        if cols and "error_code" not in cols:
            con.exec_driver_sql("ALTER TABLE reports ADD COLUMN error_code VARCHAR(32)")
            con.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _ensure_columns()
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(User(username=SEED_USERNAME, hashed_password=hash_password(SEED_PASSWORD)))
            db.commit()
    finally:
        db.close()
    yield


app = FastAPI(title="电商运营报表自动化 Agent", version="0.1.0", lifespan=lifespan)

# CORS：默认只放行本地开发源（单端口同源部署时浏览器根本不触发 CORS 预检）。
# 需要其它来源时用 CORS_ORIGINS 环境变量（英文逗号分隔）覆盖；
# 不再默认 allow_origins=["*"]——通配源 + allow_credentials=True 会让任意站点
# 都能携带凭证跨域调用本服务，属不安全的组合。
_DEFAULT_ORIGINS = (
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:8000,http://127.0.0.1:8000"
)
_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", _DEFAULT_ORIGINS).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
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
