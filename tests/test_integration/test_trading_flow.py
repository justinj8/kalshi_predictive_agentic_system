"""
Integration Tests for Trading Flow

Tests the complete trading cycle from market fetch to execution.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


class TestFullTradeCycle:
    """Test complete trade flow from signal to execution"""
    
    def test_signal_to_execution_flow(self):
        """Test that a valid signal flows through to execution"""
        # This is a placeholder for full integration test
        # In production, would mock the Kalshi API and run full cycle
        pass
    
    def test_circuit_breaker_stops_trading(self):
        """Test that circuit breaker prevents trades when triggered"""
        pass
    
    def test_no_trade_on_low_confidence(self):
        """Test that low confidence signals are rejected"""
        pass


class TestConfidenceCalibration:
    """Tests for the confidence calibration system"""
    
    def test_hard_bounds_cap_at_85(self):
        """Confidence should never exceed 85%"""
        from src.utils.calibration_tracker import calibration_tracker
        
        result = calibration_tracker.apply_hard_bounds(95.0)
        assert result == 85.0, "Confidence should be capped at 85%"
    
    def test_hard_bounds_floor_at_30(self):
        """Confidence should never go below 30%"""
        from src.utils.calibration_tracker import calibration_tracker
        
        result = calibration_tracker.apply_hard_bounds(20.0)
        assert result == 30.0, "Confidence should have floor at 30%"
    
    def test_normal_confidence_unchanged(self):
        """Normal confidence values pass through unchanged"""
        from src.utils.calibration_tracker import calibration_tracker
        
        result = calibration_tracker.apply_hard_bounds(65.0)
        assert result == 65.0, "Normal confidence should be unchanged"


class TestEdgeDecayTracker:
    """Tests for edge decay tracking"""
    
    def test_fresh_edge_is_valid(self):
        """A just-detected edge should be valid"""
        from src.utils.edge_decay_tracker import EdgeDecayTracker
        
        tracker = EdgeDecayTracker()
        tracker.record_edge(
            ticker="TEST-123",
            signal="LONG",
            our_fair_value=0.65,
            market_price=0.55,
            confidence=75,
            reasoning="Test edge"
        )
        
        # Check immediately - should be valid
        check = tracker.check_edge_persistence("TEST-123", 0.55)
        assert check.still_valid, "Fresh edge should be valid"
        assert check.recommendation == 'trade', "Should recommend trade"
    
    def test_decayed_edge_is_skipped(self):
        """An edge that has mostly decayed should be skipped"""
        from src.utils.edge_decay_tracker import EdgeDecayTracker
        
        tracker = EdgeDecayTracker()
        tracker.record_edge(
            ticker="TEST-456",
            signal="LONG",
            our_fair_value=0.65,
            market_price=0.55,  # 10% edge
            confidence=75,
            reasoning="Test edge"
        )
        
        # Price moved to 0.62 - edge mostly gone
        check = tracker.check_edge_persistence("TEST-456", 0.62)
        # 7/10 = 70% decay
        assert not check.still_valid, "Heavily decayed edge should not be valid"
        assert check.recommendation == 'skip', "Should recommend skip"
    
    def test_unrecorded_edge_returns_skip(self):
        """Check for ticker with no recorded edge returns skip"""
        from src.utils.edge_decay_tracker import EdgeDecayTracker
        
        tracker = EdgeDecayTracker()
        check = tracker.check_edge_persistence("UNKNOWN-789", 0.50)
        assert not check.still_valid, "Unknown ticker should not be valid"


class TestExternalOddsComparison:
    """Tests for external odds comparison"""
    
    def test_meaningful_edge_recommends_trade(self):
        """When we have significant edge vs external, recommend trade"""
        from src.utils.external_odds_comparison import ExternalOddsComparison, ExternalOdds
        
        comp = ExternalOddsComparison()
        external = ExternalOdds(
            source="polymarket",
            probability=0.50,
            timestamp=datetime.utcnow()
        )
        
        # Our 70% vs their 50% = 20% edge
        analysis = comp.analyze_edge(70, "LONG", external)
        assert analysis.has_meaningful_edge, "20% edge should be meaningful"
        assert analysis.recommendation == 'trade'
    
    def test_no_edge_recommends_skip(self):
        """When edge is too small, recommend skip"""
        from src.utils.external_odds_comparison import ExternalOddsComparison, ExternalOdds
        
        comp = ExternalOddsComparison()
        external = ExternalOdds(
            source="polymarket",
            probability=0.60,
            timestamp=datetime.utcnow()
        )
        
        # Our 62% vs their 60% = 2% edge (too small)
        analysis = comp.analyze_edge(62, "LONG", external)
        assert not analysis.has_meaningful_edge, "2% edge should not be meaningful"
        assert analysis.recommendation == 'skip'


class TestBinaryExitStrategy:
    """Tests for binary market exit strategy"""
    
    def test_take_profit_at_threshold(self):
        """Should recommend exit at 40%+ profit"""
        from src.utils.binary_exit_strategy import BinaryExitStrategy
        from datetime import datetime, timedelta
        
        strategy = BinaryExitStrategy()
        close_date = datetime.utcnow() + timedelta(days=7)  # Far from expiry
        
        decision = strategy.evaluate_exit(
            ticker="TEST",
            entry_price=0.40,
            current_price=0.60,  # 50% profit
            position_side='long',
            market_close_date=close_date
        )
        
        assert decision.should_exit, "Should exit at 50% profit"
        assert decision.recommendation == 'take_profit'
    
    def test_cut_loss_at_threshold(self):
        """Should recommend exit at 35%+ loss"""
        from src.utils.binary_exit_strategy import BinaryExitStrategy
        from datetime import datetime, timedelta
        
        strategy = BinaryExitStrategy()
        close_date = datetime.utcnow() + timedelta(days=7)
        
        decision = strategy.evaluate_exit(
            ticker="TEST",
            entry_price=0.60,
            current_price=0.35,  # ~42% loss
            position_side='long',
            market_close_date=close_date
        )
        
        assert decision.should_exit, "Should exit at 40%+ loss"
        assert decision.recommendation == 'cut_loss'
    
    def test_hold_strong_position_near_expiry(self):
        """Should hold strong position even near expiry"""
        from src.utils.binary_exit_strategy import BinaryExitStrategy
        from datetime import datetime, timedelta
        
        strategy = BinaryExitStrategy()
        close_date = datetime.utcnow() + timedelta(hours=2)  # Very close to expiry
        
        decision = strategy.evaluate_exit(
            ticker="TEST",
            entry_price=0.50,
            current_price=0.85,  # Strong position
            position_side='long',
            market_close_date=close_date
        )
        
        assert not decision.should_exit, "Should hold strong position (85c) to expiry"


class TestDatabaseSessionLeak:
    """Tests for database session management"""
    
    def test_context_manager_closes_session(self):
        """Session should be closed after context manager exits"""
        from src.database.models import get_db_session
        
        # This test verifies the context manager works without errors
        try:
            with get_db_session() as session:
                # Do nothing, just verify it works
                pass
        except Exception as e:
            pytest.fail(f"Context manager raised exception: {e}")


class TestMockDataRealism:
    """Tests for realistic mock data"""
    
    def test_mock_data_has_realistic_spreads(self):
        """Mock data should have 4-8 cent spreads, not 2 cent"""
        from src.utils.kalshi_client import KalshiClient
        
        client = KalshiClient()
        markets = client._get_mock_markets()
        
        for market in markets:
            spread = market['yes_ask'] - market['yes_bid']
            assert spread >= 4, f"{market['ticker']} has unrealistically tight spread: {spread}c"
    
    def test_mock_data_includes_no_edge_market(self):
        """Mock data should include at least one no-edge market"""
        from src.utils.kalshi_client import KalshiClient
        
        client = KalshiClient()
        markets = client._get_mock_markets()
        
        # Look for a market priced near 50%
        near_50_markets = [
            m for m in markets
            if 45 <= m['yes_bid'] <= 55
        ]
        
        assert len(near_50_markets) > 0, "Should have at least one fairly-priced market"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
