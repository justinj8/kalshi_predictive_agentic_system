"""
Binary Market Exit Strategy

Prediction markets behave fundamentally differently from continuous assets:
- Contracts settle at $0 or $1 (binary outcome)
- Prices can gap instantly on news (no smooth stops)
- Time decay accelerates near expiration
- Trailing stops don't work well

This module provides exit strategies designed for binary outcomes.
"""
from typing import Tuple, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ExitDecision:
    """Exit decision for a position"""
    should_exit: bool
    reason: str
    urgency: str  # 'immediate', 'normal', 'hold'
    recommendation: str  # 'take_profit', 'cut_loss', 'hold', 'let_ride'
    confidence: float


class BinaryExitStrategy:
    """
    Exit strategies designed for prediction market binary outcomes
    
    Key differences from traditional trailing stops:
    1. Event-aware: Know when resolution events are imminent
    2. Time-decay aware: Exit before theta eats the position
    3. Gap-aware: Don't rely on smooth price moves
    4. Resolution-aware: Hold through resolution if favorable
    """
    
    def __init__(self):
        # Thresholds
        self.take_profit_pct = 40.0  # Take profit at 40%+ gain
        self.cut_loss_pct = -35.0    # Cut at 35% loss
        self.pre_event_profit_lock = 25.0  # Lock in 25%+ before events
        self.pre_event_loss_cut = -20.0    # Cut at 20% before events
    
    def evaluate_exit(
        self,
        ticker: str,
        entry_price: float,
        current_price: float,
        position_side: str,  # 'long' or 'short'
        market_close_date: datetime,
        category: str = 'other',
        recent_news_count: int = 0,
        resolution_signals_present: bool = False
    ) -> ExitDecision:
        """
        Evaluate whether to exit a binary market position
        
        Args:
            ticker: Market ticker
            entry_price: Original entry price
            current_price: Current market price
            position_side: 'long' (bought YES) or 'short' (bought NO)
            market_close_date: When market resolves
            category: Market category (affects event expectations)
            recent_news_count: News articles in last 24h
            resolution_signals_present: Whether outcome is becoming clear
            
        Returns:
            ExitDecision with recommendation
        """
        # Calculate P&L
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        time_to_close = market_close_date - datetime.utcnow()
        
        # 1. Check for immediate resolution signals
        if resolution_signals_present:
            return self._handle_resolution_signals(
                pnl_pct, current_price, position_side
            )
        
        # 2. Check time-based rules
        if time_to_close <= timedelta(hours=4):
            return self._handle_imminent_close(
                pnl_pct, current_price, position_side, time_to_close
            )
        
        if time_to_close <= timedelta(hours=24):
            return self._handle_event_day(
                pnl_pct, current_price, category, time_to_close
            )
        
        # 3. Standard profit/loss thresholds
        if pnl_pct >= self.take_profit_pct:
            return ExitDecision(
                should_exit=True,
                reason=f"Take profit at {pnl_pct:.1f}% gain",
                urgency='normal',
                recommendation='take_profit',
                confidence=0.85
            )
        
        if pnl_pct <= self.cut_loss_pct:
            return ExitDecision(
                should_exit=True,
                reason=f"Cut loss at {pnl_pct:.1f}% loss",
                urgency='normal',
                recommendation='cut_loss',
                confidence=0.80
            )
        
        # 4. News-triggered caution
        if recent_news_count >= 3 and pnl_pct > 15:
            return ExitDecision(
                should_exit=True,
                reason=f"Lock in {pnl_pct:.1f}% before news uncertainty",
                urgency='normal',
                recommendation='take_profit',
                confidence=0.70
            )
        
        # 5. Default: Hold
        return ExitDecision(
            should_exit=False,
            reason="No exit trigger - continue holding",
            urgency='hold',
            recommendation='hold',
            confidence=0.60
        )
    
    def _handle_resolution_signals(
        self,
        pnl_pct: float,
        current_price: float,
        position_side: str
    ) -> ExitDecision:
        """Handle when resolution outcome is becoming clear"""
        
        # If price is moving strongly in our favor, let it ride
        if position_side == 'long' and current_price >= 0.85:
            return ExitDecision(
                should_exit=False,
                reason="Price at 85c+ and we're long - let ride to resolution",
                urgency='hold',
                recommendation='hold',
                confidence=0.90
            )
        
        if position_side == 'short' and current_price <= 0.15:
            return ExitDecision(
                should_exit=False,
                reason="Price at 15c- and we're short - let ride to resolution",
                urgency='hold',
                recommendation='hold',
                confidence=0.90
            )
        
        # If moving against us, cut immediately
        if pnl_pct <= -15:
            return ExitDecision(
                should_exit=True,
                reason=f"Resolution signals against us at {pnl_pct:.1f}% loss",
                urgency='immediate',
                recommendation='cut_loss',
                confidence=0.95
            )
        
        return ExitDecision(
            should_exit=False,
            reason="Resolution unclear - hold for now",
            urgency='hold',
            recommendation='hold',
            confidence=0.50
        )
    
    def _handle_imminent_close(
        self,
        pnl_pct: float,
        current_price: float,
        position_side: str,
        time_to_close: timedelta
    ) -> ExitDecision:
        """Handle <4 hours to market close"""
        
        hours_left = time_to_close.total_seconds() / 3600
        
        # Strong conviction positions: let ride
        if position_side == 'long' and current_price >= 0.75:
            return ExitDecision(
                should_exit=False,
                reason=f"Strong position ({current_price:.0%}) with {hours_left:.1f}h to go - ride it",
                urgency='hold',
                recommendation='hold',
                confidence=0.85
            )
        
        if position_side == 'short' and current_price <= 0.25:
            return ExitDecision(
                should_exit=False,
                reason=f"Strong short position ({current_price:.0%}) - ride it",
                urgency='hold',
                recommendation='hold',
                confidence=0.85
            )
        
        # Lock in profits before event
        if pnl_pct >= self.pre_event_profit_lock:
            return ExitDecision(
                should_exit=True,
                reason=f"Lock {pnl_pct:.1f}% profit before event in {hours_left:.1f}h",
                urgency='immediate',
                recommendation='take_profit',
                confidence=0.90
            )
        
        # Cut losses before event
        if pnl_pct <= self.pre_event_loss_cut:
            return ExitDecision(
                should_exit=True,
                reason=f"Cut {abs(pnl_pct):.1f}% loss before event",
                urgency='immediate',
                recommendation='cut_loss',
                confidence=0.85
            )
        
        # Uncertain position near event - take what you have
        if abs(pnl_pct) < 10:
            return ExitDecision(
                should_exit=True,
                reason=f"Exit near-flat position ({pnl_pct:+.1f}%) before binary event",
                urgency='normal',
                recommendation='take_profit' if pnl_pct > 0 else 'cut_loss',
                confidence=0.70
            )
        
        return ExitDecision(
            should_exit=False,
            reason=f"Keep position through event ({hours_left:.1f}h to go)",
            urgency='hold',
            recommendation='hold',
            confidence=0.50
        )
    
    def _handle_event_day(
        self,
        pnl_pct: float,
        current_price: float,
        category: str,
        time_to_close: timedelta
    ) -> ExitDecision:
        """Handle <24 hours to market close"""
        
        hours_left = time_to_close.total_seconds() / 3600
        
        # Category-specific handling
        binary_event_categories = ['sports', 'earnings', 'elections']
        
        if category in binary_event_categories:
            # These have sharp binary outcomes - size for full loss
            if pnl_pct >= 30:
                return ExitDecision(
                    should_exit=True,
                    reason=f"Take {pnl_pct:.1f}% before binary {category} event",
                    urgency='normal',
                    recommendation='take_profit',
                    confidence=0.80
                )
        
        return ExitDecision(
            should_exit=False,
            reason=f"Event day ({hours_left:.0f}h left) - standard thresholds apply",
            urgency='hold',
            recommendation='hold',
            confidence=0.60
        )


# Global instance
binary_exit_strategy = BinaryExitStrategy()
