"""报告路由：生成（含批量）、预览、确认回写、归档、历史、删除、导出、修改意见。"""
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..db import get_db
from ..exporters import export_docx, export_markdown, sanitize_filename
from ..generator import run_generation
from ..models import (
    ROLE_ADMIN,
    Feedback,
    Report,
    STATUS_ARCHIVED,
    STATUS_CONFIRMED,
    STATUS_DRAFTED,
)
from ..schemas import (
    BatchGenerateRequest,
    BatchGenerateResponse,
    CurrentUser,
    FeedbackCreate,
    FeedbackOut,
    ReportGenerateRequest,
    ReportOut,
    ReportSummary,
)
from ..security import get_current_user

router = APIRouter(prefix="/api/reports", tags=["reports"])

# 同步生成（?sync=true）会把整个生成过程阻塞在请求线程内，仅供测试使用。
# 通过环境变量 APP_ALLOW_SYNC=1 显式开启，避免该调试后门在生产接口上被任意调用。
_ALLOW_SYNC = os.getenv("APP_ALLOW_SYNC", "").strip().lower() in ("1", "true", "yes", "on")


def _get_owned(report_id: int, db: Session, current_user: CurrentUser) -> Report:
    """取报告并做归属校验（任务书 §6.2 按角色控制数据访问权限）。

    - 普通用户：仅可访问自己的报告；越权一律按 404 返回，不泄露资源是否存在
    - 管理员：可访问任何用户的报告
    """
    rep = db.get(Report, report_id)
    if not rep:
        raise HTTPException(status_code=404, detail="报告不存在")
    if rep.user_id != current_user.id and current_user.role != ROLE_ADMIN:
        raise HTTPException(status_code=404, detail="报告不存在")
    return rep


@router.post("/generate", response_model=ReportOut)
def generate(
    body: ReportGenerateRequest,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
    sync: bool = Query(False, description="测试用：同步生成，返回即已完成（需 APP_ALLOW_SYNC=1）"),
):
    if sync and not _ALLOW_SYNC:
        # 放在建记录之前，避免被拒后仍留下 pending 垃圾记录
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="同步生成仅在测试模式（APP_ALLOW_SYNC=1）下可用，请改用异步生成。",
        )
    rep = Report(user_id=current_user.id, instruction=body.instruction, status="pending")
    db.add(rep)
    db.commit()
    db.refresh(rep)
    if sync:
        run_generation(rep.id)
        db.refresh(rep)
    else:
        bg.add_task(run_generation, rep.id)
    return rep


@router.post("/generate/batch", response_model=BatchGenerateResponse)
def generate_batch(
    body: BatchGenerateRequest,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """批量任务：一次提交多条指令，各自生成一份报告（任务书 §2.2 目标 1「支持批量任务」）。

    所有报告共享同一 `batch_id`，便于在列表中按批次分组查看。
    """
    batch_id = str(uuid.uuid4())
    report_ids: list[int] = []
    for ins in body.instructions:
        rep = Report(
            user_id=current_user.id,
            instruction=ins,
            status="pending",
            batch_id=batch_id,
        )
        db.add(rep)
        db.flush()  # 立即取回自增 id，保证顺序稳定
        report_ids.append(rep.id)
    db.commit()
    for rid in report_ids:
        bg.add_task(run_generation, rid)
    return BatchGenerateResponse(batch_id=batch_id, report_ids=report_ids, total=len(report_ids))


@router.get("", response_model=list[ReportSummary])
def list_reports(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
    limit: int = Query(50, le=200),
    scope: str = Query("self", pattern="^(self|all)$", description="all 仅管理员可用"),
):
    """报告列表。

    - scope=self（默认）：仅返回当前用户自己的报告
    - scope=all：返回全部用户的报告，仅管理员可用（普通用户调用返回 403）
    """
    if scope == "all" and current_user.role != ROLE_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    q = db.query(Report)
    if scope != "all":
        q = q.filter(Report.user_id == current_user.id)
    return q.order_by(desc(Report.created_at)).limit(limit).all()


@router.get("/{report_id}", response_model=ReportOut)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return _get_owned(report_id, db, current_user)


@router.post("/{report_id}/confirm", response_model=ReportOut)
def confirm(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    rep = _get_owned(report_id, db, current_user)
    if rep.status != STATUS_DRAFTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"仅草稿态(drafted)可确认，当前状态：{rep.status}",
        )
    rep.status = STATUS_CONFIRMED
    rep.confirmed_at = datetime.now(timezone.utc)
    rep.version += 1
    db.commit()
    db.refresh(rep)
    return rep


@router.post("/{report_id}/archive", response_model=ReportOut)
def archive(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    rep = _get_owned(report_id, db, current_user)
    if rep.status not in (STATUS_DRAFTED, STATUS_CONFIRMED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"仅草稿/已确认态可归档，当前状态：{rep.status}",
        )
    rep.status = STATUS_ARCHIVED
    db.commit()
    db.refresh(rep)
    return rep


@router.delete("/{report_id}", status_code=204)
def delete(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    rep = _get_owned(report_id, db, current_user)
    db.delete(rep)
    db.commit()


@router.get("/{report_id}/export")
def export_report(
    report_id: int,
    fmt: str = Query("docx", pattern="^(docx|markdown|md)$", description="导出格式"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """导出报告：format=docx（默认）或 markdown。仅 drafted/confirmed/archived 可导出。"""
    rep = _get_owned(report_id, db, current_user)
    if rep.status not in (STATUS_DRAFTED, STATUS_CONFIRMED, STATUS_ARCHIVED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"报告状态 {rep.status} 不可导出（需 drafted/confirmed/archived）",
        )
    if not rep.markdown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="报告内容为空，无法导出",
        )
    if fmt in ("markdown", "md"):
        data = export_markdown(rep).encode("utf-8")
        media_type = "text/markdown; charset=utf-8"
        ext = "md"
    else:
        data = export_docx(rep)
        media_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        ext = "docx"
    name = sanitize_filename(rep.title or rep.instruction, f"report-{rep.id}") + "." + ext
    ascii_name = name.encode("ascii", "ignore").decode() or "report." + ext
    disposition = (
        f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(name)}'
    )
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": disposition},
    )


# ---------------- 修改意见（任务书 §2.2 目标 4：修改意见沉淀用于优化生成模板）----------------


@router.post("/{report_id}/feedback", response_model=FeedbackOut,
             status_code=status.HTTP_201_CREATED)
def create_feedback(
    report_id: int,
    body: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """对某份报告提交修改意见（指标数值 / 结论表述 / 格式排版 / 其他）。"""
    rep = _get_owned(report_id, db, current_user)
    fb = Feedback(
        report_id=rep.id,
        user_id=current_user.id,
        category=body.category,
        content=body.content.strip(),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


@router.get("/{report_id}/feedback", response_model=list[FeedbackOut])
def list_feedback(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """某份报告的修改意见列表。"""
    rep = _get_owned(report_id, db, current_user)
    return (
        db.query(Feedback)
        .filter(Feedback.report_id == rep.id)
        .order_by(desc(Feedback.created_at))
        .all()
    )
