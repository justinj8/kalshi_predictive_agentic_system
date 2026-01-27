"""
Prometheus Metrics for Institutional Trading System

Provides comprehensive metrics collection for:
- Trade execution (count, latency, success rate)
- Portfolio performance (P&L, positions, exposure)
- API health (errors, latency, rate limits)
- System health (uptime, cycle completion)
"""
from datetime import datetime
from typing import Dict, Any, Optional
import threading
import time
from dataclasses import dataclass, field
from collections import defaultdict
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MetricPoint:
    """Single metric data point with timestamp"""
    value: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    labels: Dict[str, str] = field(default_factory=dict)


class Counter:
    """Prometheus-style counter metric (monotonically increasing)"""
    
    def __init__(self, name: str, description: str, labels: list = None):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self._values: Dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()
    
    def inc(self, amount: float = 1, **labels):
        """Increment counter by amount"""
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[label_key] += amount
    
    def get(self, **labels) -> float:
        """Get current counter value"""
        label_key = tuple(sorted(labels.items()))
        return self._values.get(label_key, 0)
    
    def get_all(self) -> Dict[tuple, float]:
        """Get all counter values"""
        return dict(self._values)


class Gauge:
    """Prometheus-style gauge metric (can go up and down)"""
    
    def __init__(self, name: str, description: str, labels: list = None):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self._values: Dict[tuple, float] = {}
        self._lock = threading.Lock()
    
    def set(self, value: float, **labels):
        """Set gauge to specific value"""
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[label_key] = value
    
    def inc(self, amount: float = 1, **labels):
        """Increment gauge"""
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[label_key] = self._values.get(label_key, 0) + amount
    
    def dec(self, amount: float = 1, **labels):
        """Decrement gauge"""
        self.inc(-amount, **labels)
    
    def get(self, **labels) -> float:
        """Get current gauge value"""
        label_key = tuple(sorted(labels.items()))
        return self._values.get(label_key, 0)
    
    def get_all(self) -> Dict[tuple, float]:
        """Get all gauge values"""
        return dict(self._values)


class Histogram:
    """Prometheus-style histogram for latency/duration tracking"""
    
    DEFAULT_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    
    def __init__(self, name: str, description: str, buckets: list = None, labels: list = None):
        self.name = name
        self.description = description
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self.label_names = labels or []
        self._bucket_counts: Dict[tuple, Dict[float, int]] = defaultdict(lambda: defaultdict(int))
        self._sum: Dict[tuple, float] = defaultdict(float)
        self._count: Dict[tuple, int] = defaultdict(int)
        self._lock = threading.Lock()
    
    def observe(self, value: float, **labels):
        """Record an observation"""
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            self._sum[label_key] += value
            self._count[label_key] += 1
            for bucket in self.buckets:
                if value <= bucket:
                    self._bucket_counts[label_key][bucket] += 1
    
    def get_percentile(self, percentile: float, **labels) -> Optional[float]:
        """Estimate percentile from histogram buckets"""
        label_key = tuple(sorted(labels.items()))
        count = self._count.get(label_key, 0)
        if count == 0:
            return None
        
        target = count * (percentile / 100.0)
        cumulative = 0
        for bucket in sorted(self.buckets):
            cumulative += self._bucket_counts[label_key].get(bucket, 0)
            if cumulative >= target:
                return bucket
        return self.buckets[-1]
    
    def get_stats(self, **labels) -> Dict[str, float]:
        """Get histogram statistics"""
        label_key = tuple(sorted(labels.items()))
        count = self._count.get(label_key, 0)
        total = self._sum.get(label_key, 0)
        return {
            "count": count,
            "sum": total,
            "avg": total / count if count > 0 else 0,
            "p50": self.get_percentile(50, **labels),
            "p95": self.get_percentile(95, **labels),
            "p99": self.get_percentile(99, **labels),
        }


class TradingMetrics:
    """Central metrics registry for the trading system"""
    
    def __init__(self):
        # ==================== Trade Metrics ====================
        self.trades_total = Counter(
            "trades_total", 
            "Total number of trades",
            labels=["side", "market", "status"]
        )
        self.trades_pnl = Gauge(
            "trades_pnl_dollars",
            "Profit/Loss in dollars",
            labels=["type"]  # realized, unrealized, total
        )
        self.trade_latency = Histogram(
            "trade_latency_seconds",
            "Time from signal to execution",
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
        )
        
        # ==================== Position Metrics ====================
        self.positions_open = Gauge(
            "positions_open_count",
            "Number of open positions"
        )
        self.position_value = Gauge(
            "position_value_dollars",
            "Total position value",
            labels=["side"]
        )
        self.position_exposure = Gauge(
            "position_exposure_percent",
            "Portfolio exposure percentage",
            labels=["category"]
        )
        
        # ==================== Signal Metrics ====================
        self.signals_generated = Counter(
            "signals_generated_total",
            "Total signals generated",
            labels=["signal_type", "market"]
        )
        self.signal_confidence = Histogram(
            "signal_confidence_percent",
            "Distribution of signal confidences",
            buckets=[30, 40, 50, 60, 70, 80, 90, 95]
        )
        
        # ==================== API Metrics ====================
        self.api_requests = Counter(
            "api_requests_total",
            "Total API requests",
            labels=["api", "endpoint", "status"]
        )
        self.api_latency = Histogram(
            "api_latency_seconds",
            "API request latency",
            labels=["api"]
        )
        self.api_errors = Counter(
            "api_errors_total",
            "API errors",
            labels=["api", "error_type"]
        )
        self.api_rate_limit_hits = Counter(
            "api_rate_limit_hits_total",
            "Rate limit hits",
            labels=["api"]
        )
        
        # ==================== System Metrics ====================
        self.trading_cycles = Counter(
            "trading_cycles_total",
            "Total trading cycles completed",
            labels=["status"]  # success, error
        )
        self.cycle_duration = Histogram(
            "cycle_duration_seconds",
            "Trading cycle duration",
            buckets=[10, 30, 60, 120, 300, 600]
        )
        self.circuit_breaker_triggers = Counter(
            "circuit_breaker_triggers_total",
            "Circuit breaker activations",
            labels=["reason"]
        )
        self.system_uptime = Gauge(
            "system_uptime_seconds",
            "System uptime in seconds"
        )
        
        # ==================== Risk Metrics ====================
        self.drawdown_current = Gauge(
            "drawdown_current_percent",
            "Current drawdown percentage"
        )
        self.drawdown_max = Gauge(
            "drawdown_max_percent",
            "Maximum drawdown percentage"
        )
        self.portfolio_value = Gauge(
            "portfolio_value_dollars",
            "Total portfolio value"
        )
        self.daily_pnl = Gauge(
            "daily_pnl_dollars",
            "Daily profit/loss"
        )
        
        # Tracking
        self._start_time = datetime.utcnow()
        logger.info("Trading metrics initialized")
    
    def record_trade(self, side: str, market: str, status: str, 
                     pnl: float = 0, latency_seconds: float = 0):
        """Record a trade execution"""
        self.trades_total.inc(side=side, market=market, status=status)
        if status == "filled":
            self.trades_pnl.inc(pnl, type="realized")
            self.trade_latency.observe(latency_seconds)
    
    def record_signal(self, signal_type: str, market: str, confidence: float):
        """Record a trading signal"""
        self.signals_generated.inc(signal_type=signal_type, market=market)
        self.signal_confidence.observe(confidence)
    
    def record_api_call(self, api: str, endpoint: str, status: str, 
                        latency_seconds: float, error_type: str = None):
        """Record an API call"""
        self.api_requests.inc(api=api, endpoint=endpoint, status=status)
        self.api_latency.observe(latency_seconds, api=api)
        if error_type:
            self.api_errors.inc(api=api, error_type=error_type)
    
    def record_cycle(self, status: str, duration_seconds: float):
        """Record a trading cycle completion"""
        self.trading_cycles.inc(status=status)
        self.cycle_duration.observe(duration_seconds)
    
    def update_portfolio(self, value: float, daily_pnl: float, 
                         current_drawdown: float, max_drawdown: float):
        """Update portfolio metrics"""
        self.portfolio_value.set(value)
        self.daily_pnl.set(daily_pnl)
        self.drawdown_current.set(current_drawdown)
        self.drawdown_max.set(max_drawdown)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary for health check / dashboard"""
        uptime = (datetime.utcnow() - self._start_time).total_seconds()
        self.system_uptime.set(uptime)
        
        return {
            "uptime_seconds": uptime,
            "trades": {
                "total": sum(self.trades_total.get_all().values()),
                "by_status": {
                    k[-1][1]: v for k, v in self.trades_total.get_all().items()
                    if k and len(k) >= 3
                }
            },
            "signals": {
                "total": sum(self.signals_generated.get_all().values()),
                "confidence_avg": self.signal_confidence.get_stats().get("avg", 0)
            },
            "api": {
                "requests": sum(self.api_requests.get_all().values()),
                "errors": sum(self.api_errors.get_all().values())
            },
            "cycles": {
                "total": sum(self.trading_cycles.get_all().values()),
                "avg_duration": self.cycle_duration.get_stats().get("avg", 0)
            },
            "portfolio": {
                "value": self.portfolio_value.get(),
                "daily_pnl": self.daily_pnl.get(),
                "drawdown_current": self.drawdown_current.get(),
                "drawdown_max": self.drawdown_max.get()
            }
        }
    
    def export_prometheus(self) -> str:
        """Export metrics in Prometheus text format"""
        lines = []
        
        def add_metric(name, description, metric_type, values):
            lines.append(f"# HELP {name} {description}")
            lines.append(f"# TYPE {name} {metric_type}")
            for labels, value in values.items():
                if labels:
                    label_str = ",".join(f'{k}="{v}"' for k, v in labels)
                    lines.append(f"{name}{{{label_str}}} {value}")
                else:
                    lines.append(f"{name} {value}")
        
        # Export all counters
        add_metric("trades_total", "Total trades", "counter", self.trades_total.get_all())
        add_metric("signals_generated_total", "Total signals", "counter", self.signals_generated.get_all())
        add_metric("api_requests_total", "API requests", "counter", self.api_requests.get_all())
        add_metric("api_errors_total", "API errors", "counter", self.api_errors.get_all())
        add_metric("trading_cycles_total", "Trading cycles", "counter", self.trading_cycles.get_all())
        
        # Export gauges
        lines.append(f"portfolio_value_dollars {self.portfolio_value.get()}")
        lines.append(f"daily_pnl_dollars {self.daily_pnl.get()}")
        lines.append(f"drawdown_current_percent {self.drawdown_current.get()}")
        lines.append(f"positions_open_count {self.positions_open.get()}")
        lines.append(f"system_uptime_seconds {(datetime.utcnow() - self._start_time).total_seconds()}")
        
        return "\n".join(lines)


# Global metrics instance
metrics = TradingMetrics()
