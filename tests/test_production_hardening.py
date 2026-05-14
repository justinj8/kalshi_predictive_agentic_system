"""
Regression tests for production hardening changes.
"""
from datetime import datetime, timedelta
import sqlite3

import pytest


@pytest.fixture
def temp_database(tmp_path, monkeypatch):
    from config.settings import settings
    from src.database import models

    db_path = tmp_path / "trades.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(settings, "starting_capital", 100.0)
    models._engine = None
    models._Session = None
    models.init_database()
    yield db_path
    models._engine = None
    models._Session = None


def _market(ticker="TEST-VALID", yes_bid=45, yes_ask=51, oi=1000):
    from src.orchestrator.state_models import MarketData

    return MarketData(
        ticker=ticker,
        title=f"Will {ticker} resolve yes?",
        category="finance",
        yes_bid=yes_bid / 100.0,
        yes_ask=yes_ask / 100.0,
        no_bid=(100 - yes_ask) / 100.0,
        no_ask=(100 - yes_bid) / 100.0,
        volume_24h=10000,
        open_interest=oi,
        close_date=(datetime.utcnow() + timedelta(days=10)).isoformat() + "Z",
        status="open",
    )


def test_select_opportunity_uses_filtered_markets_only(monkeypatch):
    from config.settings import settings
    from src.orchestrator.langgraph_flow import orchestrator
    from src.orchestrator.state_models import TradingState

    monkeypatch.setattr(settings, "max_markets_per_cycle", 3)
    invalid = _market("TEST-INVALID", oi=10)
    valid = _market("TEST-VALID", oi=1000)
    state = TradingState(
        session_id="test",
        current_balance=100,
        all_markets=[invalid, valid],
        filtered_markets=[valid],
    )

    result = orchestrator._select_opportunity_node(state)

    assert result.current_market is not None
    assert result.current_market.market.ticker == "TEST-VALID"


def test_live_mode_refuses_mock_markets(monkeypatch):
    from config.settings import settings
    from src.utils.kalshi_client import KalshiClient

    monkeypatch.setattr(settings, "trading_mode", "live")
    client = KalshiClient()
    client.markets_api = None

    with pytest.raises(RuntimeError, match="Refusing to use mock data"):
        client.get_all_markets()


def test_ledger_balance_uses_trade_cashflows(temp_database):
    from src.database.models import Trade, get_db_session
    from src.orchestrator.langgraph_flow import orchestrator

    with get_db_session() as session:
        session.add(
            Trade(
                ticker="A",
                side="long",
                action="buy",
                quantity=10,
                price=0.40,
                total_cost=4.00,
                is_entry=True,
            )
        )
        session.add(
            Trade(
                ticker="A",
                side="long",
                action="sell",
                quantity=10,
                price=0.60,
                total_cost=6.00,
                is_entry=False,
                realized_pnl=2.00,
            )
        )

    assert orchestrator._get_current_balance() == pytest.approx(102.0)


def test_execution_result_and_trade_share_position_id(temp_database, monkeypatch):
    from config.settings import settings
    from src.agents.execution_agent import ExecutionAgent
    from src.database.models import Trade, get_db_session
    from src.orchestrator.state_models import MarketAnalysis, PositionSizing, TradingSignal, TradingState

    monkeypatch.setattr(settings, "trading_mode", "paper")
    agent = ExecutionAgent()
    market = _market("TEST-LINK")
    signal = TradingSignal(
        ticker="TEST-LINK",
        signal="LONG",
        confidence=75,
        expected_return=15,
        reasoning="test",
        market_edge="test",
    )
    sizing = PositionSizing(
        ticker="TEST-LINK",
        signal="LONG",
        recommended_size=2,
        risk_amount=0.1,
        max_loss=0.1,
        position_value=1.0,
        stop_loss_price=0.4,
        take_profit_price=0.8,
        risk_reward_ratio=2.0,
        reasoning="test",
        entry_limit_price=0.50,
        fee_adjusted_ev_per_contract=0.02,
    )
    state = TradingState(session_id="test", current_balance=100)

    result = agent.execute_trade(signal, sizing, MarketAnalysis(market=market), state)

    with get_db_session() as session:
        trade = session.query(Trade).one()
        assert result.position_id
        assert trade.position_id == result.position_id


def test_schema_migration_adds_missing_decision_path(tmp_path, monkeypatch):
    from config.settings import settings
    from src.database import models

    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY, timestamp DATETIME NOT NULL, ticker VARCHAR(50) NOT NULL, side VARCHAR(10) NOT NULL, action VARCHAR(10) NOT NULL, quantity INTEGER NOT NULL, price FLOAT NOT NULL, total_cost FLOAT NOT NULL)")
    conn.execute("CREATE TABLE trading_sessions (id INTEGER PRIMARY KEY, timestamp DATETIME NOT NULL)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    models._engine = None
    models._Session = None
    models.init_database()

    conn = sqlite3.connect(db_path)
    trade_cols = {row[1] for row in conn.execute("PRAGMA table_info(trades)").fetchall()}
    session_cols = {row[1] for row in conn.execute("PRAGMA table_info(trading_sessions)").fetchall()}
    conn.close()

    assert "decision_path" in trade_cols
    assert "decision_path" in session_cols
    models._engine = None
    models._Session = None


def test_capacity_gate_prevents_llm_work(monkeypatch):
    from config.settings import settings
    from src.orchestrator.langgraph_flow import orchestrator
    from src.orchestrator.state_models import MarketAnalysis, TradingState

    monkeypatch.setattr(settings, "max_daily_trades", 1)
    state = TradingState(
        session_id="test",
        current_balance=100,
        daily_trades=1,
        top_opportunities=[MarketAnalysis(market=_market("TEST-CAP"))],
    )

    result = orchestrator._select_opportunity_node(state)

    assert result.current_market is None
    assert result.top_opportunities == []


def test_fee_negative_position_is_blocked():
    from src.agents.policy_self_critic_agent import policy_agent
    from src.orchestrator.state_models import MarketAnalysis, PositionSizing, TradingSignal, TradingState

    signal = TradingSignal(
        ticker="TEST-FEE",
        signal="LONG",
        confidence=80,
        expected_return=20,
        reasoning="test",
        market_edge="test",
    )
    sizing = PositionSizing(
        ticker="TEST-FEE",
        signal="LONG",
        recommended_size=1,
        risk_amount=0.1,
        max_loss=0.1,
        position_value=0.5,
        stop_loss_price=0.4,
        take_profit_price=0.8,
        risk_reward_ratio=2.0,
        reasoning="test",
        fee_adjusted_ev_per_contract=-0.01,
    )

    ok, reason = policy_agent._rule_based_checks(
        signal,
        sizing,
        MarketAnalysis(market=_market("TEST-FEE", yes_bid=49, yes_ask=51, oi=1000)),
        TradingState(session_id="test", current_balance=100),
    )

    assert not ok
    assert "Fee-adjusted EV" in reason


def test_stale_data_triggers_circuit_breaker():
    from src.agents.data_qa_circuit_breaker import circuit_breaker
    from src.orchestrator.state_models import TradingState

    state = TradingState(
        session_id="test",
        current_balance=100,
        markets_scanned=1,
        all_markets=[_market("TEST-STALE")],
        timestamp=datetime.utcnow() - timedelta(minutes=6),
    )

    result = circuit_breaker.validate_and_check(state)

    assert result.circuit_breaker.triggered
    assert "stale" in result.circuit_breaker.reason.lower()


def test_dashboard_api_contract(temp_database, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from config.settings import settings
    from src.dashboard.app import app

    monkeypatch.setattr(settings, "dashboard_username", "admin")
    monkeypatch.setattr(settings, "dashboard_password", "secret")
    client = TestClient(app)
    response = client.get(
        "/api/summary",
        auth=("admin", "secret"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["brand"] == "J&J AI Studio"
    assert "portfolio_value" in payload
