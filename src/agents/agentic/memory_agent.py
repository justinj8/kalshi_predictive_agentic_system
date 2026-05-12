"""MemoryAgent — recalls relevant lessons before the debate runs.

This is a thin, deterministic agent (no LLM): it constructs a retrieval query
from the current market context and asks `memory_store` for top-k matches.
"""
from __future__ import annotations

from typing import List

from src.utils.logger import get_logger
from src.orchestrator.state_models import LessonRef, MarketAnalysis
from src.agents.agentic.memory_store import memory_store
from config.settings import settings

logger = get_logger(__name__)


def recall_for_market(ma: MarketAnalysis, k: int = None) -> List[LessonRef]:
    """Top-k lessons most relevant to the current market."""
    k = k or settings.memory_recall_top_k
    if not settings.enable_memory:
        return []

    m = ma.market
    yes_mid = (m.yes_bid + m.yes_ask) / 2 if (m.yes_bid + m.yes_ask) else 0.0
    query = (
        f"Kalshi market analysis. Ticker {m.ticker}. Category {m.category}. "
        f"Question: {m.title}. Implied probability {yes_mid * 100:.1f}%. "
        f"24h volume ${m.volume_24h:,.0f}. "
        f"Recent news: " + "; ".join((a.title or "") for a in ma.news_articles[:3])
    )

    try:
        hits = memory_store.search(query=query, k=k)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"memory recall failed: {exc}")
        return []

    refs: List[LessonRef] = []
    for h in hits:
        refs.append(
            LessonRef(
                id=int(h["id"]),
                similarity=float(h.get("similarity", 0.0)),
                lesson_type=str(h.get("lesson_type", "unknown")),
                snippet=str(h.get("snippet", "")),
                outcome_pnl=h.get("outcome_pnl"),
                ticker=h.get("ticker"),
                category=h.get("category"),
            )
        )
    logger.info(f"MemoryAgent recalled {len(refs)} lessons for {m.ticker}")
    return refs
