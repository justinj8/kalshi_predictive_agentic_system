"""
Institutional-Grade Logging with Structured JSON Output

Features:
- Trace IDs for request correlation
- JSON output for log aggregation (ELK, Datadog, etc.)
- Separate trade audit log
- Performance timing utilities
"""
import sys
import json
import uuid
import contextvars
from pathlib import Path
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Optional
import time
from loguru import logger
from config.settings import settings

# Remove default handler
logger.remove()

# Context variable for trace ID - allows tracking across async calls
_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
_cycle_id: contextvars.ContextVar[str] = contextvars.ContextVar("cycle_id", default="")

# Create logs directory if it doesn't exist
log_dir = Path("data/logs")
log_dir.mkdir(parents=True, exist_ok=True)


def get_trace_id() -> str:
    """Get current trace ID or generate new one"""
    trace = _trace_id.get()
    if not trace:
        trace = str(uuid.uuid4())[:8]
        _trace_id.set(trace)
    return trace


def set_trace_id(trace_id: str = None):
    """Set trace ID for current context"""
    _trace_id.set(trace_id or str(uuid.uuid4())[:8])


def set_cycle_id(cycle_id: str = None):
    """Set trading cycle ID"""
    _cycle_id.set(cycle_id or str(uuid.uuid4())[:8])


def get_cycle_id() -> str:
    """Get current cycle ID"""
    return _cycle_id.get()


def json_serializer(record: Dict) -> str:
    """Serialize log record to JSON for structured logging"""
    subset = {
        "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "level": record["level"].name,
        "logger": record["name"],
        "message": record["message"],
        "trace_id": get_trace_id(),
        "cycle_id": get_cycle_id(),
    }
    
    # Add function/line if available
    if record.get("function"):
        subset["function"] = record["function"]
    if record.get("line"):
        subset["line"] = record["line"]
    
    # Add any extra fields
    if record.get("extra"):
        for key, value in record["extra"].items():
            if key not in ["name"]:  # Skip internal keys
                subset[key] = value
    
    # Add exception info if present
    if record.get("exception"):
        subset["exception"] = {
            "type": str(record["exception"].type.__name__) if record["exception"].type else None,
            "value": str(record["exception"].value) if record["exception"].value else None,
        }
    
    return json.dumps(subset, default=str)


def json_sink(message):
    """Write JSON-formatted log to file"""
    record = message.record
    json_str = json_serializer(record)
    sys.stderr.write(json_str + "\n")


# Console handler with color (human readable)
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level=settings.log_level,
    colorize=True,
)

# File handler for all logs (JSON format for parsing)
# Using Loguru's built-in serialize option for proper JSON output
logger.add(
    log_dir / "system_{time:YYYY-MM-DD}.json",
    format="{message}",
    level="DEBUG",
    rotation="00:00",
    retention="30 days",
    compression="zip",
    serialize=True,  # Use Loguru's built-in JSON serialization
)

# File handler for all logs (human readable backup)
logger.add(
    log_dir / "system_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="DEBUG",
    rotation="00:00",
    retention="30 days",
    compression="zip",
)

# File handler for trades only (audit log)
logger.add(
    log_dir / "trades_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    level="INFO",
    filter=lambda record: "TRADE" in record["extra"] or "trade" in record["message"].lower(),
    rotation="00:00",
    retention="365 days",  # Keep trade logs for 1 year
    compression="zip",
)

# File handler for errors
logger.add(
    log_dir / "errors_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}\n{exception}",
    level="ERROR",
    rotation="00:00",
    retention="90 days",
    compression="zip",
)


def get_logger(name: str):
    """Get a logger instance with a specific name"""
    return logger.bind(name=name)


class TradeLogger:
    """Specialized logger for trade audit trail"""
    
    def __init__(self):
        self._logger = logger.bind(TRADE=True)
    
    def log_signal(self, ticker: str, signal_type: str, confidence: float, 
                   reasoning: str = "", trace_id: str = None):
        """Log a trading signal"""
        self._logger.info(
            f"SIGNAL | {ticker} | {signal_type} | Confidence: {confidence:.1f}%",
            extra={
                "event": "signal",
                "ticker": ticker,
                "signal_type": signal_type,
                "confidence": confidence,
                "reasoning": reasoning[:500],  # Truncate long reasoning
                "trace_id": trace_id or get_trace_id()
            }
        )
    
    def log_order(self, ticker: str, side: str, quantity: int, price: float,
                  order_id: str = None, trace_id: str = None):
        """Log an order submission"""
        self._logger.info(
            f"ORDER | {ticker} | {side.upper()} | {quantity} @ ${price:.2f}",
            extra={
                "event": "order",
                "ticker": ticker,
                "side": side,
                "quantity": quantity,
                "price": price,
                "order_id": order_id,
                "trace_id": trace_id or get_trace_id()
            }
        )
    
    def log_fill(self, ticker: str, side: str, quantity: int, price: float,
                 order_id: str = None, pnl: float = None, trace_id: str = None):
        """Log an order fill"""
        pnl_str = f" | P&L: ${pnl:.2f}" if pnl is not None else ""
        self._logger.info(
            f"FILL | {ticker} | {side.upper()} | {quantity} @ ${price:.2f}{pnl_str}",
            extra={
                "event": "fill",
                "ticker": ticker,
                "side": side,
                "quantity": quantity,
                "price": price,
                "order_id": order_id,
                "pnl": pnl,
                "trace_id": trace_id or get_trace_id()
            }
        )
    
    def log_position(self, ticker: str, action: str, quantity: int, 
                     entry_price: float, current_price: float = None):
        """Log position changes"""
        self._logger.info(
            f"POSITION | {action.upper()} | {ticker} | {quantity} @ ${entry_price:.2f}",
            extra={
                "event": "position",
                "ticker": ticker,
                "action": action,
                "quantity": quantity,
                "entry_price": entry_price,
                "current_price": current_price,
                "trace_id": get_trace_id()
            }
        )


def timed(func):
    """Decorator to log function execution time"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start
            logger.debug(
                f"{func.__name__} completed in {duration:.3f}s",
                extra={"duration_ms": duration * 1000, "function": func.__name__}
            )
            return result
        except Exception as e:
            duration = time.time() - start
            logger.error(
                f"{func.__name__} failed after {duration:.3f}s: {e}",
                extra={"duration_ms": duration * 1000, "function": func.__name__, "error": str(e)}
            )
            raise
    return wrapper


# Global instances
trade_logger = TradeLogger()

# Export
__all__ = [
    "logger", "get_logger", "trade_logger", 
    "get_trace_id", "set_trace_id", "set_cycle_id", "get_cycle_id",
    "timed"
]

