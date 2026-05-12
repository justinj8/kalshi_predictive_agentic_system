"""ResearchAgent — iteratively gathers evidence via tools.

Tool-using Sonnet agent that searches news, web, orderbook, history, related
markets, technicals, base rates, and recalled lessons. Terminates by calling
the `submit_evidence` tool with a structured EvidencePack.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger
from src.orchestrator.state_models import (
    EvidencePack,
    LessonRef,
    MarketAnalysis,
    TradingState,
)
from src.agents.agentic.anthropic_client import run_agent
from src.agents.agentic.tools.registry import build_tool_list, dispatch
from config.settings import settings

logger = get_logger(__name__)


SYSTEM_PROMPT = """You are a senior quantitative researcher analyzing a single Kalshi prediction market.

Your job: assemble a rigorous, evidence-backed pack that downstream agents will use to make
a trading decision. You are NOT making the trading call yourself — you are the analyst.

Process:
1. Decide which tools to invoke. Be efficient: each call costs latency.
2. Look for the EDGE: a gap between your best probability estimate and the market-implied price.
3. Cross-check qualitative news with quantitative signals (technicals, base rates, orderbook).
4. Consider what could make you wrong (the bear case is as important as the bull case).
5. When you have enough, call `submit_evidence` ONCE with the full structured pack.

Quality bar:
- Bull and bear case must each have >= 2 substantive points.
- Always populate `market_implied_pct` from the YES ask price.
- If you cite news/web findings, include source + 1-line summary.
- If you cannot establish edge, say so honestly via low `edge_estimate_pct` and `confidence_in_evidence`.

You have at most {max_iters} tool-use rounds before you MUST submit. Use them wisely.
"""


class ResearchAgent:
    def __init__(self) -> None:
        self.model = settings.specialist_model
        self.max_iterations = settings.max_research_iterations
        self.max_tokens = settings.research_max_tokens

    def run(
        self,
        market_analysis: MarketAnalysis,
        recalled_lessons: Optional[List[LessonRef]] = None,
    ) -> EvidencePack:
        market = market_analysis.market
        recalled_lessons = recalled_lessons or []

        # Context summary the model sees up front.
        opener = self._build_opener(market_analysis, recalled_lessons)

        tool_names = [
            "search_news",
            "get_market_orderbook",
            "get_market_history",
            "get_related_markets",
            "calculate_technical_indicators",
            "get_historical_base_rate",
            "recall_lessons",
            "submit_evidence",
        ]
        tools = build_tool_list(*tool_names, include_web_search=settings.enable_web_search)

        system = SYSTEM_PROMPT.format(max_iters=self.max_iterations)

        result = run_agent(
            model=self.model,
            system=system,
            messages=[{"role": "user", "content": opener}],
            tools=tools,
            tool_executor=dispatch,
            final_tool_name="submit_evidence",
            max_tokens=self.max_tokens,
            max_iterations=self.max_iterations,
            temperature=0.5,
        )

        pack = self._build_pack_from_result(result, market_analysis)
        logger.info(
            f"ResearchAgent: {pack.iterations_used} iters, {pack.tool_calls_used} tool calls, "
            f"edge={pack.edge_estimate_pct}, conf={pack.confidence_in_evidence}"
        )
        return pack

    def _build_opener(
        self,
        ma: MarketAnalysis,
        lessons: List[LessonRef],
    ) -> str:
        m = ma.market
        yes_mid = (m.yes_bid + m.yes_ask) / 2 if (m.yes_bid + m.yes_ask) else 0.0
        implied_pct = yes_mid * 100

        lessons_block = ""
        if lessons:
            bits = []
            for l in lessons[:5]:
                bits.append(f"- [{l.lesson_type} sim={l.similarity:.2f}] {l.snippet[:200]}")
            lessons_block = "\n\nRelevant lessons from past trades:\n" + "\n".join(bits)

        return (
            f"Analyze Kalshi market `{m.ticker}`.\n\n"
            f"Question: {m.title}\n"
            f"Category: {m.category}\n"
            f"YES bid/ask: ${m.yes_bid:.2f} / ${m.yes_ask:.2f}  (mid={yes_mid:.2f}, implied={implied_pct:.1f}%)\n"
            f"NO  bid/ask: ${m.no_bid:.2f} / ${m.no_ask:.2f}\n"
            f"24h volume: ${m.volume_24h:,.0f}   Open interest: ${m.open_interest:,.0f}\n"
            f"Close date: {m.close_date}\n"
            f"Related tickers (pre-scouted): {[r.get('ticker') for r in ma.related_tickers][:5]}\n"
            f"{lessons_block}\n\n"
            "Use your tools to gather evidence, then call `submit_evidence` with the structured pack."
        )

    def _build_pack_from_result(
        self,
        result: Any,
        ma: MarketAnalysis,
    ) -> EvidencePack:
        m = ma.market
        implied_pct = ((m.yes_bid + m.yes_ask) / 2) * 100 if (m.yes_bid + m.yes_ask) else 0.0

        if result.final_tool_use is None:
            # Loop truncated without final tool — synthesize a minimal pack so the
            # pipeline doesn't crash. Mark low confidence.
            logger.warning(f"ResearchAgent truncated for {m.ticker}; building fallback pack.")
            return EvidencePack(
                ticker=m.ticker,
                summary=(result.text or "No evidence synthesized.")[:600],
                bull_case_points=["(insufficient research)"],
                bear_case_points=["(insufficient research)"],
                market_implied_pct=implied_pct,
                confidence_in_evidence=0.1,
                iterations_used=result.iterations,
                tool_calls_used=len(result.tool_calls),
            )

        payload: Dict[str, Any] = result.final_tool_use.get("input", {}) or {}
        # Coerce / sanitize known fields.
        return EvidencePack(
            ticker=m.ticker,
            summary=str(payload.get("summary", ""))[:2000],
            bull_case_points=[str(x) for x in (payload.get("bull_case_points") or [])][:10],
            bear_case_points=[str(x) for x in (payload.get("bear_case_points") or [])][:10],
            base_rate_pct=_safe_float(payload.get("base_rate_pct")),
            market_implied_pct=_safe_float(payload.get("market_implied_pct"), default=implied_pct),
            edge_estimate_pct=_safe_float(payload.get("edge_estimate_pct")),
            catalysts=[str(x) for x in (payload.get("catalysts") or [])][:10],
            risk_flags=[str(x) for x in (payload.get("risk_flags") or [])][:10],
            news_highlights=list(payload.get("news_highlights") or [])[:10],
            web_findings=list(payload.get("web_findings") or [])[:10],
            technical_summary=dict(payload.get("technical_summary") or {}),
            related_markets=list(payload.get("related_markets") or [])[:10],
            confidence_in_evidence=max(
                0.0,
                min(1.0, _safe_float(payload.get("confidence_in_evidence"), default=0.5) or 0.5),
            ),
            iterations_used=result.iterations,
            tool_calls_used=len(result.tool_calls),
        )


def _safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# Module-level singleton.
research_agent = ResearchAgent()
