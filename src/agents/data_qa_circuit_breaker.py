"""
Data QA & Circuit Breaker Agent
Validates data quality and halts trading if conditions are unsafe
"""
from datetime import datetime, timedelta
from typing import Dict, Any
import yaml
from src.utils.logger import get_logger
from src.orchestrator.state_models import TradingState, CircuitBreakerStatus, MarketData
from config.settings import settings

logger = get_logger(__name__)


class DataQACircuitBreaker:
    """Validates data and implements circuit breaker logic"""

    def __init__(self):
        """Initialize circuit breaker"""
        # Load trading policy
        with open("config/trading_policy.yaml", "r") as f:
            self.policy = yaml.safe_load(f)

        self.circuit_breaker_conditions = self.policy.get("circuit_breaker", {}).get("conditions", [])

    def validate_and_check(self, state: TradingState) -> TradingState:
        """
        Perform comprehensive data validation and circuit breaker checks

        Args:
            state: Current trading state

        Returns:
            Updated state with circuit breaker status
        """
        logger.info("Running Data QA & Circuit Breaker checks...")

        breaker_status = CircuitBreakerStatus(
            triggered=False,
            data_quality_ok=True,
            risk_limits_ok=True,
            api_health_ok=True
        )

        # Run all checks
        checks = [
            self._check_data_quality(state),
            self._check_risk_limits(state),
            self._check_api_health(state),
            self._check_market_data_validity(state)
        ]

        # Evaluate results
        for check_name, passed, severity, reason in checks:
            if not passed:
                logger.warning(f"Circuit breaker check failed: {check_name} - {reason}")

                if severity in ["critical", "high"]:
                    breaker_status.triggered = True
                    breaker_status.reason = reason
                    breaker_status.severity = severity
                    logger.error(f"CIRCUIT BREAKER TRIGGERED: {reason}")
                    break
                else:
                    state.warnings.append(f"{check_name}: {reason}")

        # Update flags
        if not breaker_status.triggered:
            logger.info("✓ All circuit breaker checks passed")

        state.circuit_breaker = breaker_status
        return state

    def _check_data_quality(self, state: TradingState) -> tuple:
        """Check if data is fresh and complete"""

        # Check if we have any markets
        if state.markets_scanned == 0:
            return ("data_quality", False, "critical", "No markets fetched - data source may be down")

        # Check for missing essential data (but be lenient - some markets may have 0 values legitimately)
        if state.all_markets:
            truly_incomplete = 0
            for market in state.all_markets[:20]:  # Sample first 20
                # Only count as incomplete if no ticker (truly broken data)
                if not market.ticker:
                    truly_incomplete += 1

            if truly_incomplete > 5:
                return ("data_quality", False, "high", f"{truly_incomplete} markets have no ticker")

        # Check data timestamp (should be recent)
        time_diff = datetime.utcnow() - state.timestamp
        if time_diff.total_seconds() > 300:  # 5 minutes
            return ("data_quality", False, "critical", f"Market data is {time_diff.total_seconds():.0f}s old (stale)")

        return ("data_quality", True, "low", "Data quality checks passed")

    def _check_risk_limits(self, state: TradingState) -> tuple:
        """Check if risk limits are within bounds"""

        risk_config = self.policy.get("risk_management", {})

        # Check daily loss limit
        max_daily_loss_pct = risk_config.get("max_daily_loss_percent", 15.0)
        max_daily_loss = state.current_balance * (max_daily_loss_pct / 100.0)

        if state.daily_pnl < -max_daily_loss:
            return (
                "daily_loss_limit",
                False,
                "critical",
                f"Daily loss ${abs(state.daily_pnl):.2f} exceeds limit ${max_daily_loss:.2f}"
            )

        # Check daily trade limit
        max_daily_trades = risk_config.get("max_daily_trades", 10)
        if state.daily_trades >= max_daily_trades:
            return (
                "daily_trade_limit",
                False,
                "medium",
                f"Daily trade limit reached ({state.daily_trades}/{max_daily_trades})"
            )

        # Check position limit
        max_positions = risk_config.get("max_concurrent_positions", 5)
        if state.open_positions >= max_positions:
            return (
                "position_limit",
                False,
                "medium",
                f"Maximum concurrent positions reached ({state.open_positions}/{max_positions})"
            )

        # Warning if approaching limits
        if abs(state.daily_pnl) > max_daily_loss * 0.7:
            logger.warning(
                f"⚠️ Approaching daily loss limit: ${abs(state.daily_pnl):.2f} / ${max_daily_loss:.2f}"
            )

        return ("risk_limits", True, "low", "Risk limits within bounds")

    def _check_api_health(self, state: TradingState) -> tuple:
        """Check if APIs are responding correctly"""

        # Check if we got errors from Kalshi API
        kalshi_errors = [e for e in state.errors if "kalshi" in e.lower() or "api" in e.lower()]

        if len(kalshi_errors) >= 3:
            return (
                "api_health",
                False,
                "high",
                f"Multiple API errors detected: {len(kalshi_errors)} errors"
            )

        return ("api_health", True, "low", "API health is good")

    def _check_market_data_validity(self, state: TradingState) -> tuple:
        """Check for anomalies in market data"""

        if not state.all_markets:
            return ("market_validity", True, "low", "No markets to validate")

        # Check for price anomalies
        anomalies = 0
        for market in state.all_markets[:20]:  # Sample first 20
            # Check if bid > ask (impossible)
            if market.yes_bid > market.yes_ask:
                anomalies += 1
                logger.warning(f"Price anomaly in {market.ticker}: bid > ask")

            # Check if yes + no != 1.0 (approximately)
            yes_mid = (market.yes_bid + market.yes_ask) / 2
            no_mid = (market.no_bid + market.no_ask) / 2
            total = yes_mid + no_mid

            if abs(total - 1.0) > 0.15:  # Allow 15% tolerance
                anomalies += 1
                logger.warning(f"Price anomaly in {market.ticker}: yes+no={total:.2f} (should ≈1.0)")

        if anomalies > 5:
            return (
                "market_validity",
                False,
                "high",
                f"Found {anomalies} markets with price anomalies"
            )

        return ("market_validity", True, "low", "Market data appears valid")

    def validate_market_for_trading(self, market: MarketData) -> tuple[bool, str]:
        """
        Validate a specific market is suitable for trading

        Args:
            market: Market to validate

        Returns:
            (is_valid, reason) tuple
        """
        risk_config = self.policy.get("risk_management", {})

        # Check liquidity
        min_liquidity = risk_config.get("min_market_liquidity", 1000)
        if market.open_interest < min_liquidity:
            return False, f"Insufficient liquidity: ${market.open_interest:.0f} < ${min_liquidity:.0f}"

        # Check spread (max 10% spread)
        yes_spread = market.yes_ask - market.yes_bid
        if yes_spread > 0.10:
            return False, f"Spread too wide: {yes_spread*100:.1f}%"

        # Check if market is about to close
        try:
            close_date = datetime.fromisoformat(market.close_date.replace("Z", "+00:00"))
            time_to_close = close_date - datetime.now(close_date.tzinfo)

            min_hours = self.policy.get("signal_selection", {}).get("min_time_to_close_hours", 24)
            if time_to_close.total_seconds() < min_hours * 3600:
                return False, f"Market closes in {time_to_close.total_seconds()/3600:.1f}h (min: {min_hours}h)"

        except Exception as e:
            return False, f"Cannot parse close date: {e}"

        # Check if prices make sense
        if market.yes_bid > market.yes_ask or market.no_bid > market.no_ask:
            return False, "Invalid prices: bid > ask"

        return True, "Market is valid for trading"


# Global instance
circuit_breaker = DataQACircuitBreaker()
