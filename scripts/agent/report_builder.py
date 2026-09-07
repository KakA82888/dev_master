"""Markdown 报告生成器：将 MetricsBundle 渲染为日报/周报/月报。

- 纯模板化，无 LLM 依赖（结论来自指标与异常标注，不臆测原因）。
- 数值格式集中处理：金额 £、比率 %、环比带符号。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from query_executor import MetricsBundle

_TITLE = {"daily": "日", "weekly": "周", "monthly": "月"}


def _money(v) -> str:
    return f"£{v:,.2f}" if isinstance(v, (int, float)) else "—"


def _pct(v) -> str:
    return f"{v * 100:.2f}%" if isinstance(v, (int, float)) else "—"


def _chg(c) -> str:
    if not isinstance(c, (int, float)):
        return "—"
    sign = "+" if c >= 0 else ""
    return f"{sign}{c * 100:.2f}%"


def build_report(bundle: MetricsBundle, instruction: str) -> str:
    market = "全市场" if bundle.country is None else bundle.country
    title = _TITLE.get(bundle.report_type, "经营")
    cur, prev, ch = bundle.current, bundle.previous, bundle.change

    lines = [
        f"# {market} {bundle.start} ~ {bundle.end} 经营{title}报",
        "",
        f"> 指令：{instruction}",
        "",
        "## 一、核心经营指标",
        "",
        "| 指标 | 当期 | 环比 | 上期 |",
        "|---|---|---|---|",
        f"| GMV（有效商品） | {_money(cur['gmv'])} | {_chg(ch['gmv'])} | {_money(prev['gmv'])} |",
        f"| 有效订单数 | {cur['valid_orders']:,} | — | {prev['valid_orders']:,} |",
        f"| 全部订单数 | {cur['all_orders']:,} | — | {prev['all_orders']:,} |",
        f"| 客单价 AOV | {_money(cur['aov'])} | {_chg(ch['aov'])} | {_money(prev['aov'])} |",
        f"| 订单转化率 | {_pct(cur['conversion_rate'])} | {_chg(ch['conversion_rate'])} | {_pct(prev['conversion_rate'])} |",
        f"| 退款金额（绝对值） | {_money(cur['refund_amt_abs'])} | — | {_money(prev['refund_amt_abs'])} |",
        f"| 退款订单数 | {cur['refund_orders']:,} | — | {prev['refund_orders']:,} |",
        f"| 退款率·金额口径 | {_pct(cur['refund_rate_amount'])} | {_chg(ch['refund_rate_amount'])} | {_pct(prev['refund_rate_amount'])} |",
        f"| 退款率·订单数口径 | {_pct(cur['refund_rate_order'])} | {_chg(ch['refund_rate_order'])} | {_pct(prev['refund_rate_order'])} |",
        "",
    ]

    # 异常提示
    lines.append("## 二、异常波动提示")
    lines.append("")
    if bundle.anomalies:
        for a in bundle.anomalies:
            lines.append(f"- ⚠️ {a}")
    else:
        lines.append("- 本期未触发异常阈值。")
    lines.append("")

    # 逐日明细
    lines.append("## 三、逐日明细")
    lines.append("")
    lines.append("| 日期 | GMV | 有效订单 | 全部订单 | 退款金额 | 退款订单 |")
    lines.append("|---|---|---|---|---|---|")
    for d in bundle.daily:
        lines.append(
            f"| {d.order_date} | {_money(d.gmv)} | {d.valid_orders:,} | "
            f"{d.all_orders:,} | {_money(d.refund_amt_abs)} | {d.refund_orders:,} |"
        )
    lines.append("")

    lines.append("---")
    lines.append(
        f"> 数据来源：sales_detail（单一事实表）｜指标口径见《指标口径与数据字典 v1.0》"
        f"｜生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    return "\n".join(lines)
