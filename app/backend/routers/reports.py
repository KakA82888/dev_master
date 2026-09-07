"""报告路由：生成、预览、确认回写、归档、历史、删除。"""
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..db import get_db
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
