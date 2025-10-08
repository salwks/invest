# Automated News-Based Trading System

[![Tests](https://github.com/salwks/invest/workflows/Tests/badge.svg)](https://github.com/salwks/invest/actions)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](docker/Dockerfile)

A sophisticated automated trading system that monitors RSS news feeds, uses Claude AI for news interpretation, applies rule-based trading logic, and executes trades via Alpaca Paper Trading API.

## 🎯 Features

- **24/7 News Monitoring**: Fetches news continuously from RSS feeds, processes when market opens
- **AI-Powered Analysis**: Uses Anthropic Claude Haiku 3.5 to classify news sentiment, category, and reliability
- **Technical Analysis**: Calculates RSI, VWAP, volume ratios, and price momentum
- **Rule-Based Trading**: Configurable entry/exit rules via YAML
- **Advanced Exit Logic**:
  - Partial profit taking at +8%
  - Trailing stop at -5% from peak
  - Time-based exit after 60 minutes
  - Hard stop loss at -4%
- **Risk Management**:
  - Position sizing based on volatility
  - Daily loss limits and max concurrent positions
  - Sector exposure controls
  - Daily ticker limit (max 10 tickers/day)
- **All Trading Sessions**: Pre-market, regular, and after-hours support
- **Multiple Run Modes**:
  - `DRYRUN`: Simulation only (no real orders)
  - `SEMI_AUTO`: Requires manual approval before execution
  - `FULL_AUTO`: Fully automated trading
- **Comprehensive Logging**: SQLite database + Parquet files for analysis
- **Slack Notifications**: Real-time alerts for entries, exits, and P&L

## 📋 Requirements

- Python 3.11+
- Anthropic API key (Claude)
- Alpaca Paper Trading account
- (Optional) Slack webhook for notifications

## 🚀 Quick Start

### 1. Installation

#### Local Setup

```bash
# Clone repository
cd autotrader

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

#### Docker Setup

```bash
# Build image
docker-compose build

# Run once
docker-compose run --rm autotrader-once

# Run continuously
docker-compose up -d autotrader
```

### 2. Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env
```

**Required Settings:**

```env
ANTHROPIC_API_KEY=your_anthropic_key_here
ALPACA_API_KEY=your_alpaca_key_here
ALPACA_SECRET_KEY=your_alpaca_secret_here
RUN_MODE=DRYRUN  # Start with DRYRUN!
TICKER_WHITELIST=AAPL,TSLA,NVDA,MSFT
```

**Optional Settings:**

```env
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
CYCLE_MINUTES=5
ANTHROPIC_MODEL=claude-3-haiku-20240307
```

### 3. Run

#### Local

```bash
# Single cycle
python -m app.main --mode once

# Continuous (every 5 minutes)
python -m app.main --mode continuous
```

#### Docker

```bash
# Single run
docker-compose run --rm autotrader-once

# Continuous
docker-compose up -d autotrader

# View logs
docker-compose logs -f autotrader
```

## 🏗️ Architecture

```
RSS Feeds (24/7) → Storage (unprocessed) ┐
                                         ↓
                        ┌──── Event Processing Loop (every 5min) ────┐
                        ↓                                             │
            LLM Interpreter → Market Scanner → Rule Engine           │
                    ↓                ↓               ↓                │
               EventCard       MarketState      PreSignal            │
                                                     ↓                │
                            Risk Guard → Broker Executor             │
                                 ↓            ↓                       │
                          ApprovedSignal   Order                     │
                                                                      │
            Position Monitor ← Trade Manager ← Open Positions        │
                    ↓                                                 │
              Exit Orders → Broker → Notifications ──────────────────┘
```

### Pipeline Stages

**Entry Flow:**
1. **RSS Fetcher**: Monitors news feeds 24/7, saves events to database
2. **LLM Interpreter**: Classifies news (category, sentiment, reliability) using Claude Haiku 3.5
3. **Market Scanner**: Fetches real-time price/volume data from Alpaca IEX feed
4. **Rule Engine**: Evaluates ENTRY/SKIP based on `configs/rules.yaml`
5. **Risk Guard**: Position sizing, portfolio limits, daily ticker limits
6. **Broker Executor**: Places limit orders via Alpaca API (DRYRUN/SEMI_AUTO/FULL_AUTO)

**Exit Flow:**
1. **Position Monitor**: Checks all open positions each cycle
2. **Trade Manager**: Evaluates 4 exit conditions (hard stop, partial profit, trailing, time)
3. **Broker Executor**: Places sell orders when exit conditions met
4. **Notifier**: Sends Slack alerts with P&L

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture documentation.

## ⚙️ Configuration

### Trading Rules (`configs/rules.yaml`)

```yaml
entry:
  min_sentiment: 0.70        # Minimum positive sentiment
  min_impact: 0.70           # Minimum reliability score
  dp5m_min_pct: 1.0          # Min 5-minute price change (%)
  dp5m_max_pct: 4.0          # Max 5-minute price change (%)
  min_vol_ratio: 3.0         # Min volume vs average
  max_spread_bp: 50          # Max bid-ask spread (basis points)
  max_rsi3: 75               # Max RSI to avoid overbought

skip:
  spike01_gt_pct: 5.0        # Skip if 1-min spike > 5%
  disallow_session: []       # Allow all sessions (pre, regular, after)
  disallow_categories: [rumor]  # Skip rumors

risk:
  per_trade_risk_pct: 0.004     # Risk 0.4% per trade
  min_stop_bp: 150              # Min stop-loss distance
  max_daily_loss_pct: 0.02      # Max 2% daily loss
  max_concurrent_positions: 3
  max_daily_tickers: 10         # Max 10 unique tickers per day
  max_position_size_pct: 0.15   # Max 15% of equity per position

exit:
  # Partial profit taking (1st level)
  take_profit_lvl1_pct: 8.0     # Sell 40% at +8% gain
  take_profit_lvl1_part: 0.4    # 40% of position

  # Trailing stop (2nd level)
  trailing_stop_pct: 5.0        # Sell all at -5% from peak

  # Time-based exit
  hold_minutes: 60              # Max hold time: 60 minutes

  # Hard stop loss
  hard_stop_pct: 4.0            # Sell all at -4% loss
```

See [docs/EXIT_LOGIC.md](docs/EXIT_LOGIC.md) for detailed exit strategy documentation.

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test modules
pytest tests/test_rules.py -v
pytest tests/test_exit_rules.py -v

# Integration test (DRYRUN)
pytest tests/test_integration_dryrun.py -v

# With coverage
pytest tests/ --cov=app --cov-report=html
```

**Test Coverage:**
- ✅ Entry rules validation (16 tests)
- ✅ Exit logic (partial profit, trailing stop, time, hard stop) (16 tests)
- ✅ LLM contract validation
- ✅ Integration tests (DRYRUN mode)

## 📊 Run Modes

### DRYRUN (Recommended for Testing)

- Simulates entire pipeline
- No real orders placed
- Safe for testing rules and configuration
- Full logging and notifications

```bash
RUN_MODE=DRYRUN python -m app.main --mode once
```

### SEMI_AUTO

- Sends approval request (Slack/console)
- Waits for manual confirmation
- Places order only after approval

```bash
RUN_MODE=SEMI_AUTO python -m app.main --mode continuous
```

### FULL_AUTO

- ⚠️ **USE WITH EXTREME CAUTION** ⚠️
- Fully automated execution
- No manual intervention
- Only use after thorough testing in DRYRUN

```bash
RUN_MODE=FULL_AUTO python -m app.main --mode continuous
```

## 📁 Project Structure

```
autotrader/
├── app/
│   ├── main.py              # Main orchestration & position monitoring
│   ├── config.py            # Configuration management
│   ├── schemas.py           # Pydantic data models
│   ├── rss_fetcher.py       # RSS feed fetching (24/7)
│   ├── llm_interpreter.py   # Claude Haiku 3.5 integration
│   ├── market_scanner.py    # Market data & indicators (IEX feed)
│   ├── rule_engine.py       # Entry/skip trading rules
│   ├── trade_manager.py     # Exit logic (NEW)
│   ├── risk_guard.py        # Risk management & position sizing
│   ├── broker_exec.py       # Order execution (entry & exit)
│   ├── notifier.py          # Slack notifications
│   ├── storage.py           # SQLite database & Parquet logging
│   └── utils.py             # Utility functions
├── configs/
│   └── rules.yaml           # Entry/exit/risk rules
├── tests/
│   ├── test_rules.py        # Entry rules tests
│   ├── test_exit_rules.py   # Exit logic tests (NEW)
│   ├── test_llm_contract.py
│   └── test_integration_dryrun.py
├── docs/                    # Documentation
│   ├── ARCHITECTURE.md
│   ├── EXIT_LOGIC.md
│   └── CONFIGURATION.md
├── docker/
│   └── Dockerfile
├── data/                    # Auto-created
│   ├── autotrader.db       # SQLite database
│   ├── autotrader.log      # Log file
│   ├── events/             # Parquet logs
│   ├── market/
│   └── signals/
├── .env.example
├── requirements.txt
└── docker-compose.yml
```

## 💰 Cost Estimates

### Monthly Costs (Typical Usage)

- **Anthropic API** (Claude Haiku): ~$20-30/month
  - ~5-10 news items per 5-minute cycle
  - ~2000-3000 API calls/month
  - ~$0.25 per 1M input tokens, ~$1.25 per 1M output tokens

- **Alpaca Paper Trading**: FREE
  - Unlimited paper trades
  - Real-time market data included

- **Total**: ~$20-30/month

### Optimization Tips

1. Use `claude-3-haiku` (cheapest) for routine analysis
2. Increase `CYCLE_MINUTES` to reduce API calls
3. Use stricter filtering in `TICKER_WHITELIST`
4. Cache LLM responses for duplicate news

## 🔒 Security & Limitations

### Security

- Never commit `.env` to version control
- Store API keys securely (use secrets manager in production)
- Use read-only API keys where possible
- Enable IP whitelisting on Alpaca account

### Current Limitations

1. **RSS Feeds**: Only Seeking Alpha active (Yahoo Finance and Nasdaq rate-limited)
2. **Rumor Handling**: All rumors are skipped (low reliability)
3. **LLM Failures**: NoTrade on interpretation errors
4. **Data Delay**: RSS feeds have 3-5 minute latency
5. **IEX Data Only**: Free tier uses IEX feed (delayed data for some tickers)
6. **Long Only**: System only supports long positions (no short selling)

### Known Issues

- LLM may occasionally misclassify news category
- Market data may be unavailable during extreme volatility
- Alpaca API rate limits (200 req/min for data, 200 req/min for trading)

## 📈 Performance Monitoring

### Database Queries

```sql
-- View recent signals
SELECT * FROM signals ORDER BY created_at DESC LIMIT 10;

-- View filled orders
SELECT * FROM orders WHERE status = 'filled' ORDER BY submitted_at DESC;

-- View open positions
SELECT * FROM positions WHERE status = 'open';

-- View run statistics
SELECT
    mode,
    COUNT(*) as runs,
    AVG(events_fetched) as avg_events,
    AVG(signals_generated) as avg_signals
FROM runs
GROUP BY mode;
```

### Parquet Logs

```python
import pandas as pd

# Load event logs
events = pd.read_parquet('data/events/date=2024-01-15/')
print(events.head())

# Analyze sentiment distribution
print(events['sentiment'].describe())
```

## 🚦 Paper to Live Trading Checklist

**DO NOT** switch to live trading without completing ALL items:

- [ ] Run in DRYRUN mode for at least 1 week
- [ ] Review ALL generated signals manually
- [ ] Verify risk limits are appropriate for your capital
- [ ] Test SEMI_AUTO mode with small positions
- [ ] Monitor daily P&L for at least 2 weeks
- [ ] Set up proper alerting and monitoring
- [ ] Have manual kill switch ready
- [ ] Start with max 1-2% of total capital
- [ ] Use separate account for automated trading
- [ ] Review and understand all code thoroughly
- [ ] Set up backup/disaster recovery
- [ ] Test failure scenarios (API down, network issues)

**Live Trading Requires:**
1. Change `ALPACA_BASE_URL` to production API
2. Use production API keys (not paper)
3. Start with VERY small position sizes
4. Monitor continuously for first month

## 🛠️ Development

### Adding New Rules

Edit `configs/rules.yaml`:

```yaml
entry:
  new_metric_threshold: 1.5
```

Then update `rule_engine.py` to use the new metric.

### Adding New Indicators

Add to `market_scanner.py`:

```python
def _calculate_new_indicator(self, bars: list[dict]) -> float:
    # Your calculation here
    return value
```

### Custom Notifications

Edit `notifier.py` to customize Slack message format.

## 📝 License

This project is for educational purposes only. Use at your own risk. The authors are not responsible for any financial losses.

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## ⚠️ Disclaimer

**THIS SOFTWARE IS PROVIDED FOR EDUCATIONAL PURPOSES ONLY.**

- Automated trading carries significant financial risk
- Past performance does not guarantee future results
- Always test thoroughly in paper trading mode first
- Never risk money you cannot afford to lose
- The authors assume no liability for any losses
- Consult a financial advisor before live trading

---

**Questions?** Open an issue on GitHub or check the logs in `data/autotrader.log`
