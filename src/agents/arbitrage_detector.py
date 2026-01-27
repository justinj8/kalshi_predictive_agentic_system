"""
Arbitrage Detector Agent
Detects arbitrage opportunities within Kalshi markets
Research: $40M+ in arbitrage profits in 2024, 0.5-3% per trade
"""
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from src.utils.logger import get_logger
from src.orchestrator.state_models import TradingState, MarketData

logger = get_logger(__name__)


class ArbitrageDetector:
    """
    Detects arbitrage opportunities in Kalshi markets

    Types of arbitrage:
    1. **Within-market**: P(YES) + P(NO) should = $1.00 exactly
    2. **Temporal**: "X by Q1" price ≤ "X by Q2" price (earlier deadline more uncertain)
    3. **Binary complements**: "X happens" + "X doesn't happen" = $1.00
    4. **Category arbitrage**: Related events with inconsistent pricing
    """

    def __init__(self):
        """Initialize Arbitrage Detector"""
        # Minimum profit after fees to be worth executing
        self.min_arb_profit_pct = 1.5  # 1.5% minimum
        self.fee_rate = 0.01  # Assume 1% fees (adjust based on Kalshi's actual fees)

    def scan_for_arbitrage(self, state: TradingState) -> TradingState:
        """
        Scan all markets for arbitrage opportunities

        Args:
            state: Current trading state with all_markets populated

        Returns:
            Updated state with arbitrage opportunities in debug_info
        """
        logger.info("=" * 60)
        logger.info("ARBITRAGE DETECTION SCAN")
        logger.info("=" * 60)

        if not state.all_markets:
            logger.warning("No markets available for arbitrage scan")
            return state

        arbitrage_opportunities = []

        # Type 1: Within-market arbitrage (YES + NO ≠ $1.00)
        within_market_arbs = self._detect_within_market_arbitrage(state.all_markets)
        arbitrage_opportunities.extend(within_market_arbs)

        # Type 2: Temporal arbitrage (earlier deadline markets mispriced vs later)
        temporal_arbs = self._detect_temporal_arbitrage(state.all_markets)
        arbitrage_opportunities.extend(temporal_arbs)

        # Type 3: Binary complement arbitrage
        complement_arbs = self._detect_complement_arbitrage(state.all_markets)
        arbitrage_opportunities.extend(complement_arbs)

        # Store in state
        state.debug_info['arbitrage_opportunities'] = arbitrage_opportunities

        # Log results
        logger.info(f"Found {len(arbitrage_opportunities)} total arbitrage opportunities")

        if arbitrage_opportunities:
            logger.info("\nTop 5 Arbitrage Opportunities:")
            sorted_arbs = sorted(
                arbitrage_opportunities,
                key=lambda x: x['profit_pct'],
                reverse=True
            )
            for i, arb in enumerate(sorted_arbs[:5], 1):
                logger.info(
                    f"  {i}. {arb['type']}: {arb['description']} "
                    f"(Profit: {arb['profit_pct']:.2f}%, "
                    f"Capital: ${arb['capital_required']:.2f})"
                )

        logger.info("=" * 60)

        return state

    def _detect_within_market_arbitrage(
        self,
        markets: List[MarketData]
    ) -> List[Dict]:
        """
        Detect within-market arbitrage where YES + NO ≠ $1.00

        In theory: P(YES) + P(NO) = $1.00 always
        In practice: Temporary mispricings occur

        If YES_ASK + NO_ASK < $1.00 - fees: Buy both, guaranteed profit
        If YES_BID + NO_BID > $1.00 + fees: Sell both, guaranteed profit
        """
        opportunities = []

        for market in markets:
            # Calculate total cost to buy both sides
            yes_ask = market.yes_ask
            no_ask = market.no_ask
            buy_both_cost = yes_ask + no_ask

            # After fees
            buy_both_cost_with_fees = buy_both_cost * (1 + self.fee_rate)

            # Profit if we buy both (guaranteed $1.00 payout)
            profit = 1.00 - buy_both_cost_with_fees

            if profit > 0:
                profit_pct = (profit / buy_both_cost_with_fees) * 100

                if profit_pct >= self.min_arb_profit_pct:
                    opportunities.append({
                        "type": "within_market",
                        "market": market,
                        "description": f"{market.ticker}: Buy YES@${yes_ask:.3f} + NO@${no_ask:.3f}",
                        "profit_pct": profit_pct,
                        "profit_per_unit": profit,
                        "capital_required": buy_both_cost_with_fees,
                        "trades": [
                            {"ticker": market.ticker, "side": "YES", "price": yes_ask},
                            {"ticker": market.ticker, "side": "NO", "price": no_ask}
                        ]
                    })

        if opportunities:
            logger.info(f"  - Within-market: {len(opportunities)} opportunities")

        return opportunities

    def _detect_temporal_arbitrage(
        self,
        markets: List[MarketData]
    ) -> List[Dict]:
        """
        Detect temporal arbitrage between related markets

        Logic: If event "X happens by Q1 2025" is priced at 60%,
               then "X happens by Q2 2025" should be ≥ 60%
               (later deadline is superset of earlier)

        If Q1 > Q2: Arbitrage! Buy Q2, sell Q1
        """
        opportunities = []

        # Group markets by base event
        # This is simplified - in production, use NLP or market metadata
        market_groups = self._group_related_markets(markets)

        for group_name, group_markets in market_groups.items():
            if len(group_markets) < 2:
                continue

            # Sort by close date (earlier first)
            try:
                sorted_markets = sorted(
                    group_markets,
                    key=lambda m: datetime.fromisoformat(m.close_date.replace("Z", "+00:00"))
                )
            except:
                continue  # Skip if dates can't be parsed

            # Check for temporal violations
            for i in range(len(sorted_markets) - 1):
                earlier = sorted_markets[i]
                later = sorted_markets[i + 1]

                # Earlier market YES probability
                earlier_prob = (earlier.yes_bid + earlier.yes_ask) / 2

                # Later market YES probability
                later_prob = (later.yes_bid + later.yes_ask) / 2

                # Violation: earlier > later (shouldn't happen)
                if earlier_prob > later_prob + 0.05:  # 5% threshold
                    # Arbitrage: Buy later (underpriced), sell earlier (overpriced)
                    profit_per_unit = earlier_prob - later_prob
                    capital_required = later.yes_ask

                    profit_pct = (profit_per_unit / capital_required) * 100

                    if profit_pct >= self.min_arb_profit_pct:
                        opportunities.append({
                            "type": "temporal",
                            "market": later,  # The one we'd buy
                            "description": (
                                f"Temporal: {earlier.ticker}@{earlier_prob:.0%} > "
                                f"{later.ticker}@{later_prob:.0%}"
                            ),
                            "profit_pct": profit_pct,
                            "profit_per_unit": profit_per_unit,
                            "capital_required": capital_required,
                            "trades": [
                                {"ticker": later.ticker, "side": "YES", "price": later.yes_ask},
                                {"ticker": earlier.ticker, "side": "NO", "price": earlier.no_bid}
                            ]
                        })

        if opportunities:
            logger.info(f"  - Temporal: {len(opportunities)} opportunities")

        return opportunities

    def _detect_complement_arbitrage(
        self,
        markets: List[MarketData]
    ) -> List[Dict]:
        """
        Detect arbitrage between binary complement markets

        Example:
        - "Will X happen?" at 55%
        - "Will X NOT happen?" at 50%
        These should sum to 100%

        If complement_yes + original_yes < 95%: Arbitrage
        """
        opportunities = []

        # Group markets and their potential complements
        # This is simplified - production would use metadata or NLP
        # For now, skip this more complex detection
        # (Would require parsing market titles for negations)

        # TODO: Implement complement detection with NLP
        # For Phase 1, focus on within-market and temporal

        return opportunities

    def _group_related_markets(
        self,
        markets: List[MarketData]
    ) -> Dict[str, List[MarketData]]:
        """
        Group related markets (simplified heuristic)

        In production, use:
        - Market metadata (series_id)
        - NLP similarity on titles
        - Manual categorization

        For now: Group by first 30 characters of title
        """
        groups = {}

        for market in markets:
            # Simple grouping: first 30 chars of title
            # (Catches things like "Fed Rate Q1 2025" and "Fed Rate Q2 2025")
            if len(market.title) > 30:
                group_key = market.title[:30].strip()
            else:
                group_key = market.title.strip()

            if group_key not in groups:
                groups[group_key] = []

            groups[group_key].append(market)

        # Filter to groups with multiple markets
        related_groups = {k: v for k, v in groups.items() if len(v) > 1}

        return related_groups

    def select_best_arbitrage(
        self,
        state: TradingState
    ) -> Optional[Dict]:
        """
        Select the best arbitrage opportunity

        Criteria:
        1. Highest profit percentage
        2. Sufficient capital available
        3. Sufficient liquidity

        Args:
            state: Trading state with arbitrage opportunities

        Returns:
            Best arbitrage opportunity or None
        """
        opportunities = state.debug_info.get('arbitrage_opportunities', [])

        if not opportunities:
            return None

        # Filter by available capital
        available_capital = state.current_balance * 0.2  # Use max 20% for arbitrage

        affordable_opps = [
            opp for opp in opportunities
            if opp['capital_required'] <= available_capital
        ]

        if not affordable_opps:
            logger.info("No affordable arbitrage opportunities")
            return None

        # Select highest profit percentage
        best = max(affordable_opps, key=lambda x: x['profit_pct'])

        logger.info(
            f"Selected arbitrage: {best['type']} - "
            f"{best['profit_pct']:.2f}% profit"
        )

        return best


# Global instance
arbitrage_detector = ArbitrageDetector()
