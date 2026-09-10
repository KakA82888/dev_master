"""S6 评测回归（并入 pytest，防解析规则改动导致准确率回退）。

断言：
  1. 主集 ≥90%（SM2）
  2. 留出集 ≥90%（泛化能力，防对主集过拟合）
  3. 所有 reject 用例必须被拦截（安全网关不得失效）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.eval.eval_parse import load_golden, evaluate  # noqa: E402

MAIN = ROOT / "data" / "eval" / "eval_set_golden.csv"
HOLD = ROOT / "data" / "eval" / "eval_set_holdout.csv"
THRESHOLD = 0.90


def _score(path: Path):
    return evaluate(load_golden(path))


def test_main_set_accuracy():
    res = _score(MAIN)
    assert res["total"] >= 50, f"评测集需 ≥50 条，实际 {res['total']}"
    assert res["accuracy"] >= THRESHOLD, f"主集准确率 {res['accuracy']:.2%} < {THRESHOLD:.0%}"


def test_holdout_set_accuracy():
    res = _score(HOLD)
    assert res["accuracy"] >= THRESHOLD, f"留出集准确率 {res['accuracy']:.2%} < {THRESHOLD:.0%}"


def test_all_reject_cases_blocked():
    for path in (MAIN, HOLD):
        res = _score(path)
        leaked = [d["id"] for d in res["details"]
                  if d["expect"] == "reject" and d["blocked"] is None]
        assert not leaked, f"{path.name} 存在未被拦截的危险指令: {leaked}"
