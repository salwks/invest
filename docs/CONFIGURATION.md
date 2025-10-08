# Configuration Guide

Complete guide for configuring the Automated Trading System.

## Table of Contents

1. [Environment Variables (.env)](#environment-variables-env)
2. [Trading Rules (rules.yaml)](#trading-rules-rulesyaml)
3. [Run Modes](#run-modes)
4. [Ticker Configuration](#ticker-configuration)
5. [Slack Notifications](#slack-notifications)
6. [Advanced Settings](#advanced-settings)

---

## Environment Variables (.env)

Create `.env` file in project root (copy from `.env.example`):

```bash
cp .env.example .env
```

### Required Settings

```env
# Anthropic Claude API
ANTHROPIC_API_KEY=sk-ant-api03-your_key_here
ANTHROPIC_MODEL=claude-3-5-haiku-20241022

# Alpaca Trading API (Paper Trading)
ALPACA_API_KEY=PK...
ALPACA_SECRET_KEY=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2
ALPACA_DATA_BASE_URL=https://data.alpaca.markets

# Run Mode
RUN_MODE=DRYRUN  # DRYRUN | SEMI_AUTO | FULL_AUTO

# Trading Configuration
TICKER_WHITELIST=AAPL,TSLA,NVDA,MSFT,GOOGL,AMZN,META
CYCLE_MINUTES=5
```

### Optional Settings

```env
# Slack Notifications
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Database
DB_PATH=data/autotrader.db

# Logging
LOG_LEVEL=INFO  # DEBUG | INFO | WARNING | ERROR
LOG_FILE=data/autotrader.log

# Risk Management
INITIAL_EQUITY=100000.0
```

### Getting API Keys

**1. Anthropic Claude:**
1. Sign up at https://console.anthropic.com
2. Create API key in Settings → API Keys
3. Copy key to `.env`

**2. Alpaca Paper Trading:**
1. Sign up at https://alpaca.markets
2. Navigate to Paper Trading account
3. Generate API keys (Paper Trading section)
4. Copy both keys to `.env`
5. **Important**: Use `/v2` in base URL

**3. Slack Webhook (Optional):**
1. Create Slack app at https://api.slack.com/apps
2. Enable Incoming Webhooks
3. Create webhook for your channel
4. Copy webhook URL to `.env`

---

## Trading Rules (rules.yaml)

Edit `configs/rules.yaml` to customize trading behavior.

### Entry Rules

```yaml
entry:
  # Sentiment & Impact
  min_sentiment: 0.70        # Minimum sentiment (-1 to 1)
  min_impact: 0.70           # Minimum reliability (0 to 1)

  # Price Movement
  dp5m_min_pct: 1.0          # Min 5-minute price change (%)
  dp5m_max_pct: 4.0          # Max 5-minute price change (%)

  # Volume & Liquidity
  min_vol_ratio: 3.0         # Min volume ratio vs average
  max_spread_bp: 50          # Max bid-ask spread (basis points)

  # Technical Indicators
  max_rsi3: 75               # Max RSI (3-period)

  # Category Filter (empty = allow all)
  allowed_categories:
    - earnings
    - FDA
    - M&A
    - guidance
    - partnership
    - regulatory
```

**Explanation:**

- **min_sentiment**: Only enter on positive news (>0.70 is very positive)
- **min_impact**: Only high-reliability news (official announcements, not rumors)
- **dp5m_min_pct/max_pct**: Enter on momentum (1-4% move), avoid extreme spikes
- **min_vol_ratio**: Require 3x normal volume for confirmation
- **max_spread_bp**: Avoid illiquid stocks (50bp = 0.5%)
- **max_rsi3**: Don't buy overbought stocks (RSI > 75)

**Customization Examples:**

```yaml
# More aggressive (more trades)
entry:
  min_sentiment: 0.60       # Lower bar for sentiment
  dp5m_min_pct: 0.5         # Smaller momentum required
  min_vol_ratio: 2.0        # Lower volume requirement

# More conservative (fewer trades)
entry:
  min_sentiment: 0.80       # Very strong sentiment only
  dp5m_min_pct: 1.5         # Stronger momentum required
  min_vol_ratio: 5.0        # Very high volume required
```

---

### Skip Rules

```yaml
skip:
  # Spike Protection
  spike01_gt_pct: 5.0        # Skip if 0-1 minute spike > 5%

  # Session Filter (empty = allow all)
  disallow_session: []       # Allow pre, regular, after

  # Category Blocklist
  disallow_categories:
    - rumor                  # Skip all rumors

  # Reliability Filter
  min_reliability: 0.60      # Skip if reliability < 60%
```

**Explanation:**

- **spike01_gt_pct**: Avoid "flash crash" type moves (likely false signals)
- **disallow_session**: Filter by market session (pre-market, regular, after-hours)
- **disallow_categories**: Block specific news types
- **min_reliability**: Minimum confidence threshold

**Session Options:**
```yaml
# Only trade regular hours (9:30 AM - 4 PM ET)
disallow_session: [pre, after]

# Only trade extended hours (for high volatility)
disallow_session: [regular]

# Trade all sessions
disallow_session: []
```

**Category Options:**
```yaml
# Skip uncertain news
disallow_categories: [rumor, other]

# Only trade specific events
allowed_categories: [earnings, FDA]  # In entry section
```

---

### Risk Management

```yaml
risk:
  # Position Sizing
  per_trade_risk_pct: 0.004  # Risk 0.4% of equity per trade
  min_stop_bp: 150           # Min stop-loss distance (basis points)
  trail_take_profit_bp: 250  # Take profit target (basis points)

  # Portfolio Limits
  max_daily_loss_pct: 0.02   # Max 2% daily loss
  max_sector_exposure_pct: 0.3  # Max 30% in single sector
  max_concurrent_positions: 3   # Max 3 open positions
  max_daily_tickers: 10      # Max 10 unique tickers per day

  # Position Size Limits
  max_position_size_pct: 0.15   # Max 15% of equity per position
  min_position_size_usd: 100.0  # Minimum position size
  max_position_size_usd: 15000.0  # Maximum position size
```

**Position Sizing Formula:**

```python
# Example with $100k equity
equity = 100000
per_trade_risk_pct = 0.004

# Risk amount = $400
risk_amount = equity * per_trade_risk_pct

# Stop distance = 150 bp (1.5%)
stop_pct = 0.015

# Position size = $400 / 0.015 = $26,667
# But capped at 15% = $15,000
position_size = min(26667, 15000)

# Shares = $15,000 / $175 = 85 shares
shares = position_size / market_price
```

**Risk Parameter Guidelines:**

| Parameter | Conservative | Moderate | Aggressive |
|-----------|--------------|----------|------------|
| per_trade_risk_pct | 0.002 (0.2%) | 0.004 (0.4%) | 0.008 (0.8%) |
| max_daily_loss_pct | 0.01 (1%) | 0.02 (2%) | 0.04 (4%) |
| max_concurrent_positions | 2 | 3 | 5 |
| max_position_size_pct | 0.10 (10%) | 0.15 (15%) | 0.20 (20%) |

---

### Exit Rules

```yaml
exit:
  # Partial profit taking (1st level)
  take_profit_lvl1_pct: 8.0      # Sell 40% at +8% gain
  take_profit_lvl1_part: 0.4     # 40% of position

  # Trailing stop (2nd level)
  trailing_stop_pct: 5.0         # Sell all at -5% from peak

  # Time-based exit
  hold_minutes: 60               # Max hold time: 60 minutes

  # Hard stop loss
  hard_stop_pct: 4.0             # Sell all at -4% loss
```

**Exit Priority:**
1. Hard Stop (-4%) → Highest priority, immediate sell
2. Partial Profit (+8%) → Lock in profits
3. Trailing Stop (-5% from peak) → Protect gains
4. Time Limit (60 min) → Close intraday positions

**Customization Examples:**

```yaml
# Day trader (tight stops, fast exits)
exit:
  take_profit_lvl1_pct: 5.0      # Take profit earlier
  trailing_stop_pct: 3.0         # Tighter trailing stop
  hold_minutes: 30               # Max 30 minutes
  hard_stop_pct: 2.0             # Tight stop loss

# Swing trader (wider stops, longer holds)
exit:
  take_profit_lvl1_pct: 12.0     # Higher profit target
  trailing_stop_pct: 7.0         # Wider trailing stop
  hold_minutes: 240              # Max 4 hours
  hard_stop_pct: 6.0             # Wider stop loss
```

See [EXIT_LOGIC.md](EXIT_LOGIC.md) for complete exit strategy documentation.

---

### Execution Rules

```yaml
execution:
  # Order Execution
  max_slippage_bp: 40        # Max acceptable slippage (basis points)
  limit_offset_bp: 10        # Limit price offset from mid (basis points)

  # Order Timeouts
  order_timeout_seconds: 30  # Cancel order if not filled within 30s

  # Retry Logic
  max_retries: 1             # Retry failed orders once
  retry_delay_seconds: 2     # Wait 2s between retries
```

**Explanation:**

- **max_slippage_bp**: Max price difference allowed (40bp = 0.4%)
- **limit_offset_bp**: How far above mid price to place limit order
- **order_timeout_seconds**: Cancel if not filled quickly (avoid stale orders)
- **max_retries**: Retry failed orders (API errors, rejections)

---

### Monitoring Rules

```yaml
monitoring:
  # Alert Thresholds
  alert_on_large_loss_pct: 0.01  # Alert if single trade loses > 1%
  alert_on_daily_loss_pct: 0.015  # Alert if daily loss > 1.5%

  # Health Checks
  max_api_failures: 3        # Max consecutive API failures before pause
  pause_duration_minutes: 15 # Pause duration after max failures
```

---

## Run Modes

### DRYRUN (Simulation)

**Purpose**: Test system without placing real orders

**Behavior:**
- Fetches real news and market data
- Generates signals
- **Simulates** order placement
- Full logging and notifications
- Safe for testing

**Configuration:**
```env
RUN_MODE=DRYRUN
```

**Use Cases:**
- Initial setup and testing
- Rule tuning and optimization
- Paper trading validation
- Learning system behavior

**Output:**
```
[DRYRUN] Would place order: 5 shares of AAPL @ $175.50
[DRYRUN] Would sell: 2 shares of TSLA @ $108.00 | P&L: $16.00 (+8.00%)
```

---

### SEMI_AUTO (Manual Approval)

**Purpose**: Review each trade before execution

**Behavior:**
- Generates trading signals
- **Sends approval request** (Slack/console)
- Waits for user confirmation
- Places real order if approved

**Configuration:**
```env
RUN_MODE=SEMI_AUTO
```

**Use Cases:**
- Initial live trading (small positions)
- High-stakes trades requiring review
- Learning from AI suggestions
- Gaining confidence before full automation

**Note**: In current MVP, approval is simulated (80% rate). Implement real approval via Slack interactive messages or web UI.

---

### FULL_AUTO (Fully Automated)

**Purpose**: Fully autonomous trading

**Behavior:**
- Generates signals
- **Automatically places orders**
- No manual intervention
- Sends notifications after execution

**Configuration:**
```env
RUN_MODE=FULL_AUTO
```

**⚠️ IMPORTANT WARNINGS:**
- Only use after **extensive DRYRUN testing** (minimum 1 week)
- Start with **very small position sizes**
- Monitor continuously for first week
- Have **manual kill switch** ready
- Review all signals manually initially

**Recommended Progression:**
1. DRYRUN for 1-2 weeks
2. SEMI_AUTO with $100-500 positions
3. SEMI_AUTO with full position sizes
4. FULL_AUTO with small positions
5. FULL_AUTO with full positions (if confident)

---

## Ticker Configuration

### Ticker Whitelist

Control which stocks to trade via environment variable:

```env
# Default (7 liquid mega-caps)
TICKER_WHITELIST=AAPL,TSLA,NVDA,MSFT,GOOGL,AMZN,META

# Tech-focused
TICKER_WHITELIST=AAPL,MSFT,NVDA,AMD,GOOGL,META,NFLX

# High volatility
TICKER_WHITELIST=TSLA,GME,AMC,PLTR,COIN

# Index tracking
TICKER_WHITELIST=SPY,QQQ,IWM,DIA

# Sector-specific (Healthcare)
TICKER_WHITELIST=JNJ,PFE,ABBV,UNH,TMO
```

**Best Practices:**

1. **Liquidity**: Only trade stocks with >$10B market cap
2. **Volume**: Ensure >10M daily volume
3. **News Coverage**: Pick stocks with frequent news
4. **Familiarity**: Trade stocks you understand
5. **Diversity**: Mix sectors to reduce correlation

**Ticker Limits:**
- **Minimum**: 3-5 tickers (for diversification)
- **Maximum**: 20 tickers (to avoid over-trading)
- **Recommended**: 7-10 liquid mega-caps

### Sector Mapping

Edit `app/config.py` to customize sector mapping:

```python
SECTOR_MAP = {
    # Technology
    "AAPL": "Technology",
    "MSFT": "Technology",
    "GOOGL": "Technology",
    "META": "Technology",
    "NVDA": "Technology",

    # Automotive
    "TSLA": "Automotive",
    "GM": "Automotive",

    # Consumer
    "AMZN": "Consumer",
    "WMT": "Consumer",

    # Add your tickers here
    "YOUR_TICKER": "YourSector",
}
```

**Purpose**: Used for sector exposure limits in risk management.

---

## Slack Notifications

### Setup

1. Create Slack app at https://api.slack.com/apps
2. Enable "Incoming Webhooks"
3. Add webhook to your channel
4. Copy webhook URL to `.env`:

```env
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX
```

### Notification Types

**Entry Signals:**
- 🚀 ENTRY SIGNAL - Approved trades
- ❌ REJECTED - Failed risk checks
- 🚫 SKIP - Filtered by rules

**Exit Signals:**
- 🟢 FULL EXIT - Complete position closed
- 🔵 PARTIAL EXIT - Partial profit taken
- 🔴 STOP LOSS - Hard stop triggered

**System:**
- ✅ Run Complete - Cycle summary
- ⚠️ Error - System failures

### Disabling Notifications

```env
# Leave empty to disable
SLACK_WEBHOOK_URL=
```

### Custom Notifications

Edit `app/notifier.py` to customize message format:

```python
def _build_entry_message(self, event, signal, approved, order):
    # Customize message format here
    details = [
        f"*{headline}*",
        f"*Ticker:* {ticker}",
        # Add your custom fields
    ]
    return {"text": text, "blocks": [...]}
```

---

## Advanced Settings

### Cycle Frequency

Control how often the system checks for news:

```env
# Conservative (less API calls, slower response)
CYCLE_MINUTES=10

# Moderate (balanced)
CYCLE_MINUTES=5

# Aggressive (more API calls, faster response)
CYCLE_MINUTES=2
```

**Considerations:**
- Faster cycles = more API costs
- News feeds have 3-5 minute latency anyway
- Recommended: 5 minutes

---

### LLM Model Selection

```env
# Fastest & cheapest (recommended)
ANTHROPIC_MODEL=claude-3-5-haiku-20241022

# More capable (more expensive)
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

# Most capable (most expensive)
ANTHROPIC_MODEL=claude-opus-4-20250514
```

**Cost Comparison** (per 1M tokens):

| Model | Input | Output | Use Case |
|-------|-------|--------|----------|
| Haiku 3.5 | $0.25 | $1.25 | News classification (recommended) |
| Sonnet 3.5 | $3.00 | $15.00 | Complex analysis |
| Opus 4 | $15.00 | $75.00 | Highest accuracy |

---

### Database Configuration

```env
# Default (SQLite)
DB_PATH=data/autotrader.db

# Custom path
DB_PATH=/var/lib/autotrader/trading.db
```

**Production Considerations:**
- SQLite is fine for <100 trades/day
- For higher volume, migrate to PostgreSQL
- Backup database regularly

---

### Logging Configuration

```env
# Log level
LOG_LEVEL=INFO  # DEBUG | INFO | WARNING | ERROR

# Log file
LOG_FILE=data/autotrader.log
```

**Log Levels:**
- **DEBUG**: All details (verbose, use for troubleshooting)
- **INFO**: Normal operation (recommended)
- **WARNING**: Only warnings and errors
- **ERROR**: Only errors

**Log Rotation:**

Add to crontab for automatic log rotation:
```bash
# Rotate logs daily at midnight
0 0 * * * find /path/to/data -name "autotrader.log" -exec mv {} {}.$(date +\%Y\%m\%d) \;
```

---

## Configuration Validation

### Pre-flight Checklist

Before running, verify configuration:

```bash
# 1. Check .env file exists
ls -la .env

# 2. Validate API keys
grep -E "^(ANTHROPIC|ALPACA).*=" .env

# 3. Verify run mode
grep "^RUN_MODE=" .env

# 4. Check rules.yaml syntax
python -c "import yaml; yaml.safe_load(open('configs/rules.yaml'))"

# 5. Test database connection
sqlite3 data/autotrader.db "SELECT 1"
```

### Testing Configuration

```bash
# Run single cycle in DRYRUN mode
RUN_MODE=DRYRUN python -m app.main --mode once

# Check results
sqlite3 data/autotrader.db "SELECT * FROM runs ORDER BY started_at DESC LIMIT 1"
```

---

## Troubleshooting

### Common Issues

**1. "Anthropic API key not found"**
```bash
# Check .env file
cat .env | grep ANTHROPIC_API_KEY

# Verify key format (should start with sk-ant-)
```

**2. "Alpaca subscription does not permit querying recent SIP data"**
```bash
# Make sure ALPACA_BASE_URL ends with /v2
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2
```

**3. "RSS feeds timing out"**
```bash
# Only Seeking Alpha is active (others rate-limited)
# Check app/config.py RSS_FEEDS list
```

**4. "No signals generated"**
```bash
# Check if rules too strict
# Try lowering thresholds in configs/rules.yaml
# Enable DEBUG logging
LOG_LEVEL=DEBUG
```

**5. "Database locked"**
```bash
# Close all connections
pkill -f autotrader
# Restart system
```

---

## Configuration Examples

### Conservative Day Trader

```yaml
# configs/rules.yaml
entry:
  min_sentiment: 0.80
  dp5m_min_pct: 1.5
  min_vol_ratio: 5.0

risk:
  per_trade_risk_pct: 0.002
  max_concurrent_positions: 2
  max_daily_loss_pct: 0.01

exit:
  take_profit_lvl1_pct: 5.0
  trailing_stop_pct: 3.0
  hold_minutes: 30
  hard_stop_pct: 2.0
```

```env
# .env
RUN_MODE=SEMI_AUTO
TICKER_WHITELIST=AAPL,MSFT,GOOGL
CYCLE_MINUTES=10
```

---

### Aggressive Momentum Trader

```yaml
# configs/rules.yaml
entry:
  min_sentiment: 0.60
  dp5m_min_pct: 0.5
  min_vol_ratio: 2.0

risk:
  per_trade_risk_pct: 0.008
  max_concurrent_positions: 5
  max_daily_loss_pct: 0.04

exit:
  take_profit_lvl1_pct: 12.0
  trailing_stop_pct: 7.0
  hold_minutes: 120
  hard_stop_pct: 6.0
```

```env
# .env
RUN_MODE=FULL_AUTO
TICKER_WHITELIST=TSLA,NVDA,AMD,PLTR,COIN,GME,AMC
CYCLE_MINUTES=2
```

---

For more details, see:
- [README.md](../README.md) - Quick start guide
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design
- [EXIT_LOGIC.md](EXIT_LOGIC.md) - Exit strategy details

Questions? Open an issue on GitHub.
