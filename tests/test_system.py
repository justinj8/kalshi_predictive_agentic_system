"""
Basic system tests
"""
import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """Test that all modules can be imported"""
    from src.utils.kalshi_client import kalshi_client
    from src.utils.news_fetcher import news_fetcher
    from src.agents.market_data_fetcher import market_data_fetcher
    from src.agents.data_qa_circuit_breaker import circuit_breaker
    from src.agents.signal_selection_agent import signal_agent
    from src.agents.risk_allocation_agent import risk_agent
    from src.agents.policy_self_critic_agent import policy_agent
    from src.agents.execution_agent import execution_agent
    from src.agents.position_manager import position_manager
    from src.orchestrator.langgraph_flow import orchestrator

    assert kalshi_client is not None
    assert news_fetcher is not None
    assert market_data_fetcher is not None
    assert circuit_breaker is not None
    assert signal_agent is not None
    assert risk_agent is not None
    assert policy_agent is not None
    assert execution_agent is not None
    assert position_manager is not None
    assert orchestrator is not None


def test_database_initialization():
    """Test database initialization"""
    from src.database.models import init_database
    engine = init_database()
    assert engine is not None


def test_config_loading():
    """Test configuration loading"""
    from config.settings import settings
    assert settings.starting_capital > 0
    assert settings.risk_per_trade_percent > 0
    assert settings.llm_model is not None


def test_market_data_fetcher():
    """Test market data fetching"""
    from src.agents.market_data_fetcher import market_data_fetcher
    from src.orchestrator.state_models import TradingState

    state = TradingState(
        session_id="test",
        current_balance=1000.0
    )

    # This should work even in mock mode
    result_state = market_data_fetcher.fetch_all_markets(state)
    assert result_state.markets_scanned >= 0


def test_circuit_breaker():
    """Test circuit breaker"""
    from src.agents.data_qa_circuit_breaker import circuit_breaker
    from src.orchestrator.state_models import TradingState

    state = TradingState(
        session_id="test",
        current_balance=1000.0,
        markets_scanned=10
    )

    result_state = circuit_breaker.validate_and_check(state)
    assert result_state.circuit_breaker is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
