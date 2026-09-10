# 报表语料库（corpus/）

> 任务书 §5.2 交付物：销售数据样本库 + 指令评测集 + 报告生成提示词。
> 全部内容由 `scripts/build_corpus.py` 从本项目资产**自动生成**，可一键复现，无手工编造。

## 1. 销售数据样本库

| 项 | 值 |
|---|---|
| 文件 | `sales_sample.csv` |
| 样本行数 | 24,387 |
| 日期范围 | 2009-12-01 ~ 2011-12-09 |
| 覆盖市场数 | 27 |
| 来源 | 唯一事实表 `data/processed/report_agent.db` 的 `sales_detail`（1,033,031 行） |
| 抽样方式 | `rowid % step` 等距抽样 + 最近若干个完整交易日全量明细（确定性，可复现） |

字段与《01_指标口径与数据字典 v1.0》的 14 字段完全一致：
`order_id, order_item_no, sku, product_name, quantity, unit_price, amount,
is_refund, is_product, order_time, order_date, customer_id, country, source_sheet`

口径提醒：GMV 只统计 `is_refund = 0 AND is_product = 1` 的行；`is_refund=1` 为退款/红冲行。

## 2. 指令评测集

| 文件 | 说明 |
|---|---|
| `instructions_golden.csv`
`instructions_holdout.csv` | 主集 55 条 + 留出集 35 条，共 90 条；含 report_type/start/end/country 四项 golden 与 `normal`/`reject` 期望行为 |

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
