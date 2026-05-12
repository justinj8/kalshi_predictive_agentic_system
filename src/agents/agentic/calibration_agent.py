"""CalibrationAgent — converts debate probability estimates into a calibrated probability.

The bulk of the math is deterministic (mean of bull/bear estimates folded
through the empirical calibration curve). The cheap LLM is only used to
produce a short human-readable rationale for the audit trail.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from src.utils.logger import get_logger
from src.utils.calibration_tracker import calibration_tracker
from src.orchestrator.state_models import DebateTranscript, EvidencePack

logger = get_logger(__name__)


def calibrate(
    pack: EvidencePack,
    transcript: DebateTranscript,
) -> Dict[str, Any]:
    """Return calibrated probability + rationale.

    Algorithm:
      1. Take bull's prob estimate (for YES) and (1 - bear's prob for SHORT) — i.e. both
         agents' implicit YES probability.
      2. Average with research base_rate where available.
      3. Pull market-implied probability.
      4. Soft-blend (0.6 model, 0.4 market) to avoid runaway bets on tiny edges.
      5. Apply calibration_tracker.get_fully_calibrated_confidence on the *confidence*
         (distance from 50%), preserving direction.
    """
    bull_p = transcript.bull.probability_estimate if transcript.bull else 0.5
    bear_p = transcript.bear.probability_estimate if transcript.bear else 0.5

    # bear_p is the bear's stated probability of YES resolving — they argue it's low.
    avg_model = (bull_p + bear_p) / 2.0

    # Optional research base rate (already 0..100).
    if pack.base_rate_pct is not None:
        try:
            base = max(0.0, min(1.0, float(pack.base_rate_pct) / 100.0))
            avg_model = (avg_model * 0.7) + (base * 0.3)
        except (TypeError, ValueError):
            pass

    market_p: Optional[float] = None
    if pack.market_implied_pct is not None:
        try:
            market_p = max(0.0, min(1.0, float(pack.market_implied_pct) / 100.0))
        except (TypeError, ValueError):
            market_p = None

    blended = avg_model if market_p is None else (avg_model * 0.6 + market_p * 0.4)
    blended = max(0.01, min(0.99, blended))

    # Calibration: treat "confidence" as 100 * abs(blended - 0.5) * 2 (distance from 50%),
    # then shrink toward 50% by the empirical factor.
    raw_conf = 100.0 * abs(blended - 0.5) * 2.0
    fully = calibration_tracker.get_fully_calibrated_confidence(raw_conf)
    shrink_factor = fully / raw_conf if raw_conf > 0 else 1.0
    calibrated_offset = (blended - 0.5) * shrink_factor
    calibrated_prob = max(0.01, min(0.99, 0.5 + calibrated_offset))

    edge_vs_market = (
        (calibrated_prob - market_p) if market_p is not None else None
    )

    rationale = (
        f"bull_p={bull_p:.2f}, bear_p={bear_p:.2f}, "
        f"avg_model={avg_model:.2f}, market_p={market_p}, "
        f"blended={blended:.2f}, raw_conf={raw_conf:.1f}, "
        f"shrink={shrink_factor:.2f}, calibrated={calibrated_prob:.2f}"
    )
    logger.info(f"Calibration: {rationale}")

    return {
        "calibrated_probability": calibrated_prob,
        "market_implied_probability": market_p,
        "model_blended_probability": blended,
        "edge_vs_market": edge_vs_market,
        "raw_confidence": raw_conf,
        "calibrated_confidence": fully,
        "rationale": rationale,
    }
