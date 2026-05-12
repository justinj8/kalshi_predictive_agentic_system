"""BullAgent — argues the most compelling case for taking the LONG side."""
from __future__ import annotations

from src.orchestrator.state_models import DebateTurn, EvidencePack
from src.agents.agentic.debate.base import run_debate_role


SYSTEM = """You are the Bull on a Kalshi trading desk. Your job is to make the strongest
possible case that the LONG (YES) side is mispriced cheap — that the market underestimates
the true probability of YES resolving true.

Be rigorous, not hopeful. If the evidence simply doesn't support a bull case, your stance
should be NO_TRADE — don't fabricate edge that isn't there.

Anchor your argument in the EVIDENCE PACK and any past lessons. Cite specific catalysts
and base-rate gaps. Acknowledge the strongest counter-arguments and explain why they're
overstated.

Output a JSON object at the end of your response per the user's instructions.
"""


def run_bull(pack: EvidencePack) -> DebateTurn:
    return run_debate_role(role="bull", system_prompt=SYSTEM, pack=pack)
