"""Statistical tools: historical base rates and calibration curve lookup."""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import or_

from src.utils.logger import get_logger
from src.utils.calibration_tracker import calibration_tracker
from src.database.models import get_db_session, Trade

logger = get_logger(__name__)


def get_historical_base_rate(
    category: str,
    question_pattern: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute a rough base rate from resolved trades in our database.

    Approach: of trades in `category` (optionally filtered by title keyword), what
    fraction of the resolved YES-side bets paid off? This is a *very* rough
    historical prior — useful when no external source exists.
    """
    try:
        with get_db_session() as session:
            q = session.query(Trade).filter(Trade.category == category)
            if question_pattern:
                like = f"%{question_pattern}%"
                q = q.filter(or_(Trade.market_title.ilike(like), Trade.entry_reason.ilike(like)))
            q = q.filter(Trade.realized_pnl.isnot(None))
            resolved = q.all()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "sample_size": 0}

    n = len(resolved)
    if n == 0:
        return {
            "ok": True,
            "category": category,
            "question_pattern": question_pattern,
            "sample_size": 0,
            "base_rate_pct": None,
            "note": "No resolved trades in database for this slice. Use external priors.",
        }

    wins = sum(1 for t in resolved if (t.realized_pnl or 0) > 0)
    return {
        "ok": True,
        "category": category,
        "question_pattern": question_pattern,
        "sample_size": n,
        "base_rate_pct": round((wins / n) * 100, 2),
        "wins": wins,
        "losses": n - wins,
    }


def get_calibration_curve(confidence: float) -> Dict[str, Any]:
    """Lookup the empirical calibration factor for a raw confidence score."""
    try:
        factor = calibration_tracker.get_calibration_factor(confidence)
        calibrated = calibration_tracker.calibrate_confidence(confidence)
        bounded = calibration_tracker.apply_hard_bounds(confidence)
        fully = calibration_tracker.get_fully_calibrated_confidence(confidence)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "raw_confidence": confidence,
        "calibration_factor": factor,
        "calibrated_confidence": calibrated,
        "hard_bounded_confidence": bounded,
        "fully_calibrated_confidence": fully,
    }
