"""指标评测与性能评测（S6 / SM1、SM3、SM5）。

用法：
    python scripts/eval/eval_metrics.py            # 指标回归 + 端到端计时
    python scripts/eval/eval_metrics.py --runs 20  # 指定计时样本数

验证三件事：
  1. 三方一致：pandas 路径 / 纯 SQL 路径 / 冻结基准 reference_auto.json，9 个指标差异必须 ≤ 容差。
  2. 全量金额断言：分项加总 = 总计 = GMV 基线 19,642,692.15。
  3. 端到端性能：单份日报从提交到出稿的耗时，均值需 ≤120s（SM3），P95 ≤90s（SM5）。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "metrics"))
sys.path.insert(0, str(ROOT / "scripts" / "agent"))

import pandas as pd  # noqa: E402

from indicators import period_metrics as pandas_period_metrics  # noqa: E402
from aggregates import build_daily_agg, _period_metrics_sql  # noqa: E402
from intent_parser import parse_safe  # noqa: E402
from orchestrator import run as agent_run  # noqa: E402

DB = ROOT / "data" / "processed" / "report_agent.db"
REF_JSON = ROOT / "data" / "eval" / "reference_auto.json"
REPORT_JSON = ROOT / "data" / "eval" / "metrics_report.json"

AMOUNT_TOL = 0.01
GMV_TOTAL_BASELINE = 19642692.15
METRIC_KEYS = [
    "gmv", "valid_orders", "all_orders", "aov", "conversion_rate",
    "refund_amt_abs", "refund_orders", "refund_rate_amount", "refund_rate_order",
]
# 端到端计时用的指令样本（覆盖日/周/月 + 指定市场）
TIMING_INSTRUCTIONS = [
    "生成昨日日报", "上周德国周报", "生成上月月报", "本周英国周报",
    "2010年11月22日到28日的周报", "日本上月月报", "生成今日日报",
    "法国本周周报", "2011年6月全市场月报", "美国昨日日报",
]


def _diff(a, b):
    if a is None or b is None:
        return 0.0 if a == b else 1.0
    if isinstance(a, float) or isinstance(b, float):
        return abs(float(a) - float(b))
    return 0.0 if a == b else 1.0


def eval_metrics(con) -> dict:
    build_daily_agg(con)
    ref = json.loads(REF_JSON.read_text(encoding="utf-8"))
    rows, worst = [], 0.0
    for item in ref["feature_days"]:
        day = item["day"]
        df = pd.read_sql(
            "SELECT order_id, amount, is_refund, is_product FROM sales_detail WHERE order_date = ?",
            con, params=(day,),
        )
        m_pd = pandas_period_metrics(df)
        m_sql = _period_metrics_sql(con, day, day)
        m_ref = item["metrics"]
        d = {k: max(_diff(m_pd[k], m_sql[k]), _diff(m_sql[k], m_ref.get(k)))
             for k in METRIC_KEYS}
        worst = max(worst, max(d.values()))
        rows.append({"day": day, "label": item["label"], "max_diff": max(d.values()), "detail": d})

    cur = con.cursor()
    cur.execute("SELECT SUM(gmv) FROM daily_agg")
    daily_sum = float(cur.fetchone()[0] or 0)
    cur.execute("SELECT SUM(CASE WHEN is_refund=0 AND is_product=1 THEN amount ELSE 0 END) FROM sales_detail")
    sql_total = float(cur.fetchone()[0] or 0)
    assertions = {
        "daily_agg_gmv_sum": round(daily_sum, 2),
        "sql_total_gmv": round(sql_total, 2),
        "gmv_cross_diff": round(abs(daily_sum - sql_total), 4),
        "gmv_vs_baseline_diff": round(abs(sql_total - GMV_TOTAL_BASELINE), 4),
        "gmv_baseline": GMV_TOTAL_BASELINE,
    }
    metrics_pass = worst <= AMOUNT_TOL and assertions["gmv_cross_diff"] <= AMOUNT_TOL \
        and assertions["gmv_vs_baseline_diff"] <= AMOUNT_TOL
    return {"pass": metrics_pass, "worst_metric_diff": worst, "days": rows,
            "amount_assertions": assertions,
            "accuracy_estimate": 100.0 if metrics_pass else 0.0}


def eval_performance(con, runs: int) -> dict:
    instrs = (TIMING_INSTRUCTIONS * (runs // len(TIMING_INSTRUCTIONS) + 1))[:runs]
    times, failed = [], 0
    for ins in instrs:
        t0 = time.perf_counter()
        try:
            r = agent_run(ins, con)
            if r.get("error"):
                failed += 1
        except Exception:
            failed += 1
        times.append(time.perf_counter() - t0)
    times.sort()
    p95 = times[max(0, int(len(times) * 0.95) - 1)]
    return {
        "runs": len(times), "failed": failed,
        "mean_sec": round(statistics.mean(times), 3),
        "p95_sec": round(p95, 3),
        "max_sec": round(max(times), 3),
        "sm3_pass": statistics.mean(times) <= 120.0,
        "sm5_pass": p95 <= 90.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=10)
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    try:
        print("=== 指标回归（三方一致：pandas / SQL / 冻结基准）===")
        mr = eval_metrics(con)
        for r in mr["days"]:
            print(f"  {r['day']} ({r['label']}): 最大差异 = {r['max_diff']:.6f}")
        print("--- 全量金额断言 ---")
        for k, v in mr["amount_assertions"].items():
            print(f"  {k}: {v}")
        print("  结论:", "PASS ✅" if mr["pass"] else "FAIL ❌")

        print(f"\n=== 端到端性能（{args.runs} 次）===")
        pr = eval_performance(con, args.runs)
        print(f"  均值 {pr['mean_sec']}s｜P95 {pr['p95_sec']}s｜最大 {pr['max_sec']}s｜失败 {pr['failed']}")
        print(f"  SM3(≤120s): {'PASS ✅' if pr['sm3_pass'] else 'FAIL ❌'}｜"
              f"SM5(P95≤90s): {'PASS ✅' if pr['sm5_pass'] else 'FAIL ❌'}")
    finally:
        con.close()

    out = {"metrics": mr, "performance": pr}
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入: {REPORT_JSON}")
    ok = mr["pass"] and pr["sm3_pass"] and pr["sm5_pass"] and pr["failed"] == 0
    print("=== 总结论:", "PASS ✅" if ok else "FAIL ❌", "===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
