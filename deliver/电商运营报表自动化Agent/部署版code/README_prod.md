# 电商运营报表自动化 Agent —— 生产部署文档（README_prod）

| 项 | 内容 |
|---|---|
| 版本 / 日期 | v1.1 / 2026-09-10 |
| 适用 | 部署人员：将系统部署到服务器，单端口对外提供服务 |
| 特点 | **已内置前端构建产物**（`app/frontend/dist/`），无需 Node.js 环境 |
| 结构 | 与源码版（01.code）**完全同构**，路径规则一致，零代码改动 |

---

## 一、目录说明

```
部署版code/
├── app/
│   ├── __init__.py
│   ├── backend/          FastAPI 源码（routers / models / generator / exporters）
│   └── frontend/
│       └── dist/         前端构建产物（已内置，后端自动挂载为站点首页）
├── scripts/
│   ├── agent/            智能体内核（意图解析 / 安全网关 / LangGraph 编排 / 大模型 / 报告生成）
│   ├── metrics/          指标内核（GMV / 订单 / AOV / 转化率 / 退款率 全部在此计算）
│   ├── etl_build_sales_detail.py   数据重建脚本（原始 xlsx → 事实表）
│   ├── start.sh          一键启动（Linux / macOS / Git Bash）
│   └── start.bat         一键启动（Windows）
├── data/
│   └── processed/        数据目录（见《data/processed/README.md》：需放入事实表）
├── requirements.txt      Python 依赖清单
├── .env.example          环境配置模板（复制为 .env 后填写）
└── README_prod.md        本文档
```

> 路径约定：代码按"项目根"推算目录（`config.py` 的 `parent.parent.parent`），因此**必须在 `部署版code/` 根目录下启动**，目录结构不可改动。

## 二、部署步骤

```bash
# 0) 进入部署根目录（以下命令均在此目录执行）
cd 部署版code

# 1) 安装 Python 依赖（Python 3.12+）
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2) 配置环境变量
cp .env.example .env
#    生产环境必须修改：APP_SECRET_KEY、SEED_PASSWORD
#    如需大模型解析：填 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL，并设 LLM_MODE=llm
#    （不配置则自动走规则通道，功能完整、亚秒级解析）

# 3) 准备数据（事实表）—— 二选一，见 data/processed/README.md
#    a) 从完整项目复制 report_agent.db 到 data/processed/
#    b) 获取原始 xlsx 后运行 ETL 重建：python scripts/etl_build_sales_detail.py

# 4) 启动服务（单端口 = API + 网页）
bash scripts/start.sh            # Windows: scripts\start.bat
#    或手动：python -m uvicorn app.backend.main:app --host 0.0.0.0 --port 8000
```

启动后访问 `http://<host>:8000` 即完整应用。种子账号见 `.env.example`（默认 `demo / demo1234`，生产必须改）。

## 三、健康检查与验收

```bash
curl http://127.0.0.1:8000/api/health     # {"status":"ok"}
curl -I http://127.0.0.1:8000/            # HTTP 200（前端页面）
```

页面验收路径：登录 → 指令框输入"生成10年4月第一周周报" → 预览报告 → 确认 → 导出 Word/Markdown。

## 四、常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 启动报 `unable to open database file` | `data/processed/` 目录缺失或无写权限 | 保持目录结构；`app.db` 会自动创建，需写权限 |
| 首页 404 | `app/frontend/dist/` 缺失 | 本包已内置；若丢失从 `01.code` 重新构建 |
| 生成报告报"事实表不存在" | 未放 `report_agent.db` | 见第 2 步"准备数据" |
| 生成报告报"LLM 解析失败" | 大模型配置错误 | 自动回退规则通道，不影响出报告；或检查 `.env` 的 LLM_* 配置 |

## 五、与源码版（01.code）的关系

- **代码完全一致**（同一次提交导出），仅少了：测试文件、前端源码（保留构建产物）、评测脚本与语料（开发/质量环节专用）。
- 数据文件（事实表 194MB）体积原因**不在包内**，获取方式见 `data/processed/README.md`。
