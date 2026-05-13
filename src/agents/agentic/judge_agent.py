"""JudgeAgent — final decision maker.

Opus 4.7 with extended thinking. Reads:
  - EvidencePack from ResearchAgent
  - DebateTranscript (Bull / Bear / Red-Team)
  - Calibrated probability + market-implied probability
  - Recalled lessons from memory
  - Portfolio context

Must call `emit_trading_signal` exactly once. Output maps 1:1 to the existing
TradingSignal so downstream sizing / execution code stays unchanged.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger
from src.orchestrator.state_models import (
    DebateTranscript,
    EvidencePack,
    JudgeDecision,
    LessonRef,
    MarketAnalysis,
    TradingSignal,
    TradingState,
)
from src.agents.agentic.anthropic_client import run_agent
from src.agents.agentic.tools.registry import build_tool_list, dispatch
from config.settings import settings

logger = get_logger(__name__)


SYSTEM_PROMPT = """<role>
You are the JUDGE on a Kalshi prediction-markets trading desk. You are the final
authority on whether to deploy capital. Your standard is decision quality, not
activity. You will be evaluated on calibration (Brier score) and realized P&L
over many decisions — not on whether you traded today.
</role>

<inputs>
You receive:
  - EVIDENCE PACK from the research analyst (with bull/bear points, base rate,
    market-implied probability, edge estimate, catalysts, risk flags, source citations).
  - DEBATE TRANSCRIPT with arguments from Bull, Bear, and Red-Team agents.
  - CALIBRATED probability — already empirically adjusted via the historical
    confidence-vs-hit-rate curve. THIS IS YOUR ANCHOR.
  - PAST LESSONS — retrieved memory from similar prior trades, with outcomes.
  - PORTFOLIO state — current balance, open positions, daily P&L, daily trade count.
  - POLICY constraints — minimum edge, daily limits.
</inputs>

<decision_algorithm>
Work through these gates in order. Use extended thinking to reason carefully.

GATE 1 — Red-Team veto.
  If RedTeam.stance == "BLOCK", default to NO_TRADE unless you can name a
  specific, falsifiable reason the concern is wrong. Document the refutation
  in `reasoning`. Do not override unless the concern is clearly stale or wrong.

GATE 2 — Edge gate.
  edge = calibrated_probability − market_implied_probability
  - If |edge| < {min_edge_pct}/100: emit NO_TRADE. Insufficient edge after
    fees, slippage, and calibration uncertainty.
  - If edge > 0: candidate LONG (YES is underpriced).
  - If edge < 0: candidate SHORT (YES is overpriced).

GATE 3 — Liquidity & cost gate.
  - If the bid-ask spread eats more than 1/3 of your expected edge, emit NO_TRADE.
  - If open interest is < $500, lean NO_TRADE unless the edge is exceptionally large.

GATE 4 — Confidence calibration.
  Set `confidence` (0-100) to reflect both the size of the edge AND your
  uncertainty about the calibrated probability. Useful anchors:
    - confidence 80-95: large edge (>10%), multiple corroborating sources,
      base rate aligned, no red flags.
    - confidence 60-79: clear edge (5-10%), evidence is consistent but not
      multi-source.
    - confidence 40-59: marginal edge or mixed signals — strongly consider NO_TRADE.
    - confidence < 40: emit NO_TRADE.
  Do NOT inflate confidence to justify a trade. Calibration drift is more
  costly than missed trades.

GATE 5 — Kelly sizing.
  kelly_fraction is FRACTIONAL Kelly, capped at 0.25 (quarter-Kelly is the
  industry standard for binary markets to control variance). Compute it from
  the calibrated probability and current ask. Call `simulate_outcome` to
  sanity-check expected value, variance, and the suggested contract count.
  If full-Kelly comes out negative or below 0.005, emit NO_TRADE.
</decision_algorithm>

<bias_controls>
Actively suppress these failure modes:

- Recency bias: A single fresh headline does NOT override base rates. Discount
  any catalyst that only one source has reported.
- Overconfidence: The market often has information you don't. If your edge feels
  obvious, ask why the price hasn't already moved — usually because you're
  missing something.
- Trade-itis: You scanned this market and ran a full debate. Sunk-cost. NO_TRADE
  is the correct answer for the majority of opportunities. Refusing to emit
  NO_TRADE is a known failure mode; do not fall into it.
- Anchoring on bull/bear stance: Both debaters argue their assigned side. Their
  probability estimates are biased by their role. Use the calibrated probability,
  not the average of bull_p and bear_p.
- Pattern matching past wins: Just because a similar lesson succeeded does not
  mean this setup will. Use lessons to surface risks, not to justify trades.
</bias_controls>

<output_contract>
You MUST call `emit_trading_signal` exactly once with the full structured payload.

Required field discipline:
  - `signal` must reflect the gates above.
  - `calibrated_probability` should equal the value you were given unless you have
    a specific reason to adjust it (state the reason in reasoning).
  - `expected_return_pct` is the per-contract expected return as a percentage of
    capital at risk, NOT raw P&L.
  - `key_factors` and `risk_factors` must each have >= 2 specific items.
  - `invalidation_conditions` must be observable, testable events ("yes_ask > 0.85"
    or "FOMC postpones decision"), not vague hopes.
  - `debate_winner` reflects who made the strongest case in the transcript, not
    whose stance you adopted.
  - `lessons_applied` cites the integer ids of past lessons that materially
    influenced your reasoning (or [] if none did).

Do NOT respond in free text. The orchestrator extracts your structured tool call.
</output_contract>
"""


class JudgeAgent:
    def __init__(self) -> None:
        self.model = settings.judge_model
        self.max_tokens = settings.judge_max_tokens
        self.thinking_budget = (
            settings.judge_thinking_budget_tokens if settings.enable_extended_thinking else 0
        )

    def run(
        self,
        *,
        market_analysis: MarketAnalysis,
        pack: EvidencePack,
        transcript: DebateTranscript,
        calibrated: Dict[str, Any],
        recalled_lessons: List[LessonRef],
        state: TradingState,
    ) -> JudgeDecision:
        m = market_analysis.market

        from config.settings import settings as _s
        # Read min edge gate (default fallback if missing in policy yaml).
        # We pull it from settings.agentic for simplicity here:
        try:
            import yaml
            with open("config/trading_policy.yaml", "r") as f:
                policy = yaml.safe_load(f) or {}
            min_edge = float((policy.get("agentic") or {}).get("min_calibrated_prob_edge", 0.05))
        except Exception:
            min_edge = 0.05

        system = SYSTEM_PROMPT.format(min_edge_pct=min_edge * 100)

        user = self._build_user_prompt(
            ma=market_analysis,
            pack=pack,
            transcript=transcript,
            calibrated=calibrated,
            recalled_lessons=recalled_lessons,
            state=state,
            min_edge=min_edge,
        )

        tools = build_tool_list("simulate_outcome", "emit_trading_signal", include_web_search=False)

        result = run_agent(
            model=self.model,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=tools,
            tool_executor=dispatch,
            final_tool_name="emit_trading_signal",
            max_tokens=self.max_tokens,
            max_iterations=4,
            temperature=0.4,
            thinking_budget_tokens=self.thinking_budget if self.thinking_budget > 0 else None,
        )

        if result.final_tool_use is None:
            logger.error(f"JudgeAgent failed to emit for {m.ticker}; defaulting to NO_TRADE.")
            return JudgeDecision(
                ticker=m.ticker,
                signal="NO_TRADE",
                confidence=0.0,
                calibrated_probability=float(calibrated.get("calibrated_probability", 0.5)),
                expected_return_pct=0.0,
                kelly_fraction=0.0,
                reasoning=("Judge did not emit a structured signal within the allowed iterations. "
                           "Defaulting to NO_TRADE for safety."),
                key_factors=["judge_no_response"],
                risk_factors=["judge_no_response"],
                market_edge="None — judge truncated.",
                invalidation_conditions=[],
                lessons_applied=[],
                debate_winner="none",
                thinking_tokens_used=result.thinking_tokens,
            )

        payload = result.final_tool_use.get("input", {}) or {}
        decision = JudgeDecision(
            ticker=m.ticker,
            signal=str(payload.get("signal", "NO_TRADE")).upper(),  # type: ignore[arg-type]
            confidence=float(payload.get("confidence", 0.0) or 0.0),
            calibrated_probability=float(
                payload.get("calibrated_probability", calibrated.get("calibrated_probability", 0.5))
                or 0.5
            ),
            expected_return_pct=float(payload.get("expected_return_pct", 0.0) or 0.0),
            kelly_fraction=max(0.0, min(0.25, float(payload.get("kelly_fraction", 0.0) or 0.0))),
            reasoning=str(payload.get("reasoning", ""))[:4000],
            key_factors=[str(x) for x in (payload.get("key_factors") or [])][:10],
            risk_factors=[str(x) for x in (payload.get("risk_factors") or [])][:10],
            market_edge=str(payload.get("market_edge", ""))[:500],
            invalidation_conditions=[str(x) for x in (payload.get("invalidation_conditions") or [])][:10],
            lessons_applied=[int(x) for x in (payload.get("lessons_applied") or []) if str(x).lstrip("-").isdigit()],
            debate_winner=str(payload.get("debate_winner", "none")).lower(),  # type: ignore[arg-type]
            thinking_tokens_used=result.thinking_tokens,
        )

        logger.info(
            f"Judge decision for {m.ticker}: {decision.signal} "
            f"(conf={decision.confidence:.1f}%, calibrated_p={decision.calibrated_probability:.2f}, "
            f"kelly={decision.kelly_fraction:.3f}, winner={decision.debate_winner})"
        )
        return decision

    @staticmethod
    def _build_user_prompt(
        *,
        ma: MarketAnalysis,
        pack: EvidencePack,
        transcript: DebateTranscript,
        calibrated: Dict[str, Any],
        recalled_lessons: List[LessonRef],
        state: TradingState,
        min_edge: float,
    ) -> str:
        m = ma.market
        spread_pct = (m.yes_ask - m.yes_bid) * 100 if m.yes_ask > m.yes_bid else 0.0
        liquidity_flag = (
            "THIN" if m.open_interest < 500
            else "LIGHT" if m.open_interest < 2000
            else "OK"
        )

        def turn_block(label: str, turn) -> str:
            if not turn:
                return f"  <{label}>(no contribution)</{label}>"
            return (
                f"  <{label} stance=\"{turn.stance}\" p_yes=\"{turn.probability_estimate:.2f}\">\n"
                f"    argument: {turn.argument[:600]}\n"
                f"    key_points: {turn.key_points}\n"
                f"    counters: {turn.counters}\n"
                f"  </{label}>"
            )

        if recalled_lessons:
            lessons_block = "\n".join(
                f"    - id={l.id} type={l.lesson_type} "
                f"pnl=${(l.outcome_pnl or 0):.2f} sim={l.similarity:.2f}\n"
                f"      \"{l.snippet[:200]}\""
                for l in recalled_lessons[:5]
            )
        else:
            lessons_block = "    (no relevant lessons recalled)"

        edge_vs_market = calibrated.get("edge_vs_market")
        edge_str = f"{edge_vs_market:+.3f}" if edge_vs_market is not None else "n/a"

        return (
            "<market>\n"
            f"  Ticker: {m.ticker}\n"
            f"  Question: {m.title}\n"
            f"  Category: {m.category}\n"
            f"  YES ${m.yes_bid:.2f}/{m.yes_ask:.2f}    NO ${m.no_bid:.2f}/{m.no_ask:.2f}\n"
            f"  Spread: {spread_pct:.1f}¢   OI: ${m.open_interest:,.0f} ({liquidity_flag})   "
            f"24h vol: ${m.volume_24h:,.0f}\n"
            f"  Close: {m.close_date}\n"
            "</market>\n\n"
            f"<evidence_pack researcher_confidence=\"{pack.confidence_in_evidence:.2f}\">\n"
            f"  Summary: {pack.summary}\n"
            f"  Bull points: {pack.bull_case_points}\n"
            f"  Bear points: {pack.bear_case_points}\n"
            f"  Base rate: {pack.base_rate_pct}%   Market implied: {pack.market_implied_pct}%   "
            f"Researcher edge: {pack.edge_estimate_pct}%\n"
            f"  Catalysts: {pack.catalysts}\n"
            f"  Risk flags: {pack.risk_flags}\n"
            "</evidence_pack>\n\n"
            "<debate>\n"
            f"{turn_block('BULL', transcript.bull)}\n"
            f"{turn_block('BEAR', transcript.bear)}\n"
            f"{turn_block('RED_TEAM', transcript.red_team)}\n"
            "</debate>\n\n"
            "<calibration>\n"
            f"  Calibrated p(YES) = {calibrated.get('calibrated_probability', 0.5):.3f}   "
            f"<-- USE THIS AS YOUR ANCHOR\n"
            f"  Market-implied p  = {calibrated.get('market_implied_probability')}\n"
            f"  Edge vs market    = {edge_str}\n"
            f"  Rationale: {calibrated.get('rationale')}\n"
            "</calibration>\n\n"
            "<past_lessons>\n"
            f"{lessons_block}\n"
            "</past_lessons>\n\n"
            "<portfolio>\n"
            f"  Balance: ${state.current_balance:.2f}\n"
            f"  Open positions: {state.open_positions}\n"
            f"  Daily P&L: ${state.daily_pnl:.2f}\n"
            f"  Daily trades: {state.daily_trades}\n"
            "</portfolio>\n\n"
            "<policy>\n"
            f"  Minimum edge required: {min_edge * 100:.1f}% (Gate 2)\n"
            "</policy>\n\n"
            "<task>\n"
            "Walk through Gates 1-5 from your system prompt in your extended thinking.\n"
            "Optional: call `simulate_outcome` to sanity-check the Kelly fraction before\n"
            "emitting. Then call `emit_trading_signal` exactly once with the structured\n"
            "decision. The default answer is NO_TRADE — only override it when the gates\n"
            "clearly pass.\n"
            "</task>"
        )


# Module-level singleton.
judge_agent = JudgeAgent()
