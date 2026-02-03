"""
Confidence Calibration Tracker
Tracks predicted vs actual outcomes to calibrate future predictions
Research shows AI systems tend to be overconfident - this corrects for that bias
"""
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from collections import defaultdict
from src.utils.logger import get_logger
from src.database.models import get_session, Trade

logger = get_logger(__name__)


class CalibrationTracker:
    """
    Tracks prediction accuracy to calibrate confidence scores
    
    If Claude says 80% confidence but historically only 65% of such trades win,
    we apply a calibration factor of 0.65/0.80 = 0.81 to future predictions.
    """
    
    def __init__(self):
        """Initialize calibration tracker"""
        # Bucket confidence scores into ranges for calibration
        self.buckets = {
            "50-60": (50, 60),
            "60-70": (60, 70),
            "70-80": (70, 80),
            "80-90": (80, 90),
            "90-100": (90, 100)
        }
        
        # Cache calibration data
        self._calibration_cache = None
        self._cache_timestamp = None
        self._cache_duration = timedelta(hours=1)
    
    def get_calibration_factor(self, confidence: float) -> float:
        """
        Get calibration factor for a given confidence level
        
        Args:
            confidence: Raw confidence score (0-100)
            
        Returns:
            Calibration factor (multiply by raw confidence to get calibrated)
        """
        calibration_data = self._get_calibration_data()
        
        if not calibration_data:
            logger.info("No calibration data available, using factor 1.0")
            return 1.0
        
        # Find the appropriate bucket
        bucket_name = self._get_bucket_name(confidence)
        
        if bucket_name not in calibration_data:
            logger.info(f"No calibration data for bucket {bucket_name}, using factor 1.0")
            return 1.0
        
        bucket_data = calibration_data[bucket_name]
        
        if bucket_data['total_trades'] < 5:
            logger.info(f"Insufficient trades in bucket {bucket_name} ({bucket_data['total_trades']}), using factor 1.0")
            return 1.0
        
        # Calculate calibration factor
        predicted_avg = bucket_data['avg_predicted_confidence'] / 100.0
        actual_win_rate = bucket_data['actual_win_rate']
        
        if predicted_avg <= 0:
            return 1.0
        
        factor = actual_win_rate / predicted_avg
        
        # Clamp factor to reasonable range (0.5 to 1.5)
        factor = max(0.5, min(1.5, factor))
        
        logger.info(
            f"Calibration for {bucket_name}: predicted={predicted_avg:.1%}, "
            f"actual={actual_win_rate:.1%}, factor={factor:.2f}"
        )
        
        return factor
    
    def calibrate_confidence(self, raw_confidence: float) -> float:
        """
        Apply calibration to raw confidence score
        
        Args:
            raw_confidence: Raw confidence from Claude (0-100)
            
        Returns:
            Calibrated confidence (0-100)
        """
        factor = self.get_calibration_factor(raw_confidence)
        calibrated = raw_confidence * factor
        
        # Clamp to valid range
        calibrated = max(1, min(99, calibrated))
        
        if abs(factor - 1.0) > 0.01:
            logger.info(f"Confidence calibrated: {raw_confidence:.0f}% → {calibrated:.0f}%")
        
        return calibrated
    
    def _get_bucket_name(self, confidence: float) -> str:
        """Get bucket name for a confidence level"""
        for name, (low, high) in self.buckets.items():
            if low <= confidence < high:
                return name
        return "90-100"  # Default to highest bucket
    
    def _get_calibration_data(self) -> Optional[Dict]:
        """
        Get calibration data from database
        
        Returns:
            Dict with calibration stats per bucket
        """
        # Check cache
        if (self._calibration_cache is not None and 
            self._cache_timestamp is not None and
            datetime.utcnow() - self._cache_timestamp < self._cache_duration):
            return self._calibration_cache
        
        try:
            session = get_session()
            
            # Get all completed trades with outcomes
            trades = session.query(Trade).filter(
                Trade.realized_pnl.isnot(None),
                Trade.signal_confidence.isnot(None)
            ).all()
            
            session.close()
            
            if not trades:
                return None
            
            # Calculate stats per bucket
            calibration_data = {}
            
            for bucket_name, (low, high) in self.buckets.items():
                bucket_trades = [
                    t for t in trades 
                    if low <= t.signal_confidence < high
                ]
                
                if not bucket_trades:
                    continue
                
                wins = [t for t in bucket_trades if t.realized_pnl > 0]
                
                calibration_data[bucket_name] = {
                    'total_trades': len(bucket_trades),
                    'wins': len(wins),
                    'losses': len(bucket_trades) - len(wins),
                    'actual_win_rate': len(wins) / len(bucket_trades),
                    'avg_predicted_confidence': sum(t.signal_confidence for t in bucket_trades) / len(bucket_trades),
                    'avg_pnl': sum(t.realized_pnl for t in bucket_trades) / len(bucket_trades)
                }
            
            # Cache the results
            self._calibration_cache = calibration_data
            self._cache_timestamp = datetime.utcnow()
            
            return calibration_data
            
        except Exception as e:
            logger.error(f"Error getting calibration data: {e}")
            return None
    
    def get_calibration_report(self) -> str:
        """
        Generate a human-readable calibration report
        
        Returns:
            Formatted calibration report string
        """
        calibration_data = self._get_calibration_data()
        
        if not calibration_data:
            return "No calibration data available yet. Need completed trades with outcomes."
        
        report = []
        report.append("=" * 60)
        report.append("CONFIDENCE CALIBRATION REPORT")
        report.append("=" * 60)
        report.append("")
        report.append(f"{'Bucket':<12} {'Trades':<8} {'Predicted':<12} {'Actual':<10} {'Factor':<8}")
        report.append("-" * 60)
        
        total_trades = 0
        total_wins = 0
        
        for bucket_name in sorted(self.buckets.keys()):
            if bucket_name not in calibration_data:
                continue
                
            data = calibration_data[bucket_name]
            predicted = data['avg_predicted_confidence']
            actual = data['actual_win_rate'] * 100
            factor = (actual / predicted) if predicted > 0 else 1.0
            
            # Indicator for over/under confidence
            if factor < 0.9:
                indicator = "↓ OVERCONF"
            elif factor > 1.1:
                indicator = "↑ UNDERCONF"
            else:
                indicator = "✓ GOOD"
            
            report.append(
                f"{bucket_name:<12} {data['total_trades']:<8} "
                f"{predicted:.0f}%{'':<9} {actual:.0f}%{'':<6} {factor:.2f} {indicator}"
            )
            
            total_trades += data['total_trades']
            total_wins += data['wins']
        
        report.append("-" * 60)
        
        if total_trades > 0:
            overall_win_rate = total_wins / total_trades * 100
            report.append(f"Overall: {total_trades} trades, {overall_win_rate:.1f}% win rate")
        
        report.append("=" * 60)
        
        return "\n".join(report)
    
    def record_prediction(
        self,
        ticker: str,
        predicted_confidence: float,
        signal: str,
        entry_price: float
    ) -> str:
        """
        Record a new prediction (called at trade entry)
        
        Note: This is optional - the main tracking happens via Trade records
        This can be used for additional prediction-specific logging
        
        Args:
            ticker: Market ticker
            predicted_confidence: Claude's confidence (0-100)
            signal: LONG or SHORT
            entry_price: Entry price
            
        Returns:
            Prediction ID for tracking
        """
        prediction_id = f"pred_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{ticker}"
        
        logger.info(
            f"Prediction recorded: {prediction_id} - "
            f"{ticker} {signal} @ ${entry_price:.2f} with {predicted_confidence:.0f}% confidence"
        )
        
        return prediction_id
    
    def record_outcome(
        self,
        ticker: str,
        predicted_confidence: float,
        actual_outcome: bool,
        predicted_signal: str,
        pnl: float
    ):
        """
        Record actual outcome for a prediction (called when market resolves or position closes)
        
        This is CRITICAL for calibration - tracks whether our confidence was justified.
        AI systems (including Claude) tend to be overconfident, so we need real outcome data.
        
        Args:
            ticker: Market ticker
            predicted_confidence: Original confidence score (0-100)
            actual_outcome: True if prediction was correct (profitable)
            predicted_signal: LONG or SHORT
            pnl: Realized P&L
        """
        bucket_name = self._get_bucket_name(predicted_confidence)
        
        # Update the trade record with outcome if possible
        try:
            session = get_session()
            
            # Find the most recent trade for this ticker that doesn't have an outcome
            from sqlalchemy import desc
            trade = session.query(Trade).filter(
                Trade.ticker == ticker,
                Trade.signal_confidence.isnot(None)
            ).order_by(desc(Trade.timestamp)).first()
            
            if trade:
                trade.realized_pnl = pnl
                session.commit()
                
                logger.info(
                    f"Outcome recorded: {ticker} {predicted_signal} @ {predicted_confidence:.0f}% "
                    f"-> {'WIN' if actual_outcome else 'LOSS'} (${pnl:+.2f})"
                )
            
            session.close()
            
        except Exception as e:
            logger.error(f"Error recording outcome: {e}")
        
        # Invalidate cache so next calibration uses updated data
        self._calibration_cache = None
        self._cache_timestamp = None
    
    def apply_hard_bounds(self, raw_confidence: float) -> float:
        """
        Apply hard bounds to prevent extreme overconfidence
        
        Research shows:
        - LLMs regularly express 90%+ confidence even on uncertain predictions
        - Even expert humans rarely have 85%+ accuracy on prediction markets
        - Capping confidence prevents catastrophic Kelly overbetting
        
        Args:
            raw_confidence: Raw confidence from LLM (0-100)
            
        Returns:
            Bounded confidence (capped at 85%, floor at 30%)
        """
        MAX_CONFIDENCE = 85.0  # Never bet more than 85% confident
        MIN_CONFIDENCE = 30.0  # Below 30% = no trade
        
        bounded = max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, raw_confidence))
        
        if raw_confidence > MAX_CONFIDENCE:
            logger.warning(
                f"Confidence hard-capped: {raw_confidence:.0f}% -> {bounded:.0f}% "
                f"(max {MAX_CONFIDENCE}% to prevent overbetting)"
            )
        
        return bounded
    
    def get_fully_calibrated_confidence(self, raw_confidence: float) -> float:
        """
        Apply full calibration pipeline:
        1. Hard bounds (prevent extreme overconfidence)
        2. Historical calibration (adjust based on past accuracy)
        
        This is the main method to use for production confidence scores.
        
        Args:
            raw_confidence: Raw confidence from Claude (0-100)
            
        Returns:
            Fully calibrated and bounded confidence (0-100)
        """
        # Step 1: Apply hard bounds first
        bounded = self.apply_hard_bounds(raw_confidence)
        
        # Step 2: Apply historical calibration
        calibrated = self.calibrate_confidence(bounded)
        
        logger.info(
            f"Full calibration: raw={raw_confidence:.0f}% -> "
            f"bounded={bounded:.0f}% -> calibrated={calibrated:.0f}%"
        )
        
        return calibrated


# Global instance
calibration_tracker = CalibrationTracker()
