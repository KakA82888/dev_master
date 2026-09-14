"""API 请求/响应模型（Pydantic）。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


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
    # 注：定时任务已由独立的 /api/schedules 承载（Schedule 模型 + APScheduler），
    # 不再在本请求中保留 schedule/cron 占位字段。


class BatchGenerateRequest(BaseModel):
    """批量任务：一次提交多条指令（任务书 §2.2 目标 1「支持批量任务」）。"""

    instructions: list[str] = Field(min_length=1, max_length=20)

    @field_validator("instructions")
    @classmethod
    def _normalize(cls, v: list[str]) -> list[str]:
        cleaned = [s.strip() for s in v if s and s.strip()]
        if not cleaned:
            raise ValueError("指令列表不能为空")
        if any(len(s) > 512 for s in cleaned):
            raise ValueError("单条指令不得超过 512 字符")
        return cleaned


class BatchGenerateResponse(BaseModel):
    batch_id: str
    report_ids: list[int]
    total: int


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
    # 批量任务分组：同一次批量提交的报告共享同一 batch_id
    batch_id: Optional[str] = None
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
    batch_id: Optional[str] = None
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------- 修改意见（任务书 §2.2 目标 4）----------------


class FeedbackCreate(BaseModel):
    category: str = Field(default="other", pattern="^(metric|conclusion|format|other)$")
    content: str = Field(min_length=1, max_length=1000)


class FeedbackOut(BaseModel):
    id: int
    report_id: int
    category: str
    content: str
    author: Optional[CurrentUser] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------- 定时任务（任务书 §2.2 目标 1 / §3.2「定时调度器」）----------------


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    instruction: str = Field(min_length=1, max_length=512)
    # 标准 5 段 cron：分 时 日 月 周（如 "0 9 * * *" = 每天 09:00）
    cron: str = Field(min_length=1, max_length=64)
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    instruction: Optional[str] = Field(default=None, min_length=1, max_length=512)
    cron: Optional[str] = Field(default=None, min_length=1, max_length=64)
    enabled: Optional[bool] = None


class ScheduleOut(BaseModel):
    id: int
    name: str
    instruction: str
    cron: str
    enabled: bool
    last_run_at: Optional[datetime] = None
    run_count: int = 0
    owner: Optional[CurrentUser] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
