"""News-search tool wrappers (NewsAPI + Alpha Vantage fallback)."""
from __future__ import annotations

from typing import Any, Dict, List

from src.utils.logger import get_logger
from src.utils.news_fetcher import news_fetcher

logger = get_logger(__name__)


def search_news(
    query: str,
    lookback_hours: int = 48,
    max_results: int = 8,
) -> Dict[str, Any]:
    """Search recent news. Wraps src/utils/news_fetcher.py."""
    days_back = max(1, lookback_hours // 24 + (1 if lookback_hours % 24 else 0))
    try:
        articles: List[Dict[str, Any]] = news_fetcher.search_news(
            query=query,
            days_back=days_back,
            max_results=max_results,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"search_news failed: {exc}")
        return {"ok": False, "error": str(exc), "articles": []}

    trimmed = []
    for art in (articles or [])[:max_results]:
        trimmed.append(
            {
                "title": art.get("title"),
                "source": art.get("source"),
                "published_at": art.get("published_at"),
                "url": art.get("url"),
                "summary": (art.get("description") or "")[:400],
            }
        )

    return {"ok": True, "query": query, "count": len(trimmed), "articles": trimmed}
