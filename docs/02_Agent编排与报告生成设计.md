# 02 · Agent 编排与报告生成设计（S2 产出）

| 项 | 内容 |
|---|---|
| 版本 / 日期 | v1.0 / 2026-09-07 |
| 负责角色 | AI Agent 工程师（编排/解析/提示词）、指标算法工程师（指标层）、后端工程师（后续 S3 API 封装） |
| 依赖 | S1 metrics 模块、daily_agg 物化表、LangGraph 1.2.11 |
| 运行状态 | ✅ 7 项端到端测试通过，可离线（无 LLM Key）生成报告 |

## 1. 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| 意图解析 | `scripts/agent/intent_parser.py` | 自然语言 → `Intent{report_type,start,end,country}`；纯函数 + pydantic |
| 指标编排 | `scripts/agent/query_executor.py` | `Intent` → `MetricsBundle`（当期/上期/环比/异常/逐日明细） |
| 异常标注 | `scripts/metrics/anomaly.py` | 阈值表驱动，只标注不臆测原因 |
| 报告生成 | `scripts/agent/report_builder.py` | `MetricsBundle` → Markdown 日报/周报/月报 |
| 编排 | `scripts/agent/orchestrator.py` | LangGraph 状态机串联四节点 |

## 2. 编排状态机（LangGraph）

```
START → plan(意图解析) → execute(取数算指标) → reflect(校验+异常汇总) → build(报告生成) → END
```

- `plan`：规则通道默认；`LLM_MODE=llm` 且配置 Key 时优先调大模型，失败自动回退规则。
- `execute`：调用 `aggregates.period_metrics_from_daily`（daily_agg 快路径 / 指定国家实时 SQL）。
- `reflect`：GMV=0 或缺数提示；汇总 `anomaly.detect` 标注。
- `build`：模板化 Markdown，结论全部来自指标，无幻觉。

## 3. 双通道设计（确保无 Key 也能交付）

- **规则通道（默认上线）**：关键词 + 正则 + 中文日期解析，覆盖相对（昨日/上周/本月）、绝对（年-月-日/中文）、区间、市场维度。
- **LLM 通道（D8 接入）**：`_llm_plan()` 占位已留，届时实现 base_url+api_key 调用；失败回退规则，功能不降级。

## 4. 指令解析覆盖范围（验证通过）

- 相对：昨日日报、上周德国周报、本月全市场月报
- 绝对+区间：2010年11月22日到28日全部市场月报、2010年11月22日到28日的日报
- 市场：中文国名映射 43 国（英国/德国/法国…），"全部/所有/总体"→全市场
- 相对日期锚点：静态数据集以 `sales_detail` 最大日期 2011-12-09 为"今天"

## 5. 验证结果

- `scripts/agent/test_agent.py`：**7 passed**（4 意图解析 + 3 端到端）
- 样例报告：`docs/样例报告/` 下 3 份（周报/日报/月报），均含核心指标表、异常提示、逐日明细
- 已知修正：① 分离的"月""报"误判已修（仅识别连续"月报/周报/日报"）；② 报告标题多"报"字已修；③ 日报补全 0 销售日

## 6. 下一步（S3 衔接）

- D8 接入 LLM 双通道，补充提示词模板与防注入
- S3 将 `run()` 封装为 FastAPI 接口 + 异步任务 + 用户/任务/报告表
