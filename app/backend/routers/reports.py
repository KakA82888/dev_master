"""报告路由：生成、预览、确认回写、归档、历史、删除、导出(Markdown/Word)。"""
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..db import get_db
from ..exporters import export_docx, export_markdown, sanitize_filename
from ..generator import run_generation
from ..models import (
    Report,
    STATUS_ARCHIVED,
    STATUS_CONFIRMED,
    STATUS_DRAFTED,
)
from ..schemas import CurrentUser, ReportGenerateRequest, ReportOut, ReportSummary
from ..security import get_current_user

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _get_owned(report_id: int, db: Session, current_user: CurrentUser) -> Report:
    rep = db.get(Report, report_id)
    if not rep or rep.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="报告不存在")
    return rep


@router.post("/generate", response_model=ReportOut)
def generate(
    body: ReportGenerateRequest,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
    sync: bool = Query(False, description="测试用：同步生成，返回即已完成"),
):
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


@router.get("", response_model=list[ReportSummary])
def list_reports(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
    limit: int = Query(50, le=200),
):
    return (
        db.query(Report)
        .filter(Report.user_id == current_user.id)
        .order_by(desc(Report.created_at))
        .limit(limit)
        .all()
    )


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
