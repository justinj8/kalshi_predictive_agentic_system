"""CrossMarketScout — surfaces related markets, complement arbitrage, and baskets.

Runs once per cycle, before opportunity selection. Operates over all_markets:
  1. Embed every market title+category once.
  2. For top opportunities, find cosine-similar siblings above threshold.
  3. Detect complement mispricing (YES_A + YES_B > 1 for mutually exclusive pairs).
  4. Attach `related_tickers` to each top_opportunity for the research agent to see.
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from src.utils.logger import get_logger
from src.orchestrator.state_models import (
    ArbitrageOpportunity,
    MarketAnalysis,
    MarketData,
    TradingState,
)
from src.agents.agentic.memory_store import memory_store
from src.agents.market_data_fetcher import market_data_fetcher
from config.settings import settings

logger = get_logger(__name__)


def _embed_market(m: MarketData) -> np.ndarray:
    text = f"{m.category} | {m.title}"
    return memory_store.embed(text)


def run_scout(state: TradingState) -> TradingState:
    """Annotate top opportunities and emit complement-arbitrage candidates."""
    try:
        threshold = float(
            (_load_policy() or {}).get("agentic", {}).get(
                "related_market_similarity_threshold", 0.78
            )
        )
    except Exception:
        threshold = 0.78

    if not settings.enable_cross_market_scout:
        return state

    markets = state.all_markets or []
    if not markets:
        return state

    # Pre-populate top_opportunities so the scout has something to annotate.
    # The orchestrator's _select_opportunity_node would otherwise be the first
    # place top_opportunities is filled, meaning the scout would iterate an
    # empty list every cycle.
    if not state.top_opportunities:
        try:
            top_markets = market_data_fetcher._rank_markets(markets, top_n=10)
            state.top_opportunities = [
                MarketAnalysis(market=m) for m in top_markets
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Scout pre-ranking failed: {exc}")
            return state

    # Embed every market once.
    try:
        vectors: Dict[str, np.ndarray] = {m.ticker: _embed_market(m) for m in markets}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Scout embedding failed: {exc}")
        return state

    annotated = 0
    arbs_added: List[ArbitrageOpportunity] = []
    seen_arb_pairs = set()

    for opp in state.top_opportunities:
        anchor = opp.market
        anchor_vec = vectors.get(anchor.ticker)
        if anchor_vec is None:
            continue

        prefix = anchor.ticker.split("-")[0] if "-" in anchor.ticker else anchor.ticker
        related: List[Dict[str, Any]] = []

        for m in markets:
            if m.ticker == anchor.ticker:
                continue
            # Prefer event-prefix siblings; otherwise use cosine threshold.
            same_event = m.ticker.startswith(prefix)
            vec = vectors.get(m.ticker)
            if vec is None:
                continue
            cos = float(np.dot(anchor_vec, vec))
            sim = (cos + 1.0) / 2.0
            if not (same_event or sim >= threshold):
                continue
            related.append(
                {
                    "ticker": m.ticker,
                    "title": m.title,
                    "similarity": sim,
                    "same_event": same_event,
                    "yes_ask": m.yes_ask,
                    "no_ask": m.no_ask,
                }
            )

            # Complement arbitrage probe (mutually exclusive siblings).
            if same_event and m.yes_ask > 0 and anchor.yes_ask > 0:
                total = anchor.yes_ask + m.yes_ask
                if total > 1.02:
                    pair = tuple(sorted([anchor.ticker, m.ticker]))
                    if pair not in seen_arb_pairs:
                        seen_arb_pairs.add(pair)
                        arbs_added.append(
                            ArbitrageOpportunity(
                                type="complement",
                                markets=list(pair),
                                profit_pct=round((total - 1.0) * 100, 2),
                                trades=[
                                    {"ticker": anchor.ticker, "side": "NO", "price": anchor.no_ask},
                                    {"ticker": m.ticker, "side": "NO", "price": m.no_ask},
                                ],
                                execution_complexity="medium",
                                confidence=min(95.0, 50.0 + (total - 1.0) * 200),
                            )
                        )

        if related:
            related.sort(key=lambda d: d["similarity"], reverse=True)
            opp.related_tickers = related[:10]
            annotated += 1

    if arbs_added:
        state.arbitrage_opportunities.extend(arbs_added)
        logger.info(f"Scout: surfaced {len(arbs_added)} complement-arb candidates.")
    if annotated:
        logger.info(f"Scout: annotated {annotated} opportunities with related markets.")

    return state


def _load_policy() -> Dict[str, Any]:
    import yaml

    try:
        with open("config/trading_policy.yaml", "r") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}
