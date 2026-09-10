"""指令解析评测（S6 / SM2）。

用法：
    python scripts/eval/eval_parse.py            # 跑分 + 写报告
    python scripts/eval/eval_parse.py --show all # 逐条打印

评分口径：
  * expect=normal：report_type / start / end / country 四项全对计 1 分（三要素+类型）。
  * expect=reject：解析器必须拒绝（need_clarify=True），拒绝即计 1 分，错误放行计 0 分。
  * 总分 = 正确数 / 总条数；另按类别出分，便于定位 bad case。
  * country 用 ALL 表示全市场（对应 Intent.country=None）。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.agent.intent_parser import parse_safe  # noqa: E402

CSV_PATH = ROOT / "data" / "eval" / "eval_set_golden.csv"
REPORT_JSON = ROOT / "data" / "eval" / "parse_report.json"
BAD_CASES_MD = ROOT / "data" / "eval" / "bad_cases.md"


def load_golden(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def norm(v: str) -> str:
    return (v or "").strip()


def evaluate(rows: list[dict]) -> dict:
    details, by_cat = [], defaultdict(lambda: {"total": 0, "correct": 0})
    blocked_codes = defaultdict(int)

    for r in rows:
        cid = norm(r["编号"])
        cat = norm(r["类别"])
        text = norm(r["指令文本"])
        expect = norm(r["期望行为(normal/reject)"]) or "normal"
        g = (
            norm(r["golden_报表类型"]),
            norm(r["golden_开始"]),
            norm(r["golden_结束"]),
            norm(r["golden_市场"]),
        )

        it = parse_safe(text)
        pred = (it.report_type, it.start, it.end, (it.country or "ALL"))

        if expect == "reject":
            ok = it.need_clarify
            blocked_codes[it.blocked or "NOT_BLOCKED"] += 1
            reason = "已拒绝" if ok else "未拦截（错误放行）"
        else:
            ok = (not it.need_clarify) and pred == g
            reason = "匹配" if ok else f"预测{pred} ≠ golden{g}"

        by_cat[cat]["total"] += 1
        by_cat[cat]["correct"] += int(ok)
        details.append({
            "id": cid, "category": cat, "instruction": text, "expect": expect,
            "golden": {"report_type": g[0], "start": g[1], "end": g[2], "country": g[3]},
            "pred": {"report_type": pred[0], "start": pred[1], "end": pred[2], "country": pred[3]},
            "blocked": it.blocked, "correct": ok, "reason": reason,
        })

    total = len(details)
    correct = sum(d["correct"] for d in details)
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "by_category": {k: {"total": v["total"], "correct": v["correct"],
                            "accuracy": round(v["correct"] / v["total"], 4)}
                        for k, v in sorted(by_cat.items())},
        "blocked_codes": dict(blocked_codes),
        "details": details,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", choices=["none", "bad", "all"], default="bad")
    ap.add_argument("--csv", default=str(CSV_PATH))
    args = ap.parse_args()

    rows = load_golden(Path(args.csv))
    res = evaluate(rows)

    print("=== 指令解析评测（SM2）===")
    print(f"总条数 {res['total']}｜正确 {res['correct']}｜准确率 {res['accuracy']:.2%}")
    print("--- 分类准确率 ---")
    for cat, v in res["by_category"].items():
        flag = "" if v["accuracy"] >= 0.9 else "  ← 低于 90%"
        print(f"  {cat:<12} {v['correct']:>2}/{v['total']:<2} = {v['accuracy']:>7.2%}{flag}")
    if res["blocked_codes"]:
        print("--- 拦截原因码分布 ---")
        for k, v in sorted(res["blocked_codes"].items(), key=lambda x: -x[1]):
            print(f"  {k:<16} {v}")

    bad = [d for d in res["details"] if not d["correct"]]
    if args.show in ("bad", "all") and (bad or args.show == "all"):
        print(f"--- {'全部' if args.show=='all' else '错误'}明细 ---")
        for d in (res["details"] if args.show == "all" else bad):
            mark = "✅" if d["correct"] else "❌"
            print(f"  {mark} {d['id']} [{d['category']}] {d['instruction']}")
            if not d["correct"]:
                print(f"       {d['reason']}")

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# Bad Case 清单（指令解析）", "",
             f"- 评测集：{res['total']} 条｜准确率 {res['accuracy']:.2%}（目标 ≥90%）",
             f"- 生成脚本：scripts/eval/eval_parse.py｜明细：data/eval/parse_report.json", ""]
    if bad:
        lines += ["| 编号 | 类别 | 指令 | 期望 | 预测 | 问题 |", "|---|---|---|---|---|---|"]
        for d in bad:
            gt = d["golden"] if d["expect"] == "normal" else {"report_type": "-", "start": "-", "end": "-", "country": "-"}
            lines.append(
                f"| {d['id']} | {d['category']} | {d['instruction']} | "
                f"{gt['report_type']}/{gt['start']}~{gt['end']}/{gt['country']} | "
                f"{d['pred']['report_type']}/{d['pred']['start']}~{d['pred']['end']}/{d['pred']['country']} | "
                f"{d['reason']} |"
            )
    else:
        lines.append("本轮无 bad case。")
    BAD_CASES_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\n报告已写入: {REPORT_JSON}")
    print(f"Bad case 已写入: {BAD_CASES_MD}")
    print("=== 结论:", "达标 ✅" if res["accuracy"] >= 0.9 else "未达标 ❌", "===")
    return 0 if res["accuracy"] >= 0.9 else 1


if __name__ == "__main__":
    sys.exit(main())
