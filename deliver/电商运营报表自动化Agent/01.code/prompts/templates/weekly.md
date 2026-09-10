{# 周报模板 · 自然周（周一~周日） · 与 report_builder.py 渲染结果一致 #}
# {{market}} {{start}} ~ {{end}} 经营周报

> 指令：{{instruction}}

## 一、核心经营指标（本周合计 vs 上周）

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

## 三、本周逐日明细

| 日期 | GMV | 有效订单 | 全部订单 | 退款金额 | 退款订单 |
|---|---|---|---|---|---|
{% for d in daily %}| {{d.order_date}} | {{d.gmv|money}} | {{d.valid_orders|int}} | {{d.all_orders|int}} | {{d.refund_amt_abs|money}} | {{d.refund_orders|int}} |
{% endfor %}

> 注：区间内无交易的日期以 0 补全并标注「无交易」，不删除该行。

---

> 数据来源：sales_detail（单一事实表）｜指标口径见《指标口径与数据字典 v1.0》｜生成时间：{{generated_at}}

<!--
占位符说明：
  market        市场名（country=None 时渲染为「全市场」）
  start / end   自然周周一 ~ 周日（闭区间）
  daily         逐日明细数组，元素字段：order_date/gmv/valid_orders/all_orders/refund_amt_abs/refund_orders
  current.*/previous.*/change.*  当期 / 上期 / 环比
  anomalies     异常标注列表（阈值表见 scripts/metrics/anomaly.py）
渲染实现：scripts/agent/report_builder.py（build_report）
-->
