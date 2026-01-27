"""
Market Microstructure Analysis
Analyzes order book depth, spread dynamics, and liquidity for optimal execution
"""
from typing import Dict, Any, Optional, List
from src.utils.logger import get_logger
from src.orchestrator.state_models import MarketData

logger = get_logger(__name__)


class MarketMicrostructure:
    """
    Analyzes market microstructure for execution quality

    Key metrics:
    - Order book depth (bid/ask sizes)
    - Spread dynamics (narrowing/widening)
    - Liquidity assessment (can we fill our order?)
    - Slippage estimation
    """

    def __init__(self):
        """Initialize market microstructure analyzer"""
        pass

    def analyze_order_book(
        self,
        market: MarketData,
        order_book: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze order book depth and liquidity

        Args:
            market: Market data with bid/ask prices
            order_book: Full order book (if available) with depth at each price level
                       Format: {"bids": [(price, size), ...], "asks": [(price, size), ...]}

        Returns:
            Dict with microstructure metrics
        """
        metrics = {}

        # Basic spread analysis
        yes_spread = market.yes_ask - market.yes_bid
        no_spread = market.no_ask - market.no_bid

        metrics['yes_spread'] = yes_spread
        metrics['no_spread'] = no_spread
        metrics['yes_spread_pct'] = (yes_spread / market.yes_bid) * 100 if market.yes_bid > 0 else 0
        metrics['no_spread_pct'] = (no_spread / market.no_bid) * 100 if market.no_bid > 0 else 0

        # Spread quality classification
        avg_spread_pct = (metrics['yes_spread_pct'] + metrics['no_spread_pct']) / 2
        if avg_spread_pct < 2.0:
            metrics['spread_quality'] = 'excellent'
            metrics['execution_quality'] = 'high'
        elif avg_spread_pct < 4.0:
            metrics['spread_quality'] = 'good'
            metrics['execution_quality'] = 'medium'
        elif avg_spread_pct < 8.0:
            metrics['spread_quality'] = 'fair'
            metrics['execution_quality'] = 'medium'
        else:
            metrics['spread_quality'] = 'poor'
            metrics['execution_quality'] = 'low'

        # If we have full order book data
        if order_book:
            metrics.update(self._analyze_full_order_book(order_book, market))
        else:
            # Use volume as proxy for depth
            metrics.update(self._estimate_depth_from_volume(market))

        # Liquidity assessment
        metrics['liquidity_score'] = self._calculate_liquidity_score(market, metrics)
        metrics['liquidity_tier'] = self._classify_liquidity(metrics['liquidity_score'])

        # Execution warnings
        metrics['warnings'] = self._generate_execution_warnings(metrics)

        return metrics

    def _analyze_full_order_book(
        self,
        order_book: Dict[str, Any],
        market: MarketData
    ) -> Dict[str, Any]:
        """Analyze full order book with depth at each level"""
        metrics = {}

        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])

        # Calculate total depth
        total_bid_volume = sum(size for _, size in bids)
        total_ask_volume = sum(size for _, size in asks)

        metrics['total_bid_depth'] = total_bid_volume
        metrics['total_ask_depth'] = total_ask_volume
        metrics['total_depth'] = total_bid_volume + total_ask_volume

        # Order book imbalance
        if total_bid_volume + total_ask_volume > 0:
            metrics['order_book_imbalance'] = (
                (total_bid_volume - total_ask_volume) / (total_bid_volume + total_ask_volume)
            )
        else:
            metrics['order_book_imbalance'] = 0.0

        # Imbalance interpretation
        imbalance = metrics['order_book_imbalance']
        if imbalance > 0.3:
            metrics['imbalance_signal'] = 'strong_buying_pressure'
        elif imbalance > 0.1:
            metrics['imbalance_signal'] = 'buying_pressure'
        elif imbalance < -0.3:
            metrics['imbalance_signal'] = 'strong_selling_pressure'
        elif imbalance < -0.1:
            metrics['imbalance_signal'] = 'selling_pressure'
        else:
            metrics['imbalance_signal'] = 'balanced'

        # Top of book concentration
        if bids and asks:
            top_bid_size = bids[0][1] if bids else 0
            top_ask_size = asks[0][1] if asks else 0

            metrics['top_bid_concentration'] = (
                top_bid_size / total_bid_volume if total_bid_volume > 0 else 0
            )
            metrics['top_ask_concentration'] = (
                top_ask_size / total_ask_volume if total_ask_volume > 0 else 0
            )

            # High concentration = thin book (risky for large orders)
            avg_concentration = (
                metrics['top_bid_concentration'] + metrics['top_ask_concentration']
            ) / 2
            if avg_concentration > 0.7:
                metrics['book_thickness'] = 'very_thin'
            elif avg_concentration > 0.5:
                metrics['book_thickness'] = 'thin'
            elif avg_concentration > 0.3:
                metrics['book_thickness'] = 'medium'
            else:
                metrics['book_thickness'] = 'thick'
        else:
            metrics['book_thickness'] = 'unknown'

        return metrics

    def _estimate_depth_from_volume(self, market: MarketData) -> Dict[str, Any]:
        """Estimate depth using volume as proxy (when full order book unavailable)"""
        metrics = {}

        # Use 24h volume and open interest as proxies
        volume_24h = market.volume_24h
        open_interest = market.open_interest

        # Estimate available depth as % of daily volume
        # Assumption: ~10% of daily volume is on the book at any time
        estimated_depth = volume_24h * 0.10

        metrics['estimated_depth'] = estimated_depth
        metrics['depth_source'] = 'estimated_from_volume'

        # Classify depth adequacy
        if estimated_depth > 50000:
            metrics['depth_adequacy'] = 'excellent'
        elif estimated_depth > 20000:
            metrics['depth_adequacy'] = 'good'
        elif estimated_depth > 5000:
            metrics['depth_adequacy'] = 'fair'
        else:
            metrics['depth_adequacy'] = 'poor'

        return metrics

    def _calculate_liquidity_score(
        self,
        market: MarketData,
        metrics: Dict[str, Any]
    ) -> float:
        """
        Calculate overall liquidity score (0-100)

        Factors:
        - Spread (tighter = better)
        - Volume (higher = better)
        - Open interest (higher = better)
        - Depth (if available)
        """
        score = 0.0

        # Spread component (0-30 points)
        avg_spread_pct = (metrics['yes_spread_pct'] + metrics['no_spread_pct']) / 2
        if avg_spread_pct < 2.0:
            spread_score = 30
        elif avg_spread_pct < 4.0:
            spread_score = 25
        elif avg_spread_pct < 6.0:
            spread_score = 20
        elif avg_spread_pct < 8.0:
            spread_score = 15
        else:
            spread_score = 10
        score += spread_score

        # Volume component (0-35 points)
        volume_24h = market.volume_24h
        if volume_24h > 100000:
            volume_score = 35
        elif volume_24h > 50000:
            volume_score = 30
        elif volume_24h > 20000:
            volume_score = 25
        elif volume_24h > 10000:
            volume_score = 20
        elif volume_24h > 5000:
            volume_score = 15
        else:
            volume_score = 10
        score += volume_score

        # Open interest component (0-35 points)
        open_interest = market.open_interest
        if open_interest > 200000:
            oi_score = 35
        elif open_interest > 100000:
            oi_score = 30
        elif open_interest > 50000:
            oi_score = 25
        elif open_interest > 20000:
            oi_score = 20
        elif open_interest > 10000:
            oi_score = 15
        else:
            oi_score = 10
        score += oi_score

        return score

    def _classify_liquidity(self, liquidity_score: float) -> str:
        """Classify liquidity into tiers"""
        if liquidity_score >= 85:
            return 'tier_1_excellent'
        elif liquidity_score >= 70:
            return 'tier_2_good'
        elif liquidity_score >= 55:
            return 'tier_3_fair'
        elif liquidity_score >= 40:
            return 'tier_4_poor'
        else:
            return 'tier_5_very_poor'

    def _generate_execution_warnings(self, metrics: Dict[str, Any]) -> List[str]:
        """Generate warnings about execution risks"""
        warnings = []

        # Spread warnings
        if metrics['spread_quality'] == 'poor':
            warnings.append(
                f"Wide spread ({metrics['yes_spread_pct']:.1f}%) - "
                "expect high slippage on market orders"
            )

        # Liquidity warnings
        if metrics['liquidity_tier'] in ['tier_4_poor', 'tier_5_very_poor']:
            warnings.append(
                f"Low liquidity ({metrics['liquidity_tier']}) - "
                "consider splitting order or using limit orders"
            )

        # Book thickness warnings
        if metrics.get('book_thickness') in ['very_thin', 'thin']:
            warnings.append(
                "Thin order book - large orders may cause significant price impact"
            )

        # Imbalance warnings
        imbalance_signal = metrics.get('imbalance_signal', 'balanced')
        if 'strong' in imbalance_signal:
            warnings.append(
                f"Order book imbalance detected: {imbalance_signal} - "
                "price may move quickly"
            )

        return warnings

    def estimate_slippage(
        self,
        market: MarketData,
        side: str,
        quantity: int,
        microstructure: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Estimate expected slippage for an order

        Args:
            market: Market data
            side: "YES" or "NO"
            quantity: Number of contracts
            microstructure: Microstructure metrics from analyze_order_book

        Returns:
            Dict with slippage estimates
        """
        # Determine which side we're trading
        if side == "YES":
            entry_price = market.yes_ask
            spread_pct = microstructure['yes_spread_pct']
        else:
            entry_price = market.no_ask
            spread_pct = microstructure['no_spread_pct']

        # Order size relative to daily volume
        volume_24h = market.volume_24h
        order_value = quantity * entry_price

        if volume_24h > 0:
            size_ratio = order_value / volume_24h
        else:
            size_ratio = 1.0  # Conservative estimate

        # Slippage model:
        # Base slippage = half the spread (cross the spread)
        # Size impact = additional slippage based on order size
        base_slippage_pct = spread_pct / 2

        # Size impact (non-linear)
        if size_ratio < 0.01:  # <1% of daily volume
            size_impact_pct = 0.1
        elif size_ratio < 0.05:  # <5% of daily volume
            size_impact_pct = 0.5
        elif size_ratio < 0.10:  # <10% of daily volume
            size_impact_pct = 1.0
        else:  # >10% of daily volume
            size_impact_pct = 2.0 + (size_ratio * 10)

        total_slippage_pct = base_slippage_pct + size_impact_pct
        estimated_slippage = order_value * (total_slippage_pct / 100)

        return {
            'base_slippage_pct': base_slippage_pct,
            'size_impact_pct': size_impact_pct,
            'total_slippage_pct': total_slippage_pct,
            'estimated_slippage_dollars': estimated_slippage,
            'size_ratio': size_ratio,
            'recommendation': self._slippage_recommendation(total_slippage_pct, size_ratio)
        }

    def _slippage_recommendation(
        self,
        total_slippage_pct: float,
        size_ratio: float
    ) -> str:
        """Generate recommendation based on slippage estimate"""
        if total_slippage_pct < 0.5:
            return "Excellent execution expected - proceed with market order"
        elif total_slippage_pct < 1.0:
            return "Good execution expected - market order acceptable"
        elif total_slippage_pct < 2.0:
            if size_ratio > 0.05:
                return "Moderate slippage - consider limit order or split order"
            else:
                return "Moderate slippage - acceptable for market order"
        else:
            return "High slippage risk - use limit order and consider splitting order"

    def adjust_position_size_for_liquidity(
        self,
        recommended_size: int,
        market: MarketData,
        microstructure: Dict[str, Any],
        max_slippage_pct: float = 2.0
    ) -> Dict[str, Any]:
        """
        Adjust position size to respect liquidity constraints

        Args:
            recommended_size: Initial recommended position size
            market: Market data
            microstructure: Microstructure analysis
            max_slippage_pct: Maximum acceptable slippage

        Returns:
            Dict with adjusted size and reasoning
        """
        side = "YES"  # Assume YES for now (would be passed as parameter in real use)

        # Start with recommended size
        adjusted_size = recommended_size
        adjustment_reason = []

        # Check slippage at recommended size
        slippage = self.estimate_slippage(market, side, recommended_size, microstructure)

        if slippage['total_slippage_pct'] > max_slippage_pct:
            # Reduce size to meet slippage constraint
            # Use binary search to find acceptable size
            low, high = 1, recommended_size
            best_size = 1

            while low <= high:
                mid = (low + high) // 2
                test_slippage = self.estimate_slippage(market, side, mid, microstructure)

                if test_slippage['total_slippage_pct'] <= max_slippage_pct:
                    best_size = mid
                    low = mid + 1
                else:
                    high = mid - 1

            adjusted_size = best_size
            adjustment_reason.append(
                f"Reduced from {recommended_size} to {adjusted_size} contracts "
                f"to limit slippage to {max_slippage_pct:.1f}%"
            )

        # Check liquidity tier
        liquidity_tier = microstructure['liquidity_tier']
        if liquidity_tier in ['tier_4_poor', 'tier_5_very_poor']:
            # Further reduce size in poor liquidity
            adjusted_size = min(adjusted_size, max(1, recommended_size // 2))
            adjustment_reason.append(
                f"Further reduced due to low liquidity ({liquidity_tier})"
            )

        return {
            'original_size': recommended_size,
            'adjusted_size': adjusted_size,
            'adjustment_made': adjusted_size != recommended_size,
            'adjustment_reason': ' | '.join(adjustment_reason) if adjustment_reason else 'No adjustment needed',
            'final_slippage_estimate': self.estimate_slippage(
                market, side, adjusted_size, microstructure
            )
        }


# Global instance
market_microstructure = MarketMicrostructure()
