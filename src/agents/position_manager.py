"""
Position Manager
Monitors open positions and manages exits (stop loss, take profit, trailing stops)
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any
import uuid
from src.utils.kalshi_client import kalshi_client
from src.utils.logger import get_logger
from src.database.models import Position, Trade, get_session
from src.orchestrator.state_models import TradingState
from config.settings import settings
import yaml

logger = get_logger(__name__)


class PositionManager:
    """Manages open positions and executes exit strategies"""

    def __init__(self):
        """Initialize Position Manager"""
        self.kalshi = kalshi_client

        # Load trading policy
        with open("config/trading_policy.yaml", "r") as f:
            self.policy = yaml.safe_load(f)

    def update_positions(self, state: TradingState) -> TradingState:
        """
        Update all open positions and check for exit conditions

        Args:
            state: Current trading state

        Returns:
            Updated state with position updates
        """
        logger.info("Updating open positions...")

        try:
            session = get_session()

            # Get all open positions
            open_positions = session.query(Position).filter(
                Position.is_open == True
            ).all()

            logger.info(f"Found {len(open_positions)} open positions")

            for position in open_positions:
                # Update position with current market price
                self._update_position_price(position)

                # Check for exit conditions
                should_exit, exit_reason = self._check_exit_conditions(position)

                if should_exit:
                    logger.info(
                        f"Exit signal for {position.ticker}: {exit_reason}"
                    )
                    self._exit_position(position, exit_reason)

            # Update state
            state.open_positions = session.query(Position).filter(
                Position.is_open == True
            ).count()

            session.commit()
            session.close()

            logger.info(f"Position update complete. Open positions: {state.open_positions}")

        except Exception as e:
            logger.error(f"Error updating positions: {e}")
            state.errors.append(f"Position update error: {str(e)}")

        return state

    def create_position(
        self,
        ticker: str,
        market_title: str,
        category: str,
        side: str,
        quantity: int,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        position_id: str = None,
    ) -> Position:
        """Create a new position in the database"""

        try:
            session = get_session()

            position_id = position_id or f"pos_{uuid.uuid4().hex[:12]}"

            position = Position(
                position_id=position_id,
                ticker=ticker,
                market_title=market_title,
                category=category,
                side=side,
                quantity=quantity,
                entry_price=entry_price,
                current_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                highest_price=entry_price,
                is_open=True
            )

            session.add(position)
            session.commit()

            logger.info(
                f"Position created: {ticker} {side} {quantity}@${entry_price:.2f}",
                extra={"TRADE": True}
            )

            session.close()
            return position

        except Exception as e:
            logger.error(f"Failed to create position: {e}")
            return None

    def _update_position_price(self, position: Position):
        """Update position with current market price"""

        try:
            # Get current market data
            market = self.kalshi.get_market(position.ticker)

            if market is None:
                logger.warning(f"Could not fetch market data for {position.ticker}")
                return

            # Get current price based on position side
            if position.side == "long":
                # For LONG (YES), use bid price (what we can sell at)
                current_price = market.get("yes_bid", 0) / 100.0
            else:  # short
                # For SHORT (NO), use bid price
                current_price = market.get("no_bid", 0) / 100.0

            position.current_price = current_price

            # Update highest price (for trailing stop)
            if current_price > position.highest_price:
                position.highest_price = current_price

            # Calculate unrealized P&L
            pnl = (current_price - position.entry_price) * position.quantity
            pnl_percent = ((current_price - position.entry_price) / position.entry_price) * 100

            position.unrealized_pnl = pnl
            position.unrealized_pnl_percent = pnl_percent
            position.last_updated = datetime.utcnow()

            logger.debug(
                f"Position update: {position.ticker} @ ${current_price:.2f} "
                f"(P&L: ${pnl:.2f}, {pnl_percent:+.1f}%)"
            )

        except Exception as e:
            logger.error(f"Error updating position price: {e}")

    def _check_exit_conditions(self, position: Position) -> tuple[bool, str]:
        """
        Check if position should be exited

        Returns:
            (should_exit, reason) tuple
        """

        # Check stop loss
        if position.current_price <= position.stop_loss:
            return True, "stop_loss"

        # Check take profit
        if position.current_price >= position.take_profit:
            return True, "take_profit"

        # Check trailing stop
        trailing_config = self.policy.get("position_management", {})
        trailing_activation = trailing_config.get("trailing_stop_activation", 30) / 100.0
        trailing_distance = trailing_config.get("trailing_stop_distance", 15) / 100.0

        profit_pct = (position.current_price - position.entry_price) / position.entry_price

        if profit_pct >= trailing_activation:
            # Trailing stop is active
            trailing_stop_price = position.highest_price * (1 - trailing_distance)

            if position.current_price <= trailing_stop_price:
                return True, "trailing_stop"

        # Check time-based exit
        max_holding_days = trailing_config.get("max_holding_period_days", 30)
        holding_time = datetime.utcnow() - position.opened_at

        if holding_time.days >= max_holding_days:
            return True, "max_holding_period"

        # Check if market is closing soon
        exit_before_hours = trailing_config.get("exit_before_close_hours", 4)

        # TODO: Get market close time and check
        # For now, skip this check

        return False, ""

    def _exit_position(self, position: Position, exit_reason: str):
        """Execute position exit"""

        logger.info(
            f"Exiting position {position.ticker} ({exit_reason}): "
            f"{position.quantity} contracts @ ${position.current_price:.2f}",
            extra={"TRADE": True}
        )

        try:
            # Place exit order
            if settings.trading_mode == "paper":
                # Paper trading - simulate exit
                logger.info(
                    f"[PAPER TRADE] Exit: {position.quantity} {position.side.upper()} "
                    f"contracts of {position.ticker} @ ${position.current_price:.2f}",
                    extra={"TRADE": True}
                )
                order_id = f"paper_exit_{uuid.uuid4().hex[:8]}"
                filled = True
            else:
                # Live trading - place real order
                side = "yes" if position.side == "long" else "no"
                order = self.kalshi.place_order(
                    ticker=position.ticker,
                    side=side,
                    quantity=position.quantity,
                    price=int(position.current_price * 100),
                    order_type="market",
                    action="sell",
                )
                order_id = order.get("order_id") if order else None
                filled = order is not None

            if filled:
                # Calculate realized P&L
                realized_pnl = position.unrealized_pnl

                # Update position
                position.is_open = False
                position.closed_at = datetime.utcnow()
                position.realized_pnl = realized_pnl

                # Record exit trade
                session = get_session()
                exit_trade = Trade(
                    timestamp=datetime.utcnow(),
                    ticker=position.ticker,
                    market_title=position.market_title,
                    category=position.category,
                    side=position.side,
                    action="sell",
                    quantity=position.quantity,
                    price=position.current_price,
                    total_cost=position.quantity * position.current_price,
                    order_id=order_id,
                    status="filled",
                    position_id=position.position_id,
                    is_entry=False,
                    exit_reason=exit_reason,
                    realized_pnl=realized_pnl,
                    pnl_percent=position.unrealized_pnl_percent
                )

                session.add(exit_trade)
                session.commit()
                session.close()

                logger.info(
                    f"Position closed: {position.ticker} - "
                    f"P&L: ${realized_pnl:.2f} ({position.unrealized_pnl_percent:+.1f}%)",
                    extra={"TRADE": True}
                )

        except Exception as e:
            logger.error(f"Error exiting position: {e}")

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get summary of current portfolio"""

        try:
            session = get_session()

            # Get open positions
            open_positions = session.query(Position).filter(
                Position.is_open == True
            ).all()

            # Calculate total unrealized P&L
            total_unrealized_pnl = sum([p.unrealized_pnl for p in open_positions])

            # Get all trades
            all_trades = session.query(Trade).all()
            total_realized_pnl = sum([
                t.realized_pnl for t in all_trades
                if t.realized_pnl is not None
            ])

            session.close()

            summary = {
                "open_positions": len(open_positions),
                "total_unrealized_pnl": total_unrealized_pnl,
                "total_realized_pnl": total_realized_pnl,
                "total_pnl": total_unrealized_pnl + total_realized_pnl,
                "positions": [
                    {
                        "ticker": p.ticker,
                        "side": p.side,
                        "quantity": p.quantity,
                        "entry_price": p.entry_price,
                        "current_price": p.current_price,
                        "unrealized_pnl": p.unrealized_pnl,
                        "pnl_percent": p.unrealized_pnl_percent
                    }
                    for p in open_positions
                ]
            }

            return summary

        except Exception as e:
            logger.error(f"Error getting portfolio summary: {e}")
            return {}


# Global instance
position_manager = PositionManager()
