# Quick Start Guide

Get up and running in 5 minutes!

## Prerequisites

- Python 3.11+
- Anthropic API key (get from https://console.anthropic.com/)
- Alpaca Paper Trading account (get from https://alpaca.markets/)

## Step-by-Step Setup

### 1. Install Dependencies

```bash
cd autotrader
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy template
cp .env.example .env

# Edit with your credentials
nano .env
```

Add your keys:
```env
ANTHROPIC_API_KEY=sk-ant-xxxxx
ALPACA_API_KEY=PKxxxxx
ALPACA_SECRET_KEY=xxxxx
RUN_MODE=DRYRUN
```

### 3. Test Configuration

```bash
# Run tests to verify setup
pytest tests/test_rules.py -v
```

### 4. Run First Cycle

```bash
# Run in DRYRUN mode (safe, no real orders)
python -m app.main --mode once
```

### 5. Check Results

```bash
# View logs
cat data/autotrader.log

# Or use SQLite
sqlite3 data/autotrader.db "SELECT * FROM runs ORDER BY started_at DESC LIMIT 1;"
```

## What Happens in a Cycle?

1. **Fetch News** (10-30 seconds)
   - Queries RSS feeds for recent headlines
   - Filters by ticker whitelist (AAPL, TSLA, etc.)

2. **Interpret Events** (~2-5 seconds per event)
   - Sends headlines to Claude
   - Extracts sentiment, category, reliability

3. **Scan Market** (~1 second per ticker)
   - Gets real-time prices from Alpaca
   - Calculates RSI, volume ratios, etc.

4. **Evaluate Rules** (< 1 second)
   - Checks ENTRY/SKIP conditions
   - Applies risk management

5. **Execute** (< 1 second in DRYRUN)
   - In DRYRUN: logs order without placing
   - In FULL_AUTO: places real order

## Expected Output

```
=== Starting run abc123 in DRYRUN mode ===
Step 1: Fetching RSS feeds...
Fetched 5 RSS items
Step 2: Interpreting events with LLM...
Interpreted 3 new events
Processing event: Apple announces Q4 earnings...
Signal approved for AAPL, executing...
[DRYRUN] Would place order: 5 shares of AAPL @ $175.50
=== Run abc123 completed successfully ===
Events: 3 | Signals: 2 | Orders: 1
```

## Next Steps

1. **Tune Rules**: Edit `configs/rules.yaml` to adjust entry/exit criteria
2. **Monitor**: Run in continuous mode with `--mode continuous`
3. **Notifications**: Add Slack webhook to `.env` for alerts
4. **Analysis**: Query `data/autotrader.db` to review decisions

## Troubleshooting

### "No module named 'app'"

```bash
# Make sure you're in the autotrader directory
export PYTHONPATH=$PWD
python -m app.main --mode once
```

### "API key not found"

```bash
# Verify .env file exists and is loaded
cat .env | grep ANTHROPIC
```

### "No market data"

Check that market is open (9:30 AM - 4 PM ET, Mon-Fri) or try a different ticker.

## Ready for More?

- Read full [README.md](README.md) for advanced configuration
- Review [Paper to Live Checklist](README.md#-paper-to-live-trading-checklist)
- Set up Docker with `make docker-build && make docker-run`

**Remember**: ALWAYS test in DRYRUN mode first!
