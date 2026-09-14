"""指标查询编排层：依据 Intent 从单一事实表取数并组装指标包。

- 当期 / 上期指标：调用 aggregates.period_metrics_from_daily（daily_agg 快路径 / 指定国家实时 SQL）
- 环比：aggregates.pct_change
- 异常标注：anomaly.detect（阈值表驱动，只标注不臆测原因）
- 日报逐日明细：daily_agg 区间扫描
"""
from __future__ import annotations

import os
import sys
from datetime import date as _date, timedelta as _td

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "metrics"))

import sqlite3

from pydantic import BaseModel

import aggregates as agg
from intent_parser import Intent
from anomaly import detect

_METRIC_KEYS = [
    "gmv", "valid_orders", "all_orders", "aov", "conversion_rate",
    "refund_amt_abs", "refund_orders", "refund_rate_amount", "refund_rate_order",
]


class DailyRow(BaseModel):
    order_date: str
    gmv: float
    valid_orders: int
    all_orders: int
    refund_amt_abs: float
    refund_orders: int


class MetricsBundle(BaseModel):
    report_type: str
    start: str
    end: str
    country: str | None
    current: dict
    previous: dict
    change: dict
    anomalies: list[str]
    daily: list[DailyRow]


def execute(intent: Intent, con: sqlite3.Connection) -> MetricsBundle:
    # 确保 daily_agg 物化表就绪（幂等：已存在则秒过）
    agg.build_daily_agg(con)

    cur = agg.period_metrics_from_daily(con, intent.start, intent.end, intent.country)
    ps, pe = agg.previous_period(intent.start, intent.end)
    prev = agg.period_metrics_from_daily(con, ps, pe, intent.country)

    change = {
        k: agg.pct_change(cur.get(k), prev.get(k))
        for k in ("gmv", "aov", "conversion_rate", "refund_rate_amount", "refund_rate_order")
    }
    anomalies = detect(cur, prev)

    cur_c = con.cursor()
    if intent.country is None:
        cur_c.execute(
            """
            SELECT order_date, gmv, valid_orders, all_orders, refund_amt_abs, refund_orders
            FROM daily_agg
            WHERE order_date BETWEEN ? AND ?
            ORDER BY order_date
            """,
            (intent.start, intent.end),
        )
    else:
        # 指定市场：daily_agg 未按国家拆分，必须从单一事实表按国家实时聚合。
        # 否则逐日明细会退化为全市场数据，与核心指标（已按国家过滤）口径不一致，
        # 导致「分项加总 ≠ 总计」，违背金额对账纪律。
        cur_c.execute(
            """
            SELECT order_date,
                   SUM(CASE WHEN is_refund=0 AND is_product=1 THEN amount ELSE 0 END) AS gmv,
                   COUNT(DISTINCT CASE WHEN is_refund=0 AND is_product=1 THEN order_id END) AS valid_orders,
                   COUNT(DISTINCT order_id) AS all_orders,
                   SUM(CASE WHEN is_refund=1 THEN ABS(amount) ELSE 0 END) AS refund_amt_abs,
                   COUNT(DISTINCT CASE WHEN is_refund=1 THEN order_id END) AS refund_orders
            FROM sales_detail
            WHERE order_date BETWEEN ? AND ? AND country = ?
            GROUP BY order_date
            ORDER BY order_date
            """,
            (intent.start, intent.end, intent.country),
        )
    cols = [d[0] for d in cur_c.description]
    existing = {r[0]: DailyRow(**dict(zip(cols, r))) for r in cur_c.fetchall()}
    # 补全区间内所有日期（含 0 销售日），保证日报完整性
    sd = _date.fromisoformat(intent.start)
    ed = _date.fromisoformat(intent.end)
    daily = [
        existing.get(
            (sd + _td(days=i)).isoformat(),
            DailyRow(order_date=(sd + _td(days=i)).isoformat(), gmv=0.0,
                     valid_orders=0, all_orders=0, refund_amt_abs=0.0, refund_orders=0),
        )
        for i in range((ed - sd).days + 1)
    ]

    return MetricsBundle(
        report_type=intent.report_type, start=intent.start, end=intent.end,
        country=intent.country, current=cur, previous=prev,
        change=change, anomalies=anomalies, daily=daily,
    )
