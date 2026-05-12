"""Outcome simulation: closed-form EV + Kelly sizing for a binary contract."""
from __future__ import annotations

from typing import Any, Dict

from src.utils.logger import get_logger
from src.utils.kelly_calculator import kelly_calculator

logger = get_logger(__name__)


def simulate_outcome(
    side: str,
    price: float,
    win_probability: float,
    capital: float,
) -> Dict[str, Any]:
    """Compute EV, variance, Kelly sizing for a single binary contract bet.

    Args:
        side: "YES" or "NO".
        price: Entry price on 0-1 scale.
        win_probability: Forecasted probability the side wins, 0-1.
        capital: Available capital in dollars.
    """
    side_u = (side or "YES").upper()
    if side_u not in ("YES", "NO"):
        return {"ok": False, "error": f"side must be YES or NO, got {side!r}"}
    if not (0 < price < 1):
        return {"ok": False, "error": f"price must be in (0,1), got {price!r}"}
    if not (0 <= win_probability <= 1):
        return {"ok": False, "error": f"win_probability must be in [0,1], got {win_probability!r}"}
    if capital < 0:
        return {"ok": False, "error": f"capital must be non-negative"}

    # Per-contract math.
    win_amt = 1.0 - price
    loss_amt = price
    ev_per_contract = win_probability * win_amt - (1 - win_probability) * loss_amt
    var_per_contract = (
        win_probability * (win_amt - ev_per_contract) ** 2
        + (1 - win_probability) * (-loss_amt - ev_per_contract) ** 2
    )

    sizing = kelly_calculator.calculate_position_size(
        win_probability=max(0.001, min(0.999, win_probability)),
        entry_price=price,
        capital=capital,
        side=side_u,
    )

    return {
        "ok": True,
        "side": side_u,
        "price": price,
        "win_probability": win_probability,
        "ev_per_contract": round(ev_per_contract, 6),
        "variance_per_contract": round(var_per_contract, 6),
        "sharpe_proxy": round(ev_per_contract / max(var_per_contract ** 0.5, 1e-9), 3),
        "kelly": sizing,
    }
