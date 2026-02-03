"""
News-Price Correlation Tracker

Tracks the relationship between news events and price movements to:
1. Detect when prices move BEFORE news (possible insider trading - avoid)
2. Measure edge decay after news (how fast market absorbs info)
3. Learn optimal entry timing relative to news

Key insight: If price moved significantly BEFORE news hit, 
someone knew before you - skip the trade.
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class NewsEvent:
    """A news event related to a market"""
    ticker: str
    timestamp: datetime
    headline: str
    sentiment: float  # -1 to 1 (negative to positive)
    source: str
    significance: str  # 'high', 'medium', 'low'


@dataclass
class PriceSnapshot:
    """Price at a point in time"""
    ticker: str
    timestamp: datetime
    price: float
    volume: float


@dataclass
class NewsPriceCorrelation:
    """Analysis of price movement relative to news"""
    news: NewsEvent
    price_before_news: float
    price_after_news: float
    price_change_pct: float
    pre_news_movement: float  # Price change in hour BEFORE news
    post_news_movement: float  # Price change in hour AFTER news
    is_suspicious: bool  # True if significant pre-news movement
    interpretation: str


class NewsPriceCorrelator:
    """
    Tracks price movements relative to news events
    
    Problems it solves:
    1. Front-running detection: Skip trades where price moved before news
    2. Timing optimization: Learn best entry time relative to news
    3. Alpha measurement: Track if we add value vs random trading
    """
    
    def __init__(self):
        # Store news events by ticker
        self.news_events: Dict[str, List[NewsEvent]] = defaultdict(list)
        
        # Store price history by ticker
        self.price_history: Dict[str, List[PriceSnapshot]] = defaultdict(list)
        
        # Threshold for "suspicious" pre-news movement (5%)
        self.suspicious_pre_move_threshold = 0.05
        
        # Maximum age for data (7 days)
        self.max_data_age = timedelta(days=7)
    
    def record_news(
        self,
        ticker: str,
        headline: str,
        sentiment: float,
        source: str = "unknown",
        significance: str = "medium",
        timestamp: Optional[datetime] = None
    ):
        """
        Record a news event
        
        Args:
            ticker: Market ticker
            headline: News headline
            sentiment: -1 to 1 (bearish to bullish)
            source: News source
            significance: 'high', 'medium', 'low'
            timestamp: Event time (default: now)
        """
        event = NewsEvent(
            ticker=ticker,
            timestamp=timestamp or datetime.utcnow(),
            headline=headline,
            sentiment=sentiment,
            source=source,
            significance=significance
        )
        
        self.news_events[ticker].append(event)
        logger.debug(f"News recorded: {ticker} - {headline[:50]}...")
    
    def record_price(
        self,
        ticker: str,
        price: float,
        volume: float = 0,
        timestamp: Optional[datetime] = None
    ):
        """Record a price snapshot"""
        snapshot = PriceSnapshot(
            ticker=ticker,
            timestamp=timestamp or datetime.utcnow(),
            price=price,
            volume=volume
        )
        self.price_history[ticker].append(snapshot)
    
    def check_for_front_running(
        self,
        ticker: str,
        current_price: float,
        lookback_hours: int = 4
    ) -> Tuple[bool, str]:
        """
        Check if recent price movement suggests front-running
        
        Args:
            ticker: Market ticker
            current_price: Current market price
            lookback_hours: Hours to look back
            
        Returns:
            (is_suspicious, explanation)
        """
        now = datetime.utcnow()
        lookback_start = now - timedelta(hours=lookback_hours)
        
        # Get recent news
        recent_news = [
            n for n in self.news_events.get(ticker, [])
            if n.timestamp >= lookback_start
        ]
        
        if not recent_news:
            return False, "No recent news - normal trading"
        
        # Get price history before latest news
        latest_news = max(recent_news, key=lambda n: n.timestamp)
        hour_before_news = latest_news.timestamp - timedelta(hours=1)
        
        prices_before = [
            p for p in self.price_history.get(ticker, [])
            if hour_before_news <= p.timestamp < latest_news.timestamp
        ]
        
        if not prices_before:
            return False, "No price history before news - can't determine"
        
        # Calculate pre-news movement
        first_price = prices_before[0].price
        last_price = prices_before[-1].price
        pre_news_move = (last_price - first_price) / first_price if first_price > 0 else 0
        
        # Check if movement matches news sentiment
        moved_in_direction_of_news = (
            (pre_news_move > 0 and latest_news.sentiment > 0) or
            (pre_news_move < 0 and latest_news.sentiment < 0)
        )
        
        if abs(pre_news_move) >= self.suspicious_pre_move_threshold and moved_in_direction_of_news:
            return True, (
                f"SUSPICIOUS: Price moved {pre_news_move:.1%} in hour BEFORE "
                f"'{latest_news.headline[:30]}...' - possible front-running"
            )
        
        return False, "No suspicious pre-news movement detected"
    
    def analyze_news_impact(
        self,
        ticker: str,
        news_event: NewsEvent
    ) -> Optional[NewsPriceCorrelation]:
        """
        Analyze how a specific news event impacted price
        
        Requires price data before and after the news event.
        """
        hour_before = news_event.timestamp - timedelta(hours=1)
        hour_after = news_event.timestamp + timedelta(hours=1)
        
        prices = self.price_history.get(ticker, [])
        
        # Get price before news
        prices_before = [p for p in prices if hour_before <= p.timestamp < news_event.timestamp]
        prices_at = [p for p in prices if abs((p.timestamp - news_event.timestamp).total_seconds()) < 60]
        prices_after = [p for p in prices if news_event.timestamp < p.timestamp <= hour_after]
        
        if not prices_before or not prices_after:
            return None
        
        price_before = prices_before[0].price
        price_at_news = prices_at[0].price if prices_at else (prices_before[-1].price + prices_after[0].price) / 2
        price_after = prices_after[-1].price
        
        pre_move = (price_at_news - price_before) / price_before if price_before > 0 else 0
        post_move = (price_after - price_at_news) / price_at_news if price_at_news > 0 else 0
        total_move = (price_after - price_before) / price_before if price_before > 0 else 0
        
        is_suspicious = (
            abs(pre_move) >= self.suspicious_pre_move_threshold and
            (pre_move > 0) == (news_event.sentiment > 0)
        )
        
        if is_suspicious:
            interpretation = "⚠️ Front-running suspected - price moved BEFORE news"
        elif abs(post_move) > abs(pre_move):
            interpretation = "✅ Normal reaction - price moved AFTER news as expected"
        else:
            interpretation = "ℹ️ Muted reaction - market may have anticipated this"
        
        return NewsPriceCorrelation(
            news=news_event,
            price_before_news=price_before,
            price_after_news=price_after,
            price_change_pct=total_move * 100,
            pre_news_movement=pre_move * 100,
            post_news_movement=post_move * 100,
            is_suspicious=is_suspicious,
            interpretation=interpretation
        )
    
    def should_skip_due_to_front_running(
        self,
        ticker: str,
        our_signal: str,
        recent_news_sentiment: float
    ) -> Tuple[bool, str]:
        """
        Quick check if we should skip this trade due to suspected front-running
        
        Args:
            ticker: Market ticker
            our_signal: 'LONG' or 'SHORT'
            recent_news_sentiment: -1 to 1
            
        Returns:
            (should_skip, reason)
        """
        is_suspicious, explanation = self.check_for_front_running(ticker, 0)
        
        if is_suspicious:
            # Our signal probably reflects stale edge
            return True, f"Skip trade - {explanation}"
        
        return False, "No front-running detected"
    
    def cleanup_old_data(self):
        """Remove data older than max_data_age"""
        cutoff = datetime.utcnow() - self.max_data_age
        
        for ticker in list(self.news_events.keys()):
            self.news_events[ticker] = [
                n for n in self.news_events[ticker]
                if n.timestamp >= cutoff
            ]
            if not self.news_events[ticker]:
                del self.news_events[ticker]
        
        for ticker in list(self.price_history.keys()):
            self.price_history[ticker] = [
                p for p in self.price_history[ticker]
                if p.timestamp >= cutoff
            ]
            if not self.price_history[ticker]:
                del self.price_history[ticker]


# Global instance
news_price_correlator = NewsPriceCorrelator()
