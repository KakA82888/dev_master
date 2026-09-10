"""报告异步生成服务：调用 S2 的 orchestrator.run 产出 Markdown 与指标包，并写回数据库。"""
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from .config import DATA_DB_PATH
from .db import SessionLocal
from .models import Report, STATUS_DRAFTED, STATUS_FAILED, STATUS_RUNNING

# S2 智能体脚本目录
AGENT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "agent"


def _max_order_date() -> Optional[str]:
    """锚点：取事实表最大日期，作为「昨日/上周/本月」的相对基准。"""
    con = sqlite3.connect(str(DATA_DB_PATH))
    try:
        return con.execute("SELECT MAX(order_date) FROM sales_detail").fetchone()[0]
    finally:
        con.close()


def run_generation(report_id: int) -> None:
    """后台任务：根据指令生成报告并落库。异常一律标记为 failed，绝不静默。"""
    if str(AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(AGENT_DIR))
    import orchestrator  # 依赖 AGENT_DIR 已入路径

    db = SessionLocal()
    try:
        rep = db.get(Report, report_id)
        if not rep:
            return
        rep.status = STATUS_RUNNING
        db.commit()

        anchor = _max_order_date()
        anchor_date = date.fromisoformat(anchor) if anchor else None
        con = sqlite3.connect(str(DATA_DB_PATH))
        try:
            result = orchestrator.run(rep.instruction, con, anchor=anchor_date)
        finally:
            con.close()

        if result.get("error"):
            rep.status = STATUS_FAILED
            rep.error = result["error"]
            db.commit()
            return

        bundle = result.get("bundle") or {}
        rep.report_type = bundle.get("report_type")
        rep.period_start = bundle.get("start")
        rep.period_end = bundle.get("end")
        rep.market = bundle.get("country")
        rep.markdown = result.get("report")
        rep.metrics_json = json.dumps(bundle, ensure_ascii=False, default=str)
        rep.status = STATUS_DRAFTED
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        try:
            rep2 = db.get(Report, report_id)
            if rep2:
                rep2.status = STATUS_FAILED
                rep2.error = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
