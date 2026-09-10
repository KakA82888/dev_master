{# 日报模板 · 与 scripts/agent/report_builder.py 渲染结果一致 #}
# {{market}} {{start}} 经营日报

> 指令：{{instruction}}

## 一、核心经营指标

| 指标 | 当期 | 环比 | 上期 |
|---|---|---|---|
| GMV（有效商品） | {{current.gmv|money}} | {{change.gmv|signed_pct}} | {{previous.gmv|money}} |
| 有效订单数 | {{current.valid_orders|int}} | — | {{previous.valid_orders|int}} |
| 全部订单数 | {{current.all_orders|int}} | — | {{previous.all_orders|int}} |
| 客单价 AOV | {{current.aov|money}} | {{change.aov|signed_pct}} | {{previous.aov|money}} |
| 订单转化率 | {{current.conversion_rate|pct}} | {{change.conversion_rate|signed_pct}} | {{previous.conversion_rate|pct}} |
| 退款金额（绝对值） | {{current.refund_amt_abs|money}} | — | {{previous.refund_amt_abs|money}} |
| 退款订单数 | {{current.refund_orders|int}} | — | {{previous.refund_orders|int}} |
| 退款率·金额口径 | {{current.refund_rate_amount|pct}} | {{change.refund_rate_amount|signed_pct}} | {{previous.refund_rate_amount|pct}} |
| 退款率·订单数口径 | {{current.refund_rate_order|pct}} | {{change.refund_rate_order|signed_pct}} | {{previous.refund_rate_order|pct}} |

## 二、异常波动提示

{% if anomalies %}
{% for a in anomalies %}- ⚠️ {{a}}
{% endfor %}
{% else %}- 本期未触发异常阈值。
{% endif %}

## 三、当日明细

| 日期 | GMV | 有效订单 | 全部订单 | 退款金额 | 退款订单 |
|---|---|---|---|---|---|
| {{start}} | {{current.gmv|money}} | {{current.valid_orders|int}} | {{current.all_orders|int}} | {{current.refund_amt_abs|money}} | {{current.refund_orders|int}} |

---

> 数据来源：sales_detail（单一事实表）｜指标口径见《指标口径与数据字典 v1.0》｜生成时间：{{generated_at}}

<!--
占位符说明：
  market        市场名（country=None 时渲染为「全市场」）
  start / end   区间（日报 start=end）
  instruction   用户原始指令
  current.*     当期指标；previous.* 上期指标；change.* 环比（小数，如 0.0821）
  anomalies     异常标注列表（阈值表见 scripts/metrics/anomaly.py）
  generated_at  生成时间 YYYY-MM-DD HH:MM
过滤器：money=£千分位两位小数；pct=百分比两位；signed_pct=带符号百分比；int=千分位整数
渲染实现：scripts/agent/report_builder.py（build_report）
-->
