# 电商运营报表自动化 Agent —— 集成测试报告

- **测试日期**：2026-09-08
- **测试角色**：WebappTestingExpert（QA 视角的端到端验证）
- **被测系统**：D:\电商 全栈（FastAPI 后端 + React/Vite 前端 + scripts 智能体内核）
- **测试结论**：✅ **通过**，共发现并修复 1 个安全纵深漏洞（SQL 注入式指令未被拦截）。

---

## 1. 测试范围与策略

| 层级 | 测试方式 | 覆盖内容 |
|---|---|---|
| 单元/集成（pytest） | 自动 | agent 解析、metrics 双轨、eval 回归、backend API/export |
| 三大成功指标（S6 评测） | 自动 | SM1 指标准确性、SM2 解析准确率、SM3/SM5 性能 |
| 后端真实 HTTP 冒烟 | httpx 实打实请求 | 鉴权、报告生命周期、导出、越权校验 |
| 前端 | 构建 / typecheck / 资源托管 | 编译正确性、静态资源可加载、API 地址配置 |
| 安全自查 | 真实恶意指令注入 | 注入/越权/伪造/越界/SQLi 五类 |

---

## 2. 测试结果总览

| # | 测试项 | 结果 | 关键数字 |
|---|---|---|---|
| T1 | pytest 全量 | ✅ 26 passed | 0 失败，5.7s |
| T2 | SM1 指标准确性 | ✅ PASS | 三方（pandas/SQL/冻结基准）最大差异 **0.000000** |
| T3 | SM2 解析准确率 | ✅ 100% | 主集 55/55 + 留出集 35/35 |
| T4 | SM3 性能指标 | ✅ PASS | 均值 0.063s，P95 0.026s，失败 0 |
| T5 | 后端 HTTP 生命周期 | ✅ 15/15 | 见 §4 |
| T6 | 前端 typecheck | ✅ 0 error | `tsc --noEmit` exit 0 |
| T7 | 前端资源托管 | ✅ | JS 164197B / CSS 11969B，HTTP 200 |
| T8 | 安全网关（5 类） | ✅ 修复后全拦 | 见 §5 |

---

## 3. S6 评测指标（T2–T4）

```
=== 指令解析评测（SM2）===
总条数 55｜正确 55｜准确率 100.00%
=== 留出集 ===
总条数 35｜正确 35｜准确率 100.00%

=== 指标双轨复核（SM1）===
  10 个随机日期 × 全量金额断言：最大差异 = 0.000000
  gmv_cross_diff: 0.0 ｜ gmv_vs_baseline_diff: 0.0  → PASS ✅

=== 端到端性能（SM3/SM5）===
  均值 0.063s｜P95 0.026s｜最大 0.549s｜失败 0
```

---

## 4. 后端 HTTP 冒烟（T5，15/15）

通过 httpx 真实请求运行中的 uvicorn 服务（:8000）验证完整链路：

| 用例 | 结果 | HTTP |
|---|---|---|
| health | ✅ | 200 |
| 未授权 /generate | ✅ | 401 |
| 注册 + 登录 | ✅ | 200 |
| 重复注册 | ✅ | 400 |
| 生成报告（同步） | ✅ | 200 drafted |
| 报告含 GMV 内容 | ✅ | markdown 687B |
| 列表 / 获取单条 | ✅ | 200 |
| 确认 → confirmed | ✅ | 200 |
| 重复确认 | ✅ | 400 |
| 导出 markdown / docx | ✅ | 200 |
| 跨用户获取 / 导出 | ✅ | 404 |

复现：`python scripts/eval/smoke_http.py`（服务需先启动）

---

## 5. 安全自查与修复（T8）

### 5.1 修复前发现的问题

| 指令 | 期望 | 修复前实际 | 判定 |
|---|---|---|---|
| `生成昨日日报; DROP TABLE sales_detail;--` | 拦截 | **生成了报告** | ❌ 漏洞 |
| `生成昨日日报 DELETE FROM sales_detail` | 拦截 | **生成了报告** | ❌ 漏洞 |
| 伪造数值 / 提示词注入 / 越界日期 | 拦截 | 拦截 | ✅ |

**根因分析**：数据层 `query_executor.py` 使用**参数化查询**（`WHERE order_date BETWEEN ? AND ?` + `(intent.start, intent.end)`），指令文本从不拼进 SQL，因此该指令**不会真实删表**（已验证 `sales_detail` 仍 1,033,031 行）。但安全网关 `guard.py` 缺少对「破坏性 SQL 关键词」的识别规则，属于**纵深防御缺口**（不符合 PRD R11 / 任务书 6.2 的安全预期）。

### 5.2 修复

在 `scripts/agent/guard.py` 的 `PATTERNS` 中新增一条规则：

```python
(r"(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE|DELETE\s+FROM|INSERT\s+INTO|"
 r"UPDATE\s+\w+\s+SET|ALTER\s+TABLE|CREATE\s+TABLE|EXEC\s|EXECUTE\s|;"
 r"\s*(DROP|DELETE|UPDATE|INSERT|ALTER))",
 "sqli", "检测到危险的 SQL 指令片段，已拒绝执行。"),
```

### 5.3 修复后验证（重启服务加载新 guard）

| 指令 | 结果 | HTTP |
|---|---|---|
| SQL 注入式 DROP | ✅ 拦截 | failed + 提示 |
| DELETE FROM | ✅ 拦截 | failed + 提示 |
| 伪造数值 | ✅ 拦截 | failed + 提示 |
| 提示词注入 | ✅ 拦截 | failed + 提示 |
| 越界日期 | ✅ 拦截 | failed + 提示 |
| 正常对照 | ✅ 放行 | drafted |

> ⚠️ **测试环境注意事项**：修改 `guard.py` 后必须**重启 uvicorn** 才能生效（Python 模块在进程内缓存）。首轮线上复测未拦截正是因为测的是旧进程。

---

## 6. 遗留风险与建议

1. **评测自我验证偏差**：SM2 的 100% 由「我出题 + 我修解析器 + 我跑分」得出，留出集 35 条同为 100% 但仍是自产数据。建议答辩时主动说明，并接入 LLM 通道（D8）后重跑 90 条做对比。
2. **规则通道天花板**：当前全链路走规则通道（无 LLM Key），评测只证明「规则能覆盖我写的句子」。D8 接入大模型后必须回归全部 90 条评测集。
3. **Golden 验收**：90 条评测集的 golden 标准答案为模型预填，建议业务负责人抽查 ≥15 条（尤其 G06 类型优先于日期、F01 硬拒绝等边界）。
4. **数据源变更未书面化**：任务书 3.3 写天池数据集，实际用 UCI Online Retail II，需出《数据源变更说明》。
5. **前端仅做了静态验证**：确认了编译通过、资源可加载、API 地址配置正确，但**未在真实浏览器中做交互回归**（生成→确认→导出的可视化流程）。建议演示前人工点一遍。

---

## 7. 测试产物

| 文件 | 说明 |
|---|---|
| `scripts/eval/smoke_http.py` | 后端 HTTP 冒烟脚本（幂等，可重复运行） |
| `scripts/eval/eval_parse.py` / `eval_metrics.py` | SM1/SM2/SM3 评测脚本 |
| `data/eval/parse_report.json` / `metrics_report.json` | 机读跑分报告 |
| `data/processed/app.db.bak_test_*` | 清理测试数据前的备份 |

---

## 8. 复现命令

```bash
# 1) 单元 + 集成 + 评测回归
python -m pytest -q

# 2) 三大成功指标
python scripts/eval/eval_parse.py                 # SM2
python scripts/eval/eval_metrics.py --runs 10      # SM1 + SM3/SM5

# 3) 启动服务 + 后端 HTTP 冒烟
python -m uvicorn app.backend.main:app --host 127.0.0.1 --port 8000
python scripts/eval/smoke_http.py

# 4) 前端校验
cd app/frontend && npm run typecheck && npm run build
```
