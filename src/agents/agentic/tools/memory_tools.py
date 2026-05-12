"""Memory recall tool — surfaces lessons via the MemoryStore."""
from __future__ import annotations

from typing import Any, Dict

from src.utils.logger import get_logger

logger = get_logger(__name__)


def recall_lessons(query: str, k: int = 5) -> Dict[str, Any]:
    """Return top-k lessons from the memory store, ranked by cosine similarity."""
    # Import lazily so unit tests that don't touch memory don't pay the embedding cost.
    try:
        from src.agents.agentic.memory_store import memory_store
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"memory_store unavailable: {exc}")
        return {"ok": False, "error": str(exc), "lessons": []}

    try:
        hits = memory_store.search(query=query, k=k)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"memory recall failed: {exc}")
        return {"ok": False, "error": str(exc), "lessons": []}

    return {"ok": True, "query": query, "count": len(hits), "lessons": hits}
