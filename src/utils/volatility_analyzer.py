"""
Volatility Analyzer
Calculates volatility metrics and adjusts position sizing based on volatility regime
"""
from typing import Dict, List, Optional, Any
import statistics
from src.utils.logger import get_logger
from src.orchestrator.state_models import MarketData

logger = get_logger(__name__)


class VolatilityAnalyzer:
    """
    Analyzes market volatility and adjusts position sizing

    Key concepts:
    - Historical volatility: Standard deviation of returns
    - Volatility regimes: Low/Medium/High
    - Position sizing adjustment: Reduce size in high volatility
    """

    def __init__(self):
        """Initialize volatility analyzer"""
        # Target volatility for "normal" regime
        self.target_volatility = 0.03  # 3% daily volatility

    def calculate_historical_volatility(
        self,
        historical_prices: List[Dict[str, Any]],
        window: int = 14
    ) -> Dict[str, float]:
        """
        Calculate historical volatility metrics

        Args:
            historical_prices: List of price snapshots
                              [{timestamp, yes_mid, volume}, ...]
            window: Lookback window in periods

        Returns:
            Dict with volatility metrics
        """
        if not historical_prices or len(historical_prices) < 2:
            return {
                'volatility': 0.0,
                'regime': 'unknown',
                'data_quality': 'insufficient'
            }

        # Sort by timestamp
        sorted_prices = sorted(historical_prices, key=lambda x: x['timestamp'])

        # Extract prices
        prices = [p['yes_mid'] for p in sorted_prices]

        # Calculate returns (probability changes)
        returns = [(prices[i] - prices[i-1]) for i in range(1, len(prices))]

        if len(returns) < 2:
            return {
                'volatility': 0.0,
                'regime': 'unknown',
                'data_quality': 'insufficient'
            }

        # Use most recent window
        recent_returns = returns[-window:] if len(returns) >= window else returns

        # Calculate volatility (standard deviation)
        volatility = statistics.stdev(recent_returns) if len(recent_returns) > 1 else abs(recent_returns[0])

        # Classify regime
        regime = self._classify_volatility_regime(volatility)

        # Calculate additional metrics
        mean_return = statistics.mean(recent_returns)
        max_return = max(recent_returns)
        min_return = min(recent_returns)

        return {
            'volatility': volatility,
            'regime': regime,
            'mean_return': mean_return,
            'max_return': max_return,
            'min_return': min_return,
            'data_points': len(recent_returns),
            'data_quality': 'good' if len(recent_returns) >= window else 'limited'
        }

    def _classify_volatility_regime(self, volatility: float) -> str:
        """Classify volatility into regime"""
        if volatility < 0.02:
            return 'low'
        elif volatility < 0.05:
            return 'medium'
        elif volatility < 0.10:
            return 'high'
        else:
            return 'extreme'

    def calculate_volatility_from_spread(self, market: MarketData) -> Dict[str, float]:
        """
        Estimate volatility from bid-ask spread (when historical data unavailable)

        Wide spreads often indicate higher volatility
        """
        yes_spread = market.yes_ask - market.yes_bid
        no_spread = market.no_ask - market.no_bid
        avg_spread = (yes_spread + no_spread) / 2

        # Spread as proxy for volatility
        # Wider spread = higher implied volatility
        estimated_volatility = avg_spread * 1.5  # Rough scaling factor

        regime = self._classify_volatility_regime(estimated_volatility)

        return {
            'volatility': estimated_volatility,
            'regime': regime,
            'method': 'spread_based_estimate',
            'yes_spread': yes_spread,
            'no_spread': no_spread
        }

    def adjust_position_size_for_volatility(
        self,
        base_size: int,
        volatility_metrics: Dict[str, float],
        target_vol: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Adjust position size based on volatility regime

        Formula: adjusted_size = base_size × (target_vol / current_vol)

        Args:
            base_size: Initial recommended size
            volatility_metrics: Dict from calculate_historical_volatility
            target_vol: Target volatility (defaults to self.target_volatility)

        Returns:
            Dict with adjusted size and reasoning
        """
        if target_vol is None:
            target_vol = self.target_volatility

        current_vol = volatility_metrics['volatility']
        regime = volatility_metrics['regime']

        # If volatility is 0 or unknown, no adjustment
        if current_vol <= 0 or regime == 'unknown':
            return {
                'original_size': base_size,
                'adjusted_size': base_size,
                'adjustment_factor': 1.0,
                'reason': 'No volatility data available'
            }

        # Calculate adjustment factor
        adjustment_factor = target_vol / current_vol

        # Cap adjustment (don't scale up too much, don't scale down too much)
        adjustment_factor = max(0.25, min(2.0, adjustment_factor))

        adjusted_size = int(base_size * adjustment_factor)

        # Ensure at least 1 contract
        adjusted_size = max(1, adjusted_size)

        # Generate reasoning
        reason = self._generate_volatility_adjustment_reason(
            regime, current_vol, target_vol, adjustment_factor
        )

        return {
            'original_size': base_size,
            'adjusted_size': adjusted_size,
            'adjustment_factor': adjustment_factor,
            'current_volatility': current_vol,
            'target_volatility': target_vol,
            'regime': regime,
            'reason': reason
        }

    def _generate_volatility_adjustment_reason(
        self,
        regime: str,
        current_vol: float,
        target_vol: float,
        adjustment_factor: float
    ) -> str:
        """Generate human-readable reason for adjustment"""
        if adjustment_factor > 1.2:
            return (
                f"Increased size by {((adjustment_factor - 1) * 100):.0f}% due to LOW volatility regime. "
                f"Current vol ({current_vol:.1%}) below target ({target_vol:.1%}). "
                f"Lower risk allows larger position."
            )
        elif adjustment_factor < 0.8:
            return (
                f"Reduced size by {((1 - adjustment_factor) * 100):.0f}% due to {regime.upper()} volatility regime. "
                f"Current vol ({current_vol:.1%}) above target ({target_vol:.1%}). "
                f"Higher risk requires smaller position."
            )
        else:
            return (
                f"Volatility is near target ({current_vol:.1%} vs {target_vol:.1%}). "
                f"No significant adjustment needed."
            )

    def adjust_stops_for_volatility(
        self,
        base_stop_pct: float,
        volatility_metrics: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Adjust stop loss and take profit based on volatility

        In high volatility:
        - Widen stops (avoid noise whipsaws)
        - Widen take profit targets

        In low volatility:
        - Tighten stops (preserve capital)
        - Tighten take profit (take quick wins)

        Args:
            base_stop_pct: Base stop loss percentage (e.g., 25%)
            volatility_metrics: Volatility metrics

        Returns:
            Dict with adjusted stop/take profit levels
        """
        regime = volatility_metrics['regime']
        current_vol = volatility_metrics['volatility']

        # Multipliers based on regime
        if regime == 'low':
            stop_multiplier = 0.7  # Tighter stops
            take_profit_multiplier = 0.8
            advice = "Tight stops in low volatility - preserve capital, take quick profits"
        elif regime == 'medium':
            stop_multiplier = 1.0  # Normal stops
            take_profit_multiplier = 1.0
            advice = "Normal risk management parameters"
        elif regime == 'high':
            stop_multiplier = 1.5  # Wider stops
            take_profit_multiplier = 1.3
            advice = "Wide stops in high volatility - avoid whipsaws, let winners run"
        else:  # extreme
            stop_multiplier = 2.0  # Very wide stops
            take_profit_multiplier = 1.5
            advice = "Very wide stops in extreme volatility - high risk environment"

        adjusted_stop_pct = base_stop_pct * stop_multiplier
        adjusted_take_profit_pct = 50.0 * take_profit_multiplier  # Base 50% take profit

        return {
            'base_stop_pct': base_stop_pct,
            'adjusted_stop_pct': adjusted_stop_pct,
            'stop_multiplier': stop_multiplier,
            'adjusted_take_profit_pct': adjusted_take_profit_pct,
            'take_profit_multiplier': take_profit_multiplier,
            'regime': regime,
            'advice': advice
        }

    def calculate_position_volatility(
        self,
        position_size: int,
        entry_price: float,
        volatility: float
    ) -> Dict[str, float]:
        """
        Calculate expected volatility of a position in dollar terms

        Args:
            position_size: Number of contracts
            entry_price: Entry price per contract
            volatility: Market volatility (standard deviation of returns)

        Returns:
            Dict with position risk metrics
        """
        position_value = position_size * entry_price

        # Expected daily move in dollars
        expected_daily_move = position_value * volatility

        # 1 standard deviation move
        one_std_move = expected_daily_move

        # 2 standard deviation move (95% confidence)
        two_std_move = expected_daily_move * 2

        # Value at Risk (95% confidence, 1 day)
        var_95 = two_std_move

        return {
            'position_value': position_value,
            'expected_daily_move_dollars': expected_daily_move,
            'one_std_move': one_std_move,
            'two_std_move': two_std_move,
            'value_at_risk_95': var_95,
            'volatility_pct': volatility * 100
        }

    def get_volatility_advice(self, volatility_metrics: Dict[str, float]) -> str:
        """Get trading advice based on volatility regime"""
        regime = volatility_metrics['regime']

        advice = {
            'low': (
                "LOW VOLATILITY REGIME: Market is stable. "
                "Consider tighter stops, take profits early, increase position size slightly. "
                "Good environment for mean reversion strategies."
            ),
            'medium': (
                "MEDIUM VOLATILITY REGIME: Normal market conditions. "
                "Use standard risk management parameters. "
                "Both trend-following and mean reversion can work."
            ),
            'high': (
                "HIGH VOLATILITY REGIME: Market is volatile. "
                "Use wider stops to avoid whipsaws, reduce position size, let winners run. "
                "Favor trend-following over mean reversion."
            ),
            'extreme': (
                "EXTREME VOLATILITY REGIME: Market is highly unstable. "
                "Reduce position sizes significantly, use very wide stops, or wait for stability. "
                "Consider sitting out until volatility normalizes."
            ),
            'unknown': (
                "VOLATILITY UNKNOWN: Insufficient data. "
                "Use conservative default parameters. "
                "Monitor market carefully."
            )
        }

        return advice.get(regime, advice['unknown'])


# Global instance
volatility_analyzer = VolatilityAnalyzer()
