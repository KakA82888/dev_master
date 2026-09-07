"""异常波动预警（阈值表驱动，集中可配）。

阈值对齐《指标口径与数据字典 v1.0》第 4 节建议值。
detect() 只输出"数值 + 维度归属"的标注，不臆测原因（任务书 6.3 要求）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# 阈值表（集中管理，后续可一键调整）
THRESHOLDS = {
    "gmv_significant": 0.20,   # GMV 显著波动 环比 ±20%
    "gmv_major": 0.50,         # GMV 重大异常 环比 ±50%
    "aov_change": 0.15,        # 客单价异动 环比 ±15%
    "conversion_drop_pp": 5.0, # 订单转化率绝对下滑 ≥5 个百分点
    "refund_amount_rate_daily": 0.10,  # 退款金额率单日 ≥10%
    "refund_rise_pp": 5.0,     # 退款率环比上升 ≥5 个百分点
}


def detect(cur: dict, prev: dict | None = None) -> list[str]:
    """根据当期与上一期指标字典，返回异常标注列表。"""
    flags: list[str] = []
    if prev and prev.get("gmv"):
        g = (cur["gmv"] - prev["gmv"]) / prev["gmv"]
        if abs(g) >= THRESHOLDS["gmv_major"]:
            flags.append("GMV 重大异常（环比 ±50%）")
        elif abs(g) >= THRESHOLDS["gmv_significant"]:
            flags.append("GMV 显著波动（环比 ±20%）")

        if cur.get("aov") and prev.get("aov"):
            a = (cur["aov"] - prev["aov"]) / prev["aov"]
            if abs(a) >= THRESHOLDS["aov_change"]:
                flags.append("客单价异动（环比 ±15%）")

        if cur.get("conversion_rate") is not None and prev.get("conversion_rate") is not None:
            d = (cur["conversion_rate"] - prev["conversion_rate"]) * 100
            if d <= -THRESHOLDS["conversion_drop_pp"]:
                flags.append("转化下滑（环比 ≤ -5pp）")

        if cur.get("refund_rate_amount") is not None and prev.get("refund_rate_amount") is not None:
            d = (cur["refund_rate_amount"] - prev["refund_rate_amount"]) * 100
            if d >= THRESHOLDS["refund_rise_pp"]:
                flags.append("退款异常（金额率环比 ≥ +5pp）")

    # 单日退款金额率绝对阈值（不依赖上期）
    if cur.get("refund_rate_amount") is not None and cur["refund_rate_amount"] >= THRESHOLDS["refund_amount_rate_daily"]:
        flags.append("退款异常（金额率 ≥10%）")

    return flags
