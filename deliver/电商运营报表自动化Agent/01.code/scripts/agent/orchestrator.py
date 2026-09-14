"""智能体编排（LangGraph）：自然语言指令 → 指标包 → Markdown 报告。

状态机：plan（意图解析）→ execute（取数算指标）→ reflect（校验与异常汇总）→ build（报告生成）。

双通道设计：
- 规则通道（默认）：intent_parser 关键词+日期解析，零 LLM 依赖，保证无 Key 也能端到端跑通。
- LLM 通道（D8 接入）：设置环境变量 LLM_MODE=llm 且配置了 api_key 时优先调用大模型解析；
  失败或禁用时自动回退规则通道，不影响功能可用性。
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date
from typing import Optional, TypedDict

from langgraph.graph import StateGraph, START, END

from intent_parser import parse, parse_safe, nth_week_range, Intent, COUNTRY_MAP
from query_executor import execute, MetricsBundle
from report_builder import build_report
from llm_client import llm_parse_intent
from guard import check_range as guard_check_range


class AgentState(TypedDict):
    instruction: str
    anchor: Optional[str]
    intent: Optional[dict]
    bundle: Optional[dict]
    report: Optional[str]
    notes: list
    error: Optional[str]
    error_code: Optional[str]


# LLM 通道可接受的市场白名单 = 提示词中给出的中文国名映射值集合。
# LLM 若返回白名单外的市场名（幻觉/拼写漂移），SQL 过滤将命中 0 行，
# 会静默产出「空报告」，故必须在编排层拦截并回退规则通道。
_VALID_COUNTRIES = set(COUNTRY_MAP.values())


def _validate_llm_intent(intent: Intent) -> Optional[str]:
    """对 LLM 解析结果做确定性校验；返回不通过原因，None 表示通过。"""
    if intent.country is not None and intent.country not in _VALID_COUNTRIES:
        return f"市场「{intent.country}」不在支持列表内"
    ok, _code, msg = guard_check_range(intent.start, intent.end)
    if not ok:
        return f"日期区间未通过校验：{msg}"
    return None


def _resolve_anchor(state: AgentState) -> Optional[date]:
    a = state.get("anchor")
    if a:
        try:
            return date.fromisoformat(a)
        except Exception:
            pass
    return None


def _llm_plan(instruction: str, anchor: Optional[date]) -> Intent:
    """D8 接入：调用大模型解析自然语言意图（LLM_MODE=llm 且已配置 Key 时由 _plan 调用）。"""
    return llm_parse_intent(instruction, anchor)


def build_app(con: sqlite3.Connection):
    def _plan(state: AgentState):
        try:
            anchor = _resolve_anchor(state)
            # 安全网关始终优先（确定性拦截注入/越权/伪造/越界/SQLi）
            safe = parse_safe(state["instruction"], anchor)
            if safe.need_clarify:
                # 被安全网关拦截：不出报，直接把原因与原因码返回给调用方
                # （原因码供上层区分「安全拦截」与「技术故障」，前端据此给出明确提示）
                return {"error": safe.message, "error_code": safe.blocked or "blocked",
                        "intent": safe.model_dump(), "notes": [safe.message]}
            # 网关放行后再选通道
            if os.getenv("LLM_MODE") == "llm":
                try:
                    intent = _llm_plan(state["instruction"], anchor)
                    # LLM 结果必须再过一次确定性校验：模型可能幻觉出数据范围外的日期，
                    # 或返回支持列表外的市场名（会静默产出 GMV=0 的空报告）。
                    invalid = _validate_llm_intent(intent)
                    if invalid:
                        return {"intent": safe.model_dump(),
                                "notes": [safe.message,
                                          f"LLM 解析结果未通过校验（{invalid}），已回退规则通道"]}
                    # 确定性纠偏：「X月第N周」易被 LLM 算成"1日所在自然周"（跨到上月），
                    # 此类句式由规则解析精确给出该月内第 N 个自然周（不跨月）。
                    ov = nth_week_range(state["instruction"], anchor)
                    if ov:
                        s, e = ov
                        fixed = Intent(
                            report_type=intent.report_type or "weekly",
                            start=s.isoformat(), end=e.isoformat(),
                            country=intent.country, raw=state["instruction"],
                            message=f"已解析为{ '全市场' if intent.country is None else intent.country }的{intent.report_type or 'weekly'}报（{s}~{e}）",
                        )
                        return {"intent": fixed.model_dump(),
                                "notes": [fixed.message + "（LLM 解析 + 规则纠偏）"]}
                    return {"intent": intent.model_dump(),
                            "notes": [intent.message + "（LLM 解析）"]}
                except Exception as e:
                    # LLM 不可用/失败 → 回退规则通道，保证可用性。
                    # 注意：回退说明必须随返回值一起提交，不能只 mutate state["notes"]
                    # （返回值中的 notes 会覆盖 state 上的就地修改，导致回退事实丢失）。
                    return {"intent": safe.model_dump(),
                            "notes": [safe.message, f"LLM 解析失败，已回退规则通道：{e}"]}
            return {"intent": safe.model_dump(), "notes": [safe.message]}
        except Exception as e:
            return {"error": f"意图解析失败：{e}", "error_code": "internal_error"}

    def _execute(state: AgentState):
        if state.get("error"):
            return {}
        intent = Intent(**state["intent"])
        bundle = execute(intent, con)
        return {"bundle": bundle.model_dump()}

    def _reflect(state: AgentState):
        if state.get("error"):
            return {}
        notes = list(state.get("notes", []))
        b = state["bundle"]
        if b["current"]["gmv"] == 0:
            notes.append("⚠️ 区间内无有效商品销售数据（GMV=0），请确认日期或市场是否正确。")
        if b["anomalies"]:
            notes.append("异常波动：" + "；".join(b["anomalies"]))
        return {"notes": notes}

    def _build(state: AgentState):
        if state.get("error"):
            return {}
        bundle = MetricsBundle(**state["bundle"])
        return {"report": build_report(bundle, state["instruction"])}

    g = StateGraph(AgentState)
    g.add_node("plan", _plan)
    g.add_node("execute", _execute)
    g.add_node("reflect", _reflect)
    g.add_node("build", _build)
    g.add_edge(START, "plan")
    g.add_edge("plan", "execute")
    g.add_edge("execute", "reflect")
    g.add_edge("reflect", "build")
    g.add_edge("build", END)
    return g.compile()


def run(instruction: str, con: sqlite3.Connection, anchor: Optional[date] = None) -> dict:
    """端到端执行：返回含 intent / bundle / report / notes / error 的最终状态。"""
    app = build_app(con)
    init: AgentState = {
        "instruction": instruction,
        "anchor": anchor.isoformat() if anchor else None,
        "notes": [], "intent": None, "bundle": None, "report": None,
        "error": None, "error_code": None,
    }
    return app.invoke(init)
