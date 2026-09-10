"""ORM 模型：用户、报告记录。"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func

from .db import Base

# 报告状态机：pending -> running -> drafted -> confirmed -> archived（外加 failed）
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DRAFTED = "drafted"
STATUS_CONFIRMED = "confirmed"
STATUS_ARCHIVED = "archived"
STATUS_FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    hashed_password = Column(String(128), nullable=False)
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
    version = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
