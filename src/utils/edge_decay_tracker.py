"""
Edge Decay Tracker

Markets efficiently price in information. An "edge" detected at 9am 
may be gone by 9:15am when other traders act on the same information.

This module tracks whether detected edges persist before execution,
preventing trades on stale signals.

Key insight: If the price has already moved toward your estimate since
you detected the edge, OTHER TRADERS SAW THE SAME THING and you're late.
"""
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DetectedEdge:
    """A detected trading edge"""
    ticker: str
    detected_at: datetime
    signal: str  # 'LONG' or 'SHORT'
    our_fair_value: float  # What we think fair price is
    market_price_at_detection: float  # Price when we detected
    confidence: float
    reasoning: str


@dataclass
class EdgePersistenceCheck:
    """Result of checking if edge still exists"""
    still_valid: bool
    original_edge_pct: float
    current_edge_pct: float
    decay_pct: float  # How much edge has decayed
    recommendation: str  # 'trade', 'skip', 'reduced_size'
    explanation: str


class EdgeDecayTracker:
    """
    Tracks detected edges and monitors for decay before execution
    
    Problems it solves:
    1. Late to the party: If everyone saw the same mispricing, it's priced in
    2. Stale signals: Price changed while we were analyzing
    3. Front-running: Whales moved before we could execute
    """
    
    def __init__(self):
        # Store detected edges
        self.detected_edges: Dict[str, DetectedEdge] = {}
        
        # Decay threshold: if edge decayed more than 50%, skip trade
        self.max_decay_pct = 50.0
        
        # Maximum age for an edge to be valid
        self.max_edge_age = timedelta(minutes=10)
        
        # Minimum edge required to trade
        self.min_edge_pct = 5.0
    
    def record_edge(
        self,
        ticker: str,
        signal: str,
        our_fair_value: float,
        market_price: float,
        confidence: float,
        reasoning: str = ""
    ) -> DetectedEdge:
        """
        Record a newly detected edge
        
        Call this when signal generation identifies a mispricing.
        
        Args:
            ticker: Market ticker
            signal: 'LONG' or 'SHORT'
            our_fair_value: What we estimate fair price is (0-1)
            market_price: Current market price (0-1)
            confidence: Signal confidence (0-100)
            reasoning: Why we think there's an edge
            
        Returns:
            Recorded edge object
        """
        edge = DetectedEdge(
            ticker=ticker,
            detected_at=datetime.utcnow(),
            signal=signal,
            our_fair_value=our_fair_value,
            market_price_at_detection=market_price,
            confidence=confidence,
            reasoning=reasoning
        )
        
        self.detected_edges[ticker] = edge
        
        edge_pct = abs(our_fair_value - market_price) * 100
        logger.info(
            f"Edge recorded: {ticker} {signal} - "
            f"Fair: {our_fair_value:.0%} vs Market: {market_price:.0%} "
            f"(Edge: {edge_pct:.1f}%)"
        )
        
        return edge
    
    def check_edge_persistence(
        self,
        ticker: str,
        current_market_price: float
    ) -> EdgePersistenceCheck:
        """
        Check if a previously detected edge still exists
        
        Call this right before execution to validate the trade.
        
        Args:
            ticker: Market ticker
            current_market_price: Current price at execution time
            
        Returns:
            EdgePersistenceCheck with recommendation
        """
        edge = self.detected_edges.get(ticker)
        
        if edge is None:
            return EdgePersistenceCheck(
                still_valid=False,
                original_edge_pct=0,
                current_edge_pct=0,
                decay_pct=100,
                recommendation='skip',
                explanation="No recorded edge for this ticker"
            )
        
        # Check age
        age = datetime.utcnow() - edge.detected_at
        if age > self.max_edge_age:
            return EdgePersistenceCheck(
                still_valid=False,
                original_edge_pct=0,
                current_edge_pct=0,
                decay_pct=100,
                recommendation='skip',
                explanation=f"Edge too old ({age.seconds}s > {self.max_edge_age.seconds}s)"
            )
        
        # Calculate original and current edge
        original_edge = abs(edge.our_fair_value - edge.market_price_at_detection)
        current_edge = abs(edge.our_fair_value - current_market_price)
        
        original_edge_pct = original_edge * 100
        current_edge_pct = current_edge * 100
        
        # Calculate decay
        if original_edge > 0:
            decay_pct = ((original_edge - current_edge) / original_edge) * 100
        else:
            decay_pct = 0
        
        # Determine if price moved in direction we expected
        if edge.signal == 'LONG':
            # We're bullish - price moving UP means edge is decaying
            price_moved_our_way = current_market_price > edge.market_price_at_detection
        else:
            # We're bearish - price moving DOWN means edge is decaying
            price_moved_our_way = current_market_price < edge.market_price_at_detection
        
        # Decision logic
        if decay_pct >= self.max_decay_pct:
            # Too much decay - we're late
            return EdgePersistenceCheck(
                still_valid=False,
                original_edge_pct=original_edge_pct,
                current_edge_pct=current_edge_pct,
                decay_pct=decay_pct,
                recommendation='skip',
                explanation=(
                    f"Edge decayed {decay_pct:.0f}% "
                    f"({original_edge_pct:.1f}% → {current_edge_pct:.1f}%). "
                    f"Other traders already moved the price - we're late."
                )
            )
        
        if current_edge_pct < self.min_edge_pct:
            # Edge too small now
            return EdgePersistenceCheck(
                still_valid=False,
                original_edge_pct=original_edge_pct,
                current_edge_pct=current_edge_pct,
                decay_pct=decay_pct,
                recommendation='skip',
                explanation=(
                    f"Remaining edge ({current_edge_pct:.1f}%) below "
                    f"minimum threshold ({self.min_edge_pct}%)"
                )
            )
        
        if decay_pct >= 30:
            # Moderate decay - reduce size
            return EdgePersistenceCheck(
                still_valid=True,
                original_edge_pct=original_edge_pct,
                current_edge_pct=current_edge_pct,
                decay_pct=decay_pct,
                recommendation='reduced_size',
                explanation=(
                    f"Edge partially decayed ({decay_pct:.0f}%). "
                    f"Recommend 50% position size."
                )
            )
        
        # Edge persists - trade!
        return EdgePersistenceCheck(
            still_valid=True,
            original_edge_pct=original_edge_pct,
            current_edge_pct=current_edge_pct,
            decay_pct=decay_pct,
            recommendation='trade',
            explanation=(
                f"Edge persists at {current_edge_pct:.1f}% "
                f"(only {decay_pct:.0f}% decay). Proceed with trade."
            )
        )
    
    def clear_edge(self, ticker: str):
        """Remove edge for ticker after trade or skip"""
        if ticker in self.detected_edges:
            del self.detected_edges[ticker]
    
    def clear_stale_edges(self):
        """Remove all edges older than max_edge_age"""
        now = datetime.utcnow()
        stale_tickers = [
            ticker for ticker, edge in self.detected_edges.items()
            if now - edge.detected_at > self.max_edge_age
        ]
        for ticker in stale_tickers:
            del self.detected_edges[ticker]
        
        if stale_tickers:
            logger.info(f"Cleared {len(stale_tickers)} stale edges")


# Global instance
edge_decay_tracker = EdgeDecayTracker()
