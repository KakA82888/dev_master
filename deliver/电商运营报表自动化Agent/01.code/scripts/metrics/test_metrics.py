"""metrics 模块单元测试 + 双轨对账集成测试。

运行：在 D:/电商 下执行  pytest scripts/metrics/test_metrics.py -q
"""
import os
import sqlite3
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts", "metrics"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "qa"))

from indicators import period_metrics  # noqa: E402
from aggregates import build_daily_agg, period_metrics_from_daily, _period_metrics_sql, previous_period, pct_change  # noqa: E402
import cross_check  # noqa: E402

DB = os.path.join(ROOT, "data", "processed", "report_agent.db")
SAMPLE_WEEK = ("2010-11-22", "2010-11-28")


@pytest.fixture(scope="module")
def con():
    c = sqlite3.connect(DB)
    build_daily_agg(c)
    yield c
    c.close()


def test_sample_week_baseline(con):
    df = pd.read_sql(
        "SELECT order_id, amount, is_refund, is_product FROM sales_detail "
        "WHERE order_date BETWEEN ? AND ?",
        con,
        params=SAMPLE_WEEK,
    )
    m = period_metrics(df)
    assert abs(m["gmv"] - 296087.91) < 0.01
    assert m["valid_orders"] == 691
    assert abs(m["aov"] - 428.49) < 0.01
    assert abs(m["conversion_rate"] - 691 / 854) < 1e-9
    assert abs(m["refund_rate_amount"] - 0.03509) < 1e-4
    assert m["refund_orders"] == 157


def test_daily_agg_matches_sql(con):
    a = period_metrics_from_daily(con, *SAMPLE_WEEK)
    b = _period_metrics_sql(con, *SAMPLE_WEEK)
    for k in ("gmv", "valid_orders", "all_orders", "refund_amt_abs", "refund_orders"):
        if isinstance(a[k], float):
            assert abs(a[k] - b[k]) < 0.01
        else:
            assert a[k] == b[k]


def test_previous_period_and_pct():
    ps, pe = previous_period("2010-11-22", "2010-11-28")
    assert ps == "2010-11-15" and pe == "2010-11-21"
    assert pct_change(120, 100) == pytest.approx(0.20)
    assert pct_change(100, 0) is None


def test_cross_check_pass():
    c = sqlite3.connect(DB)
    try:
        res = cross_check.run(c)
    finally:
        c.close()
    assert res["pass"] is True, f"双轨对账未通过：{res}"
    assert abs(res["amount_assertions"]["gmv_vs_baseline_diff"]) < 0.01
