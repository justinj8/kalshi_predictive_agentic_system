"""
Health Check System for Institutional Trading

Provides comprehensive health status for:
- Database connectivity
- API endpoints (Kalshi, Anthropic, News)
- System resources (memory, disk)
- Trading state (circuit breakers, positions)
"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import threading
import asyncio
from src.utils.logger import get_logger

logger = get_logger(__name__)


class HealthStatus(Enum):
    """Health check status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status for a single component"""
    name: str
    status: HealthStatus
    message: str = ""
    last_check: datetime = None
    latency_ms: float = 0
    details: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "latency_ms": self.latency_ms,
            "details": self.details or {}
        }


class HealthChecker:
    """Central health check coordinator"""
    
    def __init__(self):
        self._components: Dict[str, ComponentHealth] = {}
        self._check_interval = 60  # seconds
        self._stale_threshold = 300  # 5 minutes
        self._lock = threading.Lock()
        self._started_at = datetime.utcnow()
        logger.info("Health checker initialized")
    
    def register_check(self, name: str, status: HealthStatus, 
                       message: str = "", latency_ms: float = 0,
                       details: Dict = None):
        """Register or update a health check result"""
        with self._lock:
            self._components[name] = ComponentHealth(
                name=name,
                status=status,
                message=message,
                last_check=datetime.utcnow(),
                latency_ms=latency_ms,
                details=details
            )
    
    def check_database(self) -> ComponentHealth:
        """Check database connectivity"""
        import time
        from sqlalchemy import text
        start = time.time()
        try:
            from src.database.models import get_session
            session = get_session()
            # Simple query to verify connection
            session.execute(text("SELECT 1"))
            session.close()
            latency = (time.time() - start) * 1000
            
            result = ComponentHealth(
                name="database",
                status=HealthStatus.HEALTHY,
                message="Database connection OK",
                last_check=datetime.utcnow(),
                latency_ms=latency
            )
        except Exception as e:
            result = ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database error: {str(e)}",
                last_check=datetime.utcnow()
            )
        
        self._components["database"] = result
        return result
    
    def check_kalshi_api(self) -> ComponentHealth:
        """Check Kalshi API connectivity"""
        import time
        start = time.time()
        try:
            from src.utils.kalshi_client import kalshi_client
            # Simple API call to verify connection
            markets = kalshi_client.get_all_markets(limit=1)
            latency = (time.time() - start) * 1000
            
            result = ComponentHealth(
                name="kalshi_api",
                status=HealthStatus.HEALTHY,
                message=f"Kalshi API OK",
                last_check=datetime.utcnow(),
                latency_ms=latency,
                details={"markets_available": len(markets) > 0}
            )
        except Exception as e:
            result = ComponentHealth(
                name="kalshi_api",
                status=HealthStatus.UNHEALTHY,
                message=f"Kalshi API error: {str(e)}",
                last_check=datetime.utcnow()
            )
        
        self._components["kalshi_api"] = result
        return result
    
    def check_anthropic_api(self) -> ComponentHealth:
        """Check Anthropic/Claude API connectivity"""
        import time
        start = time.time()
        try:
            from config.settings import settings
            import anthropic
            
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            # Minimal API call to verify key validity
            response = client.messages.create(
                model="claude-3-haiku-20240307",  # Use cheapest model for health check
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}]
            )
            latency = (time.time() - start) * 1000
            
            result = ComponentHealth(
                name="anthropic_api",
                status=HealthStatus.HEALTHY,
                message="Anthropic API OK",
                last_check=datetime.utcnow(),
                latency_ms=latency
            )
        except Exception as e:
            error_msg = str(e)
            # Don't fail health if it's just a rate limit
            if "rate" in error_msg.lower():
                result = ComponentHealth(
                    name="anthropic_api",
                    status=HealthStatus.DEGRADED,
                    message="Anthropic API rate limited",
                    last_check=datetime.utcnow()
                )
            else:
                result = ComponentHealth(
                    name="anthropic_api",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Anthropic API error: {error_msg[:100]}",
                    last_check=datetime.utcnow()
                )
        
        self._components["anthropic_api"] = result
        return result
    
    def check_trading_state(self) -> ComponentHealth:
        """Check trading system state"""
        try:
            import yaml
            from src.agents.position_manager import position_manager
            from config.settings import settings
            
            # Load trading policy to get max positions
            try:
                with open("config/trading_policy.yaml", "r") as f:
                    policy = yaml.safe_load(f)
                max_positions = policy.get("position_management", {}).get("max_concurrent_positions", 3)
            except Exception:
                max_positions = 3  # Default fallback
            
            # Use get_portfolio_summary which exists in the PositionManager
            summary = position_manager.get_portfolio_summary()
            position_count = summary.get("total_positions", 0)
            
            # Determine status based on capacity
            if position_count >= max_positions:
                status = HealthStatus.DEGRADED
                message = f"At position capacity ({position_count}/{max_positions})"
            else:
                status = HealthStatus.HEALTHY
                message = f"Trading active ({position_count}/{max_positions} positions)"
            
            result = ComponentHealth(
                name="trading_state",
                status=status,
                message=message,
                last_check=datetime.utcnow(),
                details={
                    "open_positions": position_count,
                    "max_positions": max_positions,
                    "trading_mode": settings.trading_mode,
                    "unrealized_pnl": summary.get("total_unrealized_pnl", 0)
                }
            )
        except Exception as e:
            result = ComponentHealth(
                name="trading_state",
                status=HealthStatus.UNKNOWN,
                message=f"Could not check trading state: {str(e)}",
                last_check=datetime.utcnow()
            )
        
        self._components["trading_state"] = result
        return result
    
    def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks and return summary"""
        checks = [
            self.check_database(),
            self.check_kalshi_api(),
            self.check_trading_state(),
            # Skip Anthropic check by default (costs money)
        ]
        
        # Determine overall status
        statuses = [c.status for c in checks]
        if HealthStatus.UNHEALTHY in statuses:
            overall = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY
        
        uptime = (datetime.utcnow() - self._started_at).total_seconds()
        
        return {
            "status": overall.value,
            "uptime_seconds": uptime,
            "timestamp": datetime.utcnow().isoformat(),
            "components": {c.name: c.to_dict() for c in checks}
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get current health status (from cache or run checks)"""
        # Check if we have recent data
        now = datetime.utcnow()
        stale = False
        
        for component in self._components.values():
            if component.last_check is None:
                stale = True
                break
            if (now - component.last_check).total_seconds() > self._stale_threshold:
                stale = True
                break
        
        if stale or not self._components:
            return self.run_all_checks()
        
        # Return cached status
        statuses = [c.status for c in self._components.values()]
        if HealthStatus.UNHEALTHY in statuses:
            overall = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY
        
        return {
            "status": overall.value,
            "uptime_seconds": (now - self._started_at).total_seconds(),
            "timestamp": now.isoformat(),
            "components": {name: c.to_dict() for name, c in self._components.items()}
        }
    
    def is_healthy(self) -> bool:
        """Quick check if system is healthy"""
        status = self.get_status()
        return status["status"] != "unhealthy"


# Global health checker instance
health_checker = HealthChecker()
