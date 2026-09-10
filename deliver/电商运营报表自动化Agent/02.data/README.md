# 电商运营报表自动化 Agent —— 数据说明（02.data）

| 项 | 内容 |
|---|---|
| 版本 / 日期 | v1.0 / 2026-09-10 |
| 用途 | 交付包数据目录：提供可直接查看的**数据样本**与**评测基准** |
| 口径依据 | `01.code` 内的《指标口径与数据字典 v1.0》（原始文档位于 docs/） |

---

## 一、本目录内容

| 文件 | 行数/大小 | 说明 |
|---|---|---|
| `sales_sample.csv` | 24,387 行 | **销售数据样本**：从唯一事实表 `sales_detail`（1,033,031 行）抽样得到的明细样本，14 字段与数据字典完全一致 |
| `eval_set_golden.csv` | 55 条 | **指令评测集·主集**：含 report_type / start / end / country 四项标准答案与期望行为（normal / reject） |
| `eval_set_holdout.csv` | 35 条 | **指令评测集·留出集**：用于泛化验证，防止"自己出题自己判" |
| `reference_auto.json` | 7 个特征日 | **指标冻结基准**：双轨对账（pandas / SQL）产出的 golden，用于一键回归 |

## 二、sales_sample.csv 字段（14 列）

| 字段 | 类型 | 说明 |
|---|---|---|
| order_id | TEXT | 订单号（C 开头为取消/退款单） |
| order_item_no | INT | 订单内行序号 |
| sku | TEXT | 商品编码 |
| product_name | TEXT | 商品名称 |
| quantity | INT | 数量（退款行为负数） |
| unit_price | REAL | 单价 |
| amount | REAL | 金额 = quantity × unit_price |
| is_refund | INT | 退款标记（发票 C 开头 或 数量<0） |
| is_product | INT | 是否真实销售商品（排除运费/折扣/人工调整） |
| order_time | TEXT | 下单时间 |
| order_date | TEXT | 下单日期 |
| customer_id | REAL | 客户 ID（缺失填 -1） |
| country | TEXT | 市场/国家（43 个取值） |
| source_sheet | TEXT | 来源 sheet（仅溯源用） |

> 口径提醒：**GMV 只统计 `is_refund = 0 AND is_product = 1` 的行**；退款率需区分金额口径与订单数口径。

## 三、为什么没有放原始数据

原始数据集体积较大（`online_retail_II.xlsx` 43.5 MB、事实表 `report_agent.db` 203 MB、明细 CSV 124 MB），不适合随交付包分发。需要完整数据时，按下面任一方式获取：

**方式一：重新生成（推荐，可复现）**

```bash
# 1) 下载原始数据集 UCI Online Retail II（CC BY 4.0），放入 data/raw/
#    https://archive.ics.uci.edu/dataset/502/online+retail+ii
# 2) 重建标准明细表与事实表（清洗规则 R1–R6）
python scripts/etl_build_sales_detail.py
# 3) 重建本目录的销售样本
python scripts/build_corpus.py
```

**方式二：向交付方索取**完整数据包（原始 xlsx + 事实表）。

## 四、数据校验（拿到完整数据后自检）

```bash
# 事实表行数应为 1,033,031
python -c "import sqlite3;print(sqlite3.connect('data/processed/report_agent.db').execute('select count(*) from sales_detail').fetchone())"

# 双轨对账：pandas 与 SQL 两条独立路径差异应为 0
python scripts/qa/cross_check.py

# 指标全期基线 GMV 应为 19,642,692.15 GBP（仅有效商品）
```

## 五、数据来源与授权

| 项 | 内容 |
|---|---|
| 数据集 | UCI Machine Learning Repository · Online Retail II |
| 覆盖区间 | 2009-12-01 ~ 2011-12-09（英国跨境批发零售，43 个市场） |
| 授权 | CC BY 4.0（可自由使用，需署名） |
| 币种 | GBP（英镑），报表不做汇率换算 |
| 变更说明 | 任务书原写"天池数据集"，实际采用 UCI，已书面化（见交付包《数据源变更说明》） |
