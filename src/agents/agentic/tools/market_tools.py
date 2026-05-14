"""Kalshi market tools: orderbook, history, related markets, indicators."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger
from src.utils.kalshi_client import kalshi_client
from src.utils.technical_indicators import technical_indicators
from src.orchestrator.state_models import MarketData

logger = get_logger(__name__)


def _market_to_data(raw: Dict[str, Any]) -> MarketData:
    """Normalize a Kalshi market dict into our MarketData pydantic model."""
    return MarketData(
        ticker=raw.get("ticker", ""),
        title=raw.get("title", raw.get("subtitle", "")),
        category=raw.get("category", "unknown"),
        yes_bid=float(raw.get("yes_bid", 0) or 0) / 100.0
        if (raw.get("yes_bid") or 0) > 1
        else float(raw.get("yes_bid", 0) or 0),
        yes_ask=float(raw.get("yes_ask", 0) or 0) / 100.0
        if (raw.get("yes_ask") or 0) > 1
        else float(raw.get("yes_ask", 0) or 0),
        no_bid=float(raw.get("no_bid", 0) or 0) / 100.0
        if (raw.get("no_bid") or 0) > 1
        else float(raw.get("no_bid", 0) or 0),
        no_ask=float(raw.get("no_ask", 0) or 0) / 100.0
        if (raw.get("no_ask") or 0) > 1
        else float(raw.get("no_ask", 0) or 0),
        volume_24h=float(raw.get("volume_24h", 0) or 0),
        open_interest=float(raw.get("open_interest", 0) or 0),
        close_date=str(raw.get("close_time") or raw.get("close_date") or ""),
        status=str(raw.get("status", "open")),
        metadata=raw,
    )


def get_market_orderbook(ticker: str) -> Dict[str, Any]:
    """Return order book with computed imbalance and depth."""
    book = kalshi_client.get_orderbook(ticker) or {}
    yes_book = book.get("yes", []) or []
    no_book = book.get("no", []) or []

    def _depth(side: List[Any]) -> float:
        total = 0.0
        for level in side:
            try:
                # Kalshi format may be [price, size] or {"price": ..., "quantity": ...}.
                if isinstance(level, dict):
                    size = float(level.get("quantity", level.get("count", 0)) or 0)
                else:
                    size = float(level[1])
                total += size
            except (IndexError, KeyError, TypeError, ValueError):
                continue
        return total

    yes_depth = _depth(yes_book)
    no_depth = _depth(no_book)
    total_depth = yes_depth + no_depth
    imbalance = (yes_depth - no_depth) / total_depth if total_depth > 0 else 0.0

    return {
        "ok": True,
        "ticker": ticker,
        "yes_levels": yes_book[:10],
        "no_levels": no_book[:10],
        "yes_depth": yes_depth,
        "no_depth": no_depth,
        "order_book_imbalance": imbalance,
        "imbalance_signal": (
            "yes_pressure" if imbalance > 0.2 else
            "no_pressure" if imbalance < -0.2 else
            "balanced"
        ),
    }


def get_market_history(ticker: str, limit: int = 100) -> Dict[str, Any]:
    """Return recent trades + summary stats."""
    trades = kalshi_client.get_trades(ticker, limit=limit) or []
    if not trades:
        return {"ok": True, "ticker": ticker, "count": 0, "trades": [], "summary": {}}

    prices: List[float] = []
    volumes: List[float] = []
    for t in trades:
        try:
            p = t.get("price") or t.get("yes_price")
            if p is None:
                continue
            pf = float(p)
            if pf > 1:
                pf = pf / 100.0
            prices.append(pf)
            volumes.append(float(t.get("count", 1) or 1))
        except (TypeError, ValueError):
            continue

    if not prices:
        return {"ok": True, "ticker": ticker, "count": 0, "trades": [], "summary": {}}

    summary = {
        "n": len(prices),
        "first": prices[-1],
        "last": prices[0],
        "high": max(prices),
        "low": min(prices),
        "mean": sum(prices) / len(prices),
        "total_volume": sum(volumes),
        "price_change_pct": ((prices[0] - prices[-1]) / prices[-1] * 100) if prices[-1] else 0.0,
    }
    return {
        "ok": True,
        "ticker": ticker,
        "count": len(prices),
        "summary": summary,
        # Truncate trade list for token economy.
        "trades_sample": trades[:20],
    }


def get_related_markets(ticker: str, k: int = 5) -> Dict[str, Any]:
    """Find related markets sharing an event-ticker prefix.

    Kalshi convention: tickers look like EVENT-SUBMARKET, where everything
    before the first dash is the event id. This returns sibling markets.
    """
    prefix = ticker.split("-")[0] if "-" in ticker else ticker
    try:
        # Fetch wide net then filter; many APIs don't support prefix search.
        markets = kalshi_client.get_all_markets(status="open", limit=500) or []
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "related": []}

    related: List[Dict[str, Any]] = []
    for m in markets:
        m_ticker = m.get("ticker", "")
        if m_ticker == ticker:
            continue
        if not m_ticker.startswith(prefix):
            continue
        related.append(
            {
                "ticker": m_ticker,
                "title": m.get("title") or m.get("subtitle", ""),
                "yes_ask": m.get("yes_ask"),
                "no_ask": m.get("no_ask"),
                "similarity": 1.0,  # Prefix match -> treat as direct sibling
            }
        )
        if len(related) >= k:
            break

    return {"ok": True, "ticker": ticker, "prefix": prefix, "related": related[:k]}


def calculate_technical_indicators(ticker: str) -> Dict[str, Any]:
    """Return indicators + interpretation for a ticker."""
    raw = kalshi_client.get_market(ticker)
    if not raw:
        return {"ok": False, "error": f"market {ticker} not found", "indicators": {}}

    try:
        market = _market_to_data(raw)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"normalize failed: {exc}", "indicators": {}}

    # Best-effort historical prices: pull trade history.
    historical: Optional[List[float]] = None
    try:
        trades = kalshi_client.get_trades(ticker, limit=100) or []
        prices = []
        for t in trades:
            p = t.get("price") or t.get("yes_price")
            if p is None:
                continue
            try:
                pf = float(p)
                if pf > 1:
                    pf = pf / 100.0
                prices.append(pf)
            except (TypeError, ValueError):
                continue
        if prices:
            historical = list(reversed(prices))  # oldest first
    except Exception:  # noqa: BLE001
        historical = None

    try:
        indicators = technical_indicators.calculate_all_indicators(
            market=market, historical_prices=historical
        )
        interp = technical_indicators.interpret_indicators(indicators)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "indicators": {}}

    return {
        "ok": True,
        "ticker": ticker,
        "indicators": indicators,
        "interpretation": interp,
        "had_history": historical is not None,
    }
