# Kalshi Predictive Markets Agentic AI Trading System

An end-to-end autonomous trading system for Kalshi predictive markets, powered by Claude 3.5 Sonnet and built with LangGraph.

## 🎯 Overview

This system uses a multi-agent AI architecture to:
- Scan all Kalshi markets every 15 minutes
- Analyze news and social media for market-moving information
- Generate trading signals using Claude 3.5 Sonnet
- Execute trades with sophisticated risk management
- Monitor and exit positions automatically

## 🏗️ Architecture

The system follows an agentic AI design with 10 core components:

1. **Market Data Fetcher** - Scans Kalshi markets and ranks opportunities
2. **Data QA & Circuit Breaker** - Validates data quality and enforces safety limits
3. **Signal Selection Agent** - AI-powered trading signal generation (Claude 3.5 Sonnet)
4. **Risk & Allocation Agent** - Position sizing and risk management
5. **Policy & Self-Critic Agent** - Final trade review and approval (Claude 3.5 Sonnet)
6. **Execution Agent** - Trade execution (paper or live)
7. **Position Manager** - Monitors positions and executes exits
8. **LangGraph Orchestrator** - State management and flow control
9. **15-Min Scheduler** - Automated trading cycles
10. **Journal & Observer** - Logging and performance tracking

## 🚀 Quick Start

### Prerequisites

- Python 3.10 or higher
- Anthropic API key (for Claude 3.5 Sonnet)
- Kalshi API credentials (optional for now, mock mode available)

### Installation

1. Clone the repository:
```bash
cd /Users/justinjohn/Documents/GitHub/kalshi_predictive_agentic_system
```

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
```

Edit `.env` and add your API keys:
```
ANTHROPIC_API_KEY=your_anthropic_api_key_here
# Optional: Add Kalshi, News, Twitter, Reddit API keys
```

5. Run the system:
```bash
python src/main.py
```

## 📊 Configuration

### Trading Parameters

Edit `.env` to configure:

- `STARTING_CAPITAL`: Starting capital (default: $1,000)
- `RISK_PER_TRADE_PERCENT`: Risk per trade (default: 5%)
- `TRADING_MODE`: `paper` for simulation, `live` for real trading
- `SCHEDULER_INTERVAL_MINUTES`: How often to run (default: 15 minutes)
- `MAX_DAILY_TRADES`: Maximum trades per day (default: 10)
- `MAX_DAILY_LOSS_PERCENT`: Maximum daily loss (default: 15%)

### Trading Policy

Edit `config/trading_policy.yaml` to customize:

- Risk management rules
- Signal selection criteria
- Position management (stop loss, take profit, trailing stops)
- Circuit breaker conditions
- Policy review checklist

## 🧠 How It Works

### Trading Cycle (Every 15 Minutes)

1. **Update Positions** - Check all open positions for exit conditions
2. **Fetch Markets** - Get all open Kalshi markets
3. **Circuit Breaker** - Validate data quality and risk limits
4. **Select Opportunity** - Rank and select top market to analyze
5. **Enrich Data** - Fetch news articles and social media sentiment
6. **Generate Signal** - Claude analyzes and recommends LONG/SHORT/NO_TRADE
7. **Calculate Sizing** - Determine position size based on risk
8. **Policy Review** - Claude performs final critical review
9. **Execute Trade** - Place order if approved (paper or live)
10. **Repeat** - Continue with next opportunity

### AI Decision Making

The system uses Claude 3.5 Sonnet for two critical decisions:

**Signal Selection Agent:**
- Analyzes market data, news, and social sentiment
- Identifies mispricing and edge
- Generates trading signal with confidence score
- Provides detailed reasoning

**Policy & Self-Critic Agent:**
- Critically reviews proposed trade
- Checks for hidden risks
- Validates alignment with trading policy
- Final APPROVE/BLOCK decision

## 📈 Performance Monitoring

### Database

All trades, positions, and sessions are stored in SQLite:
```
data/trades.db
```

Tables:
- `trades` - All executed trades
- `positions` - Open and closed positions
- `market_snapshots` - Historical market data
- `trading_sessions` - Each 15-min cycle
- `performance_metrics` - Aggregate performance

### Logs

Logs are stored in `data/logs/`:
- `system_*.log` - All system logs
- `trades_*.log` - Trade-specific logs
- `errors_*.log` - Error logs only

### View Portfolio

```python
from src.agents.position_manager import position_manager

summary = position_manager.get_portfolio_summary()
print(f"Open Positions: {summary['open_positions']}")
print(f"Total P&L: ${summary['total_pnl']:.2f}")
```

## 🔐 Safety Features

### Circuit Breaker

Automatically halts trading if:
- Data is stale (>5 minutes old)
- Multiple API errors
- Daily loss limit exceeded
- Daily trade limit exceeded
- Price anomalies detected

### Risk Management

- Position sizing based on Kelly Criterion
- Stop loss on every trade
- Take profit targets
- Trailing stops for winners
- Maximum position concentration limits

### Paper Trading

Always start in paper trading mode:
```
TRADING_MODE=paper
```

The system will simulate trades without risking real capital.

## 📁 Project Structure

```
kalshi_predictive_agentic_system/
├── config/
│   ├── settings.py              # Configuration management
│   └── trading_policy.yaml      # Trading rules
├── src/
│   ├── agents/                  # All agent implementations
│   │   ├── market_data_fetcher.py
│   │   ├── data_qa_circuit_breaker.py
│   │   ├── signal_selection_agent.py
│   │   ├── risk_allocation_agent.py
│   │   ├── policy_self_critic_agent.py
│   │   ├── execution_agent.py
│   │   └── position_manager.py
│   ├── orchestrator/
│   │   ├── langgraph_flow.py    # LangGraph state machine
│   │   └── state_models.py      # Pydantic state models
│   ├── utils/
│   │   ├── kalshi_client.py     # Kalshi API wrapper
│   │   ├── news_fetcher.py      # News & social media
│   │   └── logger.py            # Logging setup
│   ├── database/
│   │   └── models.py            # SQLAlchemy models
│   └── main.py                  # Entry point
├── data/
│   ├── trades.db               # SQLite database
│   └── logs/                   # Log files
├── tests/                      # Test suite
├── requirements.txt
├── .env.example
└── README.md
```

## 🧪 Testing

Run tests:
```bash
pytest tests/
```

Run a single cycle (for testing):
```python
from src.orchestrator.langgraph_flow import orchestrator
result = orchestrator.run_trading_cycle()
```

## 🛠️ Customization

### Add Custom Indicators

Edit `src/utils/indicators.py` to add technical indicators.

### Modify Trading Logic

Edit `config/trading_policy.yaml` to adjust:
- Risk parameters
- Entry/exit rules
- Signal thresholds

### Change LLM Model

In `.env`:
```
LLM_MODEL=claude-3-5-sonnet-20241022  # Default
# or
LLM_MODEL=claude-3-5-haiku-20241022   # Faster, cheaper
```

## 💰 Cost Estimation

With Claude 3.5 Sonnet:
- ~2 LLM calls per market analyzed
- ~4,000 tokens per call
- ~96 cycles/day × 30 days = 2,880 cycles/month
- ~23M tokens/month
- **Estimated cost: $50-100/month**

To reduce costs:
- Use Claude 3.5 Haiku (~$10-15/month)
- Reduce scheduler frequency
- Analyze fewer markets per cycle

## 📝 API Keys Needed

### Required
- **Anthropic API**: Get from https://console.anthropic.com/

### Optional (for enhanced analysis)
- **Kalshi API**: Get from https://kalshi.com/profile/api
- **News API**: Free tier at https://newsapi.org/
- **Twitter API**: Get from https://developer.twitter.com/
- **Reddit API**: Get from https://www.reddit.com/prefs/apps

## ⚠️ Disclaimer

This software is for educational and research purposes only. Trading involves risk of loss. Past performance does not guarantee future results. Always start in paper trading mode and never risk more than you can afford to lose.

## 📄 License

MIT License - See LICENSE file for details

## 🤝 Contributing

Contributions welcome! Please open an issue or submit a pull request.

## 📧 Support

For questions or issues, please open a GitHub issue.

---

Built with ❤️ using Claude 3.5 Sonnet, LangGraph, and the Kalshi API
