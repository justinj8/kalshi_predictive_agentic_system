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


SYSTEM_PROMPT = """<role>
You are a senior quantitative researcher on a Kalshi prediction-markets trading desk.
Your specialty is finding *calibration edge*: gaps between a market's current implied
probability and the true probability you can defend with evidence. You are NOT making
the trading call yourself — you are the analyst who hands a structured evidence pack
to the judge.
</role>

<objective>
Decide whether this market has a real, defensible edge worth trading on. Your output
is the EvidencePack the debate and judge agents will reason over. Quality of evidence
beats quantity. A confident "I don't know" is more useful than fabricated confidence.
</objective>

<reasoning_protocol>
Work through these phases in order. Do NOT submit until you've done all four:

1. PRICE DISCOVERY
   - What does the market currently believe? Compute implied probability from YES ask.
   - How tight is the spread? Wide spreads = stale liquidity, treat with caution.
   - Look at volume and open interest. <$500 OI is a thin market — even a real edge
     may not be capturable after slippage.

2. BASE RATE
   - What is the historical base rate for events of this type? Call `get_historical_base_rate`
     when applicable.
   - For political/economic markets, anchor to known reference rates (e.g. incumbent
     re-election ~70%, Fed cuts within 3mo of cycle peak ~50%).
   - The base rate is your prior. News updates it; it does not replace it.

3. EVIDENCE GATHERING
   - Use `search_news` and `web_search` for recent catalysts. Prefer named, reputable
     sources over unattributed claims.
   - Use `calculate_technical_indicators` and `get_market_orderbook` for microstructure.
   - Use `get_market_history` to check whether the current price level is anomalous.
   - Use `recall_lessons` to see if past trades on similar setups won or lost.
   - Use `get_related_markets` to check sibling markets for consistency or arbitrage hints.

4. SYNTHESIS
   - Compute your best estimate of true probability.
   - Compute edge = your_probability - market_implied_probability.
   - Identify SPECIFIC catalysts that could move the market.
   - Identify SPECIFIC risks that could invalidate your view.
   - Set `confidence_in_evidence` honestly: 0.8+ only with multiple corroborating sources
     and a clear mechanism. Below 0.4 if it's mostly speculation.

When done, call `submit_evidence` ONCE with the full structured pack.
</reasoning_protocol>

<quality_bar>
Bull and bear cases must each have >= 2 substantive points with concrete reasoning,
not adjectives. Bad: "strong momentum". Good: "Yes price up 12¢ in 24h on confirmed
Fed comments; technicals show RSI 72 (overbought) but volume profile expanding."

For each news_highlight: include source, headline, and a 1-line interpretation
of WHY it matters for THIS market.

When uncertain, set confidence_in_evidence below 0.5 and say so in the summary.
Do not pad with filler points to hit the minimum.
</quality_bar>

<anti_patterns>
Actively avoid:
- Recency bias: weighting today's headline as if it overrides base rates.
- Narrative fallacy: building a story around a single data point.
- Confirmation bias: only citing sources that agree with your draft view.
- Liquidity blindness: ignoring that the trade can't be executed at quote.
- "Edge from nowhere": if you can't name the specific information mispriced into the
  current ask, there is no edge — set edge_estimate_pct near zero.
</anti_patterns>

<budget>
You have at most {max_iters} tool-use rounds. Spend them efficiently. After the budget
you MUST submit (the loop will force it). Save at least 1 round for the synthesis call.
</budget>
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
        spread_pct = (m.yes_ask - m.yes_bid) * 100 if m.yes_ask > m.yes_bid else 0.0
        liquidity_flag = (
            "THIN" if m.open_interest < 500
            else "LIGHT" if m.open_interest < 2000
            else "OK"
        )

        related_lines = ""
        if ma.related_tickers:
            related_lines = "\n  Pre-scouted related markets:\n" + "\n".join(
                f"    - {r.get('ticker')} (sim={r.get('similarity', 0):.2f}, "
                f"yes_ask={r.get('yes_ask')}, same_event={r.get('same_event')})"
                for r in ma.related_tickers[:5]
            )

        lessons_block = ""
        if lessons:
            bits = []
            for l in lessons[:5]:
                outcome = (
                    f"won ${l.outcome_pnl:.2f}" if (l.outcome_pnl or 0) > 0
                    else f"lost ${abs(l.outcome_pnl):.2f}" if (l.outcome_pnl or 0) < 0
                    else "open/scratch"
                )
                bits.append(
                    f"  - [{l.lesson_type}, sim={l.similarity:.2f}, {outcome}] {l.snippet[:200]}"
                )
            lessons_block = (
                "\n\n<past_lessons_for_similar_setups>\n"
                + "\n".join(bits)
                + "\n</past_lessons_for_similar_setups>"
            )

        return (
            "<market>\n"
            f"  Ticker: {m.ticker}\n"
            f"  Question: {m.title}\n"
            f"  Category: {m.category}\n"
            f"  YES bid/ask: ${m.yes_bid:.2f} / ${m.yes_ask:.2f}  "
            f"(mid={yes_mid:.2f}, implied={implied_pct:.1f}%)\n"
            f"  NO  bid/ask: ${m.no_bid:.2f} / ${m.no_ask:.2f}\n"
            f"  Spread: {spread_pct:.1f}¢  (tight <2¢, normal 2-5¢, wide >5¢)\n"
            f"  24h volume: ${m.volume_24h:,.0f}\n"
            f"  Open interest: ${m.open_interest:,.0f}  (liquidity: {liquidity_flag})\n"
            f"  Close date: {m.close_date}\n"
            f"{related_lines}\n"
            "</market>"
            f"{lessons_block}\n\n"
            "<task>\n"
            "Run the four-phase research protocol from your system prompt:\n"
            "  1. PRICE DISCOVERY — assess implied probability, spread, liquidity.\n"
            "  2. BASE RATE — establish a defensible prior.\n"
            "  3. EVIDENCE GATHERING — use tools to update the prior with current news,\n"
            "     technicals, microstructure, and past lessons.\n"
            "  4. SYNTHESIS — compute edge, name catalysts, name invalidators.\n\n"
            "Then call `submit_evidence` ONCE with the structured pack. Be honest about\n"
            "uncertainty — `confidence_in_evidence` < 0.4 and `edge_estimate_pct` near\n"
            "zero is the correct output when the evidence doesn't support a trade.\n"
            "</task>"
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
