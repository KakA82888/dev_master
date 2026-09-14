"""定时任务路由：CRUD + 启停 + 立即执行一次（任务书 §2.2 目标 1「支持定时任务」）。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from .. import scheduler
from ..db import get_db
from ..models import ROLE_ADMIN, Schedule
from ..schemas import CurrentUser, ScheduleCreate, ScheduleOut, ScheduleUpdate
from ..security import get_current_user

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


def _get_owned(schedule_id: int, db: Session, current_user: CurrentUser) -> Schedule:
    """取定时任务并做归属校验（越权一律 404，管理员可跨用户）。"""
    sch = db.get(Schedule, schedule_id)
    if not sch:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    if sch.user_id != current_user.id and current_user.role != ROLE_ADMIN:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return sch


def _check_cron(expr: str) -> str:
    expr = (expr or "").strip()
    try:
        scheduler.validate_cron(expr)
    except ValueError as ex:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ex))
    return expr


@router.get("", response_model=list[ScheduleOut])
def list_schedules(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """定时任务列表：普通用户仅本人；管理员可见全部。"""
    q = db.query(Schedule)
    if current_user.role != ROLE_ADMIN:
        q = q.filter(Schedule.user_id == current_user.id)
    return q.order_by(desc(Schedule.created_at)).all()


@router.post("", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(
    body: ScheduleCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    sch = Schedule(
        user_id=current_user.id,
        name=body.name.strip(),
        instruction=body.instruction.strip(),
        cron=_check_cron(body.cron),
        enabled=body.enabled,
    )
    db.add(sch)
    db.commit()
    db.refresh(sch)
    scheduler.add_or_update(sch.id, sch.cron, sch.enabled)
    return sch


@router.patch("/{schedule_id}", response_model=ScheduleOut)
def update_schedule(
    schedule_id: int,
    body: ScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    sch = _get_owned(schedule_id, db, current_user)
    if body.name is not None:
        sch.name = body.name.strip()
    if body.instruction is not None:
        sch.instruction = body.instruction.strip()
    if body.cron is not None:
        sch.cron = _check_cron(body.cron)
    if body.enabled is not None:
        sch.enabled = body.enabled
    db.commit()
    db.refresh(sch)
    scheduler.add_or_update(sch.id, sch.cron, sch.enabled)
    return sch


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    sch = _get_owned(schedule_id, db, current_user)
    scheduler.remove(sch.id)
    db.delete(sch)
    db.commit()


@router.post("/{schedule_id}/run", response_model=ScheduleOut)
def run_now(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """立即执行一次（不影响既定 cron 计划），用于演示与验证调度链路。"""
    sch = _get_owned(schedule_id, db, current_user)
    scheduler.trigger_once(sch.id)
    db.refresh(sch)
    return sch
