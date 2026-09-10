"""构建「报表语料库」corpus/（任务书 §5.2 交付物）。

产出三类语料，全部可从本项目资产一键复现，禁止手工编造：
1. 销售数据样本库   ：从唯一事实表 sales_detail 等距抽样（rowid % step）得到样本明细。
2. 指令评测集       ：复制 data/eval 下已标注的指令集（主集 golden + 留出集 holdout）。
3. 索引说明 README  ：说明语料来源、字段、用途与复现方式（报告生成提示词指向 prompts/）。

用法：
    python scripts/build_corpus.py [--step 500] [--recent-days 7]
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
from pathlib import Path

import pandas as pd

# 项目根目录：scripts/build_corpus.py -> 电商
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DB = PROJECT_ROOT / "data" / "processed" / "report_agent.db"
CORPUS_DIR = PROJECT_ROOT / "corpus"
EVAL_DIR = PROJECT_ROOT / "data" / "eval"

# 样本表字段：与《01_指标口径》数据字典 14 字段完全一致（不含派生列）
SAMPLE_COLUMNS = [
    "order_id", "order_item_no", "sku", "product_name", "quantity",
    "unit_price", "amount", "is_refund", "is_product",
    "order_time", "order_date", "customer_id", "country", "source_sheet",
]


def build_sales_sample(step: int, recent_days: int) -> pd.DataFrame:
    """从 sales_detail 抽样。

    抽样策略（可复现、无随机性）：
    - 等距抽样：rowid % step == 0，保证覆盖全时间跨度与各国市场；
    - 追加近 N 个有交易日期的全量明细：保证样本含完整的"最近经营日"场景（日报/周报演示用）。
    """
    if not DATA_DB.exists():
        raise FileNotFoundError(f"未找到事实表：{DATA_DB}")

    cols = ", ".join(SAMPLE_COLUMNS)
    with sqlite3.connect(DATA_DB) as con:
        # 1) 全表等距抽样
        base = pd.read_sql_query(
            f"SELECT rowid, {cols} FROM sales_detail WHERE (rowid % ?) = 0",
            con, params=(step,),
        )
        # 2) 最近 N 个有交易日期的全量明细
        recent_dates = pd.read_sql_query(
            "SELECT DISTINCT order_date FROM sales_detail "
            "ORDER BY order_date DESC LIMIT ?",
            con, params=(recent_days,),
        )["order_date"].tolist()

        recent_frames = []
        for d in recent_dates:
            part = pd.read_sql_query(
                f"SELECT rowid, {cols} FROM sales_detail WHERE order_date = ?",
                con, params=(d,),
            )
            recent_frames.append(part)
        recent = pd.concat(recent_frames, ignore_index=True) if recent_frames else base.iloc[0:0]

    # 合并去重（等距样本与近期明细可能重叠，按 rowid 去重，保留首次出现）
    merged = pd.concat([recent, base], ignore_index=True)
    merged = merged.drop_duplicates(subset=["rowid"], keep="first")
    merged = merged.drop(columns=["rowid"])

    # 稳定排序：先日期后订单号，便于人工阅读与 diff
    merged = merged.sort_values(["order_date", "order_id", "order_item_no"], kind="mergesort")
    return merged.reset_index(drop=True)


def copy_eval_sets() -> list[str]:
    """复制指令评测集到 corpus/（保持文件名可读）。"""
    mapping = {
        "eval_set_golden.csv": "instructions_golden.csv",
        "eval_set_holdout.csv": "instructions_holdout.csv",
    }
    copied = []
    for src_name, dst_name in mapping.items():
        src = EVAL_DIR / src_name
        if not src.exists():
            print(f"[warn] 缺少评测集，已跳过：{src}")
            continue
        dst = CORPUS_DIR / dst_name
        shutil.copyfile(src, dst)
        copied.append(dst.name)
    return copied


def write_readme(sample_rows: int, sample_min: str, sample_max: str,
                 countries: int, copied: list[str]) -> None:
    """写入语料库索引说明。"""
    readme = f"""# 报表语料库（corpus/）

> 任务书 §5.2 交付物：销售数据样本库 + 指令评测集 + 报告生成提示词。
> 全部内容由 `scripts/build_corpus.py` 从本项目资产**自动生成**，可一键复现，无手工编造。

## 1. 销售数据样本库

| 项 | 值 |
|---|---|
| 文件 | `sales_sample.csv` |
| 样本行数 | {sample_rows:,} |
| 日期范围 | {sample_min} ~ {sample_max} |
| 覆盖市场数 | {countries} |
| 来源 | 唯一事实表 `data/processed/report_agent.db` 的 `sales_detail`（1,033,031 行） |
| 抽样方式 | `rowid % step` 等距抽样 + 最近若干个完整交易日全量明细（确定性，可复现） |

字段与《01_指标口径与数据字典 v1.0》的 14 字段完全一致：
`order_id, order_item_no, sku, product_name, quantity, unit_price, amount,
is_refund, is_product, order_time, order_date, customer_id, country, source_sheet`

口径提醒：GMV 只统计 `is_refund = 0 AND is_product = 1` 的行；`is_refund=1` 为退款/红冲行。

## 2. 指令评测集

| 文件 | 说明 |
|---|---|
| {chr(10).join(f'`{n}`' for n in copied) if copied else '（缺失）'} | 主集 55 条 + 留出集 35 条，共 90 条；含 report_type/start/end/country 四项 golden 与 `normal`/`reject` 期望行为 |

评测集按「报告类型 × 时间表达 × 市场 × 边界/歧义/注入」四维矩阵构建，跑分脚本见 `scripts/eval/eval_parse.py`。

## 3. 报告生成提示词

统一放置在 `prompts/`（本目录不重复存放，避免双份维护）：

| 路径 | 内容 |
|---|---|
| `prompts/system/agent_system.md` | 系统提示词：运营助手角色、数据引用规范、结论表述要求、硬约束（禁止生成数值） |
| `prompts/system/intent_nlu.md` | LLM 通道意图解析提示词（与 `llm_client.py` 逐字对应） |
| `prompts/schema/intent.schema.json` | 结构化意图 Intent 的 JSON Schema |
| `prompts/templates/daily.md` | 日报模板 |
| `prompts/templates/weekly.md` | 周报模板 |
| `prompts/templates/monthly.md` | 月报模板 |

## 4. 复现

```bash
python scripts/build_corpus.py            # 默认 step=500、追加最近 7 个交易日
python scripts/build_corpus.py --step 200 # 样本更密（约 5 千行）
```
"""
    (CORPUS_DIR / "README.md").write_text(readme, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="构建报表语料库 corpus/")
    ap.add_argument("--step", type=int, default=500,
                    help="等距抽样步长：rowid %% step == 0（默认 500，约 2 千行）")
    ap.add_argument("--recent-days", type=int, default=7,
                    help="追加最近 N 个有交易日期的全量明细（默认 7）")
    args = ap.parse_args()

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    # 1) 销售数据样本
    sample = build_sales_sample(args.step, args.recent_days)
    out_csv = CORPUS_DIR / "sales_sample.csv"
    sample.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"[ok] 销售样本：{len(sample):,} 行 -> {out_csv}")

    # 2) 指令评测集
    copied = copy_eval_sets()
    print(f"[ok] 指令评测集：{copied if copied else '无'}")

    # 3) README 索引
    write_readme(
        sample_rows=len(sample),
        sample_min=str(sample["order_date"].min()),
        sample_max=str(sample["order_date"].max()),
        countries=int(sample["country"].nunique()),
        copied=copied,
    )
    print(f"[ok] 索引说明 -> {CORPUS_DIR / 'README.md'}")


if __name__ == "__main__":
    main()
