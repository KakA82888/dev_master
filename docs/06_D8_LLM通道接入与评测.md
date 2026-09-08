# D8 LLM 通道接入与评测报告

**日期**：2026-09-08（D2）
**负责人**：AI-Eng（由 PM 代行）
**关联**：任务书 D8「大模型接入」、PRD R11（安全）、S6 评测闭环

---

## 1. 接入内容

用户于 10:27 提供 SiliconFlow API Key，指定模型 `Pro/deepseek-ai/DeepSeek-R1`，要求接入作为 LLM 通道。

| 配置项 | 值 |
|---|---|
| 提供方 | SiliconFlow（OpenAI 兼容） |
| `LLM_BASE_URL` | `https://api.siliconflow.cn/v1` |
| `LLM_MODEL` | `Pro/deepseek-ai/DeepSeek-R1` |
| `LLM_MODE` | `llm`（启用 LLM 通道；`rule` 或空则仅规则通道） |
| Key 存放 | `.env`（已被 `.gitignore` 忽略，不入库、不打包） |

## 2. 新增 / 改动文件

| 文件 | 改动 |
|---|---|
| `scripts/agent/llm_client.py` | **新增**。OpenAI 兼容客户端封装；`llm_parse_intent(instruction, anchor)` 调大模型做意图解析，返回结构化 `Intent`；硬约束：LLM 只做 NLU，不生成任何金额数字；失败/未配置向上抛异常，由编排层回退规则通道。 |
| `scripts/agent/orchestrator.py` | 双通道改造：`_plan` **先跑 `guard` 安全网关**（确定性拦截），放行后才按 `LLM_MODE` 选通道；LLM 解析失败自动回退规则通道。 |
| `scripts/eval/eval_llm.py` | **新增**。LLM vs 规则通道对比评测 + reject 安全不变量 + 全链路出报。 |
| `app/backend/main.py` | 顶部加 `load_dotenv`，启动即加载 `.env`。 |
| `conftest.py` | 顶部强制 `os.environ["LLM_MODE"]="rule"`，封堵测试期间误触真实 LLM。 |

> **设计要点**：安全网关（`guard.py`）在 LLM 之前运行，LLM 只处理已放行指令；LLM 输出经 JSON 提取 + 字段校验后构造 `Intent`，任何异常都回退规则通道——保证「无 Key / Key 失效 / 模型异常」时系统仍可端到端运行。

## 3. 评测结果

### 3.1 安全不变量（A 组）
LLM 模式下，12/12 危险指令仍被 `guard` **真实拦截**（注入 / 越权 / 伪造 / 越界 / SQLi 五类），LLM 通道未绕过安全网关。

### 3.2 解析准确率对比（B 组，normal 分层抽样 15 条）
| 通道 | 准确率 |
|---|---|
| LLM 通道（DeepSeek-R1） | **15/15 = 100.0%** |
| 规则通道 | 15/15 = 100.0% |

样本覆盖：昨日/前天日报、上周/本周周报、上月/本月月报、绝对日期、指定国家（德国/法国/澳大利亚/中国香港）、全市场等。两通道在该样本上表现一致。

### 3.3 全链路集成（C 组）
LLM 通道成功生成日报（report 非空，665 字符）。

### 3.4 真实 HTTP 端到端（后端 :8000）
`POST /api/reports/generate {"instruction":"生成上月德国月报"}` → HTTP 200 / `drafted` / **耗时 14.2s** / 报告 2235 字符含 GMV。14s 延迟确证走了 LLM 通道（规则通道为亚秒级）。

## 4. 关键指标对照

| 指标 | 目标 | 结果 |
|---|---|---|
| 安全网关拦截（含 LLM 模式） | 100% | ✅ 12/12 |
| 解析准确率 SM2（LLM 通道） | ≥90% | ✅ 100% |
| 端到端时效 SM3（≤2min） | ≤120s | ✅ 14.2s（R1 推理慢，但达标） |
| 规则通道可用性（无 Key 回退） | 100% | ✅ 保留 |

## 5. 回归与质量门禁
- `pytest -q` → **26 passed**（conftest 强制 rule，单测不触真实 LLM）。
- 修复一个测试污染 bug：`llm_client` 原在导入时 `load_dotenv` 会把 `LLM_MODE=llm` 注入进程，导致 pytest 后端生成类测试误调真实 LLM 而失败；已把 `.env` 加载移出模块级，改由入口显式加载，并在 conftest 强制 `rule`。

## 6. 结论与建议
1. **D8 达成**：LLM 通道已接入、可用、安全、可回退；双通道对照证明解析质量与规则通道一致。
2. **模型选型建议（重要）**：当前用 `DeepSeek-R1`（推理模型）做「意图解析」属于杀鸡用牛刀——单次 9–52s 延迟、成本偏高，且对结构化抽取无额外收益。建议生产环境改配更快的对话模型（如 `deepseek-ai/DeepSeek-V3` 或 `Pro/deepseek-ai/DeepSeek-V3`），切换仅需改 `.env` 的 `LLM_MODEL` 一行。本次按用户指定保留 R1。
3. **Key 安全提醒**：Key 曾在对话中明文出现，建议到 SiliconFlow 控制台**轮换**一次；`.env` 已 gitignore，请勿提交或截图外传。
4. **自验说明**：解析对照的 golden 仍为 AI 预填（S6 遗留），本次 LLM 通道 100% 属「AI 出题 + AI 判 + AI 跑分」；建议答辩时说明，并安排业务负责人抽查 golden（D1 待拍板项）。

## 7. 复现命令
```bash
# 单元/集成回归
python -m pytest -q

# LLM vs 规则 对比评测（需 .env 配好 Key 且 LLM_MODE=llm）
python scripts/eval/eval_llm.py

# 后端真实 HTTP 验证
uvicorn app.backend.main:app --host 127.0.0.1 --port 8000
curl -X POST http://127.0.0.1:8000/api/reports/generate \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"instruction":"生成上月德国月报"}'
```
