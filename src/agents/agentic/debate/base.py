"""Shared helpers for Bull / Bear / Red-Team debate agents."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger
from src.orchestrator.state_models import DebateTurn, EvidencePack, LessonRef
from src.agents.agentic.anthropic_client import run_agent
from src.agents.agentic.tools.registry import build_tool_list, dispatch
from config.settings import settings

logger = get_logger(__name__)


def _evidence_to_text(pack: EvidencePack) -> str:
    bits = [
        f"Ticker: {pack.ticker}",
        f"Summary: {pack.summary}",
        f"Market-implied: {pack.market_implied_pct}%",
        f"Base rate: {pack.base_rate_pct}%",
        f"Estimated edge: {pack.edge_estimate_pct}%",
        f"Researcher confidence in evidence: {pack.confidence_in_evidence:.2f}",
        "",
        "Bull case points:",
        *[f"  - {p}" for p in pack.bull_case_points],
        "Bear case points:",
        *[f"  - {p}" for p in pack.bear_case_points],
        "Catalysts: " + "; ".join(pack.catalysts),
        "Risk flags: " + "; ".join(pack.risk_flags),
    ]
    if pack.news_highlights:
        bits.append("News highlights:")
        for n in pack.news_highlights[:5]:
            bits.append(f"  - {n}")
    return "\n".join(bits)


def _parse_json_block(text: str) -> Optional[Dict[str, Any]]:
    """Pull the first JSON object out of a model response."""
    if not text:
        return None
    # Try fenced ```json first.
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not m:
        m = re.search(r"```\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not m:
        # Greedy brace match as last resort.
        m = re.search(r"(\{.*\})", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def run_debate_role(
    *,
    role: str,
    system_prompt: str,
    pack: EvidencePack,
    recalled_lessons: Optional[List[LessonRef]] = None,
    extra_tools: Optional[List[str]] = None,
    max_tokens: int = None,
) -> DebateTurn:
    """Run one debate agent and parse a structured DebateTurn out of it."""
    max_tokens = max_tokens or settings.debate_max_tokens

    lessons_block = ""
    if recalled_lessons:
        lines = []
        for l in recalled_lessons[:5]:
            lines.append(f"- [{l.lesson_type} sim={l.similarity:.2f}] {l.snippet[:200]}")
        lessons_block = "\n\nRELEVANT PAST LESSONS:\n" + "\n".join(lines)

    user = (
        f"EVIDENCE PACK:\n{_evidence_to_text(pack)}{lessons_block}\n\n"
        "Write your argument, then end your response with a JSON object on its own line, "
        "wrapped in ```json fences, with this exact schema:\n\n"
        "```json\n"
        "{\n"
        '  "stance": "LONG" | "SHORT" | "NO_TRADE" | "BLOCK" | "PROCEED",\n'
        '  "probability_estimate": <0..1>,\n'
        '  "argument": "<one paragraph>",\n'
        '  "key_points": ["...", "..."],\n'
        '  "counters": ["...", "..."]\n'
        "}\n"
        "```\n"
    )

    tools = None
    if extra_tools:
        tools = build_tool_list(*extra_tools, include_web_search=False)

    result = run_agent(
        model=settings.specialist_model,
        system=system_prompt,
        messages=[{"role": "user", "content": user}],
        tools=tools,
        tool_executor=dispatch if tools else None,
        final_tool_name=None,
        max_tokens=max_tokens,
        max_iterations=3 if tools else 1,
        temperature=0.6,
    )

    parsed = _parse_json_block(result.text) or {}
    stance = str(parsed.get("stance", "NO_TRADE")).upper()
    if stance not in {"LONG", "SHORT", "NO_TRADE", "BLOCK", "PROCEED"}:
        stance = "NO_TRADE"

    prob = parsed.get("probability_estimate")
    try:
        prob_f = float(prob)
        prob_f = max(0.0, min(1.0, prob_f))
    except (TypeError, ValueError):
        prob_f = 0.5

    return DebateTurn(
        role=role,  # type: ignore[arg-type]
        stance=stance,  # type: ignore[arg-type]
        probability_estimate=prob_f,
        argument=str(parsed.get("argument", result.text))[:2000],
        key_points=[str(x) for x in (parsed.get("key_points") or [])][:8],
        counters=[str(x) for x in (parsed.get("counters") or [])][:8],
    )
