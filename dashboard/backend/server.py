"""Cinematic dashboard backend.

A tiny FastAPI app that reads the SQLite at data/trades.db and exposes a single
/api/snapshot endpoint with everything the React dashboard needs to render one
frame. The dashboard polls this every 2-3 seconds.

Run:
    uvicorn dashboard.backend.server:app --reload --port 8765
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("KALSHI_DB_PATH", REPO_ROOT / "data" / "trades.db"))

app = FastAPI(title="Kalshi Pit Wall", version="1.0.0")

# Permissive CORS for the Vite dev server; the frontend is served separately.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _rows(cur: sqlite3.Cursor) -> List[Dict[str, Any]]:
    return [dict(r) for r in cur.fetchall()]


def _table_exists(cur: sqlite3.Cursor, name: str) -> bool:
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    )
    return cur.fetchone() is not None


def _columns(cur: sqlite3.Cursor, table: str) -> set:
    """Return the column names present on `table`. Empty if missing."""
    try:
        cur.execute(f"PRAGMA table_info({table})")
        return {row["name"] for row in cur.fetchall()}
    except sqlite3.Error:
        return set()


def _select(
    cur: sqlite3.Cursor,
    table: str,
    requested: List[str],
    *,
    where: str = "",
    order_by: str = "",
    limit: Optional[int] = None,
    params: Optional[tuple] = None,
) -> List[Dict[str, Any]]:
    """SELECT only the columns that exist on `table`. Missing requested columns
    show up as None in the row dicts. Lets the dashboard work against older DB
    schemas without the new agentic columns (e.g. `decision_path`)."""
    have = _columns(cur, table)
    if not have:
        return []
    have_cols = [c for c in requested if c in have]
    if not have_cols:
        return []
    sql = f"SELECT {', '.join(have_cols)} FROM {table}"
    if where:
        sql += f" WHERE {where}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql, params or ())
    rows = _rows(cur)
    # Pad missing columns so the frontend always sees the same shape.
    for r in rows:
        for c in requested:
            if c not in r:
                r[c] = None
    return rows


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/heartbeat")
def heartbeat() -> Dict[str, Any]:
    """Liveness probe. The frontend uses this to detect the system is up."""
    return {
        "ts": datetime.utcnow().isoformat() + "Z",
        "db_exists": DB_PATH.exists(),
        "db_path": str(DB_PATH),
    }


@app.get("/api/snapshot")
def snapshot() -> Dict[str, Any]:
    """Return everything the dashboard needs to render one frame.

    Defensive: handles a missing or schema-less DB gracefully so the dashboard
    can still render its 'standby' state when the trading system hasn't run.
    """
    if not DB_PATH.exists():
        return _empty_snapshot(reason=f"DB not found at {DB_PATH}")

    try:
        with _connect() as conn:
            cur = conn.cursor()
            data: Dict[str, Any] = {
                "ts": datetime.utcnow().isoformat() + "Z",
                "portfolio": _portfolio(cur),
                "positions": _open_positions(cur),
                "trades_recent": _recent_trades(cur, limit=20),
                "sessions_recent": _recent_sessions(cur, limit=12),
                "decisions_recent": _recent_decisions(cur, limit=8),
                "lessons_recent": _recent_lessons(cur, limit=6),
                "agentic_status": _agentic_status(),
                "markets_ticker": _markets_ticker(cur, limit=30),
            }
            return data
    except Exception as exc:  # noqa: BLE001 - surface for dashboard to display
        return _empty_snapshot(reason=str(exc))


def _empty_snapshot(reason: str) -> Dict[str, Any]:
    return {
        "ts": datetime.utcnow().isoformat() + "Z",
        "standby": True,
        "reason": reason,
        "portfolio": {
            "current_balance": 0.0,
            "starting_balance": 0.0,
            "total_pnl": 0.0,
            "total_pnl_pct": 0.0,
            "daily_pnl": 0.0,
            "open_positions": 0,
            "win_rate": 0.0,
            "total_trades": 0,
            "peak_balance": 0.0,
            "current_drawdown": 0.0,
        },
        "positions": [],
        "trades_recent": [],
        "sessions_recent": [],
        "decisions_recent": [],
        "lessons_recent": [],
        "agentic_status": _agentic_status(),
        "markets_ticker": [],
    }


# ---------------------------------------------------------------------------
# Data shapers
# ---------------------------------------------------------------------------


def _portfolio(cur: sqlite3.Cursor) -> Dict[str, Any]:
    starting_balance = float(os.environ.get("STARTING_CAPITAL", 100.0))

    if _table_exists(cur, "performance_metrics"):
        cur.execute(
            "SELECT * FROM performance_metrics ORDER BY calculated_at DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row:
            d = dict(row)
            return {
                "current_balance": d.get("current_balance") or starting_balance,
                "starting_balance": starting_balance,
                "total_pnl": d.get("total_pnl") or 0.0,
                "total_pnl_pct": d.get("total_pnl_percent") or 0.0,
                "daily_pnl": _daily_pnl(cur),
                "open_positions": d.get("current_positions") or 0,
                "win_rate": d.get("win_rate") or 0.0,
                "total_trades": d.get("total_trades") or 0,
                "winning_trades": d.get("winning_trades") or 0,
                "losing_trades": d.get("losing_trades") or 0,
                "peak_balance": d.get("peak_balance") or starting_balance,
                "current_drawdown": d.get("current_drawdown") or 0.0,
                "max_drawdown": d.get("max_drawdown") or 0.0,
                "sharpe_ratio": d.get("sharpe_ratio"),
                "average_win": d.get("average_win") or 0.0,
                "average_loss": d.get("average_loss") or 0.0,
                "largest_win": d.get("largest_win") or 0.0,
                "largest_loss": d.get("largest_loss") or 0.0,
            }

    # Fallback: synthesize from trades.
    total_pnl = 0.0
    winning = 0
    total = 0
    if _table_exists(cur, "trades"):
        cur.execute(
            "SELECT realized_pnl FROM trades WHERE realized_pnl IS NOT NULL"
        )
        for r in cur.fetchall():
            v = r["realized_pnl"] or 0.0
            total_pnl += v
            total += 1
            if v > 0:
                winning += 1
    open_positions = 0
    if _table_exists(cur, "positions"):
        cur.execute("SELECT COUNT(*) AS n FROM positions WHERE is_open = 1")
        open_positions = cur.fetchone()["n"] or 0

    return {
        "current_balance": starting_balance + total_pnl,
        "starting_balance": starting_balance,
        "total_pnl": total_pnl,
        "total_pnl_pct": (total_pnl / starting_balance * 100) if starting_balance else 0.0,
        "daily_pnl": _daily_pnl(cur),
        "open_positions": open_positions,
        "win_rate": (winning / total * 100) if total else 0.0,
        "total_trades": total,
        "winning_trades": winning,
        "losing_trades": total - winning,
        "peak_balance": starting_balance + max(0.0, total_pnl),
        "current_drawdown": 0.0,
        "max_drawdown": 0.0,
        "sharpe_ratio": None,
        "average_win": 0.0,
        "average_loss": 0.0,
        "largest_win": 0.0,
        "largest_loss": 0.0,
    }


def _daily_pnl(cur: sqlite3.Cursor) -> float:
    if not _table_exists(cur, "trades"):
        return 0.0
    since = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    cur.execute(
        "SELECT COALESCE(SUM(realized_pnl), 0) AS pnl FROM trades "
        "WHERE realized_pnl IS NOT NULL AND timestamp >= ?",
        (since,),
    )
    row = cur.fetchone()
    return float(row["pnl"]) if row else 0.0


def _open_positions(cur: sqlite3.Cursor) -> List[Dict[str, Any]]:
    rows = _select(
        cur,
        "positions",
        [
            "position_id",
            "ticker",
            "market_title",
            "category",
            "side",
            "quantity",
            "entry_price",
            "current_price",
            "stop_loss",
            "take_profit",
            "unrealized_pnl",
            "unrealized_pnl_percent",
            "opened_at",
        ],
        where="is_open = 1",
        order_by="opened_at DESC",
        limit=20,
    )
    for r in rows:
        ep = r.get("entry_price") or 0.0
        cp = r.get("current_price") or ep
        r["price_delta"] = (cp - ep) if cp and ep else 0.0
        r["price_delta_pct"] = ((cp - ep) / ep * 100) if ep else 0.0
    return rows


def _recent_trades(cur: sqlite3.Cursor, limit: int) -> List[Dict[str, Any]]:
    return _select(
        cur,
        "trades",
        [
            "timestamp",
            "ticker",
            "market_title",
            "category",
            "side",
            "action",
            "quantity",
            "price",
            "total_cost",
            "realized_pnl",
            "pnl_percent",
            "signal_confidence",
            "decision_path",
        ],
        order_by="timestamp DESC",
        limit=limit,
    )


def _recent_sessions(cur: sqlite3.Cursor, limit: int) -> List[Dict[str, Any]]:
    return _select(
        cur,
        "trading_sessions",
        [
            "timestamp",
            "markets_scanned",
            "signals_generated",
            "trades_executed",
            "starting_balance",
            "ending_balance",
            "session_pnl",
            "circuit_breaker_triggered",
            "circuit_breaker_reason",
            "opportunities_analyzed",
            "decision_path",
        ],
        order_by="timestamp DESC",
        limit=limit,
    )


def _recent_decisions(cur: sqlite3.Cursor, limit: int) -> List[Dict[str, Any]]:
    rows = _select(
        cur,
        "decision_audits",
        [
            "id",
            "created_at",
            "ticker",
            "decision_path",
            "judge_decision",
            "calibrated_probability",
            "recalled_lesson_ids",
            "thinking_tokens_used",
            "final_pnl",
            "outcome_label",
        ],
        order_by="created_at DESC",
        limit=limit,
    )
    # Flatten JSON-as-text fields for the frontend.
    import json as _json

    for r in rows:
        jd = r.get("judge_decision")
        if isinstance(jd, str):
            try:
                r["judge_decision"] = _json.loads(jd)
            except Exception:
                r["judge_decision"] = None
        lessons = r.get("recalled_lesson_ids")
        if isinstance(lessons, str):
            try:
                r["recalled_lesson_ids"] = _json.loads(lessons)
            except Exception:
                r["recalled_lesson_ids"] = []
    return rows


def _recent_lessons(cur: sqlite3.Cursor, limit: int) -> List[Dict[str, Any]]:
    # SUBSTR over text in SQL would require column knowledge, so we trim in Python.
    rows = _select(
        cur,
        "lessons",
        [
            "id",
            "created_at",
            "ticker",
            "category",
            "lesson_type",
            "text",
            "outcome_pnl",
            "source_agent",
        ],
        order_by="created_at DESC",
        limit=limit,
    )
    for r in rows:
        if isinstance(r.get("text"), str):
            r["text"] = r["text"][:320]
    return rows


def _markets_ticker(cur: sqlite3.Cursor, limit: int) -> List[Dict[str, Any]]:
    """Most recently snapshotted markets, for the scrolling tape."""
    rows = _select(
        cur,
        "market_snapshots",
        [
            "ticker",
            "title",
            "category",
            "yes_bid",
            "yes_ask",
            "no_bid",
            "no_ask",
            "volume_24h",
            "open_interest",
            "timestamp",
        ],
        order_by="timestamp DESC",
        limit=limit * 3,  # fetch extra so dedup still yields ~limit
    )
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for r in rows:
        t = r.get("ticker")
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(r)
        if len(out) >= limit:
            break
    return out


def _agentic_status() -> Dict[str, Any]:
    """Mirror the relevant settings flags. Best-effort import."""
    try:
        from config.settings import settings as s  # type: ignore

        return {
            "decision_path": "agentic_v1" if s.agentic_decision_path else "legacy",
            "shadow_legacy": bool(s.shadow_legacy),
            "judge_model": s.judge_model,
            "specialist_model": s.specialist_model,
            "cheap_model": s.cheap_model,
            "enable_web_search": bool(s.enable_web_search),
            "enable_debate": bool(s.enable_debate),
            "enable_memory": bool(s.enable_memory),
            "enable_extended_thinking": bool(s.enable_extended_thinking),
            "trading_mode": s.trading_mode,
            "starting_capital": float(s.starting_capital),
        }
    except Exception:
        return {
            "decision_path": "unknown",
            "shadow_legacy": False,
            "judge_model": "n/a",
            "specialist_model": "n/a",
            "cheap_model": "n/a",
            "enable_web_search": False,
            "enable_debate": False,
            "enable_memory": False,
            "enable_extended_thinking": False,
            "trading_mode": "n/a",
            "starting_capital": 0.0,
        }
