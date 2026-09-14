"""API 请求/响应模型（Pydantic）。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    # 长度上限对齐 DB 列宽（String(64)/bcrypt 输入长度）；下限校验仍在 auth.py 给出中文 400 提示
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(max_length=128)


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUser(BaseModel):
    id: int
    username: str
    # 角色：admin 可访问全部用户报告；user 仅可访问自己的（任务书 §6.2）
    role: str = "user"

    model_config = {"from_attributes": True}


class ReportGenerateRequest(BaseModel):
    # 上限对齐 reports.instruction 列宽 String(512)，避免超长指令入库后被静默截断
    instruction: str = Field(max_length=512)
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
    # 列表页也需要失败原因与原因码：用于把「安全网关拦截」与「技术故障」区分提示
    error: Optional[str] = None
    error_code: Optional[str] = None
    # 报告归属（管理员视角需要区分不同用户；普通用户为自己的信息，不属敏感数据）
    owner: Optional[CurrentUser] = None
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
    error_code: Optional[str] = None
    # 报告归属（管理员视角需要区分不同用户）
    owner: Optional[CurrentUser] = None
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
