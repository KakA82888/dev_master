"""D8 LLM 通道对比评测：

- A. 安全不变量：reject 类指令在 LLM_MODE=llm 下仍被 guard 网关先行拦截（不产生 LLM 费用）。
- B. 解析准确率对比：对 normal 分层抽样，分别走 LLM 通道 / 规则通道，对照 golden 计算准确率。
- C. 全链路集成：用 LLM 通道跑一条完整日报，确认 report 非空。

用法：python scripts/eval/eval_llm.py
"""
from __future__ import annotations

import csv
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))  # 使 scripts 成为可导入的命名空间包（parse_safe 内 from scripts.agent.guard 需要）
sys.path.insert(0, str(ROOT / "scripts" / "agent"))  # 兼容 agent 内部裸导入

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")  # 显式加载 .env（含 LLM Key），不依赖模块副作用
from scripts.agent import llm_client  # noqa: F401  (触发 LLM 客户端可用，内部自带路径修复)
from scripts.agent.intent_parser import ANCHOR, parse_safe
from scripts.agent.orchestrator import run as agent_run

os.environ["LLM_MODE"] = "llm"

CSV = ROOT / "data" / "eval" / "eval_set_golden.csv"
DB = ROOT / "data" / "processed" / "report_agent.db"

SAMPLE = 15  # 分层抽样条数（normal）


def golden_of(row):
    return (
        row["golden_报表类型"],
        row["golden_开始"],
        row["golden_结束"],
        (row["golden_市场"] or "ALL"),
    )


def main():
    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
    normal = [r for r in rows if r["期望行为(normal/reject)"] == "normal"]
    reject = [r for r in rows if r["期望行为(normal/reject)"] == "reject"]

    # ---- A. 安全不变量 ----
    print("=== A. 安全不变量（reject 指令在 LLM 模式下必须被 guard 拦截）===")
    con = sqlite3.connect(DB)
    a_ok = 0
    for r in reject:
        res = agent_run(r["指令文本"], con, anchor=ANCHOR)
        blocked = bool(res.get("error"))
        a_ok += blocked
        print(f"  [{'✅' if blocked else '❌'}] {r['编号']} {r['指令文本']} -> {res.get('error','')[:40]}")
    print(f"  reject 拦截率: {a_ok}/{len(reject)}")

    # ---- B. 解析准确率对比（LLM vs 规则 vs golden）----
    print(f"\n=== B. 解析准确率对比（normal 抽样 {SAMPLE} 条）===")
    step = max(1, len(normal) // SAMPLE)
    sample = normal[::step][:SAMPLE]
    llm_hit = rule_hit = 0
    details = []
    for r in sample:
        g = golden_of(r)
        ins = r["指令文本"]
        # 规则通道
        ri = parse_safe(ins, ANCHOR)
        rule_pred = (ri.report_type, ri.start, ri.end, (ri.country or "ALL"))
        rule_ok = rule_pred == g
        # LLM 通道（直接解析，隔离评测）
        try:
            li = llm_client.llm_parse_intent(ins, ANCHOR)
            llm_pred = (li.report_type, li.start, li.end, (li.country or "ALL"))
            llm_ok = llm_pred == g
        except Exception as e:
            llm_pred = ("ERR", str(e)[:30], "", "")
            llm_ok = False
        llm_hit += llm_ok
        rule_hit += rule_ok
        details.append({
            "id": r["编号"], "instruction": ins, "golden": list(g),
            "rule": list(rule_pred), "llm": list(llm_pred),
            "rule_ok": rule_ok, "llm_ok": llm_ok,
        })
        print(f"  [{'✅' if llm_ok else '❌'}|{'✅' if rule_ok else '❌'}] {r['编号']} {ins}")
        print(f"       golden={g}\n       rule  ={rule_pred}\n       llm   ={llm_pred}")
    print(f"\n  LLM 通道准确率 : {llm_hit}/{len(sample)} = {llm_hit/len(sample):.1%}")
    print(f"  规则通道准确率 : {rule_hit}/{len(sample)} = {rule_hit/len(sample):.1%}")

    # ---- C. 全链路集成确认（LLM 通道出报告）----
    print("\n=== C. 全链路集成（LLM 通道生成日报）===")
    res = agent_run("生成昨日日报", con, anchor=ANCHOR)
    ok = bool(res.get("report")) and not res.get("error")
    print(f"  status={res.get('error') or 'ok'} | report_len={len(res.get('report') or '')} | notes={res.get('notes')}")
    print(f"  [{'✅' if ok else '❌'}] LLM 全链路出报")

    con.close()

    summary = {
        "reject_blocked": f"{a_ok}/{len(reject)}",
        "llm_accuracy": f"{llm_hit}/{len(sample)}",
        "rule_accuracy": f"{rule_hit}/{len(sample)}",
        "full_chain_ok": ok,
    }
    (ROOT / "data" / "eval" / "eval_llm_report.json").write_text(
        json.dumps({"summary": summary, "details": details}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n=== 汇总 === {json.dumps(summary, ensure_ascii=False)}")
    return summary


if __name__ == "__main__":
    main()
