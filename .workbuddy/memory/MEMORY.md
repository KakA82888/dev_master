# 电商运营报表自动化 Agent — 项目长期记忆

## 项目定位
基于大模型的电商运营报表自动化 Agent Web 应用。用户用自然语言下指令（"生成昨日日报/本周周报"），
Agent 读销售数据 → 算指标 → 分析波动 → 生成报表 → 人工确认后归档导出。

## 已确立的项目约定（不可随意推翻）
- **数据源**：UCI Online Retail II（不使用天池数据集，已确认可放开该约束）
- **唯一事实表**：`data/processed/report_agent.db` 的 `sales_detail`，所有指标查它，模型禁止自己生成数值
- **转化率定义**：订单转化率 = 有效订单数 / 全部生成订单数（数据集无浏览行为，属需求重定义，须在文档中写明）
- **退款率**：必须区分「金额口径」与「订单数口径」，实测两者差约 5 倍
- **金额对账纪律**：任何金额变动都要能落到具体清洗规则，不允许出现无法解释的百分比偏差
- **指标验证（用户 09-07 拍板，替代任务书"人工核算"）**：不用人工核算、不留人力时间；≥99% 证据 = 「自动化双轨对账」：pandas/SQL 两套独立实现互验（差异=0）+ 全量金额断言（分项加总=总计）+ 7 特征日 `reference_auto.json` 一键回归（D3 落地，脚本自动跑）
- 交付节奏：先跑通数据/指标内核，再写文档

## 三周排期（21 天）
- D1 指标口径文档（5 个指标公式 + 双口径取舍 + 异常阈值）
- D1–D2 指标计算模块 metrics.py（纯函数、可单测）
- D2 自动化双轨对账基准（D3 完善：cross_check + reference_auto.json；替代人工核算，零人力）
- D3–D5 Agent 编排（LangGraph 规划-执行-反思）+ 提示词模板
- D5–D7 后端 FastAPI + 异步任务 + 用户/任务/报告表
- D8–D11 前端 React + 报表预览 + 人工确认回写
- D12 评测集 ≥50 条 + 自动评测脚本
- D13 bad case 迭代
- D15–D17 六类文档（PRD / UIUX / 数据库设计 / API / 测试报告 / 部署手册）
- D18 汇报 PPT
- D19–D20 AI 协作教程 + 参数文档 + 报表语料库
- D21 缓冲与答辩演练

**进度风险点**：双轨对账基准（自动化）必须尽早做（否则 ≥99% 无据可依）；
AI 协作教程与参数文档应边做边记，不要最后补；前端是演示层，时间不够时可裁剪。

## 目录结构
```
D:\电商\
├─ app\backend\     FastAPI（config/db/models/schemas/security/generator/exporters + routers）
├─ app\frontend\    React（tokens.css 设计系统 / api.ts / markdown.ts / ui.tsx / report.tsx / pages.tsx）
├─ data\raw\        原始 xlsx（只读）
├─ data\processed\  sales_detail.csv + report_agent.db(事实表) + app.db(应用库)
├─ data\eval\       评测集 90 条 + 跑分报告 + reference_auto.json
├─ scripts\metrics\ 指标内核（indicators/aggregates/anomaly）
├─ scripts\agent\   guard → intent_parser/llm_client → orchestrator → query_executor → report_builder
├─ scripts\qa\      双轨对账 cross_check.py
├─ scripts\eval\    评测脚本（eval_parse/eval_metrics/eval_llm/smoke_http）
├─ scripts\         ETL、build_corpus.py、start.sh / start.bat
├─ prompts\         system(系统提示词/NLU) + schema(Intent Schema) + templates(日报周报月报)
├─ corpus\          报表语料库：sales_sample.csv(24,387行) + 指令集 90 条 + README
├─ deliver\         最终交付包（待打包）
└─ docs\            六类文档 + 项目计划 + 样例报告 + 数据源变更说明 + 部署手册 + 参数文档 + AI协作教程
```

## 运行环境
托管 venv：`C:\Users\12247\.workbuddy\binaries\python\envs\default\Scripts\python.exe`
已装：pandas 3.0.5 / openpyxl 3.1.5 / ucimlrepo
沙箱限制：禁止直接删文件（`Path.unlink()` 会抛 SAFE_DELETE_FAIL_CLOSED），改用 `DROP TABLE IF EXISTS` 规避。

## 操作禁忌（2026-09-10 事故教训，务必遵守）
**禁止在 git 命令中直接书写含中文的文件路径**（Windows + Git Bash 下路径编码会错配）：
- 事故：执行 `git rm "docs/00_项目计划/__pdf_extract_智能问数.txt"` 后，**整个 `docs/` 目录被删除**，
  随后 `git add "docs/部署运维手册.md"` 报 `pathspec did not match`，`git add docs/*.md` 又把"删除"批量暂存。
- 规避：`git add -A`（不带 pathspec）或只用 ASCII 目录名做参数（如 `git add docs`）；
  删除/移动中文名文件改用 **PowerShell `Remove-Item -LiteralPath`**（原生 Unicode，可靠）。
- 恢复：`git reset -q` 取消暂存 → `git checkout HEAD -- docs` 整目录还原（已验证可用，文件全部找回）。
- 教训：任何删除操作前先确认备份；`git status` 出现成片 ` D` 立即停止并先恢复。
