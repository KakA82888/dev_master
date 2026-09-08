"""规则式自然语言指令解析器（无 LLM 依赖，可离线运行）。

输入：用户自然语言指令（如"生成昨日日报"、"上周英国周报"、"2010年11月22日到28日全部市场月报"）
输出：结构化 Intent（report_type / start / end / country / 是否需要澄清）

设计要点：
- 静态数据集以数据末尾为"今天"锚点（ANCHOR），使"昨日/上周"等相对词有确定含义。
- 报告类型：显式"日报/周报/月报"优先；未指定时按区间跨度推断。
- 市场：中文国名 → Country 代码映射；"全部/所有/总体" → None（全市场）。
- 日期：支持相对词、绝对年月日、中文区间，纯正则+datetime，不依赖不稳定的解析库。
- 安全：解析前置安全网关（guard.check），拦截注入/越权/越界/无效日期。
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from pydantic import BaseModel

# 数据集最大日期，作为相对日期的"今天"锚点（数据非实时，必须固定）
ANCHOR = date(2011, 12, 9)

# 中文市场名 → 数据集 Country 字段值（覆盖 43 国主要成员）
COUNTRY_MAP = {
    "英国": "United Kingdom", "德国": "Germany", "法国": "France",
    "爱尔兰": "EIRE", "荷兰": "Netherlands", "西班牙": "Spain",
    "瑞士": "Switzerland", "比利时": "Belgium", "葡萄牙": "Portugal",
    "澳大利亚": "Australia", "海峡群岛": "Channel Islands", "意大利": "Italy",
    "瑞典": "Sweden", "挪威": "Norway", "塞浦路斯": "Cyprus",
    "芬兰": "Finland", "奥地利": "Austria", "丹麦": "Denmark",
    "希腊": "Greece", "日本": "Japan", "美国": "USA",
    "波兰": "Poland", "阿联酋": "United Arab Emirates", "以色列": "Israel",
    "香港": "Hong Kong", "中国香港": "Hong Kong", "新加坡": "Singapore",
    "马耳他": "Malta", "加拿大": "Canada", "冰岛": "Iceland",
    "南非": "RSA", "立陶宛": "Lithuania", "巴林": "Bahrain",
    "巴西": "Brazil", "泰国": "Thailand", "韩国": "Korea",
    "欧共体": "European Community", "黎巴嫩": "Lebanon",
}
ALL_MARKETS = ["全部", "所有", "总体", "全球", "整体", "汇总", "不分国家", "不分地区"]


class InvalidDateError(ValueError):
    """指令中出现语法合法但语义不存在的日期（如 2011-02-29、2011年13月）。"""


class Intent(BaseModel):
    report_type: str          # daily | weekly | monthly
    start: str                # YYYY-MM-DD
    end: str                  # YYYY-MM-DD
    country: str | None       # Country 代码 或 None（全市场）
    raw: str
    need_clarify: bool = False
    message: str = ""
    blocked: str | None = None   # 被安全网关拦截时的原因码


# ---------- 基础日期工具 ----------
def week_range(d: date) -> tuple[date, date]:
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


def _mkdate(y: int, m: int, d: int) -> date:
    try:
        return date(y, m, d)
    except ValueError as ex:
        raise InvalidDateError(f"{y}-{m:02d}-{d:02d} 不是有效日期") from ex


def month_range(y: int, m: int) -> tuple[date, date]:
    if not 1 <= m <= 12:
        raise InvalidDateError(f"{y}年{m}月 不是有效月份")
    first = date(y, m, 1)
    nxt = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return first, nxt - timedelta(days=1)


def _prev_month(anchor: date) -> tuple[date, date]:
    return month_range(anchor.year - 1, 12) if anchor.month == 1 \
        else month_range(anchor.year, anchor.month - 1)


def _is_full_month(s: date, e: date) -> bool:
    return s.day == 1 and e == month_range(s.year, s.month)[1]


# ---------- 单日期解析 ----------
def _resolve_single_date(seg: str, anchor: date) -> date | None:
    """从片段中解析单个日期；无日期返回 None。含日号的绝对日期优先。"""
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})[日号]?", seg)
    if m:
        return _mkdate(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", seg)
    if m:
        return _mkdate(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{1,2})月(\d{1,2})[日号]", seg)
    if m:
        return _mkdate(anchor.year, int(m.group(1)), int(m.group(2)))
    # 省略"日/号"的口语写法，如"11月22"
    m = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})(?!\d)", seg)
    if m:
        return _mkdate(anchor.year, int(m.group(1)), int(m.group(2)))
    return None


def _has_explicit_day(seg: str) -> bool:
    """片段中是否含"带日号"的绝对日期（用于区分"2011年11月"与"2011年11月22日"）。"""
    return bool(
        re.search(r"\d{4}年\d{1,2}月\d{1,2}[日号]?", seg)
        or re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", seg)
        or re.search(r"\d{1,2}月\d{1,2}[日号]", seg)
    )


# ---------- 维度提取 ----------
def detect_report_type(text: str) -> str | None:
    # 仅识别连续关键词，避免"11月…日报"中分离的"月""报"误判
    if "周报" in text:
        return "weekly"
    if "月报" in text:
        return "monthly"
    if "日报" in text:
        return "daily"
    m = re.search(r"(日|周|月)报", text)
    if m:
        return {"日": "daily", "周": "weekly", "月": "monthly"}[m.group(1)]
    return None


def detect_country(text: str) -> str | None:
    for kw in ALL_MARKETS:
        if kw in text:
            return None  # 明确全市场
    for zh, code in COUNTRY_MAP.items():
        if zh in text:
            return code
    return None


def parse_date_range(text: str, rt: str | None, anchor: date) -> tuple[date, date]:
    # 0) 绝对日期（带日号）优先于整月规则，避免"2011年11月22日"被误判为整月
    if _has_explicit_day(text):
        sd = _resolve_single_date(text, anchor)
        if sd and not re.search(r"(到|至|~|—|–)", text):
            return (sd, sd)

    # 1) 显式区间：到 / 至 / ~ / —
    sep = re.search(r"(到|至|~|—|–)", text)
    if sep:
        s = _resolve_single_date(text[: sep.start()], anchor)
        e = _resolve_single_date(text[sep.end():], anchor)
        if s and not e:  # 右端仅给出"D日"或裸数字，借用左端年月
            right = text[sep.end():]
            m = re.search(r"(\d{1,2})[日号]", right)
            if m:
                e = _mkdate(s.year, s.month, int(m.group(1)))
            else:
                m = re.match(r"\s*(\d{1,2})\s*$", right)
                if m:
                    e = _mkdate(s.year, s.month, int(m.group(1)))
        if s and e:
            return (min(s, e), max(s, e))
    # 2) 整月：YYYY年MM月 或 YYYY-MM（非完整日期）
    m = re.search(r"(\d{4})年(\d{1,2})月", text)
    if m:
        return month_range(int(m.group(1)), int(m.group(2)))
    if re.search(r"\d{4}-\d{1,2}(?!-\d)", text):
        m = re.search(r"(\d{4})-(\d{1,2})", text)
        return month_range(int(m.group(1)), int(m.group(2)))
    # 3) 周相对词
    if re.search(r"上周|上一周|上礼拜", text):
        return week_range(anchor - timedelta(days=7))
    if re.search(r"本周|这周|这一周|这礼拜", text):
        return week_range(anchor)
    # 4) 月相对词
    if re.search(r"上月|上个月", text):
        return _prev_month(anchor)
    if re.search(r"本月|这个月|当月", text):
        return month_range(anchor.year, anchor.month)
    # 5) 日相对词
    if re.search(r"昨天|昨日|前一日|前一天", text):
        d = anchor - timedelta(days=1); return (d, d)
    if re.search(r"前天", text):
        d = anchor - timedelta(days=2); return (d, d)
    if re.search(r"今天|今日", text):
        return (anchor, anchor)
    # 6) 单绝对日
    sd = _resolve_single_date(text, anchor)
    if sd:
        return (sd, sd)
    # 7) 兜底（按报告类型推断区间）
    if rt == "weekly":
        return week_range(anchor - timedelta(days=7))
    if rt == "monthly":
        return _prev_month(anchor)
    d = anchor - timedelta(days=1)
    return (d, d)


def _expand_to_period(rt: str, s: date, e: date) -> tuple[date, date]:
    """显式报告类型 + 单日区间时，把单日扩展为该类型对应的完整周期。"""
    if (e - s).days != 0:
        return (s, e)
    if rt == "weekly":
        return week_range(s)
    if rt == "monthly":
        return month_range(s.year, s.month)
    return (s, e)


# ---------- 主入口 ----------
def parse(text: str, anchor: date | None = None) -> Intent:
    anchor = anchor or ANCHOR
    text = text.strip()
    rt = detect_report_type(text)
    country = detect_country(text)
    try:
        start, end = parse_date_range(text, rt, anchor)
    except InvalidDateError as ex:
        return Intent(
            report_type=rt or "daily", start=anchor.isoformat(), end=anchor.isoformat(),
            country=country, raw=text, need_clarify=True,
            message=f"指令中的日期无效：{ex}", blocked="invalid_date",
        )
    if rt is not None:
        start, end = _expand_to_period(rt, start, end)
    # 未指定报告类型时按区间跨度推断
    if rt is None:
        span = (end - start).days + 1
        if span == 1:
            rt = "daily"
        elif _is_full_month(start, end):
            rt = "monthly"
        else:
            rt = "weekly"
    msg = f"已解析为{ '全市场' if country is None else country }的{rt}报（{start}~{end}）"
    return Intent(
        report_type=rt, start=start.isoformat(), end=end.isoformat(),
        country=country, raw=text, need_clarify=False, message=msg,
    )


def parse_safe(text: str, anchor: date | None = None) -> Intent:
    """解析 + 安全网关。被拦截时返回 need_clarify=True 且 blocked=<原因码>。"""
    from scripts.agent.guard import check as guard_check  # 局部导入避免循环依赖

    ok, code, reason = guard_check(text)
    if not ok:
        a = anchor or ANCHOR
        return Intent(
            report_type="daily", start=a.isoformat(), end=a.isoformat(),
            country=None, raw=text.strip(), need_clarify=True,
            message=reason, blocked=code,
        )
    it = parse(text, anchor)
    if it.blocked is None:  # 未被无效日期拦截时，再做一次数据范围校验
        ok2, code2, reason2 = guard_check(it.raw, it.start, it.end)
        if not ok2:
            it.need_clarify = True
            it.blocked = code2
            it.message = reason2
    return it
