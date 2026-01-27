# Kalshi AI Trading System - Quick Reference

## 🚀 Getting Started

```bash
# 1. Setup environment
cp .env.example .env
nano .env  # Add ANTHROPIC_API_KEY

# 2. Verify setup
python test_setup.py

# 3. Run the system
./run.sh
```

## ⚙️ Key Configuration

### .env File
```bash
ANTHROPIC_API_KEY=sk-ant-...           # Required
STARTING_CAPITAL=1000                  # Starting capital
RISK_PER_TRADE_PERCENT=5              # Risk per trade
TRADING_MODE=paper                     # paper or live
SCHEDULER_INTERVAL_MINUTES=15          # Cycle frequency
MAX_DAILY_TRADES=10                    # Daily trade limit
MAX_DAILY_LOSS_PERCENT=15             # Daily loss limit
```

### trading_policy.yaml
```yaml
risk_management:
  max_risk_per_trade: 5.0
  max_concurrent_positions: 5

signal_selection:
  min_confidence_score: 65.0
  min_expected_return: 10.0

position_management:
  take_profit_percent: 50.0
  stop_loss_percent: 25.0
```

## 📊 Monitoring

### View Logs
```bash
# All logs
tail -f data/logs/system_*.log

# Trades only
tail -f data/logs/trades_*.log

# Errors only
tail -f data/logs/errors_*.log
```

### Check Database
```python
from src.database.models import get_session, Trade, Position

session = get_session()

# View trades
trades = session.query(Trade).all()
for t in trades:
    print(f"{t.timestamp} | {t.ticker} | {t.side} | ${t.realized_pnl:.2f}")

# View positions
positions = session.query(Position).filter(Position.is_open == True).all()
for p in positions:
    print(f"{p.ticker} | ${p.unrealized_pnl:.2f}")
```

### Portfolio Summary
```python
from src.agents.position_manager import position_manager

summary = position_manager.get_portfolio_summary()
print(f"Open Positions: {summary['open_positions']}")
print(f"Unrealized P&L: ${summary['total_unrealized_pnl']:.2f}")
print(f"Realized P&L: ${summary['total_realized_pnl']:.2f}")
print(f"Total P&L: ${summary['total_pnl']:.2f}")
```

## 🧪 Testing

```bash
# Verify setup
python test_setup.py

# Run tests
pytest tests/

# Single cycle test
python -c "from src.orchestrator.langgraph_flow import orchestrator; orchestrator.run_trading_cycle()"
```

## 🎯 Common Tasks

### Change Risk Per Trade
```bash
# In .env
RISK_PER_TRADE_PERCENT=3  # Change to 3%
```

### Change Frequency
```bash
# In .env
SCHEDULER_INTERVAL_MINUTES=30  # Every 30 min instead of 15
```

### View Recent Trades
```python
from src.database.models import get_session, Trade
from datetime import datetime, timedelta

session = get_session()
recent = session.query(Trade).filter(
    Trade.timestamp > datetime.utcnow() - timedelta(hours=24)
).all()

for trade in recent:
    print(f"{trade.ticker}: {trade.side} {trade.quantity}@${trade.price:.2f}")
```

### Calculate Performance
```python
from src.database.models import get_session, Trade

session = get_session()
trades = session.query(Trade).filter(Trade.realized_pnl.isnot(None)).all()

total_pnl = sum(t.realized_pnl for t in trades)
winning_trades = [t for t in trades if t.realized_pnl > 0]
losing_trades = [t for t in trades if t.realized_pnl < 0]

print(f"Total P&L: ${total_pnl:.2f}")
print(f"Win Rate: {len(winning_trades)/len(trades)*100:.1f}%")
print(f"Avg Win: ${sum(t.realized_pnl for t in winning_trades)/len(winning_trades):.2f}")
print(f"Avg Loss: ${sum(t.realized_pnl for t in losing_trades)/len(losing_trades):.2f}")
```

## 🛑 Emergency Stop

```bash
# Press Ctrl+C in terminal
# Or kill the process
ps aux | grep "python src/main.py"
kill <PID>
```

## 🔧 Troubleshooting

### Circuit Breaker Triggered
```bash
# Check why
tail -n 100 data/logs/system_*.log | grep "CIRCUIT BREAKER"

# Common reasons:
# - Daily loss limit reached
# - Daily trade limit reached
# - Data quality issue

# Fix: Adjust limits in .env or wait until next day
```

### No Trades Executing
```bash
# Check confidence thresholds
# In config/trading_policy.yaml
signal_selection:
  min_confidence_score: 65.0  # Lower if too strict
  min_expected_return: 10.0   # Lower if too strict
```

### API Errors
```bash
# Check API key
cat .env | grep ANTHROPIC_API_KEY

# Check logs
tail -n 50 data/logs/errors_*.log
```

## 📈 Optimization

### Reduce Costs
```bash
# Option 1: Use cheaper model
LLM_MODEL=claude-3-5-haiku-20241022

# Option 2: Reduce frequency
SCHEDULER_INTERVAL_MINUTES=30

# Option 3: Analyze fewer markets
# In src/agents/market_data_fetcher.py
# Line 255: top_n=5 instead of top_n=10
```

### Increase Aggressiveness
```yaml
# In config/trading_policy.yaml
risk_management:
  max_risk_per_trade: 10.0          # From 5.0
  max_concurrent_positions: 10      # From 5
  max_daily_trades: 20              # From 10

signal_selection:
  min_confidence_score: 60.0        # From 65.0
  min_expected_return: 8.0          # From 10.0
```

### Be More Conservative
```yaml
risk_management:
  max_risk_per_trade: 2.0
  max_concurrent_positions: 3
  max_daily_loss_percent: 10.0

signal_selection:
  min_confidence_score: 75.0
  min_expected_return: 15.0
```

## 🔐 Going Live

```bash
# 1. Get Kalshi API keys
# https://kalshi.com/profile/api

# 2. Test in demo mode first
KALSHI_ENV=demo
TRADING_MODE=live

# 3. When ready
KALSHI_ENV=prod
TRADING_MODE=live

# 4. Start with small capital
STARTING_CAPITAL=100
```

## 📚 Documentation

- **README.md**: Full documentation
- **GETTING_STARTED.md**: Quick start guide
- **PROJECT_SUMMARY.md**: System overview
- **IMPLEMENTATION_PLAN.md**: Design details

## 🆘 Support

- GitHub Issues: Open an issue
- Logs: Always check `data/logs/`
- Database: Query `data/trades.db`

## ⚠️ Safety Reminders

- ✅ Always start in paper mode
- ✅ Test thoroughly before going live
- ✅ Never risk more than you can afford to lose
- ✅ Monitor the system regularly
- ✅ Review circuit breaker alerts

---

**Built with Claude 3.5 Sonnet** 🚀
