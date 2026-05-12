"""
Configuration management for Kalshi Predictive Markets System
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


def find_env_file():
    """Find .env file in current dir or parent directories"""
    current = Path.cwd()
    # Check current directory first
    if (current / '.env').exists():
        return str(current / '.env')
    # Check parent directory (common project structure)
    if (current.parent / '.env').exists():
        return str(current.parent / '.env')
    # Fallback to default
    return '.env'


class Settings(BaseSettings):
    """System configuration loaded from environment variables"""

    model_config = SettingsConfigDict(
        env_file=find_env_file(),
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

    # LLM Configuration (legacy single-shot agents)
    # NOTE: prefer the agentic core models below; this is kept for back-compat.
    llm_model: str = "claude-sonnet-4-6"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4000

    # Agentic core model assignments
    judge_model: str = "claude-opus-4-7"               # Final adjudication
    specialist_model: str = "claude-sonnet-4-6"         # Research / debate / reflection
    cheap_model: str = "claude-haiku-4-5-20251001"      # Scout / calibration narrative

    # Agentic core feature flags
    agentic_decision_path: bool = True   # Use multi-agent core; False = legacy
    shadow_legacy: bool = True           # Also run legacy in shadow mode for comparison
    enable_web_search: bool = True       # Anthropic web_search server tool
    enable_debate: bool = True           # Bull/Bear/Red-Team parallel debate
    enable_memory: bool = True           # Memory + reflection loop
    enable_extended_thinking: bool = True  # Judge uses extended thinking
    enable_cross_market_scout: bool = True

    # Agentic budgets
    max_research_iterations: int = 8
    judge_thinking_budget_tokens: int = 10000
    research_max_tokens: int = 12000
    debate_max_tokens: int = 4000
    judge_max_tokens: int = 16000

    # Memory subsystem
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    memory_recall_top_k: int = 5

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
