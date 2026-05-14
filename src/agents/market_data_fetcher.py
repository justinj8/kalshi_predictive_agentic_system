"""
Market Data Fetcher Agent
Scans all Kalshi markets and identifies top opportunities
"""
from typing import List, Dict, Any
from datetime import datetime, timedelta
import yaml
from src.utils.kalshi_client import kalshi_client
from src.utils.news_fetcher import news_fetcher, social_fetcher
from src.utils.sentiment_analyzer import sentiment_analyzer
from src.utils.logger import get_logger
from src.orchestrator.state_models import MarketData, MarketAnalysis, NewsData, SocialData, TradingState
from config.settings import settings

logger = get_logger(__name__)


class MarketDataFetcher:
    """Fetches and enriches market data from Kalshi"""

    def __init__(self):
        """Initialize market data fetcher"""
        self.kalshi = kalshi_client
        # Load trading policy
        with open("config/trading_policy.yaml", "r") as f:
            self.policy = yaml.safe_load(f)

    def fetch_all_markets(self, state: TradingState) -> TradingState:
        """
        Fetch all open markets from Kalshi

        Args:
            state: Current trading state

        Returns:
            Updated state with market data
        """
        logger.info("Fetching all open markets from Kalshi...")

        try:
            # Get all open markets
            raw_markets = self.kalshi.get_all_markets(status="open", limit=200)

            # Convert to MarketData models
            markets = []
            for market in raw_markets:
                try:
                    # Handle close_date - could be datetime, string, or None
                    close_date = market.get("close_date", "")
                    if hasattr(close_date, 'isoformat'):
                        # It's a datetime object, convert to ISO string
                        close_date = close_date.isoformat()
                    elif close_date is None:
                        close_date = ""
                    else:
                        close_date = str(close_date)
                        
                    market_data = MarketData(
                        ticker=market.get("ticker", ""),
                        title=market.get("title", ""),
                        category=market.get("category", "unknown"),
                        yes_bid=market.get("yes_bid", 0) / 100.0,  # Convert cents to dollars
                        yes_ask=market.get("yes_ask", 0) / 100.0,
                        no_bid=market.get("no_bid", 0) / 100.0,
                        no_ask=market.get("no_ask", 0) / 100.0,
                        volume_24h=market.get("volume_24h", 0),
                        open_interest=market.get("open_interest", 0),
                        close_date=close_date,
                        status=market.get("status", "unknown"),
                        metadata=market
                    )
                    markets.append(market_data)
                except Exception as e:
                    logger.warning(f"Failed to parse market: {e}")
                    continue

            state.all_markets = markets
            state.markets_scanned = len(markets)

            logger.info(f"Fetched {len(markets)} markets successfully")

            # Filter markets based on policy
            filtered_markets = self._filter_markets(markets)
            state.filtered_markets = filtered_markets
            logger.info(f"Filtered to {len(filtered_markets)} markets meeting policy criteria")

            # Rank and get top opportunities
            top_markets = self._rank_markets(
                filtered_markets,
                top_n=min(10, max(1, settings.max_markets_per_cycle)),
            )
            state.top_opportunities = [
                MarketAnalysis(market=market)
                for market in top_markets
            ]
            state.opportunities_found = len(top_markets)

            logger.info(f"Identified {len(top_markets)} top opportunities")

            return state

        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            state.errors.append(f"Market fetch error: {str(e)}")
            return state

    def enrich_market_data(
        self,
        market: MarketData,
        fetch_news: bool = True,
        fetch_social: bool = True
    ) -> MarketAnalysis:
        """
        Enrich market data with news and social sentiment

        Args:
            market: Market data to enrich
            fetch_news: Whether to fetch news articles
            fetch_social: Whether to fetch social media data

        Returns:
            Enriched market analysis
        """
        logger.info(f"Enriching data for {market.ticker}: {market.title}")

        analysis = MarketAnalysis(market=market)

        # Extract search query from market title
        search_query = self._extract_search_keywords(market.title)

        # Try Alpha Vantage first (Consolidated News + Sentiment)
        av_data = news_fetcher.get_market_sentiment_and_news(search_query)
        av_used = False

        if av_data and av_data.get("feed"):
            try:
                av_used = True
                logger.info(f"Using Alpha Vantage data for {market.ticker}")
                
                 # Map feed to NewsData
                analysis.news_articles = []
                for item in av_data.get("feed", []):
                    # Convert AV time format "20240101T120000" to ISO
                    pub_time = item.get("time_published", "")
                    try:
                        if len(pub_time) == 16: # basic valid check
                            dt = datetime.strptime(pub_time, "%Y%m%dT%H%M%S")
                            pub_time = dt.isoformat()
                    except:
                        pass
                        
                    analysis.news_articles.append(NewsData(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        source=item.get("source", ""),
                        published_at=pub_time,
                        description=item.get("summary", ""),
                        content=item.get("summary", "")
                    ))
                
                # Use pre-calculated sentiment
                sentiment = av_data.get("sentiment_summary", {})
                analysis.news_sentiment = sentiment.get("score", 0.0)
                
                # If we have AV data, we might skip legacy news fetch, but we can still fetch social
                logger.info(f"Alpha Vantage Sentiment: {sentiment.get('label')} ({sentiment.get('score')})")
                
            except Exception as e:
                logger.warning(f"Error processing Alpha Vantage data: {e}")
                av_used = False

        # Fallback/Augment with NewsAPI if AV failed or yielded nothing
        if fetch_news and not av_used:
            try:
                raw_news = news_fetcher.search_news(
                    query=search_query,
                    days_back=2,
                    max_results=10
                )
                # ... (rest of standard news processing)
                news_articles = []
                for article in raw_news:
                    news_articles.append(NewsData(
                        title=article.get("title", ""),
                        description=article.get("description"),
                        source=article.get("source", ""),
                        url=article.get("url", ""),
                        published_at=article.get("published_at", ""),
                        content=article.get("content")
                    ))
                analysis.news_articles = news_articles
                logger.info(f"Found {len(news_articles)} news articles via NewsAPI")
            except Exception as e:
                logger.warning(f"Failed to fetch news: {e}")

        # Fetch social media data
        if fetch_social:
            try:
                # Reddit data
                reddit_posts = social_fetcher.get_reddit_sentiment(
                    query=search_query,
                    limit=30
                )

                social_posts = []
                for post in reddit_posts:
                    social_posts.append(SocialData(
                        platform="reddit",
                        text=post.get("title", "") + " " + post.get("text", ""),
                        score=post.get("score", 0),
                        created_at=str(post.get("created_utc", "")),
                        engagement_metrics={
                            "comments": post.get("num_comments", 0)
                        }
                    ))

                # Twitter data
                tweets = social_fetcher.get_twitter_sentiment(
                    query=search_query,
                    max_results=50
                )

                for tweet in tweets:
                    social_posts.append(SocialData(
                        platform="twitter",
                        text=tweet.get("text", ""),
                        score=tweet.get("likes", 0),
                        created_at=tweet.get("created_at", ""),
                        engagement_metrics={
                            "likes": tweet.get("likes", 0),
                            "retweets": tweet.get("retweets", 0),
                            "replies": tweet.get("replies", 0)
                        }
                    ))

                analysis.social_posts = social_posts
                logger.info(f"Found {len(social_posts)} social media posts")

            except Exception as e:
                logger.warning(f"Failed to fetch social data: {e}")

        # **NEW**: Calculate sentiment scores (previously these fields were never populated)
        try:
            # Analyze news sentiment (if not already provided by AV)
            if analysis.news_articles and analysis.news_sentiment is None:
                news_sentiment_result = sentiment_analyzer.analyze_news_articles(
                    [
                        {
                            "title": art.title,
                            "description": art.description or "",
                            "published_at": art.published_at
                        }
                        for art in analysis.news_articles
                    ]
                )
                analysis.news_sentiment = news_sentiment_result['average_score']
                logger.info(
                    f"News sentiment: {analysis.news_sentiment:.3f} "
                    f"({news_sentiment_result['article_count']} articles)"
                )

            # Analyze social sentiment
            if analysis.social_posts:
                social_sentiment_result = sentiment_analyzer.analyze_social_posts(
                    [
                        {
                            "text": post.text,
                            "score": post.score
                        }
                        for post in analysis.social_posts
                    ]
                )
                analysis.social_sentiment = social_sentiment_result['average_score']
                logger.info(
                    f"Social sentiment: {analysis.social_sentiment:.3f} "
                    f"({social_sentiment_result['post_count']} posts)"
                )

            # Calculate combined sentiment (weighted average)
            if analysis.news_sentiment is not None or analysis.social_sentiment is not None:
                news_weight = 0.6  # News weighted more heavily
                social_weight = 0.4

                if analysis.news_sentiment is not None and analysis.social_sentiment is not None:
                    analysis.combined_sentiment = (
                        analysis.news_sentiment * news_weight +
                        analysis.social_sentiment * social_weight
                    )
                elif analysis.news_sentiment is not None:
                    analysis.combined_sentiment = analysis.news_sentiment
                elif analysis.social_sentiment is not None:
                    analysis.combined_sentiment = analysis.social_sentiment

                logger.info(f"Combined sentiment: {analysis.combined_sentiment:.3f}")

        except Exception as e:
            logger.error(f"Failed to calculate sentiment scores: {e}")

        return analysis

    def _filter_markets(self, markets: List[MarketData]) -> List[MarketData]:
        """
        Filter markets based on trading policy criteria

        Args:
            markets: List of markets to filter

        Returns:
            Filtered list of markets
        """
        filtered = []
        policy = self.policy.get("signal_selection", {})

        min_liquidity = self.policy.get("risk_management", {}).get("min_market_liquidity", 500)
        min_hours = policy.get("min_time_to_close_hours", 4)  # More lenient - 4 hours
        max_days = policy.get("max_time_to_close_days", 180)
        
        filtered_out_reasons = {"liquidity": 0, "time_min": 0, "time_max": 0, "probability": 0, "date_parse": 0}

        for market in markets:
            # Check liquidity (use volume as fallback)
            liquidity = market.open_interest if market.open_interest > 0 else market.volume_24h
            if liquidity < min_liquidity:
                filtered_out_reasons["liquidity"] += 1
                continue

            # Check time to close
            try:
                # Handle various date formats
                close_date_str = market.close_date
                if not close_date_str:
                    filtered_out_reasons["date_parse"] += 1
                    continue
                    
                # Remove timezone info variations
                close_date_str = close_date_str.replace("Z", "+00:00")
                if "+00:00" not in close_date_str and "+" not in close_date_str:
                    close_date_str += "+00:00"
                    
                close_date = datetime.fromisoformat(close_date_str)
                time_to_close = close_date - datetime.now(close_date.tzinfo)

                if time_to_close.total_seconds() < min_hours * 3600:
                    filtered_out_reasons["time_min"] += 1
                    continue

                if time_to_close.days > max_days:
                    filtered_out_reasons["time_max"] += 1
                    continue

            except Exception as e:
                # Log parsing issues for debugging
                logger.debug(f"Could not parse close_date for {market.ticker}: {market.close_date} - {e}")
                filtered_out_reasons["date_parse"] += 1
                continue

            # Check probability ranges (prices are 0-1 after conversion)
            yes_mid = (market.yes_bid + market.yes_ask) / 2
            max_prob = policy.get("max_acceptable_probability", 0.85)
            min_prob = policy.get("min_acceptable_probability", 0.15)

            if not (min_prob < yes_mid < max_prob):
                filtered_out_reasons["probability"] += 1
                continue
                
            filtered.append(market)

        # Log filter statistics
        logger.info(f"Filter stats: {len(markets)} total, {len(filtered)} passed, filtered out: {filtered_out_reasons}")

        return filtered

    def _rank_markets(self, markets: List[MarketData], top_n: int = 3) -> List[MarketData]:
        """
        Rank markets by potential opportunity

        Scoring factors:
        - Liquidity (higher is better)
        - Spread (tighter is better)
        - Volume (higher is better)
        - Probability (closer to 0.5 is higher uncertainty/opportunity)

        Args:
            markets: List of markets to rank
            top_n: Number of top markets to return

        Returns:
            Top N markets by opportunity score
        """
        scored_markets = []

        for market in markets:
            score = 0.0

            # Liquidity score (normalized)
            liquidity_score = min(market.open_interest / 100000, 1.0) * 30

            # Spread score (tighter spread = higher score)
            yes_spread = market.yes_ask - market.yes_bid
            spread_score = max(0, (0.10 - yes_spread) / 0.10) * 20

            # Volume score
            volume_score = min(market.volume_24h / 50000, 1.0) * 20

            # Probability distance from 50% (more uncertainty = more opportunity)
            yes_mid = (market.yes_bid + market.yes_ask) / 2
            prob_distance = abs(yes_mid - 0.5)
            prob_score = (1 - prob_distance / 0.5) * 30

            total_score = liquidity_score + spread_score + volume_score + prob_score

            scored_markets.append((market, total_score))

        # Sort by score descending
        scored_markets.sort(key=lambda x: x[1], reverse=True)

        # Return top N
        top_markets = [market for market, score in scored_markets[:top_n]]

        # Log top opportunities
        logger.info("Top market opportunities:")
        for i, (market, score) in enumerate(scored_markets[:top_n], 1):
            logger.info(
                f"  {i}. {market.ticker} - {market.title[:60]}... "
                f"(Score: {score:.1f}, Liquidity: ${market.open_interest:,.0f})"
            )

        return top_markets

    def _extract_search_keywords(self, title: str) -> str:
        """
        Extract relevant keywords from market title for news/social search

        Args:
            title: Market title

        Returns:
            Search query string
        """
        # Remove common question words
        stop_words = ["will", "the", "a", "an", "in", "on", "at", "to", "for", "of", "be"]

        words = title.lower().split()
        keywords = [w for w in words if w not in stop_words and len(w) > 3]

        # Take first 5 keywords
        return " ".join(keywords[:5])


# Global instance
market_data_fetcher = MarketDataFetcher()
