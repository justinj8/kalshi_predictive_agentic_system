"""
Technical Indicators for Prediction Markets
Adapted traditional technical analysis for probability-based markets
"""
from typing import List, Dict, Optional
import statistics
from datetime import datetime, timedelta
from src.utils.logger import get_logger
from src.orchestrator.state_models import MarketData

logger = get_logger(__name__)


class TechnicalIndicators:
    """
    Technical indicators adapted for prediction markets

    Traditional indicators modified for probability markets (0-1 range instead of price)
    """

    def __init__(self):
        """Initialize Technical Indicators calculator"""
        pass

    def calculate_all_indicators(
        self,
        market: MarketData,
        historical_prices: Optional[List[Dict]] = None
    ) -> Dict[str, any]:
        """
        Calculate all available technical indicators for a market

        Args:
            market: Current market data
            historical_prices: List of historical price snapshots
                              Format: [{"timestamp": datetime, "yes_mid": float, "volume": float}, ...]

        Returns:
            Dict with all indicator values
        """
        indicators = {}

        # Current market metrics
        yes_mid = (market.yes_bid + market.yes_ask) / 2
        no_mid = (market.no_bid + market.no_ask) / 2
        spread = market.yes_ask - market.yes_bid

        indicators['current_probability'] = yes_mid
        indicators['spread'] = spread
        indicators['spread_pct'] = spread * 100

        # If we have historical data, calculate time-series indicators
        if historical_prices and len(historical_prices) > 1:
            indicators.update(self._calculate_momentum_indicators(historical_prices))
            indicators.update(self._calculate_volatility_indicators(historical_prices))
            indicators.update(self._calculate_volume_indicators(historical_prices, market.volume_24h))
        else:
            # Check if market has technical data in metadata (for mock markets)
            mock_technical = None
            if market.metadata and isinstance(market.metadata, dict):
                mock_technical = market.metadata.get('technical')
            
            if mock_technical and isinstance(mock_technical, dict):
                # Use pre-defined technical data from mock markets
                rsi = mock_technical.get('rsi', 50.0)
                price_change = mock_technical.get('price_change_24h', 0.0)
                volume_trend = mock_technical.get('volume_trend', 'unknown')
                
                indicators['rsi'] = rsi
                indicators['momentum'] = price_change  # Use price change as momentum
                indicators['rate_of_change'] = price_change * 100
                indicators['volume_trend'] = volume_trend
                indicators['volatility'] = spread
                
                # Derive MA signal from RSI/momentum
                if rsi > 55 and price_change > 0:
                    indicators['ma_signal'] = 'bullish'
                elif rsi < 45 and price_change < 0:
                    indicators['ma_signal'] = 'bearish'
                else:
                    indicators['ma_signal'] = 'neutral'
                    
                # Volatility regime based on price change
                if abs(price_change) > 0.10:
                    indicators['volatility_regime'] = 'high'
                elif abs(price_change) > 0.05:
                    indicators['volatility_regime'] = 'medium'
                else:
                    indicators['volatility_regime'] = 'low'
                    
                logger.debug(f"Using mock technical data: RSI={rsi}, momentum={price_change}")
            else:
                # No historical data and no mock data - use single-point estimates
                indicators['momentum'] = 0.0
                indicators['volatility'] = spread  # Spread as proxy for volatility
                indicators['rsi'] = 50.0  # Neutral
                indicators['volume_trend'] = "unknown"

        # Spread dynamics (can calculate without history)
        indicators.update(self._calculate_spread_dynamics(market))

        return indicators

    def _calculate_momentum_indicators(
        self,
        historical_prices: List[Dict]
    ) -> Dict[str, float]:
        """
        Calculate momentum indicators

        Momentum = rate of probability change
        RSI = Relative Strength Index (adapted for probabilities)
        """
        indicators = {}

        if len(historical_prices) < 2:
            return {"momentum": 0.0, "rsi": 50.0}

        # Sort by timestamp
        sorted_prices = sorted(historical_prices, key=lambda x: x['timestamp'])

        # Calculate price changes
        prices = [p['yes_mid'] for p in sorted_prices]

        # Momentum: Change over period
        if len(prices) >= 2:
            momentum = prices[-1] - prices[0]
            indicators['momentum'] = momentum

            # Rate of change
            if prices[0] > 0:
                indicators['rate_of_change'] = (momentum / prices[0]) * 100
            else:
                indicators['rate_of_change'] = 0.0

        # RSI (Relative Strength Index) - adapted for probabilities
        if len(prices) >= 14:
            indicators['rsi'] = self._calculate_rsi(prices, period=14)
        elif len(prices) >= 7:
            indicators['rsi'] = self._calculate_rsi(prices, period=7)
        else:
            # Calculate simple momentum-based RSI proxy
            if momentum > 0:
                indicators['rsi'] = 50 + (momentum * 100)
            else:
                indicators['rsi'] = 50 + (momentum * 100)

            # Clamp to 0-100
            indicators['rsi'] = max(0, min(100, indicators['rsi']))

        # Moving average crossover (if enough data)
        if len(prices) >= 10:
            short_ma = sum(prices[-5:]) / 5
            long_ma = sum(prices[-10:]) / 10
            indicators['ma_crossover'] = short_ma - long_ma
            indicators['ma_signal'] = "bullish" if short_ma > long_ma else "bearish"
        else:
            indicators['ma_crossover'] = 0.0
            indicators['ma_signal'] = "neutral"

        return indicators

    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """
        Calculate RSI (Relative Strength Index)

        RSI = 100 - (100 / (1 + RS))
        where RS = Average Gain / Average Loss
        """
        if len(prices) < period + 1:
            return 50.0  # Neutral

        # Calculate price changes
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]

        # Separate gains and losses
        gains = [max(0, change) for change in changes[-period:]]
        losses = [abs(min(0, change)) for change in changes[-period:]]

        # Average gain and loss
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        # Avoid division by zero
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0

        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _calculate_volatility_indicators(
        self,
        historical_prices: List[Dict]
    ) -> Dict[str, float]:
        """
        Calculate volatility indicators

        Volatility = standard deviation of probability changes
        ATR-equivalent for prediction markets
        """
        indicators = {}

        if len(historical_prices) < 2:
            return {"volatility": 0.0, "volatility_regime": "unknown"}

        # Extract prices
        prices = [p['yes_mid'] for p in sorted(historical_prices, key=lambda x: x['timestamp'])]

        # Calculate returns (probability changes)
        if len(prices) >= 2:
            returns = [(prices[i] - prices[i-1]) for i in range(1, len(prices))]

            # Standard deviation of returns
            if len(returns) > 1:
                volatility = statistics.stdev(returns)
                indicators['volatility'] = volatility

                # Volatility regime classification
                if volatility < 0.02:
                    regime = "low"
                elif volatility < 0.05:
                    regime = "medium"
                else:
                    regime = "high"

                indicators['volatility_regime'] = regime
            else:
                indicators['volatility'] = abs(returns[0]) if returns else 0.0
                indicators['volatility_regime'] = "unknown"

        # ATR-equivalent (Average True Range for prediction markets)
        if len(historical_prices) >= 14:
            true_ranges = []
            for i in range(1, len(historical_prices)):
                curr = historical_prices[i]
                prev = historical_prices[i-1]

                # True range = max(high-low, abs(high-prev_close), abs(low-prev_close))
                # For prediction markets: use spread as range
                curr_spread = curr.get('spread', abs(curr['yes_mid'] - 0.5) * 2)
                true_ranges.append(curr_spread)

            indicators['atr'] = sum(true_ranges[-14:]) / min(14, len(true_ranges))
        else:
            indicators['atr'] = indicators.get('volatility', 0.0)

        return indicators

    def _calculate_volume_indicators(
        self,
        historical_prices: List[Dict],
        current_volume: float
    ) -> Dict[str, any]:
        """
        Calculate volume-based indicators

        Volume profile, volume trends, accumulation/distribution
        """
        indicators = {}

        if len(historical_prices) < 2:
            return {"volume_trend": "unknown", "volume_momentum": 0.0}

        # Extract volumes
        volumes = [p.get('volume', 0) for p in historical_prices]

        # Volume trend
        if len(volumes) >= 5:
            recent_avg = sum(volumes[-5:]) / 5
            older_avg = sum(volumes[:-5]) / max(1, len(volumes) - 5)

            if recent_avg > older_avg * 1.2:
                indicators['volume_trend'] = "increasing"
            elif recent_avg < older_avg * 0.8:
                indicators['volume_trend'] = "decreasing"
            else:
                indicators['volume_trend'] = "stable"

            # Volume momentum
            indicators['volume_momentum'] = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0
        else:
            indicators['volume_trend'] = "insufficient_data"
            indicators['volume_momentum'] = 0.0

        # Current volume vs average
        if volumes:
            avg_volume = sum(volumes) / len(volumes)
            indicators['volume_ratio'] = current_volume / avg_volume if avg_volume > 0 else 1.0

            if indicators['volume_ratio'] > 1.5:
                indicators['volume_signal'] = "high_volume"
            elif indicators['volume_ratio'] < 0.5:
                indicators['volume_signal'] = "low_volume"
            else:
                indicators['volume_signal'] = "normal_volume"
        else:
            indicators['volume_ratio'] = 1.0
            indicators['volume_signal'] = "unknown"

        return indicators

    def _calculate_spread_dynamics(self, market: MarketData) -> Dict[str, any]:
        """
        Calculate spread-based indicators

        Spread compression often precedes big moves
        """
        indicators = {}

        spread = market.yes_ask - market.yes_bid
        yes_mid = (market.yes_bid + market.yes_ask) / 2

        # Spread as percentage of mid-price
        if yes_mid > 0:
            spread_pct = (spread / yes_mid) * 100
        else:
            spread_pct = 0.0

        indicators['spread_pct'] = spread_pct

        # Classify spread
        if spread_pct < 2.0:
            spread_quality = "tight"
        elif spread_pct < 5.0:
            spread_quality = "normal"
        elif spread_pct < 10.0:
            spread_quality = "wide"
        else:
            spread_quality = "very_wide"

        indicators['spread_quality'] = spread_quality

        # Order book imbalance (bid vs ask distance from mid)
        bid_pressure = yes_mid - market.yes_bid
        ask_pressure = market.yes_ask - yes_mid

        if bid_pressure + ask_pressure > 0:
            imbalance = (bid_pressure - ask_pressure) / (bid_pressure + ask_pressure)
        else:
            imbalance = 0.0

        indicators['order_book_imbalance'] = imbalance

        if imbalance > 0.2:
            indicators['imbalance_signal'] = "bid_heavy"  # More buying pressure
        elif imbalance < -0.2:
            indicators['imbalance_signal'] = "ask_heavy"  # More selling pressure
        else:
            indicators['imbalance_signal'] = "balanced"

        return indicators

    def interpret_indicators(self, indicators: Dict[str, any]) -> Dict[str, str]:
        """
        Interpret technical indicators into trading signals

        Args:
            indicators: Dict of calculated indicators

        Returns:
            Dict with interpretations and signals
        """
        interpretation = {}

        # RSI interpretation
        rsi = indicators.get('rsi', 50)
        if rsi > 70:
            interpretation['rsi_signal'] = "overbought"
        elif rsi < 30:
            interpretation['rsi_signal'] = "oversold"
        else:
            interpretation['rsi_signal'] = "neutral"

        # Momentum interpretation
        momentum = indicators.get('momentum', 0)
        if momentum > 0.05:
            interpretation['momentum_signal'] = "strong_bullish"
        elif momentum > 0.02:
            interpretation['momentum_signal'] = "bullish"
        elif momentum < -0.05:
            interpretation['momentum_signal'] = "strong_bearish"
        elif momentum < -0.02:
            interpretation['momentum_signal'] = "bearish"
        else:
            interpretation['momentum_signal'] = "neutral"

        # Volatility interpretation
        vol_regime = indicators.get('volatility_regime', 'unknown')
        interpretation['volatility_advice'] = {
            "low": "Tight stops, take profits early",
            "medium": "Normal risk management",
            "high": "Wider stops, reduce position size",
            "unknown": "Use default risk parameters"
        }.get(vol_regime, "Use default risk parameters")

        # Overall technical signal
        bullish_count = sum([
            indicators.get('momentum', 0) > 0.02,
            indicators.get('rsi', 50) < 40,
            indicators.get('ma_signal') == 'bullish',
            indicators.get('volume_trend') == 'increasing',
            indicators.get('imbalance_signal') == 'bid_heavy'
        ])

        bearish_count = sum([
            indicators.get('momentum', 0) < -0.02,
            indicators.get('rsi', 50) > 60,
            indicators.get('ma_signal') == 'bearish',
            indicators.get('volume_trend') == 'decreasing',
            indicators.get('imbalance_signal') == 'ask_heavy'
        ])

        if bullish_count >= 3:
            interpretation['overall_signal'] = "bullish"
        elif bearish_count >= 3:
            interpretation['overall_signal'] = "bearish"
        else:
            interpretation['overall_signal'] = "neutral"

        return interpretation


# Global instance
technical_indicators = TechnicalIndicators()
