"""
Kalshi fee and expected-value helpers.

Standard Kalshi fees scale with contract uncertainty. We model taker fees as
0.07 * price * (1 - price), and maker fees as one quarter of that by default.
Some series can have non-standard fees, so keep these helpers centralized.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from config.settings import settings


OrderFeeType = Literal["maker", "taker"]


@dataclass(frozen=True)
class FeeAdjustedEV:
    """Fee-adjusted expected value for one binary contract."""

    side: str
    price: float
    win_probability: float
    fee_type: OrderFeeType
    fee_per_contract: float
    gross_ev_per_contract: float
    net_ev_per_contract: float
    net_ev_pct_of_cost: float


def estimate_fee_per_contract(
    price: float,
    *,
    fee_type: OrderFeeType = "taker",
    fee_multiplier: float = 1.0,
) -> float:
    """Estimate one-contract trading fee in dollars."""
    p = max(0.01, min(0.99, float(price)))
    rate = (
        settings.kalshi_maker_fee_rate
        if fee_type == "maker"
        else settings.kalshi_taker_fee_rate
    )
    return max(0.0, rate * p * (1.0 - p) * fee_multiplier)


def calculate_fee_adjusted_ev(
    *,
    side: str,
    price: float,
    win_probability: float,
    fee_type: OrderFeeType = "taker",
    fee_multiplier: float = 1.0,
) -> FeeAdjustedEV:
    """Calculate fee-adjusted expected value for buying YES or NO."""
    p = max(0.01, min(0.99, float(price)))
    win_p = max(0.0, min(1.0, float(win_probability)))
    gross_ev = win_p * (1.0 - p) - (1.0 - win_p) * p
    fee = estimate_fee_per_contract(p, fee_type=fee_type, fee_multiplier=fee_multiplier)
    net_ev = gross_ev - fee
    return FeeAdjustedEV(
        side=side.upper(),
        price=p,
        win_probability=win_p,
        fee_type=fee_type,
        fee_per_contract=fee,
        gross_ev_per_contract=gross_ev,
        net_ev_per_contract=net_ev,
        net_ev_pct_of_cost=(net_ev / p) * 100.0 if p > 0 else 0.0,
    )
