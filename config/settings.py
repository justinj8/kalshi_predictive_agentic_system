"""
Configuration management for Kalshi Predictive Markets System
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    """System configuration loaded from environment variables"""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False
    )

    # Anthropic API
    anthropic_api_key: str = ""  # Required for LLM functionality

    # Kalshi API
    kalshi_api_key: str = ""
    kalshi_api_secret: str = ""
    kalshi_env: Literal["demo", "prod"] = "demo"

    # News & Social APIs
    news_api_key: str = ""
    alpha_vantage_api_key: str = ""  # New: Combined News + Sentiment
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_secret: str = ""
    twitter_bearer_token: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "KalshiPredictiveBot/1.0"

    # Trading Configuration
    starting_capital: float = 100.0  # Starting with $100 for production validation
    risk_per_trade_percent: float = 5.0
    trading_mode: Literal["paper", "live"] = "paper"  # Always start in paper mode

    # System Configuration
    log_level: str = "INFO"
    scheduler_interval_minutes: int = 15
    database_url: str = "sqlite:///data/trades.db"

    # LLM Configuration
    llm_model: str = "claude-sonnet-4-20250514"  # Updated to latest model
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4000

    # Circuit Breaker Limits (adjusted for $100 capital)
    max_daily_trades: int = 5
    max_daily_loss_percent: float = 15.0
    min_market_liquidity: float = 500.0

    # Computed properties
    @property
    def max_position_size(self) -> float:
        """Maximum size per trade based on risk percentage"""
        return self.starting_capital * (self.risk_per_trade_percent / 100.0)

    @property
    def max_daily_loss(self) -> float:
        """Maximum daily loss in dollars"""
        return self.starting_capital * (self.max_daily_loss_percent / 100.0)


# Global settings instance
settings = Settings()
