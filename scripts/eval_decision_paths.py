"""Shadow-mode evaluation: compare the agentic decision path against the legacy
single-shot pipeline using `decision_audits` rows accumulated during paper trading.

Usage:
    python scripts/eval_decision_paths.py

Reports:
  - Disagreement rate (judge LONG/SHORT/NO_TRADE vs legacy LONG/SHORT/NO_TRADE)
  - Per-path realized P&L on closed trades
  - Per-path Brier score (calibrated_probability vs realized outcome)
  - Per-path hit rate per confidence bucket
  - McNemar test on disagreement cases (light-weight, no scipy required)
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from src.database.models import DecisionAudit, Trade, get_db_session


def _judge_signal(audit: DecisionAudit) -> Optional[str]:
    j = audit.judge_decision or {}
    return (j.get("signal") or "").upper() or None


def _legacy_signal(audit: DecisionAudit) -> Optional[str]:
    l = audit.legacy_signal or {}
    return (l.get("signal") or "").upper() or None


def _confidence(audit: DecisionAudit) -> Optional[float]:
    j = audit.judge_decision or {}
    return j.get("confidence")


def _outcome_to_yes(pnl: Optional[float]) -> Optional[int]:
    """Map realized pnl > 0 to 1 (we 'won' this directional call), else 0."""
    if pnl is None:
        return None
    if pnl == 0:
        return None
    return 1 if pnl > 0 else 0


def _brier(pred: float, actual: int) -> float:
    return (pred - actual) ** 2


def _mcnemar_p(b: int, c: int) -> float:
    """Edge-cases-only McNemar p-value approximation using continuity-corrected chi-sq.

    b = trades where agentic won and legacy lost (counterfactual loss for legacy)
    c = trades where legacy won and agentic lost
    Returns one-sided p approximated via chi-square with df=1.
    """
    n = b + c
    if n == 0:
        return 1.0
    stat = ((abs(b - c) - 1) ** 2) / n if n > 0 else 0.0
    # Survival function of chi-square df=1 ~ erfc(sqrt(stat/2))
    return math.erfc(math.sqrt(stat / 2)) if stat > 0 else 1.0


def main() -> None:
    with get_db_session() as session:
        audits: List[DecisionAudit] = session.query(DecisionAudit).all()
        trades: List[Trade] = session.query(Trade).all()

    if not audits:
        print("No DecisionAudit rows yet. Run the system in shadow mode for a while first.")
        return

    print(f"Loaded {len(audits)} audits, {len(trades)} trades.")
    print()

    # Per-path counts.
    by_path = Counter(a.decision_path for a in audits)
    print("Audits by decision_path:")
    for path, n in by_path.items():
        print(f"  {path}: {n}")
    print()

    # Disagreement matrix (judge vs legacy_shadow).
    have_both = [a for a in audits if _judge_signal(a) and _legacy_signal(a)]
    print(f"Audits with BOTH judge and legacy_shadow signals: {len(have_both)}")
    if have_both:
        disagree = sum(1 for a in have_both if _judge_signal(a) != _legacy_signal(a))
        print(f"  Disagreement rate: {disagree / len(have_both) * 100:.1f}%")

        # 3x3 confusion: judge × legacy
        confusion: Dict[tuple, int] = defaultdict(int)
        for a in have_both:
            confusion[(_judge_signal(a), _legacy_signal(a))] += 1
        print("  Confusion matrix (judge \\ legacy):")
        labels = ["LONG", "SHORT", "NO_TRADE"]
        print("           " + "  ".join(f"{l:>10}" for l in labels))
        for j in labels:
            row = [confusion.get((j, l), 0) for l in labels]
            print(f"    {j:<10}" + "  ".join(f"{v:>10}" for v in row))
    print()

    # Per-path realized P&L.
    pnl_by_path: Dict[str, List[float]] = defaultdict(list)
    for t in trades:
        if t.realized_pnl is None:
            continue
        pnl_by_path[t.decision_path or "unknown"].append(t.realized_pnl)
    print("Realized P&L by decision_path (closed trades):")
    for path, pnls in pnl_by_path.items():
        n = len(pnls)
        tot = sum(pnls)
        mean = tot / n if n else 0
        wins = sum(1 for p in pnls if p > 0)
        print(f"  {path}: n={n}, total=${tot:.2f}, mean=${mean:.2f}, hit_rate={wins/n*100:.1f}%" if n else f"  {path}: n=0")
    print()

    # Brier score per path (judge calibrated_probability vs realized outcome on closed trades).
    brier_by_path: Dict[str, List[float]] = defaultdict(list)
    audit_by_ticker: Dict[str, DecisionAudit] = {}
    for a in audits:
        audit_by_ticker[a.ticker] = a  # last-write-wins; fine for smoke eval

    for t in trades:
        actual = _outcome_to_yes(t.realized_pnl)
        if actual is None:
            continue
        a = audit_by_ticker.get(t.ticker)
        if not a or a.calibrated_probability is None:
            continue
        # Direction-adjust: if trade side was 'no', actual flips.
        if (t.side or "").lower() == "no":
            actual = 1 - actual
        brier_by_path[a.decision_path or "unknown"].append(
            _brier(float(a.calibrated_probability), actual)
        )
    print("Brier score by decision_path (lower is better):")
    for path, brs in brier_by_path.items():
        if not brs:
            continue
        print(f"  {path}: n={len(brs)}, brier={sum(brs)/len(brs):.4f}")
    print()

    # McNemar-style sanity check across head-to-head trades.
    # b: agentic won, legacy would have lost
    # c: agentic lost, legacy would have won
    b = c = 0
    for a in have_both:
        # Best-effort: did this audit lead to a realized win for the actual decision_path?
        ticker_trades = [t for t in trades if t.ticker == a.ticker and t.realized_pnl is not None]
        if not ticker_trades:
            continue
        realized = sum(t.realized_pnl for t in ticker_trades)
        agentic_won = realized > 0
        # We only persisted the legacy shadow signal, not its hypothetical realized P&L.
        # Treat agreement as no-counter-factual; disagreement uses agentic outcome as proxy.
        if _judge_signal(a) != _legacy_signal(a):
            if agentic_won:
                b += 1
            else:
                c += 1
    print(f"McNemar-like comparison: agentic_won_disagreement={b}, agentic_lost_disagreement={c}, "
          f"p={_mcnemar_p(b, c):.4f}")
    print()
    print("Note: This is a smoke evaluation. Production validation needs longer runtime "
          "and proper resolved-market labels.")


if __name__ == "__main__":
    main()
