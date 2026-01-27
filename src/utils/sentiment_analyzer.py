"""
Sentiment Analyzer
Uses transformer models to score sentiment of news articles and social media posts
Fixes the broken sentiment pipeline where fields were defined but never populated
"""
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import re
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Try to import transformers, fall back to simple sentiment if unavailable
try:
    from transformers import pipeline
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    logger.warning("Transformers library not available. Using simple sentiment analysis.")
    TRANSFORMERS_AVAILABLE = False


class SentimentAnalyzer:
    """Analyzes sentiment of text using transformer models"""

    def __init__(self, model_name: str = "distilbert-base-uncased-finetuned-sst-2-english"):
        """
        Initialize sentiment analyzer

        Args:
            model_name: HuggingFace model name for sentiment analysis
                       Default: DistilBERT (fast, accurate)
                       Alternative: "ProsusAI/finbert" for financial sentiment
        """
        self.model = None
        self.model_name = model_name

        if TRANSFORMERS_AVAILABLE:
            try:
                logger.info(f"Loading sentiment model: {model_name}")
                self.model = pipeline("sentiment-analysis", model=model_name)
                logger.info("Sentiment model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load sentiment model: {e}")
                logger.info("Falling back to simple sentiment analysis")
        else:
            logger.info("Using simple sentiment analysis (no transformers)")

    def analyze_text(self, text: str) -> Dict[str, float]:
        """
        Analyze sentiment of a single text

        Args:
            text: Text to analyze

        Returns:
            Dict with 'score' (float -1 to 1) and 'confidence' (0 to 1)
        """
        if not text or len(text.strip()) == 0:
            return {"score": 0.0, "confidence": 0.0}

        # Clean text
        text = self._clean_text(text)

        # Truncate if too long (models have token limits)
        max_length = 512
        if len(text) > max_length:
            text = text[:max_length]

        if self.model:
            return self._transformer_sentiment(text)
        else:
            return self._simple_sentiment(text)

    def analyze_news_articles(
        self,
        articles: List[Dict],
        weight_by_recency: bool = True,
        recency_hours: int = 48
    ) -> Dict[str, float]:
        """
        Analyze sentiment of multiple news articles

        Args:
            articles: List of news article dicts with 'title', 'description', 'published_at'
            weight_by_recency: Weight recent articles more heavily
            recency_hours: Hours for recency weighting

        Returns:
            Dict with 'average_score', 'confidence', 'article_count'
        """
        if not articles:
            return {"average_score": 0.0, "confidence": 0.0, "article_count": 0}

        scores = []
        weights = []

        for article in articles:
            # Combine title and description for fuller context
            text = f"{article.get('title', '')} {article.get('description', '')}"

            sentiment = self.analyze_text(text)
            scores.append(sentiment['score'])

            # Calculate recency weight
            if weight_by_recency and article.get('published_at'):
                weight = self._calculate_recency_weight(
                    article['published_at'],
                    recency_hours
                )
            else:
                weight = 1.0

            weights.append(weight * sentiment['confidence'])

        # Weighted average
        if sum(weights) > 0:
            average_score = sum(s * w for s, w in zip(scores, weights)) / sum(weights)
        else:
            average_score = sum(scores) / len(scores) if scores else 0.0

        # Confidence based on number of articles and agreement
        confidence = self._calculate_confidence(scores, len(articles))

        return {
            "average_score": average_score,
            "confidence": confidence,
            "article_count": len(articles)
        }

    def analyze_social_posts(
        self,
        posts: List[Dict],
        weight_by_engagement: bool = True
    ) -> Dict[str, float]:
        """
        Analyze sentiment of social media posts

        Args:
            posts: List of social post dicts with 'text', 'score' (engagement)
            weight_by_engagement: Weight highly engaged posts more

        Returns:
            Dict with 'average_score', 'confidence', 'post_count'
        """
        if not posts:
            return {"average_score": 0.0, "confidence": 0.0, "post_count": 0}

        scores = []
        weights = []

        for post in posts:
            text = post.get('text', '')
            sentiment = self.analyze_text(text)
            scores.append(sentiment['score'])

            # Weight by engagement (likes, upvotes, etc.)
            if weight_by_engagement:
                engagement = post.get('score', 1)
                # Log scale to prevent outliers from dominating
                weight = 1.0 + (engagement ** 0.5) / 10
            else:
                weight = 1.0

            weights.append(weight * sentiment['confidence'])

        # Weighted average
        if sum(weights) > 0:
            average_score = sum(s * w for s, w in zip(scores, weights)) / sum(weights)
        else:
            average_score = sum(scores) / len(scores) if scores else 0.0

        # Confidence based on post count and agreement
        confidence = self._calculate_confidence(scores, len(posts))

        return {
            "average_score": average_score,
            "confidence": confidence,
            "post_count": len(posts)
        }

    def _transformer_sentiment(self, text: str) -> Dict[str, float]:
        """Use transformer model for sentiment analysis"""
        try:
            result = self.model(text)[0]

            # Convert to -1 to 1 scale
            label = result['label']
            confidence = result['score']

            if 'POSITIVE' in label.upper():
                score = confidence
            elif 'NEGATIVE' in label.upper():
                score = -confidence
            else:  # NEUTRAL
                score = 0.0

            return {"score": score, "confidence": confidence}

        except Exception as e:
            logger.error(f"Transformer sentiment analysis failed: {e}")
            return self._simple_sentiment(text)

    def _simple_sentiment(self, text: str) -> Dict[str, float]:
        """Simple rule-based sentiment analysis (fallback)"""
        text = text.lower()

        # Positive words
        positive_words = [
            'good', 'great', 'excellent', 'amazing', 'wonderful', 'fantastic',
            'positive', 'bullish', 'optimistic', 'strong', 'surge', 'rise',
            'gain', 'up', 'increase', 'growth', 'success', 'win', 'boom',
            'confident', 'opportunity', 'breakthrough', 'soar', 'rally'
        ]

        # Negative words
        negative_words = [
            'bad', 'terrible', 'awful', 'horrible', 'poor', 'negative',
            'bearish', 'pessimistic', 'weak', 'crash', 'fall', 'drop',
            'decline', 'loss', 'fail', 'collapse', 'recession', 'crisis',
            'concern', 'worry', 'risk', 'threat', 'plunge', 'tumble'
        ]

        pos_count = sum(1 for word in positive_words if word in text)
        neg_count = sum(1 for word in negative_words if word in text)

        total = pos_count + neg_count
        if total == 0:
            return {"score": 0.0, "confidence": 0.0}

        score = (pos_count - neg_count) / total
        confidence = min(total / 10, 1.0)  # Max confidence at 10 sentiment words

        return {"score": score, "confidence": confidence}

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        # Remove URLs
        text = re.sub(r'http\S+|www.\S+', '', text)
        # Remove special characters but keep punctuation
        text = re.sub(r'[^\w\s.,!?-]', '', text)
        # Remove extra whitespace
        text = ' '.join(text.split())
        return text

    def _calculate_recency_weight(
        self,
        published_at: str,
        recency_hours: int
    ) -> float:
        """
        Calculate weight based on article recency

        Recent articles weighted more heavily (exponential decay)
        """
        try:
            if isinstance(published_at, str):
                pub_date = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
            else:
                pub_date = published_at

            hours_old = (datetime.now(pub_date.tzinfo) - pub_date).total_seconds() / 3600

            # Exponential decay: weight = e^(-hours_old / recency_hours)
            import math
            weight = math.exp(-hours_old / recency_hours)

            return max(0.1, weight)  # Minimum weight of 0.1

        except Exception as e:
            logger.warning(f"Failed to calculate recency weight: {e}")
            return 1.0

    def _calculate_confidence(self, scores: List[float], count: int) -> float:
        """
        Calculate confidence based on agreement and sample size

        High agreement + large sample = high confidence
        """
        if not scores or count == 0:
            return 0.0

        # Agreement factor: low variance = high agreement
        try:
            import statistics
            if len(scores) > 1:
                variance = statistics.variance(scores)
                agreement = max(0, 1 - variance)  # Low variance = high agreement
            else:
                agreement = 0.5
        except:
            agreement = 0.5

        # Sample size factor: more samples = more confidence
        # Logarithmic: confidence increases with sample size but with diminishing returns
        import math
        sample_factor = min(math.log10(count + 1) / 2, 1.0)

        # Combined confidence
        confidence = (agreement * 0.6) + (sample_factor * 0.4)

        return confidence


# Global instance
sentiment_analyzer = SentimentAnalyzer()
