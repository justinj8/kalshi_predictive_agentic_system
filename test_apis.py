"""
Test API Connections - Verify all API keys are working
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()


def test_anthropic_api():
    """Test Anthropic Claude API connection"""
    print("\n" + "="*60)
    print("Testing Anthropic API...")
    print("="*60)
    
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "your_anthropic_api_key_here":
        print("❌ ANTHROPIC_API_KEY not set or is placeholder")
        return False
    
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=50,
            messages=[
                {"role": "user", "content": "Say 'API connection successful!' in exactly 4 words."}
            ]
        )
        
        response = message.content[0].text
        print(f"✅ Anthropic API connected successfully!")
        print(f"   Response: {response}")
        return True
        
    except Exception as e:
        print(f"❌ Anthropic API error: {e}")
        return False


def test_kalshi_api():
    """Test Kalshi API connection"""
    print("\n" + "="*60)
    print("Testing Kalshi API...")
    print("="*60)
    
    api_key = os.getenv("KALSHI_API_KEY", "")
    api_secret = os.getenv("KALSHI_API_SECRET", "")
    
    if not api_key or api_key == "your_kalshi_api_key_here":
        print("❌ KALSHI_API_KEY not set or is placeholder")
        return False
    
    if not api_secret or api_secret == "your_kalshi_api_secret_here":
        print("❌ KALSHI_API_SECRET not set or is placeholder")
        return False
    
    try:
        import kalshi_python
        from kalshi_python.api import markets_api
        
        # Configure API client
        config = kalshi_python.Configuration()
        
        # Determine environment
        kalshi_env = os.getenv("KALSHI_ENV", "demo")
        if kalshi_env == "prod":
            config.host = "https://api.elections.kalshi.com/trade-api/v2"
        else:
            config.host = "https://api.elections.kalshi.com/trade-api/v2"  # Use prod API for testing
        
        api_client = kalshi_python.ApiClient(config)
        
        # Set API key authentication
        api_client.default_headers["Authorization"] = f"Bearer {api_key}"
        
        markets = markets_api.MarketsApi(api_client)
        
        # Try to get markets (this tests the connection)
        response = markets.get_markets(limit=3, status="open")
        
        market_count = len(response.markets) if hasattr(response, 'markets') else 0
        print(f"✅ Kalshi API connected successfully!")
        print(f"   Environment: {kalshi_env}")
        print(f"   Markets fetched: {market_count}")
        
        if market_count > 0:
            for m in response.markets[:3]:
                title = getattr(m, 'title', 'Unknown')[:50]
                print(f"   - {title}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Kalshi API error: {e}")
        return False


def test_newsapi():
    """Test NewsAPI connection"""
    print("\n" + "="*60)
    print("Testing NewsAPI...")
    print("="*60)
    
    api_key = os.getenv("NEWS_API_KEY", "")
    if not api_key or api_key == "your_news_api_key_here":
        print("❌ NEWS_API_KEY not set or is placeholder")
        return False
    
    try:
        from newsapi import NewsApiClient
        
        newsapi = NewsApiClient(api_key=api_key)
        
        # Search for recent news
        response = newsapi.get_everything(
            q="technology",
            language="en",
            sort_by="publishedAt",
            page_size=3
        )
        
        if response.get("status") == "ok":
            article_count = response.get("totalResults", 0)
            print(f"✅ NewsAPI connected successfully!")
            print(f"   Total articles found: {article_count}")
            
            articles = response.get("articles", [])
            for article in articles[:3]:
                title = article.get("title", "Unknown")[:50]
                source = article.get("source", {}).get("name", "Unknown")
                print(f"   - [{source}] {title}...")
            
            return True
        else:
            print(f"❌ NewsAPI error: {response.get('message', 'Unknown error')}")
            return False
        
    except Exception as e:
        print(f"❌ NewsAPI error: {e}")
        return False


def test_twitter_api():
    """Test Twitter/X API connection"""
    print("\n" + "="*60)
    print("Testing Twitter/X API...")
    print("="*60)
    
    bearer_token = os.getenv("TWITTER_BEARER_TOKEN", "")
    if not bearer_token or bearer_token == "your_twitter_bearer_token_here":
        print("⚠️  TWITTER_BEARER_TOKEN not set or is placeholder (optional)")
        return None  # Optional API
    
    try:
        import tweepy
        
        client = tweepy.Client(bearer_token=bearer_token)
        
        # Search for recent tweets
        response = client.search_recent_tweets(
            query="stock market",
            max_results=10,
            tweet_fields=["created_at", "public_metrics"]
        )
        
        if response.data:
            print(f"✅ Twitter API connected successfully!")
            print(f"   Tweets fetched: {len(response.data)}")
            
            for tweet in response.data[:3]:
                text = tweet.text[:50].replace('\n', ' ')
                print(f"   - {text}...")
            
            return True
        else:
            print("⚠️  Twitter API connected but no tweets found")
            return True
        
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "Too Many Requests" in error_str:
            print("⚠️  Twitter API rate limited (429) - API key is valid but rate limited")
            return True  # Rate limit means the key works
        print(f"❌ Twitter API error: {e}")
        return False


def main():
    """Run all API tests"""
    print("\n" + "="*60)
    print("API CONNECTION TEST SUITE")
    print("="*60)
    
    results = {}
    
    # Test each API
    results["Anthropic"] = test_anthropic_api()
    results["Kalshi"] = test_kalshi_api()
    results["NewsAPI"] = test_newsapi()
    results["Twitter"] = test_twitter_api()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = 0
    failed = 0
    skipped = 0
    
    for api, result in results.items():
        if result is True:
            status = "✅ PASSED"
            passed += 1
        elif result is False:
            status = "❌ FAILED"
            failed += 1
        else:
            status = "⚠️  SKIPPED (optional)"
            skipped += 1
        
        print(f"  {api:<15} {status}")
    
    print("="*60)
    print(f"Total: {passed} passed, {failed} failed, {skipped} skipped")
    print("="*60)
    
    if failed > 0:
        print("\n⚠️  Some required APIs failed. Check your .env file.")
        return False
    else:
        print("\n🎉 All required APIs are working!")
        return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
