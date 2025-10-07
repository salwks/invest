# Automated News-Based Trading System

A sophisticated automated trading system that monitors RSS news feeds, uses Claude AI for news interpretation, applies rule-based trading logic, and executes trades via Alpaca Paper Trading API.

## 🎯 Features

- **Real-time News Monitoring**: Fetches news from Yahoo Finance, Nasdaq, and Seeking Alpha RSS feeds
- **AI-Powered Analysis**: Uses Anthropic Claude to classify news sentiment, category, and reliability
- **Technical Analysis**: Calculates RSI, VWAP, volume ratios, and price momentum
- **Rule-Based Trading**: Configurable entry/exit rules via YAML
- **Risk Management**: Position sizing, stop-loss, daily loss limits, sector exposure controls
- **Multiple Run Modes**:
  - `DRYRUN`: Simulation only (no real orders)
  - `SEMI_AUTO`: Requires manual approval before execution
  - `FULL_AUTO`: Fully automated trading
- **Comprehensive Logging**: SQLite database + Parquet files for analysis
- **Slack Notifications**: Real-time alerts for signals and orders

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
RSS Feeds → LLM Interpreter → Market Scanner → Rule Engine → Risk Guard → Broker → Notifications
                ↓                    ↓               ↓            ↓          ↓
            EventCard          MarketState      PreSignal   ApprovedSignal  Order
```

### Pipeline Stages

1. **RSS Fetcher**: Monitors news feeds, filters by ticker whitelist
2. **LLM Interpreter**: Classifies news (category, sentiment, reliability)
3. **Market Scanner**: Fetches real-time price/volume data from Alpaca
4. **Rule Engine**: Evaluates ENTRY/SKIP based on `configs/rules.yaml`
5. **Risk Guard**: Position sizing, portfolio limits, risk checks
6. **Broker Executor**: Places limit orders via Alpaca API
7. **Notifier**: Sends Slack alerts

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
  disallow_session: [pre, after]  # Skip pre/after market
  disallow_categories: [rumor]     # Skip rumors

risk:
  per_trade_risk_pct: 0.004  # Risk 0.4% per trade
  min_stop_bp: 150           # Min stop-loss distance
  max_daily_loss_pct: 0.02   # Max 2% daily loss
  max_concurrent_positions: 3
```

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_rules.py -v

# Integration test (DRYRUN)
pytest tests/test_integration_dryrun.py -v

# With coverage
pytest tests/ --cov=app --cov-report=html
```

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
│   ├── main.py              # Main orchestration
│   ├── config.py            # Configuration management
│   ├── schemas.py           # Pydantic data models
│   ├── rss_fetcher.py       # RSS feed fetching
│   ├── llm_interpreter.py   # Claude integration
│   ├── market_scanner.py    # Market data & indicators
│   ├── rule_engine.py       # Trading rules
│   ├── risk_guard.py        # Risk management
│   ├── broker_exec.py       # Order execution
│   ├── notifier.py          # Slack notifications
│   ├── storage.py           # Database & logging
│   └── utils.py             # Utility functions
├── configs/
│   └── rules.yaml           # Trading rules
├── tests/
│   ├── test_rules.py
│   ├── test_llm_contract.py
│   └── test_integration_dryrun.py
├── docker/
│   └── Dockerfile
├── data/                    # Auto-created
│   ├── autotrader.db       # SQLite database
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

1. **Pre/After Market**: Disabled by default (configure in `rules.yaml`)
2. **Rumor Handling**: All rumors are skipped (low reliability)
3. **LLM Failures**: NoTrade on interpretation errors
4. **Session Restrictions**: Regular market hours only (9:30 AM - 4 PM ET)
5. **Position Management**: No automatic exit logic (stop/limit orders only)
6. **Data Delay**: RSS feeds have 3-5 minute latency

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
