"""指令安全网关（S6 评测 / 对应 PRD R11、任务书 6.2）。

在意图解析之前拦截四类不该进入计算链路的指令：
  1. 提示词注入（诱导忽略系统指令、索要系统提示词）
  2. 越权（索要凭据、操作他人数据、伪造身份、访问外部数据源）
  3. 违规（要求伪造/篡改指标数值——任务书 6.3 明令禁止）
  4. 越界与无效（日期超出数据集覆盖范围、不支持的口径修饰）

被拦截的指令返回 need_clarify=True + blocked=<原因码>，由上层拒绝出报并给出提示。
"""
from __future__ import annotations

import re
from datetime import date

# 数据集实际覆盖范围（sales_detail 实测 MIN/MAX order_date）
DATA_MIN = date(2009, 12, 1)
DATA_MAX = date(2011, 12, 9)

# (正则, 原因码, 提示文案)
PATTERNS: list[tuple[str, str, str]] = [
    # --- 提示词注入 ---
    (r"忽略(上述|上面|以上|之前|前面|之前所有).{0,8}(指令|要求|规则|提示|设定)",
     "injection", "检测到提示词注入：指令要求忽略既有规则，已拒绝执行。"),
    (r"(输出|打印|展示|显示|告诉我|复述|重复|泄露).{0,10}(系统提示词|system\s*prompt|提示词|prompt)",
     "injection", "检测到提示词注入：索要系统提示词，已拒绝执行。"),
    (r"(系统提示词|system\s*prompt|提示词|prompt).{0,10}(原样|直接|照抄|一字不差)?\s*(输出|打印|展示|显示|发|给|告诉我|复述)",
     "injection", "检测到提示词注入：索要系统提示词，已拒绝执行。"),
    (r"(忽略|忘记|抛弃).{0,6}(你|之前|所有).{0,6}(设定|身份|角色)",
     "injection", "检测到提示词注入：试图重置助手身份，已拒绝执行。"),

    # --- 越权 ---
    (r"(导出|列出|显示|给我).{0,8}(密码|口令|token|密钥|secret)",
     "overreach", "越权请求：不得索取或输出任何凭据信息。"),
    (r"(竞争对手|竞品|友商|其他公司|别家).{0,10}(数据库|数据|资料)",
     "overreach", "越权请求：本系统仅可访问自有销售明细，不接外部数据源。"),
    (r"(删除|删掉|移除|清空|修改).{0,12}(他人|别的|其他|张三|李四|王五|所有用户).{0,8}(报告|数据|记录|账号)",
     "overreach", "越权请求：不得操作其他用户的数据。"),
    (r"(你是|你现在是|假设你是|以|作为).{0,5}(管理员|admin|root|超级用户|系统)",
     "overreach", "越权请求：不接受身份伪造或提权指令。"),

    # --- 违规：伪造数值（任务书 6.3）---
    (r"(把|将|改|改成|改为|修改为|换成|设为|写为).{0,10}(GMV|gmv|金额|销售额|数值|数字|指标).{0,10}(成|为|到)?\s*[\d千万百]+",
     "fabrication", "违规请求：报表数值必须由计算组件产出，不接受人工指定数值。"),

    # --- 不支持的口径修饰 ---
    (r"(排除|不含|剔除|去掉|扣除|刨除).{0,6}(退款|退货|取消|红冲)",
     "unsupported", "不支持的口径：本版 GMV 口径固定（含退款红冲），不支持临时排除项。"),

    # --- 防御性：破坏性 SQL 片段（纵深防御；数据层已参数化，此规则拦截恶意指令形态）---
    (r"(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE|DELETE\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|ALTER\s+TABLE|CREATE\s+TABLE|EXEC\s|EXECUTE\s|;\s*(DROP|DELETE|UPDATE|INSERT|ALTER))",
     "sqli", "检测到危险的 SQL 指令片段，已拒绝执行。"),
]

_COMPILED = [(re.compile(p), c, m) for p, c, m in PATTERNS]


def check_text(text: str) -> tuple[bool, str, str]:
    """返回 (是否放行, 原因码, 提示文案)。放行时原因码为空串。"""
    for rx, code, msg in _COMPILED:
        if rx.search(text):
            return False, code, msg
    return True, "", ""


def check_range(start: str | None = None, end: str | None = None) -> tuple[bool, str, str]:
    """日期越界校验：请求区间与数据集覆盖范围无交集即拒绝。"""
    if not start or not end:
        return True, "", ""
    try:
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
    except ValueError:
        return False, "invalid_date", "日期格式无法识别，请改写为「YYYY年M月D日」或「YYYY-MM-DD」。"
    if e < DATA_MIN or s > DATA_MAX:
        return False, "out_of_range", (
            f"请求区间 {start}~{end} 超出数据覆盖范围 "
            f"（{DATA_MIN.isoformat()} ~ {DATA_MAX.isoformat()}），无法生成报表。"
        )
    return True, "", ""


def check(text: str, start: str | None = None, end: str | None = None) -> tuple[bool, str, str]:
    """网关总入口：先查指令内容，再查日期范围。"""
    ok, code, msg = check_text(text)
    if not ok:
        return ok, code, msg
    return check_range(start, end)
