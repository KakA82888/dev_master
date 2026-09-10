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


def test_parse_month_nth_week_not_crossing_month():
    """「X月第N周」必须限定在该月内，绝不跨到上一个月（回归：曾算成 2010-03-29~04-04）。"""
    i = parse("生成10年4月第一周周报")
    assert i.report_type == "weekly"
    assert i.start == "2010-04-01" and i.end == "2010-04-04"  # 4/1 是周四，当周周日为 4/4
    assert i.start.startswith("2010-04") and i.end.startswith("2010-04")


def test_parse_month_nth_week_second_and_yearless():
    """第 2 周为完整自然周；2 位年份"10年"归一化为 2010。"""
    i = parse("生成10年4月第二周周报")
    assert i.start == "2010-04-05" and i.end == "2010-04-11"
    j = parse("2010年4月第二周周报")
    assert (j.start, j.end) == (i.start, i.end)


def test_parse_month_nth_week_out_of_range():
    """该月没有第 N 周时应拦截，而不是给出错误区间。"""
    i = parse("生成10年4月第六周周报")
    assert i.need_clarify is True


def test_parse_nth_week_guard_for_llm():
    """规则纠偏入口：仅「X月第N周」句式返回区间，其它指令返回 None。"""
    from intent_parser import nth_week_range

    assert nth_week_range("生成10年4月第一周周报") == (
        date(2010, 4, 1), date(2010, 4, 4))
    assert nth_week_range("生成昨日日报") is None


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
