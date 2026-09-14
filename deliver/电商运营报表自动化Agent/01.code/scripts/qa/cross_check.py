"""自动化双轨对账（替代人工核算，零人力，可复现）。

验证三件事：
1. 双实现互验：同一区间同一指标，pandas 路径与纯 SQL 路径结果差异必须为 0（金额容差 0.01 GBP）。
2. 全量金额断言：daily_agg 各分子之和 = 从 sales_detail 实时聚合；GMV 总计 = 19,642,692.15。
3. 参考结果集：7 个特征日自动生成 data/eval/reference_auto.json，作为回归 golden，一键复现。

用法：python scripts/qa/cross_check.py  ->  退出码 0 表示全部通过。
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts", "metrics"))
sys.path.insert(0, HERE)

from indicators import period_metrics as pandas_period_metrics  # noqa: E402
from aggregates import build_daily_agg, period_metrics_from_daily, _period_metrics_sql  # noqa: E402

DB = os.path.join(ROOT, "data", "processed", "report_agent.db")
EVAL_DIR = os.path.join(ROOT, "data", "eval")
REF_JSON = os.path.join(EVAL_DIR, "reference_auto.json")

# 7 个特征日（普通工作日/周末/促销峰值/月末/月初/中段多国/数据起点）
FEATURE_DAYS = [
    ("2009-12-01", "data_start_normal"),
    ("2010-11-22", "normal_weekday"),
    ("2010-11-27", "weekend"),
    ("2010-11-29", "promo_peak_cyber_monday"),
    ("2010-11-30", "month_end"),
    ("2010-12-01", "month_start"),
    ("2011-06-15", "mid_multi_country"),
]

# 区间对账样本：报表实际交付的是周报/月报（跨多日区间），
# 而区间取数走的是 daily_agg 累加 / 区间 DISTINCT 两条不同实现，
# 必须与 pandas 全区间切片三方互验，否则「单日对账」无法覆盖真正的交付路径。
FEATURE_RANGES = [
    ("2010-11-22", "2010-11-28", "normal_week"),
    ("2010-11-29", "2010-12-05", "cross_month"),
    ("2011-11-28", "2011-12-04", "year_end_week"),
    ("2009-12-01", "2009-12-07", "data_start_week"),
]

# 参与对账的 9 个指标；金额类用 AMOUNT_TOL，其余用严格容差
_METRIC_KEYS = (
    "gmv", "valid_orders", "all_orders", "aov", "conversion_rate",
    "refund_amt_abs", "refund_orders", "refund_rate_amount", "refund_rate_order",
)
_AMOUNT_KEYS = {"gmv", "refund_amt_abs"}
_RATIO_TOL = 1e-9

# 全期 GMV 基线（口径 C），来自口径文档 v1.0
GMV_TOTAL_BASELINE = 19642692.15
AMOUNT_TOL = 0.01  # GBP


def _sql_day(con, day):
    return _period_metrics_sql(con, day, day)


def _violation(m1: dict, m2: dict) -> tuple[bool, float, str | None]:
    """比较两组指标，返回 (是否违规, 最大差异, 违规指标名)。

    金额类容差 AMOUNT_TOL（0.01 GBP），比率类 1e-9，计数类必须完全相等。
    """
    worst, worst_key = 0.0, None
    for k in _METRIC_KEYS:
        v1, v2 = m1.get(k), m2.get(k)
        if v1 is None or v2 is None:
            diff = 0.0 if v1 == v2 else float("inf")
        else:
            diff = abs(float(v1) - float(v2))
        tol = AMOUNT_TOL if k in _AMOUNT_KEYS else _RATIO_TOL
        if diff > tol and diff >= worst:
            worst, worst_key = diff, k
    return (worst_key is not None), worst, worst_key


def run(con) -> dict:
    build_daily_agg(con)
    results = {"days": [], "amount_assertions": {}, "pass": True}

    for day, label in FEATURE_DAYS:
        # pandas 侧：加载当日切片
        df = pd.read_sql(
            "SELECT order_id, amount, is_refund, is_product FROM sales_detail WHERE order_date = ?",
            con,
            params=(day,),
        )
        m_pd = pandas_period_metrics(df)
        # SQL 侧
        m_sql = _sql_day(con, day)

        day_diff = {}
        for k in ("gmv", "valid_orders", "all_orders", "refund_amt_abs", "refund_orders"):
            pv = m_pd[k]
            sv = m_sql[k]
            if isinstance(pv, float):
                diff = abs(pv - sv)
            else:
                diff = 0 if pv == sv else 1
            day_diff[k] = diff
            if (isinstance(pv, float) and diff > AMOUNT_TOL) or (not isinstance(pv, float) and diff != 0):
                results["pass"] = False
        results["days"].append({"day": day, "label": label, "diff": day_diff, "sql": m_sql})

    # ---- 前提断言：daily_agg 存的是「按天去重」的订单数，区间累加只有在
    #      「同一订单不跨天」时才与区间 COUNT(DISTINCT) 等价。
    #      显式保护该前提——一旦数据出现跨天订单，立即 fail，
    #      而不是静默产出偏高的区间订单数（这是原对账只验单日时的盲区）。
    cur0 = con.cursor()
    cur0.execute(
        "SELECT COUNT(*) FROM (SELECT order_id FROM sales_detail "
        "GROUP BY order_id HAVING COUNT(DISTINCT order_date) > 1)"
    )
    cross_day = int(cur0.fetchone()[0])
    results["cross_day_orders"] = cross_day
    if cross_day != 0:
        results["pass"] = False

    # ---- 区间对账：报表实际交付的是周报/月报（跨多日），
    #      取数走 daily_agg 累加 或 区间 DISTINCT 两条不同实现，
    #      必须与 pandas 全区间切片三方互验，否则单日对账覆盖不到真正交付路径。
    results["ranges"] = []
    for s, e, label in FEATURE_RANGES:
        m_fast = period_metrics_from_daily(con, s, e)   # ① daily_agg 快路径（全市场）
        m_sqlr = _period_metrics_sql(con, s, e)         # ② 区间全量 SQL（独立实现）
        df_r = pd.read_sql(
            "SELECT order_id, amount, is_refund, is_product FROM sales_detail "
            "WHERE order_date BETWEEN ? AND ?",
            con,
            params=(s, e),
        )
        m_pdr = pandas_period_metrics(df_r)             # ③ pandas 全区间切片

        bad_fs, w_fs, k_fs = _violation(m_fast, m_sqlr)
        bad_fp, w_fp, k_fp = _violation(m_fast, m_pdr)
        bad_sp, w_sp, k_sp = _violation(m_sqlr, m_pdr)
        if bad_fs or bad_fp or bad_sp:
            results["pass"] = False
        results["ranges"].append({
            "start": s, "end": e, "label": label,
            "fast_vs_sql": {"violated": bad_fs, "worst": w_fs, "key": k_fs},
            "fast_vs_pandas": {"violated": bad_fp, "worst": w_fp, "key": k_fp},
            "sql_vs_pandas": {"violated": bad_sp, "worst": w_sp, "key": k_sp},
            "sql": m_sqlr,
        })

    # 全量金额断言
    cur = con.cursor()
    cur.execute("SELECT SUM(gmv) FROM daily_agg")
    daily_sum_gmv = float(cur.fetchone()[0] or 0)
    cur.execute(
        "SELECT SUM(CASE WHEN is_refund=0 AND is_product=1 THEN amount ELSE 0 END) FROM sales_detail"
    )
    sql_total_gmv = float(cur.fetchone()[0] or 0)
    cur.execute("SELECT SUM(refund_amt_abs) FROM daily_agg")
    daily_sum_refund = float(cur.fetchone()[0] or 0)
    cur.execute("SELECT SUM(ABS(amount)) FROM sales_detail WHERE is_refund=1")
    sql_total_refund = float(cur.fetchone()[0] or 0)

    results["amount_assertions"] = {
        "daily_agg_gmv_sum": round(daily_sum_gmv, 2),
        "sql_total_gmv": round(sql_total_gmv, 2),
        "gmv_diff": round(abs(daily_sum_gmv - sql_total_gmv), 4),
        "gmv_vs_baseline_diff": round(abs(sql_total_gmv - GMV_TOTAL_BASELINE), 4),
        "daily_agg_refund_sum": round(daily_sum_refund, 2),
        "sql_total_refund": round(sql_total_refund, 2),
        "refund_diff": round(abs(daily_sum_refund - sql_total_refund), 4),
    }
    if (
        abs(daily_sum_gmv - sql_total_gmv) > AMOUNT_TOL
        or abs(sql_total_gmv - GMV_TOTAL_BASELINE) > AMOUNT_TOL
        or abs(daily_sum_refund - sql_total_refund) > AMOUNT_TOL
    ):
        results["pass"] = False

    return results


def main() -> int:
    os.makedirs(EVAL_DIR, exist_ok=True)
    con = sqlite3.connect(DB)
    try:
        res = run(con)
    finally:
        con.close()

    # 写回归 golden（以 SQL 侧为权威）
    ref = {
        "gmv_total_baseline": GMV_TOTAL_BASELINE,
        "feature_days": [
            {"day": d, "label": l, "metrics": r["sql"]}
            for (d, l), r in zip(FEATURE_DAYS, res["days"])
        ],
        # 新增：区间（周报/月报）基准，覆盖实际交付路径的三方对账结果
        "cross_day_orders": res["cross_day_orders"],
        "feature_ranges": [
            {"start": r["start"], "end": r["end"], "label": r["label"], "metrics": r["sql"]}
            for r in res["ranges"]
        ],
    }
    with open(REF_JSON, "w", encoding="utf-8") as f:
        json.dump(ref, f, ensure_ascii=False, indent=2)

    print("=== 双轨对账结果（单日）===")
    for r in res["days"]:
        print(f"  {r['day']} ({r['label']}): 最大差异 = {max(r['diff'].values()):.4f}")
    print(f"--- 跨天订单前提断言：跨天订单数 = {res['cross_day_orders']}（须为 0）---")
    print("=== 双轨对账结果（区间：daily_agg累加 / 区间SQL / pandas 三方）===")
    for r in res["ranges"]:
        print(
            f"  {r['start']}~{r['end']} ({r['label']}): "
            f"fast-vs-sql {'OK' if not r['fast_vs_sql']['violated'] else 'FAIL'} / "
            f"fast-vs-pandas {'OK' if not r['fast_vs_pandas']['violated'] else 'FAIL'} / "
            f"sql-vs-pandas {'OK' if not r['sql_vs_pandas']['violated'] else 'FAIL'}"
        )
    print("--- 全量金额断言 ---")
    for k, v in res["amount_assertions"].items():
        print(f"  {k}: {v}")
    print("=== 结论:", "PASS ✅" if res["pass"] else "FAIL ❌", "===")
    print(f"参考结果集已写入: {REF_JSON}")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
