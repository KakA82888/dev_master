"""定时任务调度器（APScheduler 3.x）。

任务书依据：
- §2.2 目标 1：「规划…任务链，**支持定时任务与批量任务**」
- §3.1 后端架构：「**定时任务**与长耗时任务采用异步处理」
- §3.2 核心技术表：「外部工具/插件 — 报表模板渲染组件、**定时调度器**」

设计：
- `BackgroundScheduler`：守护线程，随 FastAPI lifespan 启动 / 关闭。
- 任务定义持久化在应用库 `schedules` 表；启动时加载全部 enabled 项。
- 触发时：新建 `Report`(pending) → 调用 `generator.run_generation` 异步生成。
- cron 采用标准 5 段表达式，由 `CronTrigger.from_crontab` 解析。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger("scheduler")

_scheduler: Optional[BackgroundScheduler] = None


def _job_id(schedule_id: int) -> str:
    return f"schedule-{schedule_id}"


def validate_cron(expr: str) -> None:
    """校验 cron 表达式；非法时抛 ValueError（由路由转为 400）。"""
    try:
        CronTrigger.from_crontab((expr or "").strip())
    except Exception as ex:  # noqa: BLE001
        raise ValueError(f"cron 表达式无效：{expr}") from ex


def _run_scheduled(schedule_id: int) -> None:
    """触发一次定时任务：建报告 → 生成（使用独立 Session，避免与请求线程共享会话）。"""
    from .db import SessionLocal
    from .generator import run_generation
    from .models import STATUS_PENDING, Report, Schedule

    db = SessionLocal()
    report_id = None
    try:
        sch = db.get(Schedule, schedule_id)
        if sch is None or not sch.enabled:
            return
        rep = Report(user_id=sch.user_id, instruction=sch.instruction, status=STATUS_PENDING)
        db.add(rep)
        sch.last_run_at = datetime.now(timezone.utc)
        sch.run_count = (sch.run_count or 0) + 1
        db.commit()
        db.refresh(rep)
        report_id = rep.id
        log.info("定时任务 #%s 触发，已建报告 #%s", schedule_id, report_id)
    except Exception:  # noqa: BLE001
        log.exception("定时任务 #%s 建报告失败", schedule_id)
    finally:
        db.close()

    if report_id is not None:
        try:
            run_generation(report_id)
        except Exception:  # noqa: BLE001
            log.exception("定时任务 #%s 生成报告 #%s 失败", schedule_id, report_id)


def _register(schedule_id: int, cron: str) -> None:
    if _scheduler is None:
        return
    _scheduler.add_job(
        _run_scheduled,
        trigger=CronTrigger.from_crontab(cron.strip()),
        args=[schedule_id],
        id=_job_id(schedule_id),
        replace_existing=True,
        misfire_grace_time=300,
    )


def start() -> Optional[BackgroundScheduler]:
    """启动调度器并从库中加载已启用任务（幂等）。"""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    sched = BackgroundScheduler()
    sched.start()
    _scheduler = sched

    from .db import SessionLocal
    from .models import Schedule

    db = SessionLocal()
    try:
        for sch in db.query(Schedule).all():
            if sch.enabled:
                try:
                    _register(sch.id, sch.cron)
                except Exception:  # noqa: BLE001
                    log.exception("加载定时任务 #%s 失败（cron=%s）", sch.id, sch.cron)
    finally:
        db.close()
    log.info("调度器已启动")
    return sched


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("调度器已关闭")


def add_or_update(schedule_id: int, cron: str, enabled: bool) -> None:
    """同步任务在调度器中的注册状态（启用→注册；停用→移除）。"""
    if _scheduler is None:
        return
    if enabled:
        _register(schedule_id, cron)
    else:
        remove(schedule_id)


def remove(schedule_id: int) -> None:
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(_job_id(schedule_id))
    except Exception:  # noqa: BLE001
        pass  # 任务本就不在调度器中


def is_running() -> bool:
    return _scheduler is not None and _scheduler.running


def trigger_once(schedule_id: int) -> None:
    """立即执行一次（同步，便于接口返回时即可看到报告与 run_count 已更新）。

    不影响既定 cron 计划。
    """
    _run_scheduled(schedule_id)
