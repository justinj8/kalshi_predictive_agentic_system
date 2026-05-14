"""ReflectionAgent — writes lessons after a position closes.

Triggered at finalize for every Position that closed since the previous cycle.
Synthesizes a short, retrievable lesson capturing what worked or what failed
and writes it to the `lessons` table via memory_store.

Uses Sonnet for the synthesis; falls back to a deterministic template if
the LLM call errors out.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger
from src.database.models import Position, DecisionAudit, get_db_session
from src.agents.agentic.anthropic_client import run_agent
from src.agents.agentic.memory_store import memory_store
from config.settings import settings

logger = get_logger(__name__)


SYSTEM = """<role>
You are the REFLECTION agent on a Kalshi trading desk. After every position
closes, you write ONE short, retrievable LESSON capturing what the desk should
remember when it sees a similar setup again.
</role>

<purpose>
Lessons are stored with an embedding and recalled by similarity later. A great
lesson is one that, six months from now, surfaces to the research/judge agents
on a similar trade and meaningfully changes the decision. A bad lesson is
either too vague to be useful or too specific to ever match.
</purpose>

<good_lesson_anatomy>
A useful lesson has four ingredients:
  1. SETUP — the recognizable pattern (category, price range, news context,
     timing relative to event).
  2. DECISION — what we actually did (side, entry conditions).
  3. OUTCOME — won/lost, magnitude.
  4. DRIVER — the SINGLE most important reason for the result.

Then a clear REPEAT_ADVICE: either "do this again under conditions X" or
"avoid this when condition Y is present".
</good_lesson_anatomy>

<examples>
GOOD (loss_pattern):
  "Bought YES on a CPI 'in-line' market at $0.78 when consensus was $0.75. Lost
   $14 — the print came in 0.1 hot and the contract collapsed. Driver: trading
   into a macro print with the edge already priced in. Repeat advice: avoid
   YES bets above $0.70 on macro print markets within 12h of the release."

GOOD (win_pattern):
  "Bought NO on a sports event at $0.55 when the favorite had a late injury.
   Won $22. Driver: news arbitrage — public injury report not yet reflected in
   YES price. Repeat advice: when a binary sports market lags wire-service
   injury news by >30 minutes, the lag is real edge if liquidity allows."

GOOD (calibration):
  "Judge confidence was 82% on a politics market that closed against us.
   This was the 3rd similar miss. Driver: model overweights catalyst headlines
   relative to base rates for incumbent re-elections. Repeat advice: shrink
   politics-incumbent confidence by ~15pp until calibration tracker catches up."

GOOD (data_quality):
  "Entered on a 'breaking' headline about a regulatory ruling that turned out
   to be premature reporting. Lost $9. Driver: single-source unconfirmed news.
   Repeat advice: when news_articles count is 1 and source is not a wire
   service, require corroboration before sizing."

BAD (too vague, do NOT write lessons like these):
  - "Be more careful next time."
  - "The market moved against us."
  - "Sentiment was wrong."
  - "Risk management failed."

BAD (too specific, will never match again):
  - "Lost on KXNFL-2025-W1-CHIEFS. Should have known."
</examples>

<output_contract>
Respond with EXACTLY the JSON object below, no prose before or after. The
"text" field is what gets embedded and recalled — make it self-contained.

```json
{
  "lesson_type": "win_pattern" | "loss_pattern" | "calibration" | "data_quality" | "edge_decay",
  "text": "<setup + decision + outcome + driver, 2-4 sentences>",
  "drivers": ["<top driver>", "<second driver if relevant>"],
  "repeat_advice": "<one actionable sentence>"
}
```

If the outcome is a scratch / break-even / very small move, still write the
lesson but use lesson_type = "edge_decay" or "data_quality" as appropriate.
Do not invent drama that wasn't in the data.
</output_contract>
"""


def reflect_on_closed_positions(state) -> int:
    """Walk recently closed positions and write a lesson for each. Returns # written."""
    if not settings.enable_memory:
        return 0

    written = 0
    cutoff = datetime.utcnow() - timedelta(hours=1)
    try:
        with get_db_session() as session:
            closed = (
                session.query(Position)
                .filter(Position.is_open == False)  # noqa: E712
                .filter(Position.closed_at != None)  # noqa: E711
                .filter(Position.closed_at >= cutoff)
                .all()
            )
            for pos in closed:
                # Skip if we already reflected on this trade.
                if pos.position_id and _lesson_already_written(session, pos.position_id):
                    continue
                # Look up the matching audit row (best-effort).
                audit = (
                    session.query(DecisionAudit)
                    .filter(DecisionAudit.ticker == pos.ticker)
                    .order_by(DecisionAudit.created_at.desc())
                    .first()
                )
                lesson = _synthesize_lesson(pos, audit)
                if lesson is None:
                    continue
                lid = memory_store.add_lesson(
                    text=lesson["text"],
                    lesson_type=lesson["lesson_type"],
                    ticker=pos.ticker,
                    category=pos.category,
                    position_id=pos.position_id,
                    outcome_pnl=pos.realized_pnl,
                    structured=lesson,
                    source_agent="ReflectionAgent",
                )
                if lid is not None:
                    written += 1
                    # Backfill the audit with outcome.
                    if audit is not None:
                        audit.final_pnl = pos.realized_pnl
                        audit.outcome_label = (
                            "win" if (pos.realized_pnl or 0) > 0
                            else "loss" if (pos.realized_pnl or 0) < 0
                            else "scratch"
                        )
                        session.add(audit)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Reflection sweep failed: {exc}", exc_info=True)
    return written


def _lesson_already_written(session, position_id: str) -> bool:
    from src.database.models import Lesson  # local import to avoid cycle
    return (
        session.query(Lesson).filter(Lesson.position_id == position_id).first() is not None
    )


def _synthesize_lesson(pos: Position, audit: Optional[DecisionAudit]) -> Optional[Dict[str, Any]]:
    pnl = pos.realized_pnl or 0.0
    outcome = "win" if pnl > 0 else "loss" if pnl < 0 else "scratch"
    pnl_pct = (pnl / (pos.entry_price * (pos.quantity or 1))) * 100 if pos.entry_price else 0.0

    judge = (audit.judge_decision if audit else None) or {}
    evidence = (audit.evidence_pack if audit else None) or {}

    judge_summary = {
        k: judge.get(k)
        for k in (
            "signal",
            "confidence",
            "calibrated_probability",
            "expected_return_pct",
            "kelly_fraction",
            "market_edge",
            "key_factors",
            "risk_factors",
            "debate_winner",
        )
        if k in judge
    }

    user_msg = (
        "<closed_position>\n"
        f"  Ticker: {pos.ticker}\n"
        f"  Category: {pos.category}\n"
        f"  Side: {pos.side}\n"
        f"  Entry: ${pos.entry_price:.2f}   Exit/current: ${pos.current_price or 0:.2f}\n"
        f"  Quantity: {pos.quantity}\n"
        f"  Realized P&L: ${pnl:.2f}  ({pnl_pct:+.1f}%)  -> {outcome.upper()}\n"
        f"  Opened: {pos.opened_at}    Closed: {pos.closed_at}\n"
        "</closed_position>\n\n"
        "<judge_decision_at_entry>\n"
        f"  {json.dumps(judge_summary, default=str, indent=2)[:1500]}\n"
        "</judge_decision_at_entry>\n\n"
        "<research_evidence_summary>\n"
        f"  {json.dumps(evidence.get('summary', ''), default=str)[:500]}\n"
        f"  Risk flags noted: {evidence.get('risk_flags', [])}\n"
        f"  Catalysts noted: {evidence.get('catalysts', [])}\n"
        "</research_evidence_summary>\n\n"
        "<task>\n"
        "Synthesize the single most useful lesson the desk should remember\n"
        "when it sees a similar setup again. Follow the SETUP -> DECISION ->\n"
        "OUTCOME -> DRIVER structure. Output the JSON object only, no prose.\n"
        "</task>"
    )

    try:
        result = run_agent(
            model=settings.specialist_model,
            system=SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            tools=None,
            tool_executor=None,
            final_tool_name=None,
            max_tokens=600,
            max_iterations=1,
            temperature=0.5,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Reflection LLM failed for {pos.ticker}: {exc}")
        return _fallback_lesson(pos, outcome)

    return _parse_lesson_json(result.text) or _fallback_lesson(pos, outcome)


def _parse_lesson_json(text: str) -> Optional[Dict[str, Any]]:
    import re

    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        if "text" not in obj or "lesson_type" not in obj:
            return None
        if obj["lesson_type"] not in {
            "win_pattern", "loss_pattern", "calibration", "data_quality", "edge_decay"
        }:
            obj["lesson_type"] = "loss_pattern"
        return obj
    except json.JSONDecodeError:
        return None


def _fallback_lesson(pos: Position, outcome: str) -> Dict[str, Any]:
    return {
        "lesson_type": "win_pattern" if outcome == "win" else "loss_pattern",
        "text": (
            f"{pos.ticker} ({pos.category}) {pos.side} entered at ${pos.entry_price:.2f} "
            f"closed with PnL=${(pos.realized_pnl or 0):.2f}. "
            f"Pattern: {pos.side.upper()} at this price level in {pos.category} markets "
            f"resulted in a {outcome}."
        ),
        "drivers": [pos.category or "unknown"],
        "repeat_advice": "Review similar setups before repeating." if outcome == "loss" else "Pattern worked; revisit conditions for repeats.",
    }
