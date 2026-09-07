# -*- coding: utf-8 -*-
"""
ETL：把 UCI Online Retail II 原始双 sheet 清洗为一张标准销售明细表 sales_detail。

设计目标（对应任务书 3.3「指标口径与模板构建阶段」）：
本项目所有报表指标都以这张表为唯一数据源，后续 Agent 的指标计算组件只查这张表，
不允许大语言模型自己生成任何数值。

输入：data/raw/online_retail_II.xlsx  （两个 sheet：Year 2009-2010 / Year 2010-2011）
输出：data/processed/sales_detail.csv    全量标准明细
      data/processed/report_agent.db     sqlite 库，表 sales_detail

清洗规则（已与需求方确认）：
  R1 完全重复行      -> 删除
  R2 Price < 0       -> 删除（录入错误）
  R3 Price == 0      -> 保留，标记 amount 为 0，不计入 GMV（赠品 / 换购行）
  R4 Quantity < 0 且非 C 单 -> 视同退款红冲，标记 is_refund = 1
  R5 Customer ID 缺失 -> 填 -1（未登记客户），行本身保留

字段命名统一为 snake_case，避免原始 "Customer ID" 带空格导致后续 SQL 写起来别扭。
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

# ----------------------------- 路径配置 -----------------------------
# 用 __file__ 定位项目根目录，保证脚本从任意工作目录执行都能找到文件
ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = ROOT / "data" / "raw" / "online_retail_II.xlsx"
OUT_DIR = ROOT / "data" / "processed"
CSV_OUT = OUT_DIR / "sales_detail.csv"
DB_OUT = OUT_DIR / "report_agent.db"


def read_raw() -> pd.DataFrame:
    """读取两个年度 sheet 并纵向拼接。

    两个 sheet 的列顺序、列名完全一致，直接 concat 即可。
    """
    if not RAW_FILE.exists():
        sys.exit(f"[ERROR] 找不到原始数据文件：{RAW_FILE}")

    print(f"[1/5] 读取原始文件：{RAW_FILE.name}  ({RAW_FILE.stat().st_size / 1024 / 1024:.1f} MB)")
    excel = pd.ExcelFile(RAW_FILE)
    print(f"      发现 sheet：{excel.sheet_names}")

    frames = []
    for sheet in excel.sheet_names:
        df = excel.parse(sheet)
        df["source_sheet"] = sheet          # 保留来源标记，便于回溯数据出处
        frames.append(df)
        print(f"      - {sheet}: {len(df):,} 行")

    merged = pd.concat(frames, ignore_index=True)
    print(f"      合并后：{len(merged):,} 行")
    return merged


def rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    """把原始列名换成 snake_case，并做类型规范。"""
    return df.rename(columns={
        "Invoice": "order_id",
        "StockCode": "sku",
        "Description": "product_name",
        "Quantity": "quantity",
        "InvoiceDate": "order_time",
        "Price": "unit_price",
        "Customer ID": "customer_id",   # 注意原列名中间有空格
        "Country": "country",
    })


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict, dict]:
    """执行 R1~R6 清洗规则。

    返回：清洗后的表、行数统计字典、被删行的金额统计字典。
    金额统计用于对账 —— 任务书要求指标与人工核算对照准确率 ≥99%，
    所以每一分钱的增减都必须能落到某一条具体规则上，不允许出现说不清的差异。
    """
    stats: dict[str, int] = {}
    removed_amt: dict[str, float] = {}          # 记录每条规则删掉了多少钱
    before = len(df)
    # 金额口径：数量 × 单价，与后续 amount 字段保持一致
    amt = lambda d: float((d["quantity"] * d["unit_price"]).sum())

    # ---- R1：删除完全重复行（同一订单同一 SKU 同一时间的重复录入）----
    dup1 = df.duplicated()
    removed_amt["R1 重复行"] = amt(df[dup1])
    df = df[~dup1].copy()
    stats["R1_删除完全重复行"] = before - len(df)
    before = len(df)

    # ---- R6：剔除跨 sheet 的重复块 ----
    # 体检发现两张 sheet 的时间区间在 2010-12-01 ~ 2010-12-09 重叠了 9 天，
    # 且这段数据是逐行完全相同的重复录入（22,202 行 / 1,088 单 / GBP 376,266.82）。
    # 不去重会让这段时间的 GMV 直接翻倍。keep='last' 表示保留靠后的那张表
    # （即 Year 2010-2011），与其所属年度区间语义一致。
    # business_key = 除来源标记外的全部业务列，用它做跨表去重
    business_key = [c for c in df.columns if c != "source_sheet"]
    dup6 = df.duplicated(subset=business_key, keep="last")
    removed_amt["R6 跨表重叠"] = amt(df[dup6])
    df = df[~dup6].copy()
    stats["R6_删除跨sheet重叠块"] = before - len(df)
    before = len(df)

    # ---- R2：删除负单价（共 5 行，明显是录入或坏账冲销异常）----
    mask_neg_price = df["unit_price"] < 0
    removed_amt["R2 负单价"] = amt(df[mask_neg_price])
    stats["R2_删除负单价行"] = int(mask_neg_price.sum())
    df = df[~mask_neg_price].copy()
    before = len(df)

    # ---- R3：零单价行保留（赠品 / 换购），后续统一不计入 GMV ----
    stats["R3_保留零单价行"] = int((df["unit_price"] == 0).sum())

    # ---- R5：缺失客户号填 -1；缺失商品描述填 UNKNOWN ----
    # 这里不删行：即便没有客户号，金额与时间仍然有效，删掉会丢 24 万行的真实 GMV
    stats["R5_客户号缺失填-1"] = int(df["customer_id"].isna().sum())
    df["customer_id"] = df["customer_id"].fillna(-1).astype("int64")

    stats["__desc_missing__"] = int(df["product_name"].isna().sum())
    df["product_name"] = df["product_name"].fillna("UNKNOWN").str.strip()

    # 额外体检：忽略 source_sheet 后仍有跨 sheet 完全相同的行，说明两个年度表有重叠区间
    cross = df.drop(columns=["source_sheet"]).duplicated().sum()
    stats["__跨sheet疑似重复__"] = int(cross)

    stats["清洗后总行数"] = len(df)
    return df.reset_index(drop=True), stats, removed_amt


def derive(df: pd.DataFrame) -> pd.DataFrame:
    """派生金额、退款标记、商品类型、日期分区键等字段。"""
    print("[3/5] 派生字段")

    # 金额 = 数量 × 单价；退款红冲行 quantity 为负，amount 自然为负，不需要额外处理
    df["amount"] = (df["quantity"] * df["unit_price"]).round(2)

    # 退款标记：满足任一条件即视为退款/冲销
    #   1) 发票号以 C 开头（官方定义的取消单）
    #   2) 数量为负但不是 C 单（后台手工红冲调整，共约 3457 行）
    invoice_str = df["order_id"].astype(str)
    is_cancel_invoice = invoice_str.str.startswith("C")
    is_negative_row = df["quantity"] < 0
    df["is_refund"] = (is_cancel_invoice | is_negative_row).astype("int64")

    # 商品类型：正规 SKU 是 5 位数字开头（可带字母后缀，如 85123A、79323P）
    # 其余如 POST(邮费) / M(人工) / D(折扣) / DOT / CRUK / DCGS* 均属非销售条目
    df["is_product"] = df["sku"].astype(str).str.match(r"^\d{5}").astype("int64")

    # 日期分区键：日报、周报都按这个字段切片
    # 统一转成 "YYYY-MM-DD HH:MM:SS" 字符串：sqlite 无法直接绑定 pandas Timestamp，
    # 字符串格式也让 CSV 在 Excel 里打开即可读，方便人工核对
    order_time = pd.to_datetime(df["order_time"])
    df["order_time"] = order_time.dt.strftime("%Y-%m-%d %H:%M:%S")
    df["order_date"] = order_time.dt.strftime("%Y-%m-%d")

    # 订单内行号：方便定位明细行，也用于后续同名作品的重复下单识别
    df["order_item_no"] = df.groupby("order_id").cumcount() + 1

    print(f"      退款/冲销行占比：{df['is_refund'].mean() * 100:.2f}%")
    print(f"      非销售条目(运费/折扣等)：{int((df['is_product'] == 0).sum()):,} 行")
    return df


def reorder(df: pd.DataFrame) -> pd.DataFrame:
    """整理最终列顺序，形成稳定的标准表契约。"""
    cols = [
        "order_id", "order_item_no", "sku", "product_name",
        "quantity", "unit_price", "amount",
        "is_refund", "is_product",
        "order_time", "order_date",
        "customer_id", "country", "source_sheet",
    ]
    return df[cols]


def write_outputs(df: pd.DataFrame) -> None:
    """写 CSV 与 sqlite 两种介质。

    CSV：便于快速用 Excel 人工核对，支撑任务书「与人工核算对照」的评测环节。
    sqlite：后续 Agent 的指标计算组件直接查库，符合任务书的关系数据库要求。
    """
    print("[4/5] 写出结果")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    df.to_csv(CSV_OUT, index=False, encoding="utf-8-sig")   # utf-8-sig 让 Excel 直接打开不乱码
    print(f"      CSV : {CSV_OUT}  ({CSV_OUT.stat().st_size / 1024 / 1024:.1f} MB)")

    # 用标准库 sqlite3 落库，不额外依赖 SQLAlchemy
    # 重跑时不动磁盘文件，只在库内重建表，避免在受保护环境下触发文件删除限制
    conn = sqlite3.connect(DB_OUT)
    conn.execute("DROP TABLE IF EXISTS sales_detail")
    conn.execute("""
        CREATE TABLE sales_detail (
            order_id       TEXT NOT NULL,
            order_item_no  INTEGER NOT NULL,
            sku            TEXT NOT NULL,
            product_name   TEXT,
            quantity       INTEGER NOT NULL,
            unit_price     REAL NOT NULL,
            amount         REAL NOT NULL,
            is_refund      INTEGER NOT NULL,
            is_product     INTEGER NOT NULL,
            order_time     TEXT NOT NULL,
            order_date     TEXT NOT NULL,
            customer_id    INTEGER NOT NULL,
            country        TEXT,
            source_sheet   TEXT
        )
    """)
    payload = df.where(df.notna(), None)          # NaN 转成 None，sqlite 才能写成 NULL
    conn.executemany(
        "INSERT INTO sales_detail VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        payload.itertuples(index=False, name=None),
    )
    conn.commit()

    # 为报表高频查询建索引：按日期查日报周报、按国家切片、按 SKU 汇总
    conn.execute("CREATE INDEX idx_date   ON sales_detail(order_date)")
    conn.execute("CREATE INDEX idx_country ON sales_detail(country)")
    conn.execute("CREATE INDEX idx_sku    ON sales_detail(sku)")
    conn.commit()

    cnt = conn.execute("SELECT COUNT(*) FROM sales_detail").fetchone()[0]
    conn.close()
    print(f"      DB  : {DB_OUT}  写入 {cnt:,} 行，已建 3 个索引")


def verify(raw: pd.DataFrame, df: pd.DataFrame, removed_amt: dict) -> None:
    """金额对账：原始总额 - 各规则剔除额 必须严格等于 清洗后的总额。

    这是对「指标可追溯」要求的落地：任何 C 位数级别的差异都必须能在下面的
    明细里找到出处，而不是留一个说不清的百分比偏差。
    """
    print("[5/5] 金额对账")

    raw_total = float((raw["quantity"] * raw["unit_price"]).sum())
    clean_total = float(df["amount"].sum())

    print(f"      原始总额            : {raw_total:>15,.2f}")
    for rule, v in removed_amt.items():
        print(f"      - {rule:<12}: {v:>15,.2f}   ({v / raw_total * 100:>7.3f}%)")
    expected = raw_total - sum(removed_amt.values())
    print(f"      = 应得总额          : {expected:>15,.2f}")
    print(f"        实际清洗后总额    : {clean_total:>15,.2f}")

    diff = round(clean_total - expected, 2)
    print(f"        差异              : {diff:>15,.2f}")
    if abs(diff) <= 0.05:
        print("      [OK] 账目完全对平，所有金额变动均有规则可追溯")
    else:
        print("      [FAIL] 存在差异，需排查清洗逻辑")

    # 输出清洗后的三档 GMV，作为后续《指标口径说明》的官方基线数字
    print("\n      清洗后各口径 GMV（写入口径文档的基线）:")
    print(f"        GMV-<｜hy_place▁holder▁no▁813｜> 含退款红冲 : {clean_total:,.2f}")
    print(f"        GMV-剔除退款红冲     : {float(df.loc[df['is_refund'] == 0, 'amount'].sum()):,.2f}")
    print(f"        GMV-仅商品且有效行   : "
          f"{float(df.loc[(df['is_refund'] == 0) & (df['is_product'] == 1), 'amount'].sum()):,.2f}")


def main() -> None:
    raw = read_raw()

    print("\n[2/5] 清洗")
    raw = rename_columns(raw)
    df, stats, removed_amt = clean(raw)
    for k, v in stats.items():
        print(f"      {k}: {v:,}")

    df = derive(df)
    df = reorder(df)
    write_outputs(df)
    verify(raw, df, removed_amt)

    print("\n=== 表示例 ===")
    print(df.head(8).to_string())
    print(f"\n完成：{len(df):,} 行 × {df.shape[1]} 列")


if __name__ == "__main__":
    main()
