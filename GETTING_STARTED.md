# Getting Started - Kalshi Predictive Markets AI Trading System

## Quick Start (5 Minutes)

### 1. Get Your Anthropic API Key

1. Go to https://console.anthropic.com/
2. Sign up or log in
3. Navigate to API Keys
4. Create a new key
5. Copy the key (starts with `sk-ant-...`)

### 2. Set Up the Environment

```bash
cd /Users/justinjohn/Documents/GitHub/kalshi_predictive_agentic_system

# Copy environment template
cp .env.example .env

# Edit .env and add your Anthropic API key
nano .env  # or use any text editor
```

In the `.env` file, replace:
```
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

with:
```
ANTHROPIC_API_KEY=sk-ant-your-actual-key-here
```

### 3. Verify Setup

```bash
python test_setup.py
```

This will check that everything is configured correctly.

### 4. Run the System

```bash
./run.sh
```

Or manually:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python src/main.py
```

## What Happens When You Run It?

The system will:

1. **Initialize** - Set up database and logging
2. **Run First Cycle** - Immediately execute one trading cycle:
   - Fetch all Kalshi markets (using mock data for now)
   - Rank markets by opportunity
   - Analyze top markets with Claude
   - Generate trading signals
   - Review and approve/block trades
   - Execute approved trades (in PAPER mode - no real money)
3. **Schedule** - Continue running every 15 minutes

## Understanding the Output

You'll see logs like:

```
2024-01-18 12:00:00 | INFO     | Starting trading cycle...
2024-01-18 12:00:01 | INFO     | Fetched 50 markets from Kalshi
2024-01-18 12:00:01 | INFO     | Top opportunity: PRES-2024-TRUMP
2024-01-18 12:00:05 | INFO     | Claude analysis: LONG signal, 75% confidence
2024-01-18 12:00:10 | INFO     | Position sizing: 10 contracts @ $0.47
2024-01-18 12:00:15 | INFO     | Policy review: APPROVED
2024-01-18 12:00:16 | INFO     | [PAPER TRADE] Executed: 10 contracts
```

## Configuration Options

### Change Trading Parameters

Edit `.env`:

```bash
# Capital
STARTING_CAPITAL=1000  # Start with $1,000

# Risk
RISK_PER_TRADE_PERCENT=5  # Risk 5% per trade

# Trading mode
TRADING_MODE=paper  # paper or live

# Frequency
SCHEDULER_INTERVAL_MINUTES=15  # Run every 15 min

# Limits
MAX_DAILY_TRADES=10
MAX_DAILY_LOSS_PERCENT=15
```

### Adjust Trading Strategy

Edit `config/trading_policy.yaml`:

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

## Viewing Results

### Check the Database

```python
from src.database.models import get_session, Trade, Position

session = get_session()

# View all trades
trades = session.query(Trade).all()
for trade in trades:
    print(f"{trade.ticker}: {trade.side} {trade.quantity}@${trade.price:.2f}")

# View open positions
positions = session.query(Position).filter(Position.is_open == True).all()
for pos in positions:
    print(f"{pos.ticker}: ${pos.unrealized_pnl:.2f} P&L")
```

### Check Logs

```bash
# View all logs
tail -f data/logs/system_*.log

# View trades only
tail -f data/logs/trades_*.log

# View errors
tail -f data/logs/errors_*.log
```

### Portfolio Summary

```python
from src.agents.position_manager import position_manager

summary = position_manager.get_portfolio_summary()
print(f"Open Positions: {summary['open_positions']}")
print(f"Total P&L: ${summary['total_pnl']:.2f}")
```

## Adding Real API Keys (Optional)

### Kalshi API

1. Go to https://kalshi.com/profile/api
2. Create API credentials
3. Add to `.env`:
```
KALSHI_API_KEY=your_email@example.com
KALSHI_API_SECRET=your_secret_here
KALSHI_ENV=demo  # Use demo first!
```

### News API (Free)

1. Go to https://newsapi.org/
2. Sign up for free tier (100 requests/day)
3. Add to `.env`:
```
NEWS_API_KEY=your_news_api_key_here
```

### Reddit API (Free)

1. Go to https://www.reddit.com/prefs/apps
2. Create an app
3. Add to `.env`:
```
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
```

### Twitter API (Optional)

Twitter API requires approval. For now, the system works without it.

## Switching to Live Trading

⚠️ **WARNING**: Only do this after extensive paper trading!

1. Verify you have real Kalshi API credentials
2. Test in demo mode first (`KALSHI_ENV=demo`)
3. When ready for live:

```bash
# In .env
TRADING_MODE=live
KALSHI_ENV=prod
```

## Troubleshooting

### "Anthropic API key not found"

Make sure `.env` exists and contains:
```
ANTHROPIC_API_KEY=sk-ant-...
```

### "Module not found"

Install dependencies:
```bash
pip install -r requirements.txt
```

### "Circuit breaker triggered"

This is a safety feature. Check logs to see why:
```bash
tail data/logs/system_*.log
```

Common reasons:
- Daily loss limit reached
- Daily trade limit reached
- Data quality issues

### "No markets fetched"

This is expected if you don't have Kalshi API keys. The system will use mock data for testing.

## Next Steps

1. **Run for a few days** in paper mode to see how it performs
2. **Review the trades** in `data/trades.db`
3. **Adjust parameters** in `config/trading_policy.yaml`
4. **Add real API keys** for better data
5. **Monitor performance** through logs and database

## Support

- **Issues**: Open a GitHub issue
- **Questions**: Check README.md
- **Logs**: Always check `data/logs/` for details

## Important Reminders

✅ **Always start in paper mode**
✅ **Test thoroughly before going live**
✅ **Monitor the system regularly**
✅ **Never risk more than you can afford to lose**
✅ **Review the circuit breaker alerts**

---

**Happy Trading! 🚀**
