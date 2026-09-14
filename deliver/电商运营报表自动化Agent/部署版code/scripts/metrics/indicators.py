"""指标核心定义（pandas 纯函数，单一事实口径来源）。

设计原则：
- 每个函数只接受一行已加载的 DataFrame（可来自某日 / 某周 / 某市场切片）。
- 所有金额与计数口径严格对齐《指标口径与数据字典 v1.0》第 3 节。
- 不在此处做任何 IO，便于双轨对账与单测。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd

# 有效商品行过滤条件（GMV / 有效订单 / 客单价 的统一定义）
VALID_MASK = "is_refund = 0 AND is_product = 1"


def _valid(df: pd.DataFrame) -> pd.DataFrame:
    return df.loc[(df["is_refund"] == 0) & (df["is_product"] == 1)]


def gmv(df: pd.DataFrame) -> float:
    """口径 C：仅有效商品行金额之和（GBP）。"""
    return float(_valid(df)["amount"].sum())


def valid_order_count(df: pd.DataFrame) -> int:
    """有效订单数：有效商品行去重 order_id 数。"""
    return int(_valid(df)["order_id"].nunique())


def all_order_count(df: pd.DataFrame) -> int:
    """全部生成订单数：区间内去重 order_id 数（含退款/取消单）。"""
    return int(df["order_id"].nunique())


def aov(df: pd.DataFrame):
    """客单价 = GMV / 有效订单数；分母为 0 返回 None。"""
    g = gmv(df)
    n = valid_order_count(df)
    return None if n == 0 else g / n


def conversion_rate(df: pd.DataFrame):
    """订单转化率（重定义）= 有效订单数 / 全部生成订单数；分母 0 返回 None。"""
    v = valid_order_count(df)
    a = all_order_count(df)
    return None if a == 0 else v / a


def refund_amount_abs(df: pd.DataFrame) -> float:
    """退款金额 = SUM(|amount|) where is_refund=1（逐笔取绝对值后求和，GBP）。

    注意与「退款净额 SUM(amount)」（带符号，仅用于 GMV 三口径闭合）区分：
    全期两者相差 747.14 GBP（存在 1 行正额退款记录），详见《01_指标口径与数据字典》§3。
    本口径**按天可加**，是 daily_agg 物化表与区间累加口径成立的前提。
    """
    return float(df.loc[df["is_refund"] == 1, "amount"].abs().sum())


def refund_order_count(df: pd.DataFrame) -> int:
    """退款订单数：退款行去重 order_id 数。"""
    return int(df.loc[df["is_refund"] == 1, "order_id"].nunique())


def refund_rate_amount(df: pd.DataFrame):
    """退款率·金额口径 = |退款金额| / GMV；GMV 0 返回 None。"""
    g = gmv(df)
    r = refund_amount_abs(df)
    return None if g == 0 else r / g


def refund_rate_order(df: pd.DataFrame):
    """退款率·订单数口径 = 退款订单数 / 全部订单数；分母 0 返回 None。"""
    a = all_order_count(df)
    r = refund_order_count(df)
    return None if a == 0 else r / a


def period_metrics(df: pd.DataFrame) -> dict:
    """返回某切片下的全量指标字典（双轨对账与报表共用）。"""
    return {
        "gmv": gmv(df),
        "valid_orders": valid_order_count(df),
        "all_orders": all_order_count(df),
        "aov": aov(df),
        "conversion_rate": conversion_rate(df),
        "refund_amt_abs": refund_amount_abs(df),
        "refund_orders": refund_order_count(df),
        "refund_rate_amount": refund_rate_amount(df),
        "refund_rate_order": refund_rate_order(df),
    }
