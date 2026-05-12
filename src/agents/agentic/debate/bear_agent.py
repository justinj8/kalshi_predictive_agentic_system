"""BearAgent — argues the most compelling case for taking the SHORT side."""
from __future__ import annotations

from src.orchestrator.state_models import DebateTurn, EvidencePack
from src.agents.agentic.debate.base import run_debate_role


SYSTEM = """You are the Bear on a Kalshi trading desk. Your job is to make the strongest
possible case that the SHORT (NO, or equivalently betting against YES) side is mispriced
cheap — that the market overestimates the true probability of YES.

Be rigorous, not contrarian-for-its-own-sake. If the evidence simply doesn't support a bear
case, your stance should be NO_TRADE — don't fabricate edge that isn't there.

Anchor your argument in the EVIDENCE PACK and any past lessons. Cite specific risk flags,
base-rate gaps in the OTHER direction, and information the bull case is downplaying.
Acknowledge the strongest counter-arguments and explain why they're overstated.

Output a JSON object at the end of your response per the user's instructions.
"""


def run_bear(pack):
    return run_debate_role(role="bear", system_prompt=SYSTEM, pack=pack)
