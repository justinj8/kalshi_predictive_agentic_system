"""
Risk & Allocation Agent
Calculates position sizes based on risk management rules
Now uses proper Kelly Criterion for mathematically optimal position sizing
Phase 2: Enhanced with volatility adjustment, liquidity checks, and correlation analysis
"""
import yaml
from src.utils.logger import get_logger
from src.utils.kelly_calculator import kelly_calculator
from src.utils.volatility_analyzer import volatility_analyzer
from src.utils.market_microstructure import market_microstructure
from src.utils.correlation_analyzer import correlation_analyzer
from src.orchestrator.state_models import TradingSignal, PositionSizing, TradingState, MarketAnalysis
from config.settings import settings

logger = get_logger(__name__)


class RiskAllocationAgent:
    """Calculates optimal position sizes based on risk parameters"""

    def __init__(self):
        """Initialize Risk & Allocation Agent"""
        # Load trading policy
        with open("config/trading_policy.yaml", "r") as f:
            self.policy = yaml.safe_load(f)

    def calculate_position_size(
        self,
        signal: TradingSignal,
        market_analysis: MarketAnalysis,
        state: TradingState
    ) -> PositionSizing:
        """
        Calculate optimal position size for a trading signal

        Args:
            signal: Trading signal from Signal Selection Agent
            market_analysis: Market data
            state: Current trading state

        Returns:
            Position sizing recommendation
        """
        logger.info(f"Calculating position size for {signal.ticker}")

        if signal.signal == "NO_TRADE":
            logger.info("Signal is NO_TRADE, returning zero position")
            return self._create_no_trade_sizing(signal)

        market = market_analysis.market

        # Get risk parameters
        max_concentration = self.policy["risk_management"]["max_position_concentration"]

        # Determine entry price and side
        if signal.signal == "LONG":
            # Buying YES
            entry_price = market.yes_ask  # We pay the ask
            side_str = "YES"
        else:  # SHORT
            # Buying NO
            entry_price = market.no_ask  # We pay the ask
            side_str = "NO"

        # Use Kelly Criterion for position sizing
        # Convert confidence (0-100) to win probability (0-1)
        # Apply FULL calibration with hard bounds to prevent overbetting
        from src.utils.calibration_tracker import calibration_tracker
        calibrated_confidence = calibration_tracker.get_fully_calibrated_confidence(signal.confidence)
        win_probability = calibrated_confidence / 100.0

        logger.info(
            f"Using Kelly Criterion: Raw Confidence={signal.confidence:.0f}%, "
            f"Calibrated={calibrated_confidence:.0f}%, Win Probability={win_probability:.2%}, "
            f"Entry=${entry_price:.3f}, Capital=${state.current_balance:.2f}"
        )

        # Calculate Kelly optimal size
        kelly_result = kelly_calculator.calculate_position_size(
            win_probability=win_probability,
            entry_price=entry_price,
            capital=state.current_balance,
            side=side_str
        )

        quantity = kelly_result['recommended_size']
        position_value = kelly_result['position_value']
        kelly_pct = kelly_result['kelly_pct']

        logger.info(
            f"Kelly sizing: {quantity} contracts @ ${entry_price:.3f} = ${position_value:.2f} "
            f"(Kelly%: {kelly_pct:.1%}, Adjusted Kelly%: {kelly_result['kelly_adjusted']:.1%})"
        )

        # Apply maximum position size limit (concentration)
        max_position_value = state.current_balance * (max_concentration / 100.0)
        max_quantity = int(max_position_value / entry_price)

        if quantity > max_quantity:
            logger.info(
                f"Position size limited by concentration: {quantity} -> {max_quantity} contracts"
            )
            quantity = max_quantity
            position_value = quantity * entry_price

        # Ensure at least 1 contract if signal is strong
        if quantity < 1 and signal.confidence >= 70:
            quantity = 1
            position_value = entry_price
            logger.info("Minimum position size applied: 1 contract")

        # Ensure we have enough capital
        if position_value > state.current_balance * 0.95:  # Keep 5% reserve
            quantity = int((state.current_balance * 0.95) / entry_price)
            position_value = quantity * entry_price
            logger.info(f"Position size reduced due to capital constraints: {quantity} contracts")

        # PHASE 2 ENHANCEMENTS START

        # 1. Volatility Adjustment
        historical_prices = state.debug_info.get('historical_prices', {}).get(signal.ticker, [])
        if historical_prices and len(historical_prices) >= 2:
            vol_metrics = volatility_analyzer.calculate_historical_volatility(historical_prices)
        else:
            # Fall back to spread-based estimate
            vol_metrics = volatility_analyzer.calculate_volatility_from_spread(market)

        vol_adjustment = volatility_analyzer.adjust_position_size_for_volatility(
            quantity, vol_metrics
        )
        quantity = vol_adjustment['adjusted_size']
        position_value = quantity * entry_price

        logger.info(
            f"Volatility adjustment: {vol_adjustment['original_size']} → {quantity} contracts "
            f"(Regime: {vol_metrics['regime']}, Vol: {vol_metrics['volatility']:.1%})"
        )

        # 2. Liquidity/Microstructure Adjustment
        microstructure = market_microstructure.analyze_order_book(market)
        liquidity_adjustment = market_microstructure.adjust_position_size_for_liquidity(
            quantity, market, microstructure, max_slippage_pct=2.0
        )
        quantity = liquidity_adjustment['adjusted_size']
        position_value = quantity * entry_price

        if liquidity_adjustment['adjustment_made']:
            logger.info(
                f"Liquidity adjustment: {liquidity_adjustment['original_size']} → {quantity} contracts. "
                f"Reason: {liquidity_adjustment['adjustment_reason']}"
            )

        # 3. Correlation Check (if we have open positions)
        correlation_warning = None
        if state.open_positions > 0:
            # Get open positions from state
            current_positions = state.debug_info.get('current_positions', [])
            correlation_matrix = state.debug_info.get('correlation_matrix', {})

            if current_positions and correlation_matrix:
                corr_check = correlation_analyzer.suggest_correlation_limits(
                    current_positions, signal.ticker, correlation_matrix
                )

                if corr_check['recommendation'] == 'block':
                    logger.warning(
                        f"Correlation check: {corr_check['reason']}. "
                        f"Reducing position size by 50%."
                    )
                    quantity = max(1, quantity // 2)
                    position_value = quantity * entry_price
                    correlation_warning = corr_check['reason']
                elif corr_check['recommendation'] == 'caution':
                    logger.info(f"Correlation check: {corr_check['reason']}")

        # Store Phase 2 adjustments in debug_info
        state.debug_info['phase2_adjustments'] = {
            'volatility': vol_adjustment,
            'liquidity': liquidity_adjustment,
            'microstructure': microstructure,
            'correlation_warning': correlation_warning
        }

        # PHASE 2 ENHANCEMENTS END

        # Calculate stop loss after Kelly sizing and Phase 2 adjustments
        stop_loss_price = self._calculate_stop_loss(entry_price, signal, signal.signal)

        # Adjust stop loss for volatility regime
        vol_stop_adjustment = volatility_analyzer.adjust_stops_for_volatility(
            25.0,  # Base 25% stop
            vol_metrics
        )
        # Override stop loss with volatility-adjusted value
        stop_loss_distance_pct = vol_stop_adjustment['adjusted_stop_pct'] / 100
        stop_loss_price = entry_price * (1 - stop_loss_distance_pct)

        # Calculate take profit
        take_profit_price = self._calculate_take_profit(entry_price, signal)

        # Calculate risk/reward ratio
        potential_profit = abs(take_profit_price - entry_price) * quantity
        potential_loss = abs(stop_loss_price - entry_price) * quantity
        risk_reward_ratio = potential_profit / potential_loss if potential_loss > 0 else 0

        # Calculate risk amount (actual dollars at risk)
        risk_amount = potential_loss

        # Create position sizing
        sizing = PositionSizing(
            ticker=signal.ticker,
            signal=signal.signal,
            recommended_size=quantity,
            risk_amount=risk_amount,
            max_loss=potential_loss,
            position_value=position_value,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            risk_reward_ratio=risk_reward_ratio,
            reasoning=self._create_sizing_reasoning(
                quantity,
                entry_price,
                risk_amount,
                position_value,
                state.current_balance,
                risk_reward_ratio,
                kelly_pct,
                win_probability
            )
        )

        logger.info(
            f"Position sizing: {quantity} contracts @ ${entry_price:.2f} = ${position_value:.2f} "
            f"(Risk: ${potential_loss:.2f}, R/R: {risk_reward_ratio:.2f})"
        )

        return sizing

    def _calculate_stop_loss(
        self,
        entry_price: float,
        signal: TradingSignal,
        side: str
    ) -> float:
        """Calculate stop loss price"""

        stop_loss_pct = self.policy["position_management"]["stop_loss_percent"]

        # Adjust stop loss based on confidence
        # Higher confidence = tighter stop
        confidence_factor = 1.0 - (signal.confidence / 200.0)  # 0.5 to 1.0
        adjusted_stop_pct = stop_loss_pct * confidence_factor

        # For LONG (buying YES), stop is below entry
        # For SHORT (buying NO), stop is below entry (in NO price terms)
        stop_loss = entry_price * (1 - adjusted_stop_pct / 100.0)

        # Ensure stop loss is reasonable (between 0.05 and 0.95)
        stop_loss = max(0.05, min(0.95, stop_loss))

        return stop_loss

    def _calculate_take_profit(
        self,
        entry_price: float,
        signal: TradingSignal
    ) -> float:
        """Calculate take profit price"""

        take_profit_pct = self.policy["position_management"]["take_profit_percent"]

        # For predictive markets, max profit is usually $1.00
        # So take profit is closer to $1.00

        # Calculate based on percentage gain
        take_profit = entry_price * (1 + take_profit_pct / 100.0)

        # Cap at $0.98 (reasonable max for predictive markets)
        take_profit = min(0.98, take_profit)

        return take_profit

    def _create_sizing_reasoning(
        self,
        quantity: int,
        entry_price: float,
        risk_amount: float,
        position_value: float,
        balance: float,
        risk_reward: float,
        kelly_pct: float,
        win_probability: float
    ) -> str:
        """Create human-readable reasoning for position size"""

        reasoning = f"""
Position Sizing Analysis (Kelly Criterion):
- Quantity: {quantity} contracts
- Entry Price: ${entry_price:.2f} per contract
- Total Position Value: ${position_value:.2f}
- Capital at Risk: ${risk_amount:.2f} ({(risk_amount/balance)*100:.1f}% of portfolio)
- Portfolio Allocation: {(position_value/balance)*100:.1f}%
- Risk/Reward Ratio: {risk_reward:.2f}:1

Kelly Criterion Details:
- Win Probability: {win_probability:.1%}
- Optimal Kelly: {kelly_pct:.1%}
- Adjusted Kelly (0.5x): {(kelly_pct * 0.5):.1%}
- This position size is mathematically optimal based on expected edge and probability of success.

Formula: f* = (p × b - q) / b, where p={win_probability:.2f}, b={1.0-entry_price:.2f}/{entry_price:.2f}
"""
        return reasoning.strip()

    def _create_no_trade_sizing(self, signal: TradingSignal) -> PositionSizing:
        """Create a no-trade position sizing"""
        return PositionSizing(
            ticker=signal.ticker,
            signal="LONG",  # Dummy value
            recommended_size=0,
            risk_amount=0.0,
            max_loss=0.0,
            position_value=0.0,
            stop_loss_price=0.0,
            take_profit_price=0.0,
            risk_reward_ratio=0.0,
            reasoning="No trade signal - position size is zero"
        )


# Global instance
risk_agent = RiskAllocationAgent()
