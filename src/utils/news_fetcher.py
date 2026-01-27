"""
News and Social Media Data Fetcher
Gathers information from news APIs, Reddit, Twitter to inform trading decisions
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import requests
from newsapi import NewsApiClient
from config.settings import settings
from src.utils.logger import get_logger
from src.utils.alpha_vantage_client import alpha_vantage

logger = get_logger(__name__)


class NewsFetcher:
    """Fetches news articles related to markets"""

    def __init__(self):
        """Initialize news API client"""
        self.api_key = settings.news_api_key
        self.client = None
        if self.api_key:
            try:
                self.client = NewsApiClient(api_key=self.api_key)
                logger.info("NewsAPI client initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize NewsAPI: {e}")

    def search_news(
        self,
        query: str,
        days_back: int = 1,
        language: str = "en",
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search for news articles

        Args:
            query: Search query
            days_back: How many days back to search
            language: Language code
            max_results: Maximum number of results

        Returns:
            List of news articles
        """
        try:
            if self.client is None:
                logger.warning("NewsAPI client not initialized, returning mock data")
                return self._get_mock_news(query)

            from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

            response = self.client.get_everything(
                q=query,
                from_param=from_date,
                language=language,
                sort_by="relevancy",
                page_size=max_results
            )

            articles = response.get("articles", [])
            logger.info(f"Found {len(articles)} articles for query: {query}")

            return [
                {
                    "title": article.get("title"),
                    "description": article.get("description"),
                    "source": article.get("source", {}).get("name"),
                    "url": article.get("url"),
                    "published_at": article.get("publishedAt"),
                    "content": article.get("content", ""),
                }
                for article in articles
            ]

        except Exception as e:
            logger.error(f"Error fetching news: {e}")
            return []

    def _get_mock_news(self, query: str) -> List[Dict[str, Any]]:
        """Generate mock news for testing"""
        return [
            {
                "title": f"Breaking: Major development in {query}",
                "description": f"Recent analysis shows significant changes related to {query}",
                "source": "Mock News Source",
                "url": "https://example.com/news/1",
                "published_at": datetime.now().isoformat(),
                "content": f"Detailed analysis of {query} shows positive momentum."
            },
            {
                "title": f"Experts weigh in on {query}",
                "description": f"Industry analysts provide insights on {query}",
                "source": "Mock Financial Times",
                "url": "https://example.com/news/2",
                "published_at": (datetime.now() - timedelta(hours=2)).isoformat(),
                "content": f"Experts suggest {query} has strong fundamentals."
            }
        ]

    def get_market_sentiment_and_news(self, query: str) -> Dict[str, Any]:
        """
        Get consolidated news and sentiment context using Alpha Vantage.
        
        Args:
            query: Market topic or ticker
            
        Returns:
            Dict containing sentiment score and news articles
        """
        # Try to map query to likely tickers if possible, otherwise use topic search
        # For now, just pass the query as a topic/ticker string
        return alpha_vantage.get_news_and_sentiment(topics=query, limit=10)


class SocialMediaFetcher:
    """Fetches social media sentiment (Reddit, Twitter)"""

    def __init__(self):
        """Initialize social media API clients"""
        # Reddit client - check for real credentials (not placeholders)
        self.reddit_client = None
        reddit_id = settings.reddit_client_id
        reddit_secret = settings.reddit_client_secret
        
        # Check if credentials are real (not placeholder values)
        if (reddit_id and reddit_secret and 
            'your_' not in reddit_id.lower() and 
            'your_' not in reddit_secret.lower() and
            reddit_id != 'your_reddit_client_id_here'):
            try:
                import praw
                self.reddit_client = praw.Reddit(
                    client_id=reddit_id,
                    client_secret=reddit_secret,
                    user_agent=settings.reddit_user_agent
                )
                # Test the connection
                self.reddit_client.read_only = True
                logger.info("Reddit client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Reddit client: {e}")
                self.reddit_client = None
        else:
            logger.info("Reddit credentials not configured - using mock data")

        # Twitter client - check for real credentials
        self.twitter_client = None
        twitter_token = settings.twitter_bearer_token
        
        if (twitter_token and 
            'your_' not in twitter_token.lower() and
            twitter_token != 'your_twitter_bearer_token_here'):
            try:
                import tweepy
                self.twitter_client = tweepy.Client(
                    bearer_token=twitter_token
                )
                logger.info("Twitter client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Twitter client: {e}")
                self.twitter_client = None
        else:
            logger.info("Twitter credentials not configured - using mock data")

    def get_reddit_sentiment(
        self,
        query: str,
        subreddits: List[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get Reddit posts and comments related to query

        Args:
            query: Search query
            subreddits: List of subreddits to search (default: popular ones)
            limit: Maximum number of posts

        Returns:
            List of Reddit posts with sentiment data
        """
        if subreddits is None:
            subreddits = ["politics", "news", "worldnews", "economics", "wallstreetbets"]

        try:
            if self.reddit_client is None:
                return self._get_mock_reddit(query)

            posts = []
            for subreddit_name in subreddits:
                try:
                    subreddit = self.reddit_client.subreddit(subreddit_name)
                    for post in subreddit.search(query, limit=limit // len(subreddits)):
                        posts.append({
                            "title": post.title,
                            "text": post.selftext,
                            "score": post.score,
                            "num_comments": post.num_comments,
                            "created_utc": post.created_utc,
                            "subreddit": subreddit_name,
                            "url": f"https://reddit.com{post.permalink}"
                        })
                except Exception as e:
                    logger.warning(f"Error searching r/{subreddit_name}: {e}")

            logger.info(f"Found {len(posts)} Reddit posts for: {query}")
            return posts

        except Exception as e:
            logger.error(f"Error fetching Reddit data: {e}")
            return []

    def get_twitter_sentiment(
        self,
        query: str,
        max_results: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get recent tweets related to query

        Args:
            query: Search query
            max_results: Maximum number of tweets

        Returns:
            List of tweets with metrics
        """
        try:
            if self.twitter_client is None:
                return self._get_mock_twitter(query)

            tweets = self.twitter_client.search_recent_tweets(
                query=query,
                max_results=max_results,
                tweet_fields=["created_at", "public_metrics", "text"]
            )

            if not tweets.data:
                return []

            results = []
            for tweet in tweets.data:
                results.append({
                    "text": tweet.text,
                    "created_at": tweet.created_at.isoformat(),
                    "likes": tweet.public_metrics.get("like_count", 0),
                    "retweets": tweet.public_metrics.get("retweet_count", 0),
                    "replies": tweet.public_metrics.get("reply_count", 0),
                })

            logger.info(f"Found {len(results)} tweets for: {query}")
            return results

        except Exception as e:
            logger.error(f"Error fetching Twitter data: {e}")
            return []

    def _get_mock_reddit(self, query: str) -> List[Dict[str, Any]]:
        """Generate mock Reddit data"""
        return [
            {
                "title": f"Discussion: {query}",
                "text": f"What does everyone think about {query}?",
                "score": 150,
                "num_comments": 45,
                "created_utc": datetime.now().timestamp(),
                "subreddit": "politics",
                "url": "https://reddit.com/mock"
            }
        ]

    def _get_mock_twitter(self, query: str) -> List[Dict[str, Any]]:
        """Generate mock Twitter data"""
        return [
            {
                "text": f"Interesting developments in {query}! #news",
                "created_at": datetime.now().isoformat(),
                "likes": 120,
                "retweets": 45,
                "replies": 23
            }
        ]


# Global instances
news_fetcher = NewsFetcher()
social_fetcher = SocialMediaFetcher()
