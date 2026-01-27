"""
Alpha Vantage Client for Financial News and Sentiment
Provides consolidated news and sentiment analysis using Alpha Vantage's Intelligence API.
"""
from typing import List, Dict, Any, Optional
import requests
from datetime import datetime, timedelta
import random
from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

class AlphaVantageClient:
    """Client for Alpha Vantage News & Sentiment API"""
    
    BASE_URL = "https://www.alphavantage.co/query"
    
    def __init__(self):
        self.api_key = settings.alpha_vantage_api_key
        self.is_mock_mode = not bool(self.api_key and "your_" not in self.api_key.lower())
        if self.is_mock_mode:
            logger.info("Alpha Vantage API key not found or invalid. Using MOCK mode.")
        else:
            logger.info("Alpha Vantage client initialized with API key.")

    def get_news_and_sentiment(
        self, 
        tickers: Optional[str] = None, 
        topics: Optional[str] = None, 
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Fetch news availability and sentiment scores.
        
        Args:
            tickers: Comma-separated list of tickers (e.g., "AAPL,MSFT")
            topics: Comma-separated list of topics (e.g., "technology,earnings")
            limit: Maximum number of items
            
        Returns:
            Dict containing sentiment summary and list of news articles
        """
        if self.is_mock_mode:
            return self._get_mock_data(tickers or "MARKET")
            
        params = {
            "function": "NEWS_SENTIMENT",
            "apikey": self.api_key,
            "limit": limit,
            "sort": "LATEST"
        }
        
        if tickers:
            params["tickers"] = tickers
        if topics:
            params["topics"] = topics
            
        try:
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            data = response.json()
            
            if "feed" not in data:
                logger.warning(f"Alpha Vantage API error: {data.get('Note', data.get('Information', 'Unknown error'))}")
                return self._get_mock_data(tickers or "MARKET")
                
            return {
                "sentiment_summary": self._calculate_aggregate_sentiment(data.get("feed", [])),
                "feed": data.get("feed", [])
            }
            
        except Exception as e:
            logger.error(f"Error fetching Alpha Vantage data: {e}")
            return self._get_mock_data(tickers or "MARKET")

    def _calculate_aggregate_sentiment(self, feed: List[Dict]) -> Dict[str, float]:
        """Calculate average sentiment metrics from feed"""
        if not feed:
            return {"score": 0.0, "label": "Neutral", "confidence": 0.0}
            
        total_score = 0.0
        count = 0
        
        for item in feed:
            score = float(item.get("overall_sentiment_score", 0))
            total_score += score
            count += 1
            
        avg_score = total_score / count if count > 0 else 0
        
        # Map score to label
        if avg_score <= -0.35:
            label = "Bearish"
        elif avg_score <= -0.15:
            label = "Somewhat-Bearish"
        elif avg_score < 0.15:
            label = "Neutral"
        elif avg_score < 0.35:
            label = "Somewhat-Bullish"
        else:
            label = "Bullish"
            
        return {
            "score": round(avg_score, 4),
            "label": label,
            "article_count": count
        }

    def _get_mock_data(self, query: str) -> Dict[str, Any]:
        """Generate meaningful mock data for testing"""
        mock_feed = []
        base_time = datetime.now()
        
        # Create 5 mock articles
        for i in range(5):
             # Randomize sentiment slightly to test aggregation
            sentiment_score = random.uniform(-0.5, 0.8)
            sentiment_label = "Neutral"
            if sentiment_score > 0.15: sentiment_label = "Bullish"
            if sentiment_score < -0.15: sentiment_label = "Bearish"
            
            mock_feed.append({
                "title": f"Analyst Report: Update on {query} Market Position",
                "url": f"https://mock-news.com/{query}/{i}",
                "time_published": (base_time - timedelta(hours=i)).strftime("%Y%m%dT%H%M%S"),
                "authors": ["Mock Analyst"],
                "summary": f"Latest developments in {query} suggest potential volatility ahead with key indicators showing {sentiment_label.lower()} signals.",
                "overall_sentiment_score": sentiment_score,
                "overall_sentiment_label": sentiment_label,
                "source": "AlphaVantageMock"
            })
            
        return {
            "sentiment_summary": self._calculate_aggregate_sentiment(mock_feed),
            "feed": mock_feed
        }

# Global instance
alpha_vantage = AlphaVantageClient()
