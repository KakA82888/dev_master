# 03 · 后端 API 与数据模型设计（S3 产出）

| 项 | 内容 |
|---|---|
| 版本 / 日期 | v1.0 / 2026-09-07 |
| 状态 | 已实现并通过接口测试（6 passed）+ uvicorn 真实 HTTP 冒烟 |
| 角色 | 后端工程师 实现，测试工程师 把关，产品经理 验收 |
| 技术栈 | FastAPI 0.141 · Uvicorn · SQLAlchemy 2.0 · PyJWT(jose) · passlib[bcrypt] · SQLite |

## 1. 架构与分层

```
app/backend/
├── config.py        路径 / 密钥 / JWT 参数（支持 APP_DB_PATH 环境变量覆盖）
├── db.py            SQLAlchemy 引擎、SessionLocal、Base、init_db、get_db
├── models.py        ORM：User、Report（含状态机常量）
├── schemas.py       Pydantic：UserCreate/UserLogin/Token/CurrentUser/ReportGenerateRequest/ReportOut/ReportSummary
├── security.py      密码哈希、JWT 签发/校验、get_current_user 依赖
├── generator.py     报告异步生成服务（调用 S2 orchestrator.run）
├── routers/
│   ├── auth.py      /api/auth/register、/api/auth/login
│   └── reports.py   报告生成/预览/确认/归档/历史/删除
├── main.py          FastAPI 入口（CORS、lifespan 种子账号、路由装配）
└── test_api.py      接口测试（pytest + TestClient，6 passed）
```

设计要点：
- **单一事实表隔离**：分析库 `data/processed/report_agent.db`（只读查询，S1 产出）与应用状态库 `data/processed/app.db`（用户/报告）分离，保证金额对账纪律不被污染。
- **生成与请求解耦**：`POST /generate` 立即返回 `report_id`（status=pending），后台 `BackgroundTasks` 调用 `orchestrator.run` 落库；前端轮询 `GET /{id}` 即可。测试可用 `?sync=true` 同步拿到结果。
- **鉴权返回 Pydantic 而非 ORM**：`get_current_user` 返回 `CurrentUser`（Pydantic），避免 FastAPI 把 SQLAlchemy 模型误识别为请求参数（已踩坑修复）。

## 2. 数据模型

### User
| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| username | str UNIQUE | 登录名 |
| hashed_password | str | bcrypt 哈希 |
| created_at | datetime | |

### Report（状态机：pending→running→drafted→confirmed→archived，外加 failed）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| user_id | int FK | 归属用户（越权隔离） |
| instruction | str | 用户自然语言指令 |
| report_type | str | daily/weekly/monthly |
| period_start / period_end | str | 报告周期（锚点：数据表最大日期） |
| market | str | Country 维度或 ALL |
| title / markdown | str/Text | 报告标题与正文 |
| metrics_json | Text | MetricsBundle 序列化，供 S5 导出 |
| status | str | 状态机当前态 |
| error | Text | 失败原因 |
| version | int | 确认回写自增，便于审计 |
| created_at / updated_at / confirmed_at | datetime | |

## 3. API 清单

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | /api/health | 否 | 健康检查 |
| POST | /api/auth/register | 否 | 注册，返回 JWT |
| POST | /api/auth/login | 否 | 登录，返回 JWT |
| POST | /api/reports/generate?sync= | **是** | 生成报告（异步后台；sync=true 同步） |
| GET | /api/reports | **是** | 当前用户报告历史（按时间倒序） |
| GET | /api/reports/{id} | **是** | 报告预览（含 markdown/metrics） |
| POST | /api/reports/{id}/confirm | **是** | 草稿→已确认（version+1） |
| POST | /api/reports/{id}/archive | **是** | 已确认→归档 |
| DELETE | /api/reports/{id} | **是** | 删除（仅本人） |
| GET | /api/reports/{id}/export?fmt=docx\|markdown | **是** | 导出 Word(docx)/Markdown；drafted/confirmed/archived 可导出，其余 400 |

鉴权：除 health/register/login 外均需在 `Authorization: Bearer <token>` 携带 JWT；越权访问他人报告返回 404（不暴露存在性）。

## 4. 启动方式

```bash
# 开发启动
python -m uvicorn app.backend.main:app --app-dir D:/电商 --host 127.0.0.1 --port 8000 --reload
# 首次启动自动创建 app.db 并写入种子账号 demo / demo1234（生产请改密或删除）
# 测试（独立测试库，不污染开发数据）
python -m pytest app/backend/test_api.py app/backend/test_export.py -q
```

## 5. 已知约束 / 后续

- 演示用种子账号 `demo/demo1234` 仅方便本地演示，部署前请删除或改密（见 config.SEED_*）。
- 定时报告（`schedule/cron`）字段已预留，调度器（APScheduler）在 S4 后端扩展接入。
- 大并发下 SQLite 为单写库，演示足够；若需并发写入可换 PostgreSQL（仅改 db.py 引擎串）。
- 报告导出（Markdown/Word 双格式）在 S5 接入，复用本模块的 `markdown` 与 `metrics_json`。
