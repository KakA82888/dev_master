# 部署运维手册

| 项 | 内容 |
|---|---|
| 版本 / 日期 | v1.0 / 2026-09-10 |
| 适用 | 电商运营报表自动化 Agent（FastAPI + React，单端口部署） |
| 依据 | 任务书 §四-7「系统集成与联调 → 部署文档」、§6.2 安全与合规要求 |
| 实测环境 | Windows 11 / Python 3.13 / Node 22.22 / SQLite |

---

## 1. 环境要求

| 组件 | 版本 | 说明 |
|---|---|---|
| Python | 3.12+（实测 3.13） | 后端、指标内核、Agent 编排 |
| Node.js | 18+（实测 22.22） | 仅前端构建需要；**运行期不需要** |
| 磁盘 | ≥ 1 GB | 数据文件合计约 370 MB（见 §2） |
| 内存 | ≥ 2 GB | pandas 读取百万人级明细 |

## 2. 数据资产（部署时必须存在）

| 文件 | 大小 | 用途 | 是否入库 |
|---|---|---|---|
| `data/raw/online_retail_II.xlsx` | 43.5 MB | 原始数据集（只读） | 否（.gitignore） |
| `data/processed/report_agent.db` | 203 MB | **唯一事实表** `sales_detail`（1,033,031 行） | 否（大文件） |
| `data/processed/sales_detail.csv` | 124 MB | ETL 中间产物（不入库） | 否 |
| `data/processed/app.db` | 90 KB | 应用库：`users` + `reports` | 否 |

> ⚠️ 前三项体积较大，不随 Git 分发。新环境请按 §6 重新生成，或从既有环境拷贝。

## 3. 安装

```bash
# 3.1 后端（建议使用虚拟环境）
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# 3.2 前端构建产物（仅首次或前端改动后需要）
cd app/frontend
npm install
npm run typecheck               # 类型检查，应 0 error
npm run build                   # 产出 app/frontend/dist
cd ../..
```

## 4. 配置（`.env`）

```bash
cp .env.example .env            # 复制后按实填写
```

| 变量 | 必填 | 说明 |
|---|---|---|
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | 否 | OpenAI 兼容大模型。**不填则自动走规则通道**，功能完整、响应亚秒级 |
| `LLM_MODE` | 否 | `llm` 启用大模型解析；`rule`/留空 = 规则通道（推荐默认，成本与延迟更低） |
| `APP_SECRET_KEY` | **生产必改** | JWT 签名密钥，默认值为开发占位 |
| `APP_DB_PATH` | 否 | 应用库路径，默认 `data/processed/app.db` |
| `SEED_USERNAME` / `SEED_PASSWORD` | 否 | 首次启动创建的种子账号，默认 `demo` / `demo1234` |

> `.env` 已被 `.gitignore` 忽略，**禁止提交或随交付包外传**；API Key 建议定期轮换。

## 5. 启动

### 5.1 生产/演示模式（推荐，单端口）

后端在 :8000 同时提供 API 与前端静态页面，浏览器访问 `http://127.0.0.1:8000` 即为完整应用：

```bash
python -m uvicorn app.backend.main:app --host 127.0.0.1 --port 8000
```

一键脚本（自动判断是否需要构建前端）：

```bash
bash scripts/start.sh           # Linux/macOS/Git Bash
scripts\start.bat               # Windows cmd
```

### 5.2 开发模式（前后端分离，前端热更新）

```bash
# 终端1：后端
python -m uvicorn app.backend.main:app --host 127.0.0.1 --port 8000 --reload
# 终端2：前端（vite 已配置 /api 代理到 8000）
cd app/frontend && npm run dev   # http://127.0.0.1:5173
```

### 5.3 停止

- 前台启动：`Ctrl + C`
- 后台启动：记录 PID 后 `kill <pid>`；Windows 可用 `netstat -ano | findstr :8000` 查 PID 后 `taskkill /PID <pid> /F`

## 6. 数据准备与校验

```bash
# 6.1 重建事实表（需 data/raw 原始 xlsx，耗时数分钟）
python scripts/etl_build_sales_detail.py

# 6.2 事实表行数校验（应为 1,033,031）
python -c "import sqlite3;print(sqlite3.connect('data/processed/report_agent.db').execute('select count(*) from sales_detail').fetchone())"

# 6.3 指标双轨对账（pandas vs SQL，差异应为 0）
python scripts/qa/cross_check.py

# 6.4 评测回归（SM1 指标 / SM2 解析 / SM3 性能）
python scripts/eval/eval_parse.py
python scripts/eval/eval_metrics.py --runs 10
```

## 7. 健康检查与冒烟

| 检查 | 命令 / 方式 | 期望 |
|---|---|---|
| 健康检查 | `curl http://127.0.0.1:8000/api/health` | `{"status":"ok"}` |
| 首页 | 浏览器打开 `http://127.0.0.1:8000` | 登录页正常加载 |
| 接口冒烟 | `python scripts/eval/smoke_http.py`（需服务已启动） | 15/15 通过 |
| 全量测试 | `python -m pytest -q` | 26 passed |

## 8. 备份与恢复

| 对象 | 备份方式 | 频率 |
|---|---|---|
| 应用库 `app.db` | 直接复制文件（SQLite 单文件） | 每次发版前 |
| 事实表 `report_agent.db` | 可由 `data/raw` + ETL 脚本重建，一般无需备份 | 视需要 |
| `.env` | 妥善保管，不进仓库 | 变更时 |

恢复：停止服务 → 覆盖 `app.db` → 启动服务（表结构由 `init_db()` 自动创建）。

## 9. 安全与合规（对应任务书 §6.2）

| 要求 | 当前状态 | 生产建议 |
|---|---|---|
| 数值可回溯 | ✅ 已实现（指标全部来自 `sales_detail`，报告附来源脚注） | 保持 |
| 异常如实标注 | ✅ 已实现（阈值表驱动，不臆测原因） | 保持 |
| 提示词注入防护 | ✅ 已实现（`scripts/agent/guard.py`，五类拦截） | 保持；新增指令模式时同步扩充规则 |
| 敏感内容过滤 | 🟡 部分（网关拦截伪造数值/越权） | 接入 LLM 撰写结论时需补输出侧过滤 |
| HTTPS 加密传输 | ⬜ 开发态为 HTTP | 前置 Nginx/Caddy 反代并启用 TLS；内网演示可豁免 |
| 数据库存储加密 | ⬜ 明文 SQLite | 敏感环境改用 SQLCipher，或限制文件访问权限 |
| 密钥管理 | 🟡 `.env` 本地存放、已 gitignore | 生产改用密钥管理服务，定期轮换 API Key |
| 角色权限 | 🟡 单角色（报告归属校验已实现：跨用户返回 404） | 如需多角色，扩展 `User.role` 与路由守卫 |

> 改 `guard.py` 后**必须重启服务**才生效（Python 模块进程内缓存）。

## 10. 运维命令速查

```bash
python -m pytest -q                                   # 全量测试
python scripts/eval/smoke_http.py                     # 后端 HTTP 冒烟
python scripts/build_corpus.py                        # 重建报表语料库 corpus/
python -m uvicorn app.backend.main:app --port 8000    # 启动
```

## 11. 常见故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 访问 :8000 只有 API、无页面 | 前端未构建 | `cd app/frontend && npm run build` |
| 前端报接口 404/CORS | 前端走了错误端口 | 生产模式统一访问 :8000；开发模式用 :5173（已配代理） |
| 生成报告很慢（10–50s） | 启用了 `LLM_MODE=llm` 且用推理型模型 | 改 `.env` 的 `LLM_MODE=rule`，或换更快对话模型 |
| LLM 配置无效 | 环境变量缺失或进程未重载 | 检查 `.env` 三项 LLM 配置，重启服务 |
| 报告数值异常/为 0 | 区间超出数据范围 | 数据仅到 2011-12-09，确认日期与市场 |
| 端口被占用 | 旧进程残留 | 见 §5.3 结束进程后重启 |
| 修改 guard 后规则未生效 | 模块缓存 | 重启 uvicorn |

## 12. 部署检查清单

- [ ] Python 依赖安装完成（`pip install -r requirements.txt`）
- [ ] `data/processed/report_agent.db` 就位且行数 = 1,033,031
- [ ] 前端已构建（`app/frontend/dist/index.html` 存在）
- [ ] `.env` 已配置（生产环境至少改 `APP_SECRET_KEY` 与种子账号密码）
- [ ] `/api/health` 返回 `{"status":"ok"}`
- [ ] 页面可登录并走通「生成 → 预览 → 确认 → 导出」
- [ ] `pytest -q` 全绿、`smoke_http.py` 15/15
