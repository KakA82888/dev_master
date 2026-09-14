"""ORM 模型：用户、报告记录。"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .db import Base

# 报告状态机：pending -> running -> drafted -> confirmed -> archived（外加 failed）
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DRAFTED = "drafted"
STATUS_CONFIRMED = "confirmed"
STATUS_ARCHIVED = "archived"
STATUS_FAILED = "failed"

# 角色（对应任务书 §6.2「按角色控制数据访问权限」）
ROLE_ADMIN = "admin"   # 可查看与管理全部用户的报告
ROLE_USER = "user"     # 仅可访问自己的报告


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    hashed_password = Column(String(128), nullable=False)
    # 新注册用户默认 user；种子账号由启动逻辑提升为 admin（见 main.lifespan）
    role = Column(String(16), default=ROLE_USER, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    instruction = Column(String(512), nullable=False)
    report_type = Column(String(16), nullable=True)        # daily / weekly / monthly
    period_start = Column(String(10), nullable=True)
    period_end = Column(String(10), nullable=True)
    market = Column(String(64), nullable=True)             # Country 维度或 "ALL"
    title = Column(String(255), nullable=True)
    markdown = Column(Text, nullable=True)
    metrics_json = Column(Text, nullable=True)             # MetricsBundle 序列化，供 S5 导出/回看
    status = Column(String(16), default=STATUS_PENDING, nullable=False)
    error = Column(Text, nullable=True)
    # 失败/拦截原因码（blocked=安全网关拦截 / out_of_range=日期越界 /
    # generation_error=生成链路故障 / internal_error=内部异常），供前端区分提示语义
    error_code = Column(String(32), nullable=True)
    version = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    # 归属用户：列表/详情接口需带出 owner，供管理员视角区分报告归属
    owner = relationship("User", lazy="joined")
