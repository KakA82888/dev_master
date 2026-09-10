"""周期聚合与预聚合（daily_agg 物化表）。

- build_daily_agg：按 order_date 预聚合，供报表快速取数（S5 端到端 ≤2min 的关键）。
- period_metrics_from_daily：在日期区间上累加 daily_agg 分子，再统一算比率。
- period_metrics_pandas：等价于 indicators.period_metrics，供双轨对账的 pandas 侧。
"""
from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd

from indicators import period_metrics as _period_metrics_pandas


def build_daily_agg(con: sqlite3.Connection, force: bool = False) -> None:
    """构建/刷新 daily_agg 物化表（按天）。"""
    cur = con.cursor()
    if force:
        cur.execute("DROP TABLE IF EXISTS daily_agg")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_agg (
            order_date      TEXT PRIMARY KEY,
            gmv             REAL,
            valid_orders    INTEGER,
            all_orders      INTEGER,
            refund_amt_abs  REAL,
            refund_orders   INTEGER
        )
        """
    )
    cur.execute("SELECT COUNT(*) FROM daily_agg")
    if cur.fetchone()[0] == 0:
        cur.execute(
            """
            INSERT INTO daily_agg
                (order_date, gmv, valid_orders, all_orders, refund_amt_abs, refund_orders)
            SELECT
                order_date,
                SUM(CASE WHEN is_refund=0 AND is_product=1 THEN amount ELSE 0 END),
                COUNT(DISTINCT CASE WHEN is_refund=0 AND is_product=1 THEN order_id END),
                COUNT(DISTINCT order_id),
                SUM(CASE WHEN is_refund=1 THEN ABS(amount) ELSE 0 END),
                COUNT(DISTINCT CASE WHEN is_refund=1 THEN order_id END)
            FROM sales_detail
            GROUP BY order_date
            """
        )
        con.commit()


def _ratio(numer: float, denom: float):
    return None if denom in (0, None) else numer / denom


def period_metrics_from_daily(
    con: sqlite3.Connection, start: str, end: str, country: str | None = None
) -> dict:
    """从 daily_agg 累加得到区间指标（快路径）。

    若指定 country，则从 sales_detail 实时聚合（daily_agg 未按国家拆分）。
    """
    if country is not None:
        return _period_metrics_sql(con, start, end, country)
    cur = con.cursor()
    cur.execute(
        """
        SELECT COALESCE(SUM(gmv),0), COALESCE(SUM(valid_orders),0),
               COALESCE(SUM(all_orders),0), COALESCE(SUM(refund_amt_abs),0),
               COALESCE(SUM(refund_orders),0)
        FROM daily_agg
        WHERE order_date BETWEEN ? AND ?
        """,
        (start, end),
    )
    gmv_v, vo, ao, ra, ro = cur.fetchone()
    return {
        "gmv": float(gmv_v),
        "valid_orders": int(vo),
        "all_orders": int(ao),
        "aov": _ratio(gmv_v, vo),
        "conversion_rate": _ratio(vo, ao),
        "refund_amt_abs": float(ra),
        "refund_orders": int(ro),
        "refund_rate_amount": _ratio(ra, gmv_v),
        "refund_rate_order": _ratio(ro, ao),
    }


def _period_metrics_sql(
    con: sqlite3.Connection, start: str, end: str, country: str | None = None
) -> dict:
    sql = """
        SELECT
            SUM(CASE WHEN is_refund=0 AND is_product=1 THEN amount ELSE 0 END),
            COUNT(DISTINCT CASE WHEN is_refund=0 AND is_product=1 THEN order_id END),
            COUNT(DISTINCT order_id),
            SUM(CASE WHEN is_refund=1 THEN ABS(amount) ELSE 0 END),
            COUNT(DISTINCT CASE WHEN is_refund=1 THEN order_id END)
        FROM sales_detail
        WHERE order_date BETWEEN ? AND ?
    """
    params = [start, end]
    if country is not None:
        sql += " AND country = ?"
        params.append(country)
    cur = con.cursor()
    cur.execute(sql, params)
    gmv_v, vo, ao, ra, ro = cur.fetchone()
    gmv_v = float(gmv_v or 0)
    vo = int(vo or 0)
    ao = int(ao or 0)
    ra = float(ra or 0)
    ro = int(ro or 0)
    return {
        "gmv": gmv_v,
        "valid_orders": vo,
        "all_orders": ao,
        "aov": _ratio(gmv_v, vo),
        "conversion_rate": _ratio(vo, ao),
        "refund_amt_abs": ra,
        "refund_orders": ro,
        "refund_rate_amount": _ratio(ra, gmv_v),
        "refund_rate_order": _ratio(ro, ao),
    }


def period_metrics_pandas(df: pd.DataFrame) -> dict:
    """pandas 侧指标（双轨对账用，等价于 SQL 侧）。"""
    return _period_metrics_pandas(df)


def previous_period(start: str, end: str):
    """返回紧邻的上一个等长区间 (prev_start, prev_end)。"""
    from datetime import date, timedelta

    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    span = (e - s).days + 1
    prev_end = s - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span - 1)
    return prev_start.isoformat(), prev_end.isoformat()


def pct_change(cur, prev):
    """环比：(cur-prev)/prev；prev 缺失或 0 返回 None。"""
    if prev in (None, 0):
        return None
    return (cur - prev) / prev
