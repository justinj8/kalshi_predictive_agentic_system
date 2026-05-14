"""Read-only FastAPI dashboard for J&J AI Studio."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from config.settings import settings
from src.database.models import (
    DecisionAudit,
    Position,
    Trade,
    TradingSession,
    get_db_session,
    init_database,
)
from src.monitoring.health_check import health_checker


security = HTTPBasic()
app = FastAPI(
    title="J&J AI Studio Kalshi Dashboard",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Authorization", "Content-Type"],
)


def require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """Protect read APIs with HTTP Basic auth."""
    username_ok = secrets.compare_digest(
        credentials.username,
        settings.dashboard_username,
    )
    password_ok = secrets.compare_digest(
        credentials.password,
        settings.dashboard_password,
    )
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid dashboard credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@app.on_event("startup")
def _startup() -> None:
    init_database()


@app.get("/api/health")
def api_health(_: str = Depends(require_auth)) -> Dict[str, Any]:
    return health_checker.get_status()


@app.get("/api/summary")
def api_summary(_: str = Depends(require_auth)) -> Dict[str, Any]:
    with get_db_session() as session:
        open_positions = session.query(Position).filter(Position.is_open == True).all()
        trades = session.query(Trade).all()
        sessions = (
            session.query(TradingSession)
            .order_by(TradingSession.timestamp.desc())
            .limit(50)
            .all()
        )
        realized_pnl = sum((t.realized_pnl or 0.0) for t in trades)
        unrealized_pnl = sum((p.unrealized_pnl or 0.0) for p in open_positions)
        position_value = sum((p.current_price or 0.0) * p.quantity for p in open_positions)
        cash_spent = sum((t.total_cost or 0.0) for t in trades if t.is_entry)
        cash_received = sum((t.total_cost or 0.0) for t in trades if not t.is_entry)
        cash_balance = settings.starting_capital - cash_spent + cash_received
        wins = sum(1 for t in trades if (t.realized_pnl or 0.0) > 0)
        closed = sum(1 for t in trades if t.realized_pnl is not None)
        pnl_curve = _build_pnl_curve(trades, sessions)

    return {
        "brand": "J&J AI Studio",
        "slogan": "An AI studio for Main Street, not Silicon Valley.",
        "mode": settings.trading_mode,
        "cash_balance": cash_balance,
        "portfolio_value": cash_balance + position_value,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "total_pnl": realized_pnl + unrealized_pnl,
        "open_positions": len(open_positions),
        "total_trades": len(trades),
        "win_rate": (wins / closed * 100.0) if closed else 0.0,
        "latest_cycle": pnl_curve[-1] if pnl_curve else None,
        "pnl_curve": pnl_curve,
    }


@app.get("/api/positions")
def api_positions(_: str = Depends(require_auth)) -> Dict[str, Any]:
    with get_db_session() as session:
        rows = (
            session.query(Position)
            .order_by(Position.opened_at.desc())
            .limit(100)
            .all()
        )
        positions = [
            {
                "position_id": p.position_id,
                "ticker": p.ticker,
                "title": p.market_title,
                "category": p.category,
                "side": p.side,
                "quantity": p.quantity,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "unrealized_pnl": p.unrealized_pnl,
                "unrealized_pnl_percent": p.unrealized_pnl_percent,
                "realized_pnl": p.realized_pnl,
                "is_open": p.is_open,
                "opened_at": _iso(p.opened_at),
                "closed_at": _iso(p.closed_at),
            }
            for p in rows
        ]
    return {"positions": positions}


@app.get("/api/opportunities")
def api_opportunities(_: str = Depends(require_auth)) -> Dict[str, Any]:
    with get_db_session() as session:
        rows = (
            session.query(DecisionAudit)
            .order_by(DecisionAudit.created_at.desc())
            .limit(50)
            .all()
        )
        opportunities = []
        for row in rows:
            judge = row.judge_decision or {}
            evidence = row.evidence_pack or {}
            opportunities.append(
                {
                    "id": row.id,
                    "created_at": _iso(row.created_at),
                    "ticker": row.ticker,
                    "decision_path": row.decision_path,
                    "signal": judge.get("signal", "NO_TRADE"),
                    "confidence": judge.get("confidence", 0),
                    "calibrated_probability": row.calibrated_probability,
                    "expected_return_pct": judge.get("expected_return_pct", 0),
                    "market_edge": judge.get("market_edge", ""),
                    "reasoning": judge.get("reasoning", ""),
                    "risk_factors": judge.get("risk_factors", []),
                    "summary": evidence.get("summary", ""),
                    "outcome_label": row.outcome_label,
                    "final_pnl": row.final_pnl,
                }
            )
    return {"opportunities": opportunities}


@app.get("/api/cycles")
def api_cycles(_: str = Depends(require_auth)) -> Dict[str, Any]:
    with get_db_session() as session:
        rows = (
            session.query(TradingSession)
            .order_by(TradingSession.timestamp.desc())
            .limit(100)
            .all()
        )
        cycles = [
            {
                "id": r.id,
                "timestamp": _iso(r.timestamp),
                "markets_scanned": r.markets_scanned or 0,
                "signals_generated": r.signals_generated or 0,
                "trades_executed": r.trades_executed or 0,
                "starting_balance": r.starting_balance,
                "ending_balance": r.ending_balance,
                "session_pnl": r.session_pnl,
                "circuit_breaker_triggered": bool(r.circuit_breaker_triggered),
                "circuit_breaker_reason": r.circuit_breaker_reason,
                "decision_path": getattr(r, "decision_path", "agentic_v1"),
                "errors": r.errors,
            }
            for r in rows
        ]
    return {"cycles": cycles}


@app.get("/api/costs")
def api_costs(_: str = Depends(require_auth)) -> Dict[str, Any]:
    cadences = [
        ("Every 5 min", 5, 6261, 8.85),
        ("Every 15 min", 15, 2087, 3.05),
        ("Every 30 min", 30, 1044, 1.60),
        ("Hourly", 60, 522, 0.88),
    ]
    llm_per_run = [0.50, 1.00, 3.00, 5.00]
    rows = []
    for label, minutes, runs, railway in cadences:
        rows.append(
            {
                "label": label,
                "minutes": minutes,
                "weekday_runs_per_month": runs,
                "railway_compute_storage_estimate": railway,
                "hobby_bill_estimate": max(5.0, railway),
                "llm_monthly": {
                    f"${cost:.2f}/run": round(cost * runs, 2)
                    for cost in llm_per_run
                },
            }
        )
    return {
        "assumptions": {
            "runtime": "Railway cron, python src/main.py --once, weekdays only",
            "resource_shape": "1 vCPU, 1 GB RAM, 2 minute average run, 1 GB volume",
            "llm_note": "LLM spend usually dominates Railway hosting cost.",
        },
        "cadences": rows,
    }


def _build_pnl_curve(trades: List[Trade], sessions: List[TradingSession]) -> List[Dict[str, Any]]:
    curve = []
    running = 0.0
    closed_trades = sorted(
        [t for t in trades if t.realized_pnl is not None],
        key=lambda t: t.timestamp,
    )
    for trade in closed_trades:
        running += trade.realized_pnl or 0.0
        curve.append(
            {
                "timestamp": _iso(trade.timestamp),
                "realized_pnl": running,
                "event": trade.ticker,
            }
        )
    if not curve:
        for session in sorted(sessions, key=lambda s: s.timestamp)[-30:]:
            curve.append(
                {
                    "timestamp": _iso(session.timestamp),
                    "realized_pnl": session.session_pnl or 0.0,
                    "event": "cycle",
                }
            )
    return curve


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


STATIC_DIR = Path(__file__).resolve().parents[2] / "dashboard" / "dist"


@app.get("/", include_in_schema=False, response_model=None)
def root() -> HTMLResponse | FileResponse:
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse(
        """
        <main style="font-family:Inter,system-ui,sans-serif;padding:48px;max-width:900px">
          <p style="letter-spacing:.12em;text-transform:uppercase;color:#47616b">J&J AI Studio</p>
          <h1>Kalshi Intelligence Dashboard</h1>
          <p>An AI studio for Main Street, not Silicon Valley.</p>
          <p>Build the React dashboard with <code>cd dashboard && npm install && npm run build</code>.</p>
          <p>Read-only API docs are at <a href="/api/docs">/api/docs</a>.</p>
        </main>
        """
    )


if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")
