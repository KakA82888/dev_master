"""ORM 模型：用户、报告、修改意见、定时任务。"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
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

# 修改意见分类（对应任务书 §2.2 目标 4：修改意见沉淀用于优化生成模板）
FEEDBACK_METRIC = "metric"          # 指标数值问题
FEEDBACK_CONCLUSION = "conclusion"  # 结论/表述问题
FEEDBACK_FORMAT = "format"          # 格式/排版问题
FEEDBACK_OTHER = "other"


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
    # 批量任务分组：同一次批量提交（POST /generate/batch）产生的报告共享同一 batch_id
    batch_id = Column(String(36), nullable=True, index=True)

    # 归属用户：列表/详情接口需带出 owner，供管理员视角区分报告归属
    owner = relationship("User", lazy="joined")


class Feedback(Base):
    """报告修改意见（任务书 §2.2 目标 4：修改意见沉淀用于优化生成模板）。"""

    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("reports.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    category = Column(String(16), default=FEEDBACK_OTHER, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    report = relationship("Report", lazy="joined")
    author = relationship("User", lazy="joined")


class Schedule(Base):
    """定时报表任务（任务书 §2.2 目标 1「支持定时任务」+ §3.2「定时调度器」）。"""

    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    name = Column(String(64), nullable=False)
    instruction = Column(String(512), nullable=False)
    cron = Column(String(64), nullable=False)          # 标准 5 段 cron：分 时 日 月 周
    enabled = Column(Boolean, default=True, nullable=False)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    run_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", lazy="joined")
