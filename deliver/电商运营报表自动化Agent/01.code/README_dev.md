# 电商运营报表自动化 Agent —— 开发环境部署文档（README_dev）

| 项 | 内容 |
|---|---|
| 版本 / 日期 | v1.0 / 2026-09-10 |
| 适用 | 开发者：在本机搭建开发环境、运行测试、二次开发 |

---

## 一、项目概述

**项目名称**：电商运营报表自动化 Agent
**技术架构**：前后端分离（B/S）

- **前端**：React 18 + TypeScript + Vite 5（开发端口 5173）
- **后端**：FastAPI + Python 3.13（端口 8000）
- **数据库**：SQLite（`report_agent.db` 事实表 + `app.db` 应用库）
- **智能体**：LangGraph 状态机（plan → execute → reflect → build）
- **大模型**：OpenAI 兼容接口（默认 SiliconFlow，可选；不配置则走规则通道）

**核心功能**：

- 自然语言下达报表指令（"生成昨日日报 / 本周德国周报"）
- 自动计算 GMV、订单量、客单价、订单转化率、退款率（双口径）及环比
- 异常波动标注 → 结构化报告 → 人工确认 → 归档 → Markdown / Word 导出
- 用户注册登录、历史报告管理与筛选

## 二、系统需求

| 组件 | 最低配置 | 推荐配置 |
|---|---|---|
| CPU | 2 核 | 4 核及以上 |
| 内存 | 4 GB | 8 GB 及以上 |
| 磁盘 | 2 GB | 5 GB 及以上 |
| 网络 | 可选（调用大模型 API 时需要） | — |

**操作系统**：Windows / Linux / macOS
**Python 版本**：3.12+（实测 3.13）
**Node.js 版本**：18+（实测 22.22，仅前端构建需要）

## 三、环境依赖

### 3.1 后端依赖

```bash
pip install -r requirements.txt
```

主要依赖：`fastapi`、`uvicorn`、`sqlalchemy`、`pydantic`、`python-jose`、`passlib`、`bcrypt`、`openai`、`langgraph`、`pandas`、`openpyxl`、`python-docx`、`python-dotenv`、`pytest`、`httpx`

### 3.2 前端依赖

```bash
cd app/frontend
npm install
```

## 四、数据准备

```bash
# 1) 原始数据集 UCI Online Retail II（CC BY 4.0）放入 data/raw/online_retail_II.xlsx
# 2) 生成标准明细表 + 事实表（清洗规则 R1–R6）
python scripts/etl_build_sales_detail.py
# 3) 生成销售样本语料（可选）
python scripts/build_corpus.py
```

## 五、配置

```bash
cp .env.example .env      # 按需填写
```

| 变量 | 说明 |
|---|---|
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | 大模型配置；**留空则自动走规则通道** |
| `LLM_MODE` | `llm` 启用大模型解析；`rule`/留空 = 仅规则通道 |
| `APP_SECRET_KEY` | JWT 密钥（开发可用默认值） |
| `SEED_USERNAME` / `SEED_PASSWORD` | 种子账号，默认 `demo` / `demo1234` |

## 六、启动

```bash
# 后端（:8000）
python -m uvicorn app.backend.main:app --host 127.0.0.1 --port 8000 --reload

# 前端（:5173，vite 已配置 /api 代理到 8000）
cd app/frontend && npm run dev
```

> 前端构建产物存在时（`app/frontend/dist`），后端会自动托管它，此时访问 `http://127.0.0.1:8000` 即完整应用（无需另起前端）。

## 七、测试与评测

```bash
python -m pytest -q                            # 单元/集成测试（26 passed）
python scripts/qa/cross_check.py               # 指标双轨对账（差异应为 0）
python scripts/eval/eval_parse.py              # 指令解析评测（SM2）
python scripts/eval/eval_metrics.py --runs 10  # 指标回归 + 性能（SM1/SM3）
python scripts/eval/smoke_http.py              # 后端 HTTP 冒烟（需服务已启动）
```

## 八、目录结构

```
01.code/
├── app/
│   ├── backend/          FastAPI：config / db / models / schemas / security /
│   │                     generator / exporters / routers(auth,reports) / main
│   └── frontend/         React：tokens.css 设计系统 / api.ts / markdown.ts /
│                         ui.tsx / report.tsx / pages.tsx / main.tsx
├── scripts/
│   ├── metrics/          指标内核（indicators / aggregates / anomaly）
│   ├── agent/            guard → intent_parser / llm_client → orchestrator →
│   │                     query_executor → report_builder
│   ├── qa/               双轨对账 cross_check.py
│   ├── eval/             评测脚本（eval_parse / eval_metrics / eval_llm / smoke_http）
│   ├── etl_build_sales_detail.py   ETL（清洗规则 R1–R6）
│   ├── build_corpus.py             语料库构建
│   └── start.sh / start.bat        一键启动
├── prompts/              system(系统提示词/NLU) + schema(Intent Schema) + templates(日报周报月报)
├── conftest.py           pytest 配置（测试库隔离 + 强制规则通道）
├── requirements.txt
└── .env.example
```

## 九、常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 页面打不开 | 前端未构建 | `cd app/frontend && npm run build` |
| 生成报告很慢 | 启用 LLM 通道且用推理型模型 | 改 `.env` 的 `LLM_MODE=rule` |
| 指标为 0 | 区间超出数据范围（数据仅到 2011-12-09） | 调整日期或市场 |
| 测试报 LLM 错误 | 环境变量泄漏进测试进程 | 已由 `conftest.py` 强制 `LLM_MODE=rule` 兜底 |
| 改 `guard.py` 不生效 | 模块进程内缓存 | 重启 uvicorn |
