# Quick Start Guide

Get your automated news trading system up and running in 5 minutes!

## What You'll Get

- **24/7 News Monitoring**: Continuous RSS feed tracking
- **AI-Powered Analysis**: Claude Haiku 3.5 interprets news sentiment
- **Smart Entry Logic**: Rule-based filtering for high-quality trades
- **Advanced Exit Strategy**: 4-stage exit system (partial profit, trailing stop, time limit, hard stop)
- **Risk Management**: Position sizing, daily limits, sector controls
- **Real-time Alerts**: Slack notifications for all trades

## Prerequisites

- Python 3.11+ (or 3.13 recommended)
- Anthropic API key (get from https://console.anthropic.com/)
- Alpaca Paper Trading account (get from https://alpaca.markets/)
- (Optional) Slack workspace for notifications

## Step-by-Step Setup

### 1. Clone & Install

```bash
# Clone repository (if not already done)
git clone https://github.com/salwks/invest.git
cd invest/autotrader

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy template
cp .env.example .env

# Edit with your API keys
nano .env  # or use your preferred editor
```

**Required settings:**
```env
# Anthropic Claude API
ANTHROPIC_API_KEY=sk-ant-api03-your_key_here
ANTHROPIC_MODEL=claude-3-5-haiku-20241022

# Alpaca Paper Trading API
ALPACA_API_KEY=PKxxxxx
ALPACA_SECRET_KEY=xxxxx
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2

# Run Mode (IMPORTANT: Start with DRYRUN!)
RUN_MODE=DRYRUN

# Tickers to monitor
TICKER_WHITELIST=AAPL,TSLA,NVDA,MSFT,GOOGL,AMZN,META

# Cycle frequency (minutes)
CYCLE_MINUTES=5
```

**Optional settings:**
```env
# Slack notifications
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Initial equity for position sizing
INITIAL_EQUITY=100000.0
```

> **Note**: The `.env` file is in `.gitignore` - your API keys will never be committed.

### 3. Verify Installation

```bash
# Run all tests to verify setup
pytest tests/ -v

# Should see:
# ✅ test_rules.py - 16 passed (Entry rules)
# ✅ test_exit_rules.py - 16 passed (Exit logic)
# ✅ test_llm_contract.py - passed
```

### 4. Run First Cycle

```bash
# Run single cycle in DRYRUN mode (safe, no real orders)
python -m app.main --mode once
```

**What to expect:**
- Fetches recent news from RSS feeds
- Interprets events with Claude AI
- Scans market data for mentioned tickers
- Applies entry/exit rules
- **Simulates** order placement (no real trades!)
- Saves results to database

### 5. Check Results

```bash
# View log file
tail -f data/autotrader.log

# Query database for latest run
sqlite3 data/autotrader.db "SELECT * FROM runs ORDER BY started_at DESC LIMIT 1;"

# View signals generated
sqlite3 data/autotrader.db "SELECT ticker, action, approved FROM signals ORDER BY created_at DESC LIMIT 5;"

# View simulated orders
sqlite3 data/autotrader.db "SELECT ticker, side, quantity, status FROM orders ORDER BY submitted_at DESC LIMIT 5;"
```

## What Happens in a Cycle?

Every 5 minutes (configurable), the system executes this pipeline:

### Entry Flow

1. **Fetch News** (10-30 seconds)
   - Queries RSS feeds for recent headlines (24/7)
   - Deduplicates by cluster_id
   - Saves unprocessed events to database

2. **Interpret Events** (~2-5 seconds per event)
   - Sends headlines to Claude Haiku 3.5
   - Extracts: sentiment, category, reliability, tickers, key facts
   - Classifies market session (pre-market, regular, after-hours)

3. **Scan Market** (~1 second per ticker)
   - Gets real-time prices from Alpaca (IEX feed)
   - Calculates technical indicators: RSI(3), VWAP, volume ratios
   - Determines price momentum (1-min, 5-min changes)

4. **Evaluate Entry Rules** (< 1 second)
   - Checks sentiment + impact thresholds
   - Validates price momentum (1-4% range)
   - Confirms volume spike (3x average)
   - Filters by category and session

5. **Risk Management** (< 1 second)
   - Calculates position size based on volatility
   - Checks daily loss limits
   - Validates max concurrent positions (max 3)
   - Enforces daily ticker limit (max 10/day)
   - Checks sector exposure limits

6. **Execute Entry** (< 1 second in DRYRUN)
   - **DRYRUN**: Logs order without placing
   - **SEMI_AUTO**: Requests approval, then places
   - **FULL_AUTO**: Places order immediately

### Exit Flow

7. **Monitor Positions** (every cycle)
   - Retrieves all open positions from database
   - Gets current market price for each position
   - Updates peak price tracking
   - Evaluates 4 exit conditions:
     - **Hard Stop**: -4% loss → immediate sell
     - **Partial Profit**: +8% gain → sell 40%
     - **Trailing Stop**: -5% from peak → full sell
     - **Time Limit**: 60 minutes → full sell

8. **Execute Exit** (when conditions met)
   - Places sell order via Alpaca
   - Updates position in database
   - Calculates realized P&L
   - Sends Slack notification with results

### Notifications

9. **Send Alerts** (Slack)
   - Entry signals (approved, rejected, skipped)
   - Exit signals (partial, full, with P&L)
   - Run completion summary
   - Error alerts

## Expected Output

### First Run (DRYRUN Mode)

```
=== Starting run abc123de in DRYRUN mode ===

Step 1: Fetching RSS feeds...
Fetched 5 RSS items

Step 2: Interpreting events with LLM...
Interpreted 3 new events
Found 2 unprocessed events from previous runs

Step 3: Processing events...
Processing event: Apple announces record Q4 earnings, beats estimates...
  Market state: AAPL @ $175.50, +2.3% (5m), volume 4.2x avg
  Rule Engine: ENTRY (sentiment 0.85, impact 0.90)
  Risk Guard: APPROVED - 5 shares @ $175.50 = $877.50
  [DRYRUN] Would place order: 5 shares of AAPL @ $175.50

Processing event: Tesla recalls Model 3 vehicles...
  Market state: TSLA @ $242.10, -1.2% (5m)
  Rule Engine: SKIP (negative sentiment -0.45)

Step 4: Monitoring open positions...
Monitoring 1 open positions
  HOLD NVDA: +5.2% | In position: +5.2%, 25m

=== Run abc123de completed successfully ===
Events: 3 | Signals: 2 | Orders: 1
```

### Continuous Mode Output

```
=== Starting run in DRYRUN mode ===
[... full cycle ...]
=== Run completed successfully ===
Waiting 5 minutes until next cycle...

=== Starting run in DRYRUN mode ===
Step 4: Monitoring open positions...
  PARTIAL EXIT: AAPL - LVL1_PROFIT
  [DRYRUN] Would sell: 2 shares of AAPL @ $190.00 | P&L: $29.00 (+8.28%)
[... continues every 5 minutes ...]
```

## Next Steps

### 1. Run Continuous Mode

```bash
# Run continuously (checks news every 5 minutes)
python -m app.main --mode continuous

# Press Ctrl+C to stop
```

### 2. Set Up Slack Notifications

```bash
# Add to .env
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

You'll receive notifications for:
- 🚀 Entry signals (with sentiment & reasoning)
- 🟢 Exit signals (with P&L)
- ✅ Run completions
- ⚠️ Errors

### 3. Customize Trading Rules

Edit `configs/rules.yaml`:

```yaml
# Make it more conservative
entry:
  min_sentiment: 0.80  # Higher bar (was 0.70)
  dp5m_min_pct: 1.5    # Stronger momentum required

# Or more aggressive
exit:
  take_profit_lvl1_pct: 5.0  # Take profit earlier (was 8.0)
  hold_minutes: 30           # Shorter holds (was 60)
```

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for complete guide.

### 4. Analyze Performance

```bash
# View all trades
sqlite3 data/autotrader.db "
  SELECT ticker, entry_price, exit_price, realized_pnl
  FROM positions
  WHERE status = 'closed'
  ORDER BY exit_time DESC;
"

# Calculate win rate
sqlite3 data/autotrader.db "
  SELECT
    COUNT(*) as total_trades,
    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
    SUM(realized_pnl) as total_pnl
  FROM positions
  WHERE status = 'closed';
"
```

### 5. Learn the System

Read comprehensive documentation:

- **[EXIT_LOGIC.md](docs/EXIT_LOGIC.md)** - Complete exit strategy guide
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System design & components
- **[CONFIGURATION.md](docs/CONFIGURATION.md)** - All configuration options
- **[README.md](README.md)** - Full features & paper-to-live checklist

## Troubleshooting

### "No module named 'app'"

```bash
# Make sure you're in the autotrader directory
cd /path/to/invest/autotrader

# Verify directory structure
ls app/  # Should see main.py, config.py, etc.

# Run from autotrader directory
python -m app.main --mode once
```

### "API key not found" or "Invalid API key"

```bash
# 1. Verify .env file exists
ls -la .env

# 2. Check key format
cat .env | grep ANTHROPIC_API_KEY
# Should start with: sk-ant-api03-

cat .env | grep ALPACA_API_KEY
# Should start with: PK

# 3. Verify keys are valid
# - Anthropic: https://console.anthropic.com/settings/keys
# - Alpaca: https://app.alpaca.markets/paper/dashboard/overview
```

### "subscription does not permit querying recent SIP data"

```bash
# Make sure ALPACA_BASE_URL ends with /v2
# Edit .env:
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2
```

### "No market data" or "Market scanner returned None"

**Causes:**
1. Market is closed (regular hours: 9:30 AM - 4 PM ET, Mon-Fri)
2. Ticker not available on IEX feed
3. Network/API issues

**Solutions:**
```bash
# Check market hours
date -u  # Should be within market hours (13:30-20:00 UTC weekdays)

# Try different ticker
TICKER_WHITELIST=AAPL,MSFT,GOOGL  # Stick to mega-caps

# Check logs for errors
tail -50 data/autotrader.log | grep ERROR
```

### "RSS feeds timing out"

```bash
# Only Seeking Alpha is active (Yahoo Finance and Nasdaq are rate-limited)
# This is expected - the system will still work with 1 feed

# Check app/config.py to verify RSS_FEEDS list
grep -A5 "RSS_FEEDS" app/config.py
```

### Tests failing

```bash
# Make sure you're in virtual environment
source venv/bin/activate

# Install test dependencies
pip install pytest pytest-asyncio

# Run tests with verbose output
pytest tests/ -v --tb=short

# Run specific test file
pytest tests/test_exit_rules.py -v
```

### Database locked error

```bash
# Close all connections
pkill -f "python -m app.main"

# Remove lock file if exists
rm -f data/autotrader.db-journal

# Restart system
python -m app.main --mode once
```

### "No signals generated" or "All signals SKIP"

**Your rules might be too strict!**

```bash
# Check current rules
cat configs/rules.yaml

# Try more relaxed settings (temporarily for testing)
# Edit configs/rules.yaml:
entry:
  min_sentiment: 0.60  # Lower (was 0.70)
  dp5m_min_pct: 0.5    # Lower (was 1.0)
  min_vol_ratio: 2.0   # Lower (was 3.0)

# Enable debug logging
# Edit .env:
LOG_LEVEL=DEBUG

# Run again and check logs
python -m app.main --mode once
tail -100 data/autotrader.log
```

## Common Questions

**Q: How much does it cost to run?**
- Anthropic API: ~$20-30/month (Claude Haiku 3.5)
- Alpaca Paper Trading: FREE
- Total: ~$20-30/month

**Q: Can I run this on live trading?**
- Yes, but ONLY after extensive DRYRUN testing (minimum 1-2 weeks)
- Read the [Paper to Live Checklist](README.md#-paper-to-live-trading-checklist)
- Start with very small position sizes
- Never risk money you can't afford to lose

**Q: How often does it trade?**
- Depends on news volume and market conditions
- Typical: 1-5 signals per day
- With strict rules: 0-2 signals per day
- Positions held: 5-60 minutes (avg ~30 min)

**Q: What's the expected win rate?**
- Not guaranteed - this is for educational purposes
- Exit logic designed for asymmetric risk/reward
- Hard stop at -4%, trailing stop protects gains
- Partial profit taking locks in gains

**Q: Can I backtest this?**
- Not currently built-in
- You can analyze historical performance in database
- Consider adding backtesting module (future enhancement)

## Ready for Production?

### Before Live Trading:

1. ✅ Run in DRYRUN for **minimum 1 week**
2. ✅ Review **every signal** manually
3. ✅ Verify risk limits appropriate for your capital
4. ✅ Test with SEMI_AUTO mode first
5. ✅ Start with **very small positions** (1-5% of normal size)
6. ✅ Set up monitoring and alerts
7. ✅ Have manual kill switch ready
8. ✅ Read [README.md#paper-to-live-checklist](README.md#-paper-to-live-trading-checklist)

### Going Live:

```bash
# 1. Switch to SEMI_AUTO first
RUN_MODE=SEMI_AUTO

# 2. Reduce position sizes
# Edit configs/rules.yaml:
risk:
  per_trade_risk_pct: 0.001  # Start with 0.1% (was 0.4%)
  max_position_size_usd: 500.0  # Small positions

# 3. Monitor closely
python -m app.main --mode continuous

# 4. After 1 week of successful SEMI_AUTO, consider FULL_AUTO
RUN_MODE=FULL_AUTO
```

## Additional Resources

- **Documentation**:
  - [EXIT_LOGIC.md](docs/EXIT_LOGIC.md) - Exit strategy details
  - [ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture
  - [CONFIGURATION.md](docs/CONFIGURATION.md) - Configuration guide

- **Community**:
  - GitHub Issues: https://github.com/salwks/invest/issues
  - Discussions: https://github.com/salwks/invest/discussions

- **APIs**:
  - Anthropic Docs: https://docs.anthropic.com
  - Alpaca Docs: https://docs.alpaca.markets

---

**⚠️ DISCLAIMER**: This software is for educational purposes only. Trading involves risk. Never risk money you cannot afford to lose. The authors assume no liability for financial losses.

**Remember**: ALWAYS test in DRYRUN mode first!
