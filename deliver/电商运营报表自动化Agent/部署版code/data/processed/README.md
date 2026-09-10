# data/processed —— 数据目录说明

本目录存放应用运行数据。**出于体积考虑（事实表约 194MB），交付包内不含数据文件**，首次部署需按以下方式准备。

## 需要的文件

| 文件 | 作用 | 是否必须 |
|---|---|---|
| `app.db` | 应用状态库（用户 / 报告记录） | 否——首次启动自动创建 |
| `report_agent.db` | 唯一事实表（sales_detail，1,033,031 行） | **是**——生成报告的数据来源 |

## 获取方式（二选一）

### 方式 a：直接复制（推荐，最快）
从完整项目 / 交付方处获取 `report_agent.db`，放到本目录：

```
data/processed/report_agent.db     ← 放这里
```

### 方式 b：ETL 重建（可复现）
1. 下载 UCI Online Retail II 原始数据（两个 sheet 的 xlsx，约 44MB）：
   <https://archive.ics.uci.edu/dataset/502/online+retail+ii>
2. 放到 `data/raw/online_retail_II.xlsx`
3. 运行 ETL（在部署根目录执行）：

```bash
python scripts/etl_build_sales_detail.py
```

4. 校验（应输出 1,033,031 行、日期 2009-12-01 ~ 2011-12-09）：

```bash
python -c "import sqlite3;con=sqlite3.connect('data/processed/report_agent.db');print(con.execute('SELECT COUNT(*),MIN(order_date),MAX(order_date) FROM sales_detail').fetchone())"
```

## 校验基准（重建后核对）

| 项 | 基准值 |
|---|---|
| 行数 | 1,033,031 |
| 字段数 | 14 |
| 市场数 | 43 |
| 日期范围 | 2009-12-01 ~ 2011-12-09 |
| 全期 GMV（有效商品） | £19,642,692.15 |

> 口径详见交付包《01_指标口径与数据字典》。数据不放包内是刻意设计：保证 git 仓库轻量，数据获取路径清晰可复现。
