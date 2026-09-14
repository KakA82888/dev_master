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
from . import scheduler
from .models import ROLE_ADMIN, User
from .routers import auth, feedback, reports, schedules
from .security import hash_password


def _ensure_columns() -> bool:
    """轻量列迁移：SQLite 的 create_all 不会为已存在的表补列。

    开发库/生产库可能是旧版本创建的，缺少后加的 reports.error_code / users.role，
    升级后直接查询会报 no such column，故此处按需要 ALTER 补列（幂等）。

    返回：本次是否新建了 users.role 列（供启动逻辑决定是否提升既有种子账号）。
    """
    role_added = False
    with engine.connect() as con:
        rep_cols = {row[1] for row in con.exec_driver_sql("PRAGMA table_info(reports)")}
        if rep_cols and "error_code" not in rep_cols:
            con.exec_driver_sql("ALTER TABLE reports ADD COLUMN error_code VARCHAR(32)")
        if rep_cols and "batch_id" not in rep_cols:
            # 批量任务分组列（任务书 §2.2 目标 1）
            con.exec_driver_sql("ALTER TABLE reports ADD COLUMN batch_id VARCHAR(36)")
        user_cols = {row[1] for row in con.exec_driver_sql("PRAGMA table_info(users)")}
        if user_cols and "role" not in user_cols:
            # 历史用户统一回填为普通用户；种子账号由下方启动逻辑提升为 admin
            con.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'user'"
            )
            role_added = True
        con.commit()
    return role_added


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    role_added = _ensure_columns()
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            # 种子账号设为管理员，便于演示「按角色控制数据访问权限」（任务书 §6.2）
            db.add(User(username=SEED_USERNAME,
                        hashed_password=hash_password(SEED_PASSWORD),
                        role=ROLE_ADMIN))
            db.commit()
        elif role_added:
            # 本次刚补出 role 列：既有库中的种子账号提升为管理员，保证演示可用
            seed = db.query(User).filter(User.username == SEED_USERNAME).first()
            if seed is not None:
                seed.role = ROLE_ADMIN
                db.commit()
    finally:
        db.close()

    # 启动定时任务调度器（任务书 §2.2 目标 1「支持定时任务」/ §3.2「定时调度器」）
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()


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
app.include_router(schedules.router)
app.include_router(feedback.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# 前端静态托管：vite build 产物存在时挂载（单端口访问 http://host:8000 即完整应用）
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
