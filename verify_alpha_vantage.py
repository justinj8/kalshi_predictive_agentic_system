import sys
import os
import logging

# Add src to path
sys.path.append(os.getcwd())

from src.utils.alpha_vantage_client import alpha_vantage
from src.agents.market_data_fetcher import market_data_fetcher
from src.orchestrator.state_models import MarketData

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_alpha_vantage_direct():
    logger.info("--- Testing Alpha Vantage Client Directly ---")
    data = alpha_vantage.get_news_and_sentiment(topics="technology")
    
    if "sentiment_summary" in data and "feed" in data:
        logger.info("✅ Alpha Vantage returned valid structure")
        logger.info(f"Sentiment: {data['sentiment_summary']}")
        logger.info(f"Feed Items: {len(data['feed'])}")
        return True
    else:
        logger.error("❌ Invalid Alpha Vantage response")
        return False

def test_integration_with_fetcher():
    logger.info("\n--- Testing Integration with MarketDataFetcher ---")
    
    # Create a dummy market
    market = MarketData(
        ticker="TEST-MARKET",
        title="Will Apple stock close above $200?",
        category="Technology",
        yes_bid=0.6,
        yes_ask=0.65,
        no_bid=0.35,
        no_ask=0.4,
        volume_24h=1000,
        open_interest=5000,
        close_date="2024-12-31T23:59:00Z",
        status="active",
        metadata={}
    )
    
    # Enrich data
    # This should trigger the AV fetch for "apple stock close" or similar keywords
    analysis = market_data_fetcher.enrich_market_data(market)
    
    # Check if we got news and sentiment
    if analysis.news_articles:
        logger.info(f"✅ Found {len(analysis.news_articles)} news articles")
        # Check source to see if it looks like our mock AV data (if we are in mock mode)
        example_source = analysis.news_articles[0].source
        logger.info(f"Source: {example_source}")
        
    if analysis.news_sentiment is not None:
        logger.info(f"✅ News Sentiment: {analysis.news_sentiment}")
    else:
        logger.error("❌ News Sentiment is missing")
        
    if analysis.combined_sentiment is not None:
        logger.info(f"✅ Combined Sentiment: {analysis.combined_sentiment}")
    else:
        logger.error("❌ Combined Sentiment is missing")

if __name__ == "__main__":
    alpha_vantage.is_mock_mode = True # Force mock mode for reliable testing
    
    if test_alpha_vantage_direct():
        test_integration_with_fetcher()
