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

from intent_parser import parse, Intent
from query_executor import execute, MetricsBundle
from report_builder import build_report


class AgentState(TypedDict):
    instruction: str
    anchor: Optional[str]
    intent: Optional[dict]
    bundle: Optional[dict]
    report: Optional[str]
    notes: list
    error: Optional[str]


def _resolve_anchor(state: AgentState) -> Optional[date]:
    a = state.get("anchor")
    if a:
        try:
            return date.fromisoformat(a)
        except Exception:
            pass
    return None


def _llm_plan(instruction: str, anchor: Optional[date]) -> Intent:
    """D8 接入：调用大模型解析自然语言意图。当前为占位，未启用 LLM_MODE 时不会被调用。"""
    raise NotImplementedError("LLM 解析通道将在 D8 接入（base_url + api_key）。")


def build_app(con: sqlite3.Connection):
    def _plan(state: AgentState):
        try:
            anchor = _resolve_anchor(state)
            if os.getenv("LLM_MODE") == "llm":
                try:
                    intent = _llm_plan(state["instruction"], anchor)
                    return {"intent": intent.model_dump(),
                            "notes": [intent.message + "（LLM 解析）"]}
                except Exception:
                    pass  # 回退规则通道
            intent = parse(state["instruction"], anchor)
            return {"intent": intent.model_dump(), "notes": [intent.message]}
        except Exception as e:
            return {"error": f"意图解析失败：{e}"}

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
        "notes": [], "intent": None, "bundle": None, "report": None, "error": None,
    }
    return app.invoke(init)
