"""API 请求/响应模型（Pydantic）。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUser(BaseModel):
    id: int
    username: str

    model_config = {"from_attributes": True}


class ReportGenerateRequest(BaseModel):
    instruction: str
    schedule: bool = False   # 预留：定时任务（S4 后端扩展）
    cron: Optional[str] = None


class ReportSummary(BaseModel):
    id: int
    instruction: str
    report_type: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    market: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReportOut(BaseModel):
    id: int
    instruction: str
    report_type: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    market: Optional[str] = None
    title: Optional[str] = None
    markdown: Optional[str] = None
    metrics_json: Optional[str] = None
    status: str
    error: Optional[str] = None
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
