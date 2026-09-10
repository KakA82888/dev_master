"""S2 端到端测试：意图解析、指标编排、LangGraph 链路、Markdown 生成。

验证在无 LLM Key 情况下，自然语言指令可端到端生成报告。
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date

from intent_parser import parse
from orchestrator import run

DB = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "report_agent.db")


def _con():
    return sqlite3.connect(DB)


# ---------- 意图解析单测 ----------
def test_parse_daily_default():
    i = parse("生成昨日日报")
    assert i.report_type == "daily"
    assert i.country is None
    assert i.start == "2011-12-08"  # 锚点 2011-12-09 的昨日


def test_parse_market_weekly():
    i = parse("上周德国周报")
    assert i.report_type == "weekly"
    assert i.country == "Germany"
    s, e = date.fromisoformat(i.start), date.fromisoformat(i.end)
    assert (e - s).days == 6  # 整周


def test_parse_range_monthly():
    i = parse("2010年11月22日到28日全部市场月报")
    assert i.start == "2010-11-22" and i.end == "2010-11-28"
    assert i.report_type == "monthly"  # 显式月报优先于区间推断
    assert i.country is None


def test_parse_this_month():
    i = parse("本月全市场月报")
    assert i.report_type == "monthly"
    assert i.start.startswith("2011-12")


# ---------- 端到端链路 ----------
def test_e2e_yesterday():
    r = run("生成昨日日报", _con())
    assert r["error"] is None
    assert r["report"] and "经营日报" in r["report"]
    assert "GMV" in r["report"]
    assert r["bundle"]["current"]["gmv"] > 0


def test_e2e_germany_week():
    r = run("上周德国周报", _con())
    assert r["error"] is None
    assert "Germany" in r["report"]
    assert r["bundle"]["current"]["gmv"] > 0


def test_e2e_november_range():
    r = run("2010年11月22日到28日的日报", _con())
    assert r["error"] is None
    # 逐日明细表应含 7 天
    assert r["report"].count("| 2010-11-") == 7
