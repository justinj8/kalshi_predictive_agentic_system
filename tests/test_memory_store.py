"""Tests for the persistent lesson store.

Uses an in-memory SQLite DB so no real `data/trades.db` is touched. The
embedding model is the deterministic hash fallback (no network).
"""
from __future__ import annotations

import os
import pytest

import sqlalchemy
from sqlalchemy.orm import sessionmaker

# Force hash-fallback embeddings BEFORE importing memory_store.
os.environ.setdefault("EMBEDDING_MODEL", "_unloadable_model_")


@pytest.fixture
def isolated_db(monkeypatch):
    """Replace the global DB engine with an in-memory SQLite."""
    from src.database import models as dbm

    engine = sqlalchemy.create_engine("sqlite:///:memory:")
    dbm.Base.metadata.create_all(engine)

    SessionFactory = sessionmaker(bind=engine)
    monkeypatch.setattr(dbm, "_engine", engine)
    monkeypatch.setattr(dbm, "_Session", SessionFactory)
    return engine


def test_memory_store_add_and_search(isolated_db, monkeypatch):
    from src.agents.agentic.memory_store import memory_store

    # Force hash fallback so the test doesn't try to load sentence-transformers.
    monkeypatch.setattr(memory_store, "_model", "_hash_fallback_")

    id1 = memory_store.add_lesson(
        text="Lost on a NFL spread market when injury news broke late.",
        lesson_type="loss_pattern",
        ticker="KXNFL-2025-W1",
        category="sports",
        outcome_pnl=-12.50,
    )
    id2 = memory_store.add_lesson(
        text="Won big on a CPI print after under-weighting consensus.",
        lesson_type="win_pattern",
        ticker="KXECON-CPI-2025",
        category="economics",
        outcome_pnl=42.10,
    )
    assert id1 is not None
    assert id2 is not None
    assert id1 != id2

    hits = memory_store.search(query="NFL injury news late breaking", k=2)
    assert len(hits) <= 2
    # Sanity: every hit has the keys our consumers expect.
    for h in hits:
        for k in ("id", "similarity", "lesson_type", "snippet"):
            assert k in h


def test_empty_search_returns_empty(isolated_db, monkeypatch):
    from src.agents.agentic.memory_store import memory_store

    monkeypatch.setattr(memory_store, "_model", "_hash_fallback_")
    out = memory_store.search(query="nothing here", k=5)
    assert out == []
