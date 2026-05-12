"""RedTeamAgent — adversarial reviewer that hunts for reasons NOT to trade."""
from __future__ import annotations

from typing import List, Optional

from src.orchestrator.state_models import DebateTurn, EvidencePack, LessonRef
from src.agents.agentic.debate.base import run_debate_role


SYSTEM = """You are the Red Team. Your job is to FIND REASONS NOT TO TRADE.

Treat the Bull AND Bear cases as suspect. Identify:
  - Data-quality holes ("we don't actually know X")
  - Recency bias / over-fitting to one news cycle
  - Liquidity traps (wide spreads, tiny open interest)
  - Confidence built on speculative or unconfirmed sources
  - Past patterns where similar trades lost (use `recall_lessons` if useful)
  - Edge that is real but too small after slippage

Recommend stance:
  - BLOCK: there is a critical flaw — do not trade.
  - PROCEED: no critical flaw found, the desk may consider the trade.

Be skeptical but fair. If everything checks out, say PROCEED.

You may call the `recall_lessons` tool ONCE to find prior loss patterns matching this trade.

Output a JSON object at the end per the user's instructions, with `stance` set to
either BLOCK or PROCEED.
"""


def run_red_team(pack: EvidencePack, recalled_lessons: Optional[List[LessonRef]] = None) -> DebateTurn:
    return run_debate_role(
        role="red_team",
        system_prompt=SYSTEM,
        pack=pack,
        recalled_lessons=recalled_lessons,
        extra_tools=["recall_lessons"],
    )
