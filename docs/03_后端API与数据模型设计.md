# 03 · 后端 API 与数据模型设计（S3 产出）

| 项 | 内容 |
|---|---|
| 版本 / 日期 | v1.2 / 2026-09-14（补录：RBAC / 定时任务 / 批量任务 / 修改意见） |
| 状态 | 已实现并通过接口测试 + uvicorn 真实 HTTPS 冒烟；全量 pytest 40 passed（含 RBAC / 定时 / 批量 / 意见用例） |
| 角色 | 后端工程师 实现，测试工程师 把关，产品经理 验收 |
| 技术栈 | FastAPI 0.141 · Uvicorn · SQLAlchemy 2.0 · PyJWT(jose) · passlib[bcrypt] · SQLite |

## 1. 架构与分层

```
app/backend/
├── config.py        路径 / 密钥 / JWT 参数（支持 APP_DB_PATH 环境变量覆盖）
├── db.py            SQLAlchemy 引擎、SessionLocal、Base、init_db、get_db
├── models.py        ORM：User（含 role）、Report（含状态机常量、batch_id）、Feedback、Schedule
├── schemas.py       Pydantic：UserCreate/UserLogin/Token/CurrentUser/ReportGenerateRequest/BatchGenerateRequest/ReportOut/ReportSummary/FeedbackCreate/FeedbackOut/ScheduleCreate/ScheduleUpdate/ScheduleOut
├── security.py      密码哈希、JWT 签发/校验、get_current_user / require_admin 依赖
├── generator.py     报告异步生成服务（调用 S2 orchestrator.run）
├── scheduler.py     定时任务调度器（APScheduler：启动加载、增删改同步、触发建报告）
├── routers/
│   ├── auth.py      /api/auth/register、/api/auth/login、/api/auth/me
│   ├── reports.py   报告生成/批量生成/预览/确认/归档/历史/删除/导出/修改意见
│   ├── schedules.py 定时任务 CRUD、启停、立即执行
│   └── feedback.py  修改意见汇总（供模板迭代）
├── main.py          FastAPI 入口（CORS、lifespan 种子账号、路由装配）
└── test_api.py      接口测试（pytest + TestClient，含 RBAC 权限用例）
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
| **role** | str | **角色：`admin`（可查看与管理全部用户报告）/ `user`（仅本人的报告）；新注册默认 `user`，种子账号自动提升为 `admin`** |
| created_at | datetime | |

> 角色对应任务书 §6.2「按角色控制数据访问权限」。旧库升级时由 `main._ensure_columns()` 幂等补列（回填 `user`），并把既有种子账号提升为 `admin`。

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
| error_code | str | 失败/拦截原因码：`blocked`/`injection`/`out_of_range`/`generation_error`/`internal_error`，供前端区分「安全网关拦截」与「技术故障」 |
| batch_id | str | 批量任务分组：同一次批量提交的报告共享同一 UUID（任务书 §2.2 目标 1） |
| version | int | 确认回写自增，便于审计 |
| created_at / updated_at / confirmed_at | datetime | |

### Feedback（修改意见 —— 任务书 §2.2 目标 4）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| report_id | int FK | 所属报告 |
| user_id | int FK | 提交人 |
| category | str | `metric` 指标数值 / `conclusion` 结论表述 / `format` 格式排版 / `other` |
| content | Text | 意见内容 |
| created_at | datetime | |

### Schedule（定时任务 —— 任务书 §2.2 目标 1 / §3.2「定时调度器」）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| user_id | int FK | 归属用户 |
| name | str | 任务名称 |
| instruction | str | 报表指令 |
| cron | str | 标准 5 段 cron（分 时 日 月 周），由 `CronTrigger.from_crontab` 解析 |
| enabled | bool | 是否启用（停用即从调度器移除） |
| last_run_at | datetime | 上次触发时间 |
| run_count | int | 累计触发次数 |
| created_at | datetime | |

## 3. API 清单

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | /api/health | 否 | 健康检查 |
| POST | /api/auth/register | 否 | 注册，返回 JWT |
| POST | /api/auth/login | 否 | 登录，返回 JWT |
| GET | /api/auth/me | **是** | 当前用户信息（含 `role`），前端据此渲染管理员入口 |
| POST | /api/reports/generate?sync= | **是** | 生成报告（异步后台；`sync=true` 仅测试模式 `APP_ALLOW_SYNC=1` 下可用） |
| GET | /api/reports?scope= | **是** | 报告历史（倒序）；`scope=self`（默认）仅本人，`scope=all` 仅管理员（普通用户 403） |
| GET | /api/reports/{id} | **是** | 报告预览（含 markdown/metrics；管理员可读任意报告，附 `owner` 归属） |
| POST | /api/reports/{id}/confirm | **是** | 草稿→已确认（version+1） |
| POST | /api/reports/{id}/archive | **是** | 已确认→归档 |
| DELETE | /api/reports/{id} | **是** | 删除（本人或管理员） |
| POST | /api/reports/generate/batch | **是** | **批量任务**：一次提交多条指令（≤20 条），返回 `batch_id` 与 `report_ids` |
| POST | /api/reports/{id}/feedback | **是** | 提交修改意见（category / content） |
| GET | /api/reports/{id}/feedback | **是** | 该报告的修改意见列表 |
| GET | /api/feedback/summary | **是** | 修改意见汇总（按分类计数 + 最近明细，供模板迭代） |
| GET | /api/schedules | **是** | 定时任务列表（普通用户仅本人；管理员全部） |
| POST | /api/schedules | **是** | 新建定时任务（cron 非法 → 400） |
| PATCH | /api/schedules/{id} | **是** | 修改名称 / 指令 / cron / 启停 |
| DELETE | /api/schedules/{id} | **是** | 删除定时任务 |
| POST | /api/schedules/{id}/run | **是** | **立即执行一次**（不影响既定 cron 计划），便于演示与验证 |
| GET | /api/reports/{id}/export?fmt=docx\|markdown | **是** | 导出 Word(docx)/Markdown；drafted/confirmed/archived 可导出，其余 400 |

鉴权：除 health/register/login 外均需在 `Authorization: Bearer <token>` 携带 JWT；越权访问他人报告返回 404（不暴露存在性）。

**角色控制（任务书 §6.2）**

| 角色 | 权限 |
|---|---|
| `user` | 仅可访问自己的报告；请求 `?scope=all` 返回 **403** |
| `admin` | 可用 `?scope=all` 查看全部用户报告；可访问/管理任意报告（详情附 `owner` 归属信息） |

管理员校验由 `security.require_admin` 提供；越权访问一律按 404 处理，越权列表按 403 处理。

## 4. 启动方式

```bash
# 开发启动
python -m uvicorn app.backend.main:app --app-dir D:/电商 --host 127.0.0.1 --port 8000 --reload
# 首次启动自动创建 app.db 并写入种子账号 demo / demo1234（生产请改密或删除）
# 测试（独立测试库，不污染开发数据）
python -m pytest app/backend/test_api.py app/backend/test_export.py -q
```

## 5. 已知约束 / 后续

- 演示用种子账号 `demo/demo1234`（**角色自动提升为 `admin`**）仅方便本地演示，部署前请删除或改密（见 config.SEED_*）。
- **定时报表已实现**：`/api/schedules` + `app/backend/scheduler.py`（APScheduler `BackgroundScheduler`，随服务 lifespan 启停；启动时从 `schedules` 表加载已启用任务）。原 `ReportGenerateRequest` 中的 `schedule/cron` 占位字段已移除。
- **批量任务已实现**：`POST /api/reports/generate/batch`，单次最多 20 条指令，报告共享 `batch_id`。
- **修改意见已实现**：`feedback` 表 + `/api/reports/{id}/feedback` + `/api/feedback/summary`（分类统计供模板迭代）。
- 大并发下 SQLite 为单写库，演示足够；若需并发写入可换 PostgreSQL（仅改 db.py 引擎串）。
- 报告导出（Markdown/Word 双格式）在 S5 接入，复用本模块的 `markdown` 与 `metrics_json`。
