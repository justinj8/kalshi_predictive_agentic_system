"""
Kalshi API Client Wrapper with Institutional-Grade Resilience

Features:
- Exponential backoff with jitter for retries
- Circuit breaker pattern for API failures
- Metrics tracking for monitoring
- Rate limit handling
"""
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime, timedelta
import time
import random
from functools import wraps
from dataclasses import dataclass
from config.settings import settings
from src.utils.logger import get_logger, timed

logger = get_logger(__name__)

# Try to import kalshi_python, fall back to mock mode if unavailable
try:
    import kalshi_python
    from kalshi_python.api import markets_api
    KALSHI_AVAILABLE = True
except ImportError:
    KALSHI_AVAILABLE = False
    logger.warning("kalshi_python not available, using mock mode")


@dataclass
class RetryConfig:
    """Configuration for retry behavior"""
    max_retries: int = 3
    initial_delay: float = 1.0  # seconds
    max_delay: float = 30.0  # seconds
    exponential_base: float = 2.0
    jitter: float = 0.1  # 10% jitter
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt with exponential backoff and jitter"""
        delay = min(
            self.initial_delay * (self.exponential_base ** attempt),
            self.max_delay
        )
        # Add jitter
        jitter_amount = delay * self.jitter
        delay += random.uniform(-jitter_amount, jitter_amount)
        return max(0, delay)


class CircuitBreaker:
    """Circuit breaker for API calls to prevent cascading failures"""
    
    def __init__(self, failure_threshold: int = 5, reset_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time: Optional[datetime] = None
        self.is_open = False
    
    def record_success(self):
        """Record a successful call"""
        self.failures = 0
        self.is_open = False
    
    def record_failure(self):
        """Record a failed call"""
        self.failures += 1
        self.last_failure_time = datetime.utcnow()
        if self.failures >= self.failure_threshold:
            self.is_open = True
            logger.warning(f"Circuit breaker OPEN after {self.failures} failures")
    
    def can_execute(self) -> bool:
        """Check if circuit allows execution"""
        if not self.is_open:
            return True
        
        # Check if enough time has passed to try again
        if self.last_failure_time:
            elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
            if elapsed >= self.reset_timeout:
                logger.info("Circuit breaker attempting reset (half-open)")
                return True
        
        return False


def retry_with_backoff(retry_config: RetryConfig = None, circuit_breaker: CircuitBreaker = None):
    """Decorator for retrying API calls with exponential backoff"""
    config = retry_config or RetryConfig()
    
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Check circuit breaker
            if circuit_breaker and not circuit_breaker.can_execute():
                logger.error(f"Circuit breaker OPEN, skipping {func.__name__}")
                raise Exception(f"Circuit breaker open for {func.__name__}")
            
            last_exception = None
            
            for attempt in range(config.max_retries + 1):
                try:
                    start_time = time.time()
                    result = func(*args, **kwargs)
                    
                    # Record success
                    if circuit_breaker:
                        circuit_breaker.record_success()
                    
                    # Try to record metrics
                    try:
                        from src.monitoring.metrics import metrics
                        latency = time.time() - start_time
                        metrics.record_api_call(
                            api="kalshi",
                            endpoint=func.__name__,
                            status="success",
                            latency_seconds=latency
                        )
                    except ImportError:
                        pass
                    
                    return result
                    
                except Exception as e:
                    last_exception = e
                    error_str = str(e)
                    
                    # Check for rate limit (429)
                    if "429" in error_str or "rate" in error_str.lower():
                        logger.warning(f"Rate limit hit on {func.__name__}, waiting...")
                        try:
                            from src.monitoring.metrics import metrics
                            metrics.api_rate_limit_hits.inc(api="kalshi")
                        except ImportError:
                            pass
                    
                    # Record failure
                    if circuit_breaker:
                        circuit_breaker.record_failure()
                    
                    # Check for non-retryable errors
                    if "401" in error_str or "403" in error_str:
                        logger.error(f"Auth error on {func.__name__}: {e}")
                        raise  # Don't retry auth errors
                    
                    if attempt < config.max_retries:
                        delay = config.get_delay(attempt)
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{config.max_retries + 1}), "
                            f"retrying in {delay:.2f}s: {e}"
                        )
                        time.sleep(delay)
                    else:
                        # Record final failure
                        try:
                            from src.monitoring.metrics import metrics
                            metrics.record_api_call(
                                api="kalshi",
                                endpoint=func.__name__,
                                status="error",
                                latency_seconds=0,
                                error_type=type(e).__name__
                            )
                        except ImportError:
                            pass
            
            # All retries exhausted
            logger.error(f"{func.__name__} failed after {config.max_retries + 1} attempts")
            raise last_exception
        
        return wrapper
    return decorator


# Global circuit breaker for Kalshi API
kalshi_circuit_breaker = CircuitBreaker(failure_threshold=5, reset_timeout=60)


class KalshiClientWrapper:
    """Wrapper around Kalshi API client with error handling and retry logic"""

    def __init__(self):
        """Initialize Kalshi client"""
        self.env = settings.kalshi_env
        self.client = None
        self.markets_api = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize the Kalshi API client"""
        try:
            if not KALSHI_AVAILABLE:
                logger.warning("Kalshi API not available - using mock mode")
                return
                
            if not settings.kalshi_api_key or not settings.kalshi_api_secret:
                logger.warning("Kalshi API keys not found - using mock mode")
                return
            
            # Configure API client
            config = kalshi_python.Configuration()
            
            # Use correct API endpoint
            config.host = "https://api.elections.kalshi.com/trade-api/v2"
            
            # Create API client
            self.client = kalshi_python.ApiClient(config)
            
            # Set authorization header
            self.client.default_headers["Authorization"] = f"Bearer {settings.kalshi_api_key}"
            
            # Create markets API
            self.markets_api = markets_api.MarketsApi(self.client)
            
            logger.info(f"Kalshi client initialized in {self.env} mode")
            
        except Exception as e:
            logger.error(f"Failed to initialize Kalshi client: {e}")
            self.client = None
            self.markets_api = None

    def _mock_allowed(self) -> bool:
        """Mock data is allowed only outside live trading."""
        return settings.trading_mode != "live"

    def _raise_if_live_without_api(self, operation: str):
        if not self._mock_allowed():
            raise RuntimeError(
                f"Kalshi {operation} unavailable in live mode. "
                "Refusing to use mock data."
            )

    def get_all_markets(
        self,
        status: str = "open",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Fetch all available markets

        Args:
            status: Market status (open, closed, settled)
            limit: Maximum number of markets to fetch

        Returns:
            List of market dictionaries
        """
        try:
            if self.markets_api is None:
                # Return mock data for testing
                self._raise_if_live_without_api("markets API")
                logger.info("No Kalshi API connection - using mock markets")
                return self._get_mock_markets()

            # Use the markets API
            response = self.markets_api.get_markets(limit=limit * 3, status=status)
            
            if hasattr(response, 'markets') and response.markets:
                markets = []
                for m in response.markets:
                    # Convert market object to dict
                    yes_bid = getattr(m, 'yes_bid', 0) or 0
                    yes_ask = getattr(m, 'yes_ask', 0) or 0
                    volume = getattr(m, 'volume_24h', getattr(m, 'volume', 0)) or 0
                    open_interest = getattr(m, 'open_interest', 0) or 0
                    
                    # Skip markets with no real liquidity
                    # Must have either: volume > 0 OR yes_bid > 0 (someone willing to buy)
                    if volume == 0 and yes_bid == 0 and open_interest == 0:
                        continue
                        
                    market_dict = {
                        "ticker": getattr(m, 'ticker', ''),
                        "title": getattr(m, 'title', getattr(m, 'subtitle', '')),
                        "category": getattr(m, 'category', 'other'),
                        "yes_bid": yes_bid,
                        "yes_ask": yes_ask,
                        "no_bid": getattr(m, 'no_bid', 50) or 50,
                        "no_ask": getattr(m, 'no_ask', 50) or 50,
                        "volume_24h": volume,
                        "open_interest": open_interest,
                        "close_date": getattr(m, 'close_time', getattr(m, 'expiration_time', '')),
                        "status": getattr(m, 'status', 'open')
                    }
                    markets.append(market_dict)
                    
                    if len(markets) >= limit:
                        break
                
                logger.info(f"Fetched {len(markets)} liquid markets from Kalshi (filtered from {len(response.markets)} total)")
                
                # If we got some real markets, return them
                if markets:
                    return markets
            
            # Fall back to mock data if no real markets
            self._raise_if_live_without_api("markets API returned no liquid markets")
            logger.info("No liquid markets found from Kalshi API - using mock markets")
            return self._get_mock_markets()

        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            self._raise_if_live_without_api("market fetch")
            return self._get_mock_markets()  # Fall back to mock data

    def get_market(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get details for a specific market

        Args:
            ticker: Market ticker symbol

        Returns:
            Market details dictionary or None
        """
        try:
            if self.client is None:
                # Return mock data
                self._raise_if_live_without_api("market detail API")
                return self._get_mock_market(ticker)

            response = self.markets_api.get_market(ticker=ticker)
            
            if hasattr(response, 'market'):
                market = response.market
            else:
                market = response.get("market")

            if isinstance(market, dict):
                return market

            return {
                "ticker": getattr(market, "ticker", ticker),
                "title": getattr(market, "title", getattr(market, "subtitle", "")),
                "category": getattr(market, "category", "other"),
                "yes_bid": getattr(market, "yes_bid", 0) or 0,
                "yes_ask": getattr(market, "yes_ask", 0) or 0,
                "no_bid": getattr(market, "no_bid", 0) or 0,
                "no_ask": getattr(market, "no_ask", 0) or 0,
                "volume_24h": getattr(market, "volume_24h", getattr(market, "volume", 0)) or 0,
                "open_interest": getattr(market, "open_interest", 0) or 0,
                "close_date": getattr(market, "close_time", getattr(market, "expiration_time", "")),
                "status": getattr(market, "status", "open"),
            }

        except Exception as e:
            logger.error(f"Error fetching market {ticker}: {e}")
            if not self._mock_allowed():
                raise
            return None

    def get_orderbook(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get order book for a market

        Args:
            ticker: Market ticker symbol

        Returns:
            Order book dictionary or None
        """
        try:
            if self.client is None:
                self._raise_if_live_without_api("orderbook API")
                return self._get_mock_orderbook(ticker)

            response = self.client.get_market_orderbook(ticker=ticker)
            return response.get("orderbook")

        except Exception as e:
            logger.error(f"Error fetching orderbook for {ticker}: {e}")
            if not self._mock_allowed():
                raise
            return None

    def get_trades(self, ticker: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent trades for a market

        Args:
            ticker: Market ticker symbol
            limit: Maximum number of trades to fetch

        Returns:
            List of trade dictionaries
        """
        try:
            if self.client is None:
                self._raise_if_live_without_api("trades API")
                return self._get_mock_trades(ticker)

            response = self.client.get_trades(
                ticker=ticker,
                limit=limit
            )
            return response.get("trades", [])

        except Exception as e:
            logger.error(f"Error fetching trades for {ticker}: {e}")
            if not self._mock_allowed():
                raise
            return []

    def place_order(
        self,
        ticker: str,
        side: str,
        quantity: int,
        price: int,
        order_type: str = "limit",
        action: str = "buy",
    ) -> Optional[Dict[str, Any]]:
        """
        Place an order on Kalshi

        Args:
            ticker: Market ticker symbol
            side: 'yes' or 'no'
            quantity: Number of contracts
            price: Price in cents (1-99)
            order_type: 'limit' or 'market'

        Returns:
            Order details or None
        """
        try:
            if settings.trading_mode == "paper":
                logger.info(
                    f"[PAPER TRADE] Would place {action.upper()} {side.upper()} order: "
                    f"{quantity} contracts of {ticker} at ${price/100:.2f}"
                )
                return self._create_mock_order(ticker, side, quantity, price)

            if self.client is None:
                logger.error("Cannot place order: Kalshi client not initialized")
                return None

            response = self.client.create_order(
                ticker=ticker,
                client_order_id=f"order_{int(time.time())}",
                side=side,
                action=action,
                count=quantity,
                type=order_type,
                yes_price=price if side == "yes" else None,
                no_price=price if side == "no" else None,
            )

            logger.info(
                f"Order placed: {quantity} {side.upper()} contracts of {ticker}",
                extra={"TRADE": True}
            )
            return response.get("order")

        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None

    def get_portfolio(self) -> Dict[str, Any]:
        """Get current portfolio positions"""
        try:
            if self.client is None:
                self._raise_if_live_without_api("portfolio API")
                return self._get_mock_portfolio()

            response = self.client.get_portfolio()
            return response

        except Exception as e:
            logger.error(f"Error fetching portfolio: {e}")
            if not self._mock_allowed():
                raise
            return {"positions": [], "balance": 0}

    # Mock data methods for testing without API keys
    def _get_mock_markets(self) -> List[Dict[str, Any]]:
        """
        Generate REALISTIC mock market data for proper paper trading validation
        
        Key differences from previous version:
        - Normal spreads (4-8 cents, not 2 cents)
        - Realistic edges (3-8%, not 40%)
        - Some markets with NO edge (test NO_TRADE logic)
        - Varied liquidity levels
        - Mix of categories
        """
        from datetime import timedelta
        
        now = datetime.now()
        
        return [
            # REALISTIC EDGE (5-7%): Apple earnings - priced at 58%, might be worth 65%
            {
                "ticker": "AAPL-EARNINGS-Q1",
                "title": "Will Apple beat Q1 2026 earnings estimates?",
                "category": "finance",
                "yes_bid": 55,  # Realistic spread
                "yes_ask": 61,  # 6-cent spread
                "no_bid": 39,
                "no_ask": 45,
                "volume_24h": 250000,
                "open_interest": 800000,
                "close_date": (now + timedelta(days=5)).isoformat() + "Z",
                "status": "open"
            },
            # NO EDGE: This market is fairly priced - tests NO_TRADE logic
            {
                "ticker": "SP500-UP-WEEK",
                "title": "Will S&P 500 close higher this week?",
                "category": "finance",
                "yes_bid": 48,  # Almost 50/50, no edge
                "yes_ask": 54,
                "no_bid": 46,
                "no_ask": 52,
                "volume_24h": 500000,
                "open_interest": 1200000,
                "close_date": (now + timedelta(days=4)).isoformat() + "Z",
                "status": "open"
            },
            # SMALL EDGE (3-4%): Fed decision - consensus 70%, priced at 66%
            {
                "ticker": "FED-HOLD-MAR",
                "title": "Will Fed hold rates at March meeting?",
                "category": "economics",
                "yes_bid": 63,
                "yes_ask": 69,  # 6-cent spread
                "no_bid": 31,
                "no_ask": 37,
                "volume_24h": 350000,
                "open_interest": 900000,
                "close_date": (now + timedelta(days=14)).isoformat() + "Z",
                "status": "open"
            },
            # BONDING OPPORTUNITY: High probability event for consistent returns
            {
                "ticker": "JOBS-POSITIVE-FEB",
                "title": "Will February jobs report show positive job growth?",
                "category": "economics",
                "yes_bid": 88,  # High prob but wide spread
                "yes_ask": 94,
                "no_bid": 6,
                "no_ask": 12,
                "volume_24h": 180000,
                "open_interest": 450000,
                "close_date": (now + timedelta(days=7)).isoformat() + "Z",
                "status": "open"
            },
            # SPORTS - moderate edge available
            {
                "ticker": "NFL-SUPERBOWL-WINNER",
                "title": "Will current favorite win Super Bowl 2026?",
                "category": "sports",
                "yes_bid": 30,
                "yes_ask": 36,  # Vegas might say 38-40%
                "no_bid": 64,
                "no_ask": 70,
                "volume_24h": 800000,
                "open_interest": 2500000,
                "close_date": (now + timedelta(days=10)).isoformat() + "Z",
                "status": "open"
            },
            # CRYPTO - volatile, wide spread, uncertain
            {
                "ticker": "BTC-100K-EOM",
                "title": "Will Bitcoin be above $100K end of month?",
                "category": "crypto",
                "yes_bid": 42,
                "yes_ask": 50,  # Wide 8-cent spread (volatile market)
                "no_bid": 50,
                "no_ask": 58,
                "volume_24h": 1200000,
                "open_interest": 3500000,
                "close_date": (now + timedelta(days=28)).isoformat() + "Z",
                "status": "open"
            },
            # TEMPORAL ARB PAIR 1: Same event, different timeframes
            {
                "ticker": "ETH-5K-Q1",
                "title": "Will Ethereum be above $5K by end of Q1 2026?",
                "category": "crypto",
                "yes_bid": 25,
                "yes_ask": 31,
                "no_bid": 69,
                "no_ask": 75,
                "volume_24h": 400000,
                "open_interest": 1000000,
                "close_date": (now + timedelta(days=60)).isoformat() + "Z",
                "status": "open"
            },
            # TEMPORAL ARB PAIR 2: Later deadline should have >= price
            {
                "ticker": "ETH-5K-Q2",
                "title": "Will Ethereum be above $5K by end of Q2 2026?",
                "category": "crypto",
                "yes_bid": 38,  # Higher than Q1 (correct)
                "yes_ask": 44,
                "no_bid": 56,
                "no_ask": 62,
                "volume_24h": 300000,
                "open_interest": 750000,
                "close_date": (now + timedelta(days=120)).isoformat() + "Z",
                "status": "open"
            },
            # LOW LIQUIDITY - should be avoided
            {
                "ticker": "NICHE-EVENT-123",
                "title": "Will obscure regulatory decision happen?",
                "category": "politics",
                "yes_bid": 35,
                "yes_ask": 48,  # Huge 13-cent spread = low liquidity
                "no_bid": 52,
                "no_ask": 65,
                "volume_24h": 15000,  # Very low volume
                "open_interest": 50000,
                "close_date": (now + timedelta(days=30)).isoformat() + "Z",
                "status": "open"
            }
        ]

    def _get_mock_market(self, ticker: str) -> Dict[str, Any]:
        """Get mock market details"""
        markets = self._get_mock_markets()
        for market in markets:
            if market["ticker"] == ticker:
                return market
        return markets[0]  # Return first market as fallback

    def _get_mock_orderbook(self, ticker: str) -> Dict[str, Any]:
        """Get mock orderbook"""
        return {
            "yes": [
                {"price": 47, "quantity": 100},
                {"price": 46, "quantity": 200},
                {"price": 45, "quantity": 300},
            ],
            "no": [
                {"price": 53, "quantity": 150},
                {"price": 54, "quantity": 250},
                {"price": 55, "quantity": 350},
            ]
        }

    def _get_mock_trades(self, ticker: str) -> List[Dict[str, Any]]:
        """Get mock recent trades"""
        return [
            {
                "price": 46,
                "quantity": 50,
                "side": "yes",
                "timestamp": datetime.now().isoformat()
            }
        ]

    def _create_mock_order(
        self, ticker: str, side: str, quantity: int, price: int
    ) -> Dict[str, Any]:
        """Create mock order response"""
        return {
            "order_id": f"mock_{int(time.time())}",
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "price": price,
            "status": "filled",
            "filled_quantity": quantity,
            "timestamp": datetime.now().isoformat()
        }

    def _get_mock_portfolio(self) -> Dict[str, Any]:
        """Get mock portfolio"""
        return {
            "balance": settings.starting_capital,
            "positions": []
        }


# Global client instance
KalshiClient = KalshiClientWrapper
kalshi_client = KalshiClientWrapper()
