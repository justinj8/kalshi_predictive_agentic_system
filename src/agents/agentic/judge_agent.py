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


SYSTEM_PROMPT = """You are the JUDGE on a Kalshi trading desk. Your decision determines whether
real (paper) capital is deployed.

Inputs you receive:
  - EVIDENCE PACK from the research analyst
  - DEBATE TRANSCRIPT with arguments from Bull, Bear, and Red-Team
  - CALIBRATED probability (already empirically adjusted)
  - PAST LESSONS from similar trades
  - PORTFOLIO state and policy constraints

Decision protocol:
  1. Decide LONG / SHORT / NO_TRADE.
  2. Use the CALIBRATED probability as your anchor — do NOT inflate it.
  3. If Red-Team flagged BLOCK, you should almost always emit NO_TRADE unless you can
     specifically refute the concern.
  4. If calibrated edge vs market < {min_edge_pct}%, emit NO_TRADE.
  5. Kelly fraction must be fractional Kelly (<= 0.25); use the simulate_outcome tool
     if you want a sanity check.
  6. You MUST call `emit_trading_signal` exactly once with the full structured object.
     Do NOT respond in free text.

Bias warnings to actively suppress:
  - Recency bias: heavy weighting of the latest news headline.
  - Overconfidence: confidence should reflect calibrated probability.
  - Trade-itis: refusing to emit NO_TRADE because you scanned the market.
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

        def turn_block(label: str, turn):
            if not turn:
                return f"{label}: (no contribution)"
            return (
                f"{label}: stance={turn.stance}, p(YES)={turn.probability_estimate:.2f}\n"
                f"  argument: {turn.argument[:600]}\n"
                f"  key_points: {turn.key_points}\n"
                f"  counters: {turn.counters}"
            )

        lessons_block = "\n".join(
            f"  - id={l.id} type={l.lesson_type} pnl={l.outcome_pnl} :: {l.snippet[:200]}"
            for l in recalled_lessons[:5]
        ) or "  (no relevant lessons)"

        return (
            f"MARKET\n"
            f"  Ticker: {m.ticker}\n"
            f"  Question: {m.title}\n"
            f"  Category: {m.category}\n"
            f"  YES ${m.yes_bid:.2f}/{m.yes_ask:.2f}  NO ${m.no_bid:.2f}/{m.no_ask:.2f}\n"
            f"  Volume ${m.volume_24h:,.0f}   OI ${m.open_interest:,.0f}\n"
            f"  Close: {m.close_date}\n\n"
            f"EVIDENCE PACK (researcher confidence {pack.confidence_in_evidence:.2f})\n"
            f"  Summary: {pack.summary}\n"
            f"  Bull points: {pack.bull_case_points}\n"
            f"  Bear points: {pack.bear_case_points}\n"
            f"  Base rate: {pack.base_rate_pct}%, Market implied: {pack.market_implied_pct}%, "
            f"Edge estimate: {pack.edge_estimate_pct}%\n"
            f"  Catalysts: {pack.catalysts}\n"
            f"  Risk flags: {pack.risk_flags}\n\n"
            f"DEBATE\n"
            f"  {turn_block('BULL', transcript.bull)}\n"
            f"  {turn_block('BEAR', transcript.bear)}\n"
            f"  {turn_block('RED_TEAM', transcript.red_team)}\n\n"
            f"CALIBRATION\n"
            f"  Calibrated p(YES) = {calibrated.get('calibrated_probability'):.3f}\n"
            f"  Market-implied p = {calibrated.get('market_implied_probability')}\n"
            f"  Edge vs market   = {calibrated.get('edge_vs_market')}\n"
            f"  Rationale: {calibrated.get('rationale')}\n\n"
            f"PAST LESSONS\n{lessons_block}\n\n"
            f"PORTFOLIO\n"
            f"  Balance: ${state.current_balance:.2f}\n"
            f"  Open positions: {state.open_positions}\n"
            f"  Daily P&L: ${state.daily_pnl:.2f}\n"
            f"  Daily trades: {state.daily_trades}\n\n"
            f"REMINDER: Required min edge vs market is {min_edge * 100:.1f}%. "
            "Call `emit_trading_signal` exactly once. Optional: call `simulate_outcome` first "
            "to sanity-check the kelly_fraction."
        )


# Module-level singleton.
judge_agent = JudgeAgent()
