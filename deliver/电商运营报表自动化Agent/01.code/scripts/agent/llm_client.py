"""LLM 通道：OpenAI 兼容大模型意图解析（D8 接入）。

职责边界（硬约束）：
- 仅做自然语言理解：把用户指令解析为结构化 Intent。
- 绝不生成/编造任何金额、销量等数字——数字一律由指标计算组件产出。
- 调用方（orchestrator._plan）必须先跑 guard 安全网关，LLM 只处理已放行的指令。

配置（.env）：LLM_BASE_URL / LLM_API_KEY / LLM_MODEL / LLM_TIMEOUT / LLM_MAX_RETRIES
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

# 注意：本模块不在导入时自动 load_dotenv，避免污染测试/其它进程的环境变量。
# 由入口（app/backend/main.py 或评测脚本）在使用前显式 load_dotenv。

# 确保同目录可裸导入 intent_parser（与 orchestrator 一致）
AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from openai import OpenAI  # noqa: E402

from intent_parser import ANCHOR, COUNTRY_MAP, Intent  # noqa: E402

SYSTEM_PROMPT = """你是电商运营报表系统的"自然语言理解"模块，只负责把用户指令解析成结构化查询意图，绝不生成或编造任何金额、销量等数字。

# 数据背景
- 数据集最新一天（"今天"）固定为 {anchor}，所有"昨日/上周/本月/今年"等相对词以此为准。
- 货币单位为 GBP（英镑），但你不负责金额计算。

# 输出格式
只输出一个 JSON 对象，不要任何解释、不要 markdown 代码块、不要 <think> 标签：
{{
  "report_type": "daily | weekly | monthly",
  "start": "YYYY-MM-DD",
  "end": "YYYY-MM-DD",
  "country": "数据集 Country 字段值 或 null（表示全部市场）",
  "need_clarify": false
}}

# 规则
1. 报告类型：指令含"日报"→daily；含"周报"→weekly；含"月报"→monthly。若同时出现类型词和具体日期（如"周报 11月22日"），类型词优先，并把该日期作为区间锚点。若都未指定，按区间跨度推断：跨度≤2天→daily；≤8天→weekly；否则→monthly。
2. 区间计算（start/end 为闭区间，包含 end 当天）：
   - daily：start=end=该天。
   - weekly：该天所在周一至周日（含该天）。
   - monthly：该天所在月份 1 号至月末最后一天。
   - 相对词："昨日"=anchor 前一天；"今天/今日"=anchor；"上周"=anchor 所在周的上一个完整周（周一~周日）；"本周"=anchor 所在周；"上月"=anchor 上个月整月；"本月"=anchor 所在月；"今年"=anchor 所在年 1-1 至 12-31；"去年"=去年全年。
   - 绝对日期：YYYY年M月D日 / YYYY-MM-DD / M月D日（年份取 anchor 年）等。
3. 市场（country）：将中文国名映射到数据集 Country 字段值。常见映射：
{country_block}
   指令含"全部/所有/总体/全球/整体/汇总/不分国家"或省略 → null（全市场）。
4. 信息不足或无法确定时把 need_clarify 设为 true。

严格按以上规则输出 JSON。"""


def _country_block() -> str:
    return "\n".join(f'   - "{zh}" → "{code}"' for zh, code in COUNTRY_MAP.items())


def _extract_json(text: str) -> dict:
    """从模型输出中提取第一个 JSON 对象（兼容带 <think> 或代码块的情况）。"""
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1 or e <= s:
        raise ValueError(f"模型未返回可用 JSON：{text[:200]!r}")
    return json.loads(text[s:e + 1])


def llm_parse_intent(instruction: str, anchor: date | None = None) -> Intent:
    """调用大模型解析意图，返回 Intent。任何异常都向上抛出，由编排层回退规则通道。"""
    anchor = anchor or ANCHOR
    base_url = os.getenv("LLM_BASE_URL")
    api_key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL")
    if not (base_url and api_key and model):
        raise RuntimeError("LLM 未配置（缺少 LLM_BASE_URL/LLM_API_KEY/LLM_MODEL）")
    timeout = float(os.getenv("LLM_TIMEOUT", "30"))
    max_retries = int(os.getenv("LLM_MAX_RETRIES", "3"))

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    sys_prompt = SYSTEM_PROMPT.format(anchor=anchor.isoformat(), country_block=_country_block())

    last_err: Exception | None = None
    for _ in range(max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": f"指令：{instruction}"},
                ],
                temperature=0,
                max_tokens=2048,
            )
            content = resp.choices[0].message.content or ""
            data = _extract_json(content)
            rt = str(data.get("report_type", "")).lower()
            if rt not in ("daily", "weekly", "monthly"):
                raise ValueError(f"report_type 非法：{rt!r}")
            start = str(data.get("start", ""))
            end = str(data.get("end", ""))
            date.fromisoformat(start)  # 格式校验
            date.fromisoformat(end)
            country = data.get("country") or None
            if country is not None:
                country = str(country)
            return Intent(
                report_type=rt,
                start=start,
                end=end,
                country=country,
                raw=instruction,
                need_clarify=bool(data.get("need_clarify", False)),
                message="LLM 已解析意图",
            )
        except Exception as ex:  # 重试；全部失败则抛出交由编排层回退
            last_err = ex
    raise RuntimeError(f"LLM 解析失败：{last_err}")
