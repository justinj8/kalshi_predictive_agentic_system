"""
Kelly Criterion Calculator
Implements proper Kelly Criterion for position sizing in prediction markets
Research shows most profitable traders use fractional Kelly (0.25-0.5x)
"""
from typing import Dict, Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)


class KellyCalculator:
    """
    Kelly Criterion position sizing calculator

    Formula: f* = (p × b - q) / b
    where:
        p = win probability
        q = loss probability (1 - p)
        b = odds ratio (win_amount / loss_amount)

    For prediction markets:
        - Buy YES at $0.60: win $0.40, lose $0.60 → b = 0.40/0.60 = 0.67
        - If confidence is 70%: f* = (0.70 × 0.67 - 0.30) / 0.67 = 0.25 (25% of capital)
    """

    def __init__(self, kelly_fraction: float = 0.5, max_position_pct: float = 10.0):
        """
        Initialize Kelly Calculator

        Args:
            kelly_fraction: Fraction of Kelly to use (0.5 = half-Kelly, industry standard)
            max_position_pct: Maximum position size as % of capital (safety cap)
        """
        self.kelly_fraction = kelly_fraction
        self.max_position_pct = max_position_pct

        logger.info(f"Kelly Calculator initialized: {kelly_fraction}x Kelly, max {max_position_pct}% per position")

    def calculate_position_size(
        self,
        win_probability: float,
        entry_price: float,
        capital: float,
        side: str = "YES"
    ) -> Dict[str, float]:
        """
        Calculate optimal position size using Kelly Criterion

        Args:
            win_probability: Estimated probability of winning (0-1, from Claude confidence)
            entry_price: Entry price for the contract (0-1 scale, e.g., 0.60)
            capital: Total capital available
            side: "YES" or "NO"

        Returns:
            Dict with:
                - kelly_fraction_optimal: Full Kelly percentage
                - recommended_size: Contracts to buy (fractional Kelly applied)
                - position_value: Dollar value of position
                - kelly_pct: Percentage of capital recommended
                - max_win: Maximum profit if trade wins
                - max_loss: Maximum loss if trade loses
        """

        # Input validation
        if not (0 < win_probability < 1):
            logger.warning(f"Invalid win probability: {win_probability}, clamping to [0.01, 0.99]")
            win_probability = max(0.01, min(0.99, win_probability))

        if not (0 < entry_price < 1):
            logger.error(f"Invalid entry price: {entry_price}")
            return self._create_zero_position()

        # Calculate win and loss amounts
        if side.upper() == "YES":
            # Buying YES: win $(1 - price), lose $price
            win_amount = 1.0 - entry_price
            loss_amount = entry_price
        else:  # NO
            # Buying NO: win $(1 - price), lose $price (same math)
            win_amount = 1.0 - entry_price
            loss_amount = entry_price

        # Edge case: if win_amount is tiny, position isn't worth it
        if win_amount < 0.01:
            logger.info(f"Win amount too small ({win_amount:.3f}), skipping position")
            return self._create_zero_position()

        # Calculate odds ratio (b)
        odds_ratio = win_amount / loss_amount

        # Calculate loss probability
        loss_probability = 1.0 - win_probability

        # Kelly formula: f* = (p × b - q) / b
        numerator = (win_probability * odds_ratio) - loss_probability
        kelly_optimal = numerator / odds_ratio

        # Handle negative Kelly (no edge)
        if kelly_optimal <= 0:
            logger.info(
                f"No edge detected: Kelly={kelly_optimal:.3f} "
                f"(p={win_probability:.2f}, b={odds_ratio:.2f})"
            )
            return self._create_zero_position()

        # Apply fractional Kelly
        kelly_adjusted = kelly_optimal * self.kelly_fraction

        # Cap at maximum position size
        kelly_final = min(kelly_adjusted, self.max_position_pct / 100.0)

        if kelly_final < kelly_adjusted:
            logger.info(f"Kelly capped: {kelly_adjusted*100:.1f}% → {kelly_final*100:.1f}%")

        # Calculate position size
        position_value = capital * kelly_final
        recommended_size = int(position_value / entry_price)

        # Ensure at least 1 contract if Kelly suggests position
        if kelly_final > 0.01 and recommended_size == 0:
            recommended_size = 1
            position_value = recommended_size * entry_price

        # Calculate max win and loss
        max_win = recommended_size * win_amount
        max_loss = recommended_size * loss_amount

        result = {
            "kelly_optimal": kelly_optimal * 100,  # Full Kelly percentage
            "kelly_adjusted": kelly_adjusted * 100,  # Fractional Kelly percentage
            "kelly_final": kelly_final * 100,  # After capping
            "recommended_size": recommended_size,
            "position_value": position_value,
            "kelly_pct": (position_value / capital) * 100,
            "max_win": max_win,
            "max_loss": max_loss,
            "risk_reward_ratio": max_win / max_loss if max_loss > 0 else 0,
            "edge": numerator  # Positive edge required for position
        }

        logger.info(
            f"Kelly sizing: {win_probability*100:.0f}% confidence @ ${entry_price:.2f} → "
            f"{recommended_size} contracts (${position_value:.2f}, {result['kelly_pct']:.1f}% of capital)"
        )

        return result

    def calculate_with_calibration(
        self,
        win_probability: float,
        entry_price: float,
        capital: float,
        historical_accuracy: Optional[Dict[str, float]] = None,
        side: str = "YES"
    ) -> Dict[str, float]:
        """
        Calculate position size with confidence calibration

        Adjusts Kelly based on historical accuracy of predictions
        If Claude says 70% but historically only 60% accurate, adjust down

        Args:
            win_probability: Estimated probability (from Claude)
            entry_price: Entry price
            capital: Available capital
            historical_accuracy: Dict with 'predicted' and 'actual' win rates
            side: "YES" or "NO"

        Returns:
            Position sizing dict (same as calculate_position_size)
        """

        # If we have historical data, calibrate the confidence
        if historical_accuracy:
            predicted_avg = historical_accuracy.get('predicted', win_probability)
            actual_avg = historical_accuracy.get('actual', win_probability)

            if predicted_avg > 0:
                # Calibration factor: if we're overconfident, reduce Kelly
                calibration = actual_avg / predicted_avg
                calibrated_probability = win_probability * calibration

                # Clamp to reasonable range
                calibrated_probability = max(0.01, min(0.99, calibrated_probability))

                logger.info(
                    f"Calibration applied: {win_probability*100:.0f}% → "
                    f"{calibrated_probability*100:.0f}% "
                    f"(factor: {calibration:.2f})"
                )

                win_probability = calibrated_probability

        # Calculate with calibrated probability
        return self.calculate_position_size(win_probability, entry_price, capital, side)

    def _create_zero_position(self) -> Dict[str, float]:
        """Return a zero-sized position"""
        return {
            "kelly_optimal": 0.0,
            "kelly_adjusted": 0.0,
            "kelly_final": 0.0,
            "recommended_size": 0,
            "position_value": 0.0,
            "kelly_pct": 0.0,
            "max_win": 0.0,
            "max_loss": 0.0,
            "risk_reward_ratio": 0.0,
            "edge": 0.0
        }

    def compare_to_fixed_sizing(
        self,
        win_probability: float,
        entry_price: float,
        capital: float,
        fixed_pct: float = 5.0
    ) -> Dict[str, any]:
        """
        Compare Kelly sizing to fixed percentage sizing

        Useful for understanding how much better Kelly is than naive sizing

        Args:
            win_probability: Win probability
            entry_price: Entry price
            capital: Available capital
            fixed_pct: Fixed percentage to compare against (default 5%)

        Returns:
            Comparison dict with Kelly and fixed sizing
        """
        kelly_result = self.calculate_position_size(win_probability, entry_price, capital)

        fixed_position_value = capital * (fixed_pct / 100.0)
        fixed_size = int(fixed_position_value / entry_price)

        comparison = {
            "kelly_size": kelly_result['recommended_size'],
            "kelly_value": kelly_result['position_value'],
            "fixed_size": fixed_size,
            "fixed_value": fixed_position_value,
            "kelly_advantage": kelly_result['recommended_size'] - fixed_size,
            "recommended": "Kelly" if kelly_result['recommended_size'] > 0 else "Skip"
        }

        logger.info(
            f"Kelly vs Fixed: {comparison['kelly_size']} contracts "
            f"vs {fixed_size} contracts ({comparison['kelly_advantage']:+d})"
        )

        return comparison


# Global instance with 0.5x Kelly (moderate risk)
kelly_calculator = KellyCalculator(kelly_fraction=0.5, max_position_pct=10.0)
