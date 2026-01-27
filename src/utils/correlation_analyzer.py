"""
Correlation Analyzer
Builds correlation matrix across open positions to manage portfolio-level risk
"""
from typing import Dict, List, Optional, Tuple, Any
import statistics
from datetime import datetime, timedelta
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CorrelationAnalyzer:
    """
    Analyzes correlations between markets for portfolio risk management

    Key concepts:
    - Correlation: How markets move together
    - Diversification: Reduce correlated exposure
    - Natural hedges: Identify opposing positions
    """

    def __init__(self):
        """Initialize correlation analyzer"""
        pass

    def calculate_correlation(
        self,
        prices_a: List[float],
        prices_b: List[float]
    ) -> float:
        """
        Calculate correlation coefficient between two price series

        Args:
            prices_a: Price series for market A
            prices_b: Price series for market B

        Returns:
            Correlation coefficient (-1 to 1)
        """
        if len(prices_a) != len(prices_b) or len(prices_a) < 2:
            return 0.0

        # Calculate returns
        returns_a = [(prices_a[i] - prices_a[i-1]) for i in range(1, len(prices_a))]
        returns_b = [(prices_b[i] - prices_b[i-1]) for i in range(1, len(prices_b))]

        if len(returns_a) < 2:
            return 0.0

        # Calculate correlation
        try:
            # Mean
            mean_a = statistics.mean(returns_a)
            mean_b = statistics.mean(returns_b)

            # Covariance
            covariance = sum(
                (returns_a[i] - mean_a) * (returns_b[i] - mean_b)
                for i in range(len(returns_a))
            ) / len(returns_a)

            # Standard deviations
            std_a = statistics.stdev(returns_a)
            std_b = statistics.stdev(returns_b)

            if std_a == 0 or std_b == 0:
                return 0.0

            # Correlation
            correlation = covariance / (std_a * std_b)

            # Clamp to [-1, 1]
            return max(-1.0, min(1.0, correlation))

        except Exception as e:
            logger.warning(f"Failed to calculate correlation: {e}")
            return 0.0

    def build_correlation_matrix(
        self,
        historical_prices: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, Dict[str, float]]:
        """
        Build correlation matrix for multiple markets

        Args:
            historical_prices: Dict mapping ticker to price history
                              {ticker: [{timestamp, yes_mid, volume}, ...]}

        Returns:
            Correlation matrix: {ticker_a: {ticker_b: correlation, ...}}
        """
        tickers = list(historical_prices.keys())
        correlation_matrix = {}

        for ticker_a in tickers:
            correlation_matrix[ticker_a] = {}

            for ticker_b in tickers:
                if ticker_a == ticker_b:
                    correlation_matrix[ticker_a][ticker_b] = 1.0
                else:
                    # Extract price series
                    prices_a = [p['yes_mid'] for p in historical_prices[ticker_a]]
                    prices_b = [p['yes_mid'] for p in historical_prices[ticker_b]]

                    # Align lengths (use shorter)
                    min_len = min(len(prices_a), len(prices_b))
                    prices_a = prices_a[-min_len:]
                    prices_b = prices_b[-min_len:]

                    # Calculate correlation
                    correlation = self.calculate_correlation(prices_a, prices_b)
                    correlation_matrix[ticker_a][ticker_b] = correlation

        return correlation_matrix

    def analyze_portfolio_correlations(
        self,
        open_positions: List[Dict[str, Any]],
        correlation_matrix: Dict[str, Dict[str, float]]
    ) -> Dict[str, Any]:
        """
        Analyze correlations across open positions

        Args:
            open_positions: List of open positions
                           [{ticker, side, quantity, entry_price, ...}, ...]
            correlation_matrix: Correlation matrix from build_correlation_matrix

        Returns:
            Dict with portfolio correlation analysis
        """
        if not open_positions or len(open_positions) < 2:
            return {
                'num_positions': len(open_positions),
                'avg_correlation': 0.0,
                'max_correlation': 0.0,
                'highly_correlated_pairs': [],
                'diversification_score': 100.0,
                'warnings': []
            }

        tickers = [pos['ticker'] for pos in open_positions]
        correlations = []
        highly_correlated_pairs = []

        # Collect all pairwise correlations
        for i in range(len(tickers)):
            for j in range(i + 1, len(tickers)):
                ticker_a = tickers[i]
                ticker_b = tickers[j]

                # Get correlation (if available)
                corr = correlation_matrix.get(ticker_a, {}).get(ticker_b, 0.0)
                correlations.append(abs(corr))  # Use absolute value

                # Flag high correlations
                if abs(corr) > 0.7:
                    highly_correlated_pairs.append({
                        'ticker_a': ticker_a,
                        'ticker_b': ticker_b,
                        'correlation': corr,
                        'same_direction': corr > 0
                    })

        # Calculate metrics
        avg_correlation = statistics.mean(correlations) if correlations else 0.0
        max_correlation = max(correlations) if correlations else 0.0

        # Diversification score (inverse of avg correlation)
        # 0 correlation = 100 score, 1 correlation = 0 score
        diversification_score = (1.0 - avg_correlation) * 100

        # Generate warnings
        warnings = []
        if avg_correlation > 0.6:
            warnings.append(
                f"Portfolio is highly correlated (avg {avg_correlation:.2f}). "
                f"Consider diversifying into uncorrelated markets."
            )

        if len(highly_correlated_pairs) > 0:
            warnings.append(
                f"Found {len(highly_correlated_pairs)} highly correlated position pairs. "
                f"Risk is concentrated."
            )

        return {
            'num_positions': len(open_positions),
            'avg_correlation': avg_correlation,
            'max_correlation': max_correlation,
            'highly_correlated_pairs': highly_correlated_pairs,
            'diversification_score': diversification_score,
            'warnings': warnings
        }

    def identify_natural_hedges(
        self,
        open_positions: List[Dict[str, Any]],
        correlation_matrix: Dict[str, Dict[str, float]]
    ) -> List[Dict[str, Any]]:
        """
        Identify pairs of positions that act as natural hedges

        Natural hedge: Two positions that move in opposite directions
        (negative correlation)

        Args:
            open_positions: List of open positions
            correlation_matrix: Correlation matrix

        Returns:
            List of natural hedge pairs
        """
        hedges = []
        tickers = [pos['ticker'] for pos in open_positions]

        for i in range(len(tickers)):
            for j in range(i + 1, len(tickers)):
                ticker_a = tickers[i]
                ticker_b = tickers[j]

                # Get correlation
                corr = correlation_matrix.get(ticker_a, {}).get(ticker_b, 0.0)

                # Negative correlation = natural hedge
                if corr < -0.5:
                    hedges.append({
                        'ticker_a': ticker_a,
                        'ticker_b': ticker_b,
                        'correlation': corr,
                        'hedge_quality': 'excellent' if corr < -0.7 else 'good'
                    })

        return hedges

    def calculate_correlation_adjusted_risk(
        self,
        positions: List[Dict[str, Any]],
        correlation_matrix: Dict[str, Dict[str, float]]
    ) -> Dict[str, float]:
        """
        Calculate portfolio risk adjusted for correlations

        Formula: Portfolio variance = sum of (w_i × w_j × corr_ij × vol_i × vol_j)

        Args:
            positions: List of positions with 'ticker', 'position_value', 'volatility'
            correlation_matrix: Correlation matrix

        Returns:
            Dict with risk metrics
        """
        if not positions:
            return {
                'individual_risk_sum': 0.0,
                'portfolio_risk': 0.0,
                'diversification_benefit': 0.0
            }

        # Calculate total portfolio value
        total_value = sum(pos['position_value'] for pos in positions)

        if total_value == 0:
            return {
                'individual_risk_sum': 0.0,
                'portfolio_risk': 0.0,
                'diversification_benefit': 0.0
            }

        # Calculate weights
        for pos in positions:
            pos['weight'] = pos['position_value'] / total_value

        # Sum of individual risks (ignoring correlations)
        individual_risk_sum = sum(
            pos['weight'] * pos.get('volatility', 0.03) * pos['position_value']
            for pos in positions
        )

        # Portfolio variance (considering correlations)
        portfolio_variance = 0.0
        for i, pos_i in enumerate(positions):
            for j, pos_j in enumerate(positions):
                ticker_i = pos_i['ticker']
                ticker_j = pos_j['ticker']

                # Get correlation (1.0 if same ticker)
                if ticker_i == ticker_j:
                    corr = 1.0
                else:
                    corr = correlation_matrix.get(ticker_i, {}).get(ticker_j, 0.0)

                # Add to variance
                vol_i = pos_i.get('volatility', 0.03)
                vol_j = pos_j.get('volatility', 0.03)
                weight_i = pos_i['weight']
                weight_j = pos_j['weight']

                portfolio_variance += (
                    weight_i * weight_j * corr * vol_i * vol_j * total_value * total_value
                )

        # Portfolio risk (standard deviation)
        portfolio_risk = portfolio_variance ** 0.5

        # Diversification benefit
        diversification_benefit = individual_risk_sum - portfolio_risk

        return {
            'individual_risk_sum': individual_risk_sum,
            'portfolio_risk': portfolio_risk,
            'diversification_benefit': diversification_benefit,
            'diversification_benefit_pct': (
                (diversification_benefit / individual_risk_sum) * 100
                if individual_risk_sum > 0 else 0.0
            )
        }

    def suggest_correlation_limits(
        self,
        current_positions: List[Dict[str, Any]],
        new_position_ticker: str,
        correlation_matrix: Dict[str, Dict[str, float]],
        max_avg_correlation: float = 0.6
    ) -> Dict[str, Any]:
        """
        Suggest if a new position would violate correlation limits

        Args:
            current_positions: Existing positions
            new_position_ticker: Ticker for proposed new position
            correlation_matrix: Correlation matrix
            max_avg_correlation: Maximum acceptable average correlation

        Returns:
            Dict with recommendation
        """
        if not current_positions:
            return {
                'recommendation': 'approve',
                'reason': 'No existing positions - no correlation risk',
                'avg_correlation_with_portfolio': 0.0
            }

        # Calculate average correlation with existing positions
        correlations = []
        for pos in current_positions:
            ticker = pos['ticker']
            corr = correlation_matrix.get(new_position_ticker, {}).get(ticker, 0.0)
            correlations.append(abs(corr))

        avg_corr = statistics.mean(correlations) if correlations else 0.0

        # Check if adding this position would exceed limit
        if avg_corr > max_avg_correlation:
            return {
                'recommendation': 'block',
                'reason': (
                    f"New position would increase portfolio correlation to {avg_corr:.2f}, "
                    f"exceeding limit of {max_avg_correlation:.2f}. "
                    f"Consider closing correlated positions first or choosing different market."
                ),
                'avg_correlation_with_portfolio': avg_corr
            }
        elif avg_corr > max_avg_correlation * 0.8:
            return {
                'recommendation': 'caution',
                'reason': (
                    f"New position has moderate correlation ({avg_corr:.2f}) with portfolio. "
                    f"Acceptable but approaching limit of {max_avg_correlation:.2f}."
                ),
                'avg_correlation_with_portfolio': avg_corr
            }
        else:
            return {
                'recommendation': 'approve',
                'reason': (
                    f"New position has low correlation ({avg_corr:.2f}) with portfolio. "
                    f"Good diversification."
                ),
                'avg_correlation_with_portfolio': avg_corr
            }

    def detect_category_correlations(
        self,
        positions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Detect if positions are concentrated in same categories

        Example: Multiple "Federal Reserve" related markets are likely correlated

        Args:
            positions: List of positions with 'ticker', 'category'

        Returns:
            Dict with category concentration analysis
        """
        if not positions:
            return {
                'category_counts': {},
                'most_concentrated_category': None,
                'concentration_score': 0.0,
                'warnings': []
            }

        # Count positions by category
        category_counts = {}
        for pos in positions:
            category = pos.get('category', 'unknown')
            category_counts[category] = category_counts.get(category, 0) + 1

        # Find most concentrated category
        most_concentrated = max(category_counts.items(), key=lambda x: x[1])
        most_concentrated_category = most_concentrated[0]
        max_count = most_concentrated[1]

        # Concentration score (% in most concentrated category)
        concentration_score = (max_count / len(positions)) * 100

        # Generate warnings
        warnings = []
        if concentration_score > 60:
            warnings.append(
                f"High category concentration: {concentration_score:.0f}% of positions "
                f"in '{most_concentrated_category}' category. Markets in same category "
                f"are likely correlated."
            )

        return {
            'category_counts': category_counts,
            'most_concentrated_category': most_concentrated_category,
            'concentration_score': concentration_score,
            'warnings': warnings
        }


# Global instance
correlation_analyzer = CorrelationAnalyzer()
