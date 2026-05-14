"""
Execution Agent
Executes approved trades via Kalshi API (paper or live trading)
"""
from datetime import datetime
import uuid
from src.utils.kalshi_client import kalshi_client
from src.utils.logger import get_logger
from src.orchestrator.state_models import (
    TradingSignal,
    PositionSizing,
    ExecutionResult,
    TradingState,
    MarketAnalysis
)
from src.database.models import Trade, get_session
from config.settings import settings

logger = get_logger(__name__)


class ExecutionAgent:
    """Executes trades on Kalshi (paper or live mode)"""

    def __init__(self):
        """Initialize Execution Agent"""
        self.kalshi = kalshi_client
        self.mode = settings.trading_mode

    def execute_trade(
        self,
        signal: TradingSignal,
        sizing: PositionSizing,
        market_analysis: MarketAnalysis,
        state: TradingState
    ) -> ExecutionResult:
        """
        Execute an approved trade

        Args:
            signal: Trading signal
            sizing: Position sizing
            market_analysis: Market analysis
            state: Current trading state

        Returns:
            Execution result
        """
        logger.info(
            f"Executing {signal.signal} trade: {sizing.recommended_size} contracts "
            f"of {signal.ticker}"
        )

        market = market_analysis.market

        # Determine side and price
        if signal.signal == "LONG":
            side = "yes"
            price = sizing.entry_limit_price or market.yes_ask
        else:  # SHORT
            side = "no"
            price = sizing.entry_limit_price or market.no_ask

        # Convert price to cents for Kalshi API
        price_cents = int(price * 100)
        position_id = f"pos_{uuid.uuid4().hex[:12]}"

        # Execute based on mode
        if settings.trading_mode == "paper":
            result = self._execute_paper_trade(
                signal, sizing, market, side, price, price_cents, position_id
            )
        else:
            result = self._execute_live_trade(
                signal, sizing, market, side, price, price_cents, position_id
            )

        # Record trade in database
        if result.success:
            self._record_trade(signal, sizing, market, result, state.decision_path)

        return result

    def _execute_paper_trade(
        self,
        signal: TradingSignal,
        sizing: PositionSizing,
        market,
        side: str,
        price: float,
        price_cents: int,
        position_id: str,
    ) -> ExecutionResult:
        """Execute trade in paper trading mode (simulation)"""

        logger.info(
            f"[PAPER TRADE] {signal.signal}: {sizing.recommended_size} {side.upper()} "
            f"contracts of {signal.ticker} @ ${price:.2f}",
            extra={"TRADE": True}
        )

        # Simulate order fill
        filled_quantity = sizing.recommended_size
        filled_price = price
        total_cost = filled_quantity * filled_price

        # Generate mock order ID
        order_id = f"paper_{uuid.uuid4().hex[:8]}"

        logger.info(
            f"[PAPER TRADE] Order filled: {filled_quantity} contracts @ ${filled_price:.2f} "
            f"= ${total_cost:.2f}",
            extra={"TRADE": True}
        )

        return ExecutionResult(
            ticker=signal.ticker,
            success=True,
            position_id=position_id,
            order_id=order_id,
            filled_quantity=filled_quantity,
            filled_price=filled_price,
            total_cost=total_cost,
            error_message=None
        )

    def _execute_live_trade(
        self,
        signal: TradingSignal,
        sizing: PositionSizing,
        market,
        side: str,
        price: float,
        price_cents: int,
        position_id: str,
    ) -> ExecutionResult:
        """Execute trade in live trading mode"""

        logger.info(
            f"[LIVE TRADE] Placing order: {sizing.recommended_size} {side.upper()} "
            f"contracts of {signal.ticker} @ ${price:.2f}",
            extra={"TRADE": True}
        )

        try:
            # Place order via Kalshi API
            order = self.kalshi.place_order(
                ticker=signal.ticker,
                side=side,
                quantity=sizing.recommended_size,
                price=price_cents,
                order_type="limit"
            )

            if order is None:
                return ExecutionResult(
                    ticker=signal.ticker,
                    success=False,
                    position_id=position_id,
                    error_message="Failed to place order - API returned None"
                )

            # Extract order details
            filled_quantity = order.get("filled_quantity", 0)
            filled_price = order.get("price", 0) / 100.0  # Convert cents to dollars
            total_cost = filled_quantity * filled_price
            if filled_quantity <= 0:
                return ExecutionResult(
                    ticker=signal.ticker,
                    success=False,
                    position_id=position_id,
                    order_id=order.get("order_id"),
                    error_message="Order placed but not filled; no position opened"
                )

            logger.info(
                f"[LIVE TRADE] Order placed: {filled_quantity} contracts @ ${filled_price:.2f}",
                extra={"TRADE": True}
            )

            return ExecutionResult(
                ticker=signal.ticker,
                success=True,
                position_id=position_id,
                order_id=order.get("order_id"),
                filled_quantity=filled_quantity,
                filled_price=filled_price,
                total_cost=total_cost,
                error_message=None
            )

        except Exception as e:
            logger.error(f"Error executing live trade: {e}")
            return ExecutionResult(
                ticker=signal.ticker,
                success=False,
                position_id=position_id,
                error_message=str(e)
            )

    def _record_trade(
        self,
        signal: TradingSignal,
        sizing: PositionSizing,
        market,
        result: ExecutionResult,
        decision_path: str,
    ):
        """Record trade in database"""

        try:
            session = get_session()

            trade = Trade(
                timestamp=datetime.utcnow(),
                ticker=signal.ticker,
                market_title=market.title,
                category=market.category,
                side=signal.signal.lower(),
                action="buy",
                quantity=result.filled_quantity,
                price=result.filled_price,
                total_cost=result.total_cost,
                order_id=result.order_id,
                status="filled",
                signal_confidence=signal.confidence,
                entry_reason=signal.reasoning[:500] if signal.reasoning else "",
                risk_score=100 - signal.confidence,
                position_id=result.position_id,
                is_entry=True,
                unrealized_pnl=0.0,
                decision_path=decision_path,
            )

            session.add(trade)
            session.commit()
            
            logger.info(f"Trade recorded in database: {trade.id}")
            
            session.close()

        except Exception as e:
            logger.error(f"Failed to record trade in database: {e}")


# Global instance
execution_agent = ExecutionAgent()
