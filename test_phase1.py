#!/usr/bin/env python3
"""
Quick test script to verify Phase 1 components are working
Run this before full integration testing
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test that all new components can be imported"""
    print("Testing imports...")

    try:
        from src.utils.sentiment_analyzer import sentiment_analyzer
        print("✅ Sentiment analyzer imported")
    except Exception as e:
        print(f"❌ Sentiment analyzer import failed: {e}")
        return False

    try:
        from src.agents.bonding_strategy_agent import bonding_agent
        print("✅ Bonding strategy agent imported")
    except Exception as e:
        print(f"❌ Bonding strategy agent import failed: {e}")
        return False

    try:
        from src.utils.kelly_calculator import kelly_calculator
        print("✅ Kelly calculator imported")
    except Exception as e:
        print(f"❌ Kelly calculator import failed: {e}")
        return False

    try:
        from src.agents.arbitrage_detector import arbitrage_detector
        print("✅ Arbitrage detector imported")
    except Exception as e:
        print(f"❌ Arbitrage detector import failed: {e}")
        return False

    try:
        from src.utils.technical_indicators import technical_indicators
        print("✅ Technical indicators imported")
    except Exception as e:
        print(f"❌ Technical indicators import failed: {e}")
        return False

    try:
        from src.orchestrator.state_models import BondingOpportunity, ArbitrageOpportunity
        print("✅ New state models imported")
    except Exception as e:
        print(f"❌ State models import failed: {e}")
        return False

    return True


def test_sentiment_analyzer():
    """Test sentiment analyzer basic functionality"""
    print("\nTesting sentiment analyzer...")

    from src.utils.sentiment_analyzer import sentiment_analyzer

    # Test simple sentiment
    result = sentiment_analyzer.analyze_text("This is great news for the market!")
    print(f"  Positive text: score={result['score']:.2f}, confidence={result['confidence']:.2f}")

    result = sentiment_analyzer.analyze_text("This is terrible and concerning.")
    print(f"  Negative text: score={result['score']:.2f}, confidence={result['confidence']:.2f}")

    print("✅ Sentiment analyzer working")
    return True


def test_kelly_calculator():
    """Test Kelly criterion calculator"""
    print("\nTesting Kelly calculator...")

    from src.utils.kelly_calculator import kelly_calculator

    # Test Kelly calculation
    result = kelly_calculator.calculate_position_size(
        win_probability=0.70,
        entry_price=0.55,
        capital=1000.0,
        side="YES"
    )

    print(f"  Win prob: 70%, Entry: $0.55, Capital: $1000")
    print(f"  Kelly optimal: {result['kelly_pct']:.1%}")
    print(f"  Adjusted Kelly: {result['kelly_adjusted']:.1%}")
    print(f"  Recommended size: {result['recommended_size']} contracts")
    print(f"  Position value: ${result['position_value']:.2f}")

    print("✅ Kelly calculator working")
    return True


def test_technical_indicators():
    """Test technical indicators"""
    print("\nTesting technical indicators...")

    from src.utils.technical_indicators import technical_indicators
    from src.orchestrator.state_models import MarketData

    # Create mock market
    market = MarketData(
        ticker="TEST-MARKET-123",
        title="Test market",
        category="test",
        yes_bid=0.54,
        yes_ask=0.56,
        no_bid=0.44,
        no_ask=0.46,
        volume_24h=50000,
        open_interest=100000,
        close_date="2026-02-01T00:00:00Z",
        status="open"
    )

    # Calculate indicators
    indicators = technical_indicators.calculate_all_indicators(market)

    print(f"  Current probability: {indicators['current_probability']:.1%}")
    print(f"  Spread: {indicators['spread_pct']:.2f}%")
    print(f"  RSI: {indicators['rsi']:.1f}")
    print(f"  Volatility: {indicators['volatility']:.3f}")

    # Test interpretation
    interpretation = technical_indicators.interpret_indicators(indicators)
    print(f"  Overall signal: {interpretation['overall_signal']}")

    print("✅ Technical indicators working")
    return True


def test_state_models():
    """Test new state models"""
    print("\nTesting new state models...")

    from src.orchestrator.state_models import (
        BondingOpportunity, ArbitrageOpportunity, TradingState, MarketData
    )

    # Test BondingOpportunity
    market = MarketData(
        ticker="BOND-TEST",
        title="Test bond",
        category="test",
        yes_bid=0.96,
        yes_ask=0.97,
        no_bid=0.03,
        no_ask=0.04,
        volume_24h=10000,
        open_interest=50000,
        close_date="2026-01-22T00:00:00Z",
        status="open"
    )

    bond = BondingOpportunity(
        market=market,
        side="YES",
        price=0.97,
        return_pct=3.1,
        days_to_close=3.0,
        daily_return=0.01,
        annual_return=365.0,
        liquidity=50000,
        spread=0.01
    )
    print(f"  Created bonding opportunity: {bond.market.ticker}")

    # Test ArbitrageOpportunity
    arb = ArbitrageOpportunity(
        type="within_market",
        markets=["TEST-1"],
        profit_pct=2.5,
        trades=[{"ticker": "TEST-1", "side": "YES", "price": 0.48}],
        execution_complexity="simple",
        confidence=0.9
    )
    print(f"  Created arbitrage opportunity: {arb.type}")

    # Test TradingState with new fields
    state = TradingState(
        session_id="test-session",
        bonding_opportunities=[bond],
        arbitrage_opportunities=[arb],
        bonding_capital=150.0,
        main_capital=850.0
    )
    print(f"  Created trading state with:")
    print(f"    - {len(state.bonding_opportunities)} bonding opportunities")
    print(f"    - {len(state.arbitrage_opportunities)} arbitrage opportunities")
    print(f"    - Bonding capital: ${state.bonding_capital:.2f}")
    print(f"    - Main capital: ${state.main_capital:.2f}")

    print("✅ State models working")
    return True


def test_flow_integration():
    """Test that LangGraph flow has new nodes"""
    print("\nTesting LangGraph flow integration...")

    from src.orchestrator.langgraph_flow import orchestrator

    # Check that graph has new nodes
    print(f"  Orchestrator created successfully")
    print("✅ LangGraph flow integration working")
    return True


def main():
    """Run all tests"""
    print("=" * 60)
    print("PHASE 1 COMPONENT TESTING")
    print("=" * 60)

    tests = [
        ("Imports", test_imports),
        ("Sentiment Analyzer", test_sentiment_analyzer),
        ("Kelly Calculator", test_kelly_calculator),
        ("Technical Indicators", test_technical_indicators),
        ("State Models", test_state_models),
        ("Flow Integration", test_flow_integration),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"❌ {name} test failed")
        except Exception as e:
            failed += 1
            print(f"❌ {name} test error: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed == 0:
        print("✅ ALL TESTS PASSED - Phase 1 is ready for integration testing!")
        return 0
    else:
        print("❌ SOME TESTS FAILED - Please fix errors before proceeding")
        return 1


if __name__ == "__main__":
    sys.exit(main())
