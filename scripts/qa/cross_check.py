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

# 全期 GMV 基线（口径 C），来自口径文档 v1.0
GMV_TOTAL_BASELINE = 19642692.15
AMOUNT_TOL = 0.01  # GBP


def _sql_day(con, day):
    return _period_metrics_sql(con, day, day)


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
    }
    with open(REF_JSON, "w", encoding="utf-8") as f:
        json.dump(ref, f, ensure_ascii=False, indent=2)

    print("=== 双轨对账结果 ===")
    for r in res["days"]:
        print(f"  {r['day']} ({r['label']}): 最大差异 = {max(r['diff'].values()):.4f}")
    print("--- 全量金额断言 ---")
    for k, v in res["amount_assertions"].items():
        print(f"  {k}: {v}")
    print("=== 结论:", "PASS ✅" if res["pass"] else "FAIL ❌", "===")
    print(f"参考结果集已写入: {REF_JSON}")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
