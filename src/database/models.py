"""
Database models for tracking trades, positions, and performance
"""
from datetime import datetime
from typing import Optional
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config.settings import settings

Base = declarative_base()


class Trade(Base):
    """Trade execution records"""
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Market info
    ticker = Column(String(50), nullable=False)
    market_title = Column(String(500))
    category = Column(String(50))

    # Trade details
    side = Column(String(10), nullable=False)  # 'yes' or 'no'
    action = Column(String(10), nullable=False)  # 'buy' or 'sell'
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)  # Price per contract
    total_cost = Column(Float, nullable=False)  # Total cost/proceeds

    # Order details
    order_id = Column(String(100))
    status = Column(String(20), default="pending")  # pending, filled, cancelled

    # Entry reasoning
    signal_confidence = Column(Float)
    entry_reason = Column(Text)
    news_summary = Column(Text)
    risk_score = Column(Float)

    # Position management
    position_id = Column(String(100))  # Link related trades
    is_entry = Column(Boolean, default=True)  # Entry or exit trade
    exit_reason = Column(String(100))  # stop_loss, take_profit, trailing_stop, manual

    # P&L tracking
    unrealized_pnl = Column(Float, default=0.0)
    realized_pnl = Column(Float)
    pnl_percent = Column(Float)

    def __repr__(self):
        return f"<Trade {self.ticker} {self.side} {self.quantity}@${self.price:.2f}>"


class Position(Base):
    """Open position tracking"""
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    position_id = Column(String(100), unique=True, nullable=False)

    # Market info
    ticker = Column(String(50), nullable=False)
    market_title = Column(String(500))
    category = Column(String(50))

    # Position details
    side = Column(String(10), nullable=False)
    quantity = Column(Integer, nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float)

    # Timestamps
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Risk management
    stop_loss = Column(Float)
    take_profit = Column(Float)
    trailing_stop_activation = Column(Float)
    highest_price = Column(Float)  # For trailing stop

    # P&L
    unrealized_pnl = Column(Float, default=0.0)
    unrealized_pnl_percent = Column(Float, default=0.0)
    realized_pnl = Column(Float)

    # Status
    is_open = Column(Boolean, default=True)

    def __repr__(self):
        return f"<Position {self.ticker} {self.side} {self.quantity}@${self.entry_price:.2f}>"


class MarketSnapshot(Base):
    """Historical market data snapshots"""
    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    ticker = Column(String(50), nullable=False)
    title = Column(String(500))
    category = Column(String(50))

    # Pricing
    yes_bid = Column(Float)
    yes_ask = Column(Float)
    no_bid = Column(Float)
    no_ask = Column(Float)

    # Volume & liquidity
    volume_24h = Column(Float)
    open_interest = Column(Float)

    # Market status
    status = Column(String(20))
    close_date = Column(DateTime)

    # Additional data
    market_metadata = Column(JSON)

    def __repr__(self):
        return f"<MarketSnapshot {self.ticker} @ {self.timestamp}>"


class TradingSession(Base):
    """Trading session logs (each 15-min cycle)"""
    __tablename__ = "trading_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Session results
    markets_scanned = Column(Integer)
    signals_generated = Column(Integer)
    trades_executed = Column(Integer)

    # Performance
    starting_balance = Column(Float)
    ending_balance = Column(Float)
    session_pnl = Column(Float)

    # Circuit breaker
    circuit_breaker_triggered = Column(Boolean, default=False)
    circuit_breaker_reason = Column(String(200))

    # AI decisions
    top_opportunity = Column(String(100))
    top_opportunity_score = Column(Float)
    opportunities_analyzed = Column(JSON)

    # Logs
    execution_log = Column(Text)
    errors = Column(Text)

    def __repr__(self):
        return f"<TradingSession @ {self.timestamp}>"


class PerformanceMetrics(Base):
    """Aggregate performance metrics"""
    __tablename__ = "performance_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    calculated_at = Column(DateTime, default=datetime.utcnow)

    # Overall stats
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)

    # P&L
    total_pnl = Column(Float, default=0.0)
    total_pnl_percent = Column(Float, default=0.0)
    average_win = Column(Float, default=0.0)
    average_loss = Column(Float, default=0.0)
    largest_win = Column(Float, default=0.0)
    largest_loss = Column(Float, default=0.0)

    # Risk metrics
    max_drawdown = Column(Float, default=0.0)
    current_drawdown = Column(Float, default=0.0)
    sharpe_ratio = Column(Float)

    # Position stats
    average_holding_period_hours = Column(Float)
    current_positions = Column(Integer, default=0)

    # Capital
    current_balance = Column(Float)
    peak_balance = Column(Float)

    def __repr__(self):
        return f"<PerformanceMetrics WinRate={self.win_rate:.1f}% PnL=${self.total_pnl:.2f}>"


# Database initialization
def init_database():
    """Initialize database and create tables"""
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    return engine


# Global engine and session factory (singleton pattern for efficiency)
_engine = None
_Session = None


def _get_engine():
    """Get or create the database engine (singleton)"""
    global _engine
    if _engine is None:
        _engine = create_engine(settings.database_url)
    return _engine


def _get_session_factory():
    """Get or create session factory (singleton)"""
    global _Session
    if _Session is None:
        _Session = sessionmaker(bind=_get_engine())
    return _Session


def get_session():
    """
    Get database session (legacy, for backward compatibility)
    
    WARNING: Caller is responsible for closing the session!
    Prefer using get_db_session() context manager instead.
    """
    Session = _get_session_factory()
    return Session()


@contextmanager
def get_db_session():
    """
    Context manager for safe database sessions
    
    Automatically commits on success, rolls back on exception,
    and always closes the session to prevent leaks.
    
    Usage:
        with get_db_session() as session:
            # your database operations
            session.query(Trade).all()
            # commits automatically on exit
    """
    Session = _get_session_factory()
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
