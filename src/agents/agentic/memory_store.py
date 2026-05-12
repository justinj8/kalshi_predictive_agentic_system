"""Persistent lesson store with embedding-based recall.

Writes go through `MemoryStore.add_lesson(...)`. Reads use `search(query, k)`
and return the top-k matching lessons by cosine similarity. The embedding
model is loaded lazily on first use so importing this module never hits the
network or GPU.
"""
from __future__ import annotations

import json
import struct
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from src.utils.logger import get_logger
from src.database.models import Lesson, get_db_session
from config.settings import settings

logger = get_logger(__name__)

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 default


class MemoryStore:
    """Lesson read/write + embedding index over the `lessons` SQL table."""

    def __init__(self, model_name: Optional[str] = None) -> None:
        self.model_name = model_name or settings.embedding_model
        self._model = None  # lazy

    # ------------------------------------------------------------------ embed

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"sentence-transformers unavailable ({exc}). "
                "Falling back to deterministic hash embedding."
            )
            self._model = "_hash_fallback_"

    def embed(self, text: str) -> np.ndarray:
        """Return a (EMBEDDING_DIM,) float32 unit vector for `text`."""
        self._ensure_model()
        if self._model == "_hash_fallback_":
            return self._hash_embed(text)
        try:
            vec = self._model.encode([text], normalize_embeddings=True)[0]
            return np.asarray(vec, dtype=np.float32)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Embedding failed, using hash fallback: {exc}")
            return self._hash_embed(text)

    @staticmethod
    def _hash_embed(text: str) -> np.ndarray:
        """Deterministic hash-bag embedding so the system never breaks offline."""
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        vec = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
        norm = np.linalg.norm(vec) or 1.0
        return vec / norm

    # ------------------------------------------------------------------ pack

    @staticmethod
    def _pack(vec: np.ndarray) -> bytes:
        v = np.asarray(vec, dtype=np.float32).reshape(-1)
        if v.shape[0] != EMBEDDING_DIM:
            # Project / pad to EMBEDDING_DIM defensively.
            out = np.zeros(EMBEDDING_DIM, dtype=np.float32)
            n = min(v.shape[0], EMBEDDING_DIM)
            out[:n] = v[:n]
            v = out
        return struct.pack(f"{EMBEDDING_DIM}f", *v.tolist())

    @staticmethod
    def _unpack(blob: bytes) -> Optional[np.ndarray]:
        if blob is None or len(blob) < EMBEDDING_DIM * 4:
            return None
        v = np.array(struct.unpack(f"{EMBEDDING_DIM}f", blob[: EMBEDDING_DIM * 4]), dtype=np.float32)
        return v

    # ----------------------------------------------------------------- write

    def add_lesson(
        self,
        *,
        text: str,
        lesson_type: str,
        ticker: Optional[str] = None,
        category: Optional[str] = None,
        trade_id: Optional[int] = None,
        position_id: Optional[str] = None,
        outcome_pnl: Optional[float] = None,
        structured: Optional[Dict[str, Any]] = None,
        source_agent: str = "ReflectionAgent",
        decision_path: str = "agentic_v1",
    ) -> Optional[int]:
        """Persist a new lesson; returns the row id."""
        embed_text = self._compose_embed_text(
            text=text, ticker=ticker, category=category, structured=structured
        )
        vec = self.embed(embed_text)
        blob = self._pack(vec)

        try:
            with get_db_session() as session:
                row = Lesson(
                    text=text,
                    lesson_type=lesson_type,
                    ticker=ticker,
                    category=category,
                    trade_id=trade_id,
                    position_id=position_id,
                    outcome_pnl=outcome_pnl,
                    structured=structured,
                    source_agent=source_agent,
                    decision_path=decision_path,
                    embedding=blob,
                    created_at=datetime.utcnow(),
                )
                session.add(row)
                session.flush()
                return row.id
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Failed to write lesson: {exc}", exc_info=True)
            return None

    @staticmethod
    def _compose_embed_text(
        *,
        text: str,
        ticker: Optional[str],
        category: Optional[str],
        structured: Optional[Dict[str, Any]],
    ) -> str:
        parts = [text or ""]
        if ticker:
            parts.append(f"ticker={ticker}")
        if category:
            parts.append(f"category={category}")
        if structured:
            try:
                parts.append(json.dumps(structured, default=str)[:400])
            except Exception:
                pass
        return " | ".join(parts)

    # ------------------------------------------------------------------ read

    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Top-k lessons by cosine similarity over `query`."""
        if k <= 0:
            return []
        q_vec = self.embed(query)

        # Materialize everything we need while still inside the session, so the
        # rows don't get detached before we read their columns.
        rows_data: List[Dict[str, Any]] = []
        try:
            with get_db_session() as session:
                rows = session.query(Lesson).all()
                for row in rows:
                    if not row.embedding:
                        continue
                    rows_data.append(
                        {
                            "id": row.id,
                            "lesson_type": row.lesson_type,
                            "text": row.text,
                            "ticker": row.ticker,
                            "category": row.category,
                            "outcome_pnl": row.outcome_pnl,
                            "embedding": bytes(row.embedding),
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Could not load lessons: {exc}")
            return []

        if not rows_data:
            return []

        scored: List[Dict[str, Any]] = []
        for r in rows_data:
            vec = self._unpack(r["embedding"])
            if vec is None:
                continue
            sim = float(np.dot(q_vec, vec))
            sim = max(-1.0, min(1.0, sim))
            scored.append(
                {
                    "id": r["id"],
                    "similarity": (sim + 1.0) / 2.0,  # Map [-1,1] -> [0,1]
                    "lesson_type": r["lesson_type"],
                    "snippet": (r["text"] or "")[:300],
                    "ticker": r["ticker"],
                    "category": r["category"],
                    "outcome_pnl": r["outcome_pnl"],
                }
            )

        scored.sort(key=lambda d: d["similarity"], reverse=True)
        return scored[:k]


# Module-level singleton.
memory_store = MemoryStore()
