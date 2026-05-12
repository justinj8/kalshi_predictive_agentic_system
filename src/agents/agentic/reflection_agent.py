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


SYSTEM = """You are the reflection agent on a Kalshi trading desk. After a position closes
you write a single short LESSON the desk should remember for similar future trades.

A good lesson:
  - 1-3 sentences, retrievable on similar future setups.
  - Names the SETUP (what pattern you saw), the DECISION (what we did), and the OUTCOME.
  - Calls out the SINGLE most important driver of the result.
  - States whether to repeat or avoid this pattern.

Output strictly the JSON object below (no prose):

```json
{
  "lesson_type": "win_pattern" | "loss_pattern" | "calibration" | "data_quality" | "edge_decay",
  "text": "<1-3 sentence lesson>",
  "drivers": ["<top driver>", "<second driver>"],
  "repeat_advice": "<one short sentence>"
}
```
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

    judge = (audit.judge_decision if audit else None) or {}
    evidence = (audit.evidence_pack if audit else None) or {}

    user_msg = (
        f"Closed position summary:\n"
        f"  ticker={pos.ticker} category={pos.category} side={pos.side}\n"
        f"  entry=${pos.entry_price:.2f} current=${pos.current_price or 0:.2f}\n"
        f"  realized_pnl=${pnl:.2f} ({outcome})\n"
        f"  opened_at={pos.opened_at} closed_at={pos.closed_at}\n"
        f"  judge_decision={json.dumps(judge, default=str)[:1500]}\n"
        f"  evidence_summary={json.dumps(evidence.get('summary', ''))[:500]}\n"
        f"Write the lesson JSON now."
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
