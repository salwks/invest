# System Architecture Documentation

## Overview

The Automated News-Based Trading System is a sophisticated event-driven trading platform that monitors news feeds, interprets them with AI, applies rule-based trading logic, and executes trades automatically.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    AUTOMATED TRADING SYSTEM                      │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│  RSS Feeds   │      │  Alpaca API  │      │  Slack       │
│  (24/7)      │      │  (IEX Data)  │      │  Webhooks    │
└──────┬───────┘      └──────┬───────┘      └──────┬───────┘
       │                     │                      │
       ├─────────────────────┴──────────────────────┤
       │                                            │
┌──────▼────────────────────────────────────────────▼─────┐
│              MAIN ORCHESTRATION LOOP                     │
│                 (every 5 minutes)                        │
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │  Step 1: Fetch RSS Items (with deduplication) │    │
│  └──────────────────┬─────────────────────────────┘    │
│                     ▼                                    │
│  ┌────────────────────────────────────────────────┐    │
│  │  Step 2: LLM Interpretation (Claude Haiku 3.5) │    │
│  └──────────────────┬─────────────────────────────┘    │
│                     ▼                                    │
│  ┌────────────────────────────────────────────────┐    │
│  │  Step 3: Process Events (Entry Logic)          │    │
│  │  • Get market state                            │    │
│  │  • Apply entry rules                           │    │
│  │  • Risk management                             │    │
│  │  • Execute orders                              │    │
│  └──────────────────┬─────────────────────────────┘    │
│                     ▼                                    │
│  ┌────────────────────────────────────────────────┐    │
│  │  Step 4: Monitor Positions (Exit Logic)        │    │
│  │  • Update peak prices                          │    │
│  │  • Evaluate exit conditions                    │    │
│  │  • Execute exit orders                         │    │
│  └──────────────────┬─────────────────────────────┘    │
│                     ▼                                    │
│  ┌────────────────────────────────────────────────┐    │
│  │  Step 5: Send Notifications & Log Results      │    │
│  └────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  PERSISTENT STORAGE                     │
│  • SQLite Database (events, signals,    │
│    orders, positions, runs)             │
│  • Parquet Logs (time-series data)      │
└─────────────────────────────────────────┘
```

---

## Component Architecture

### 1. RSS Fetcher (`rss_fetcher.py`)

**Purpose**: Continuously monitor RSS feeds for news events

**Key Features:**
- Fetches from multiple RSS sources (Seeking Alpha, Yahoo Finance, Nasdaq)
- Deduplication via cluster_id (headline hash)
- Delay-aware fetching (respects feed latency)
- 24/7 operation (events saved to database)

**Data Flow:**
```python
RSS Feed URL → feedparser → RSSFeedItem → Storage (unprocessed)
```

**Configuration:**
```python
RSS_FEEDS = [
    {
        "name": "Seeking Alpha Market News",
        "url": "https://seekingalpha.com/feed.xml",
        "delay_minutes": 3
    }
]
```

**Important Notes:**
- Uses aiohttp with 10-second timeout per feed
- User-Agent header to avoid blocking
- Returns items published within time window

---

### 2. LLM Interpreter (`llm_interpreter.py`)

**Purpose**: Convert raw news into structured EventCard using Claude AI

**Key Features:**
- Uses Claude Haiku 3.5 (fast, cheap, accurate)
- Extracts: sentiment, category, reliability, tickers, key facts
- Session classification (pre-market, regular, after-hours)
- Robust error handling with fallback to "NoTrade"

**Data Flow:**
```python
RSSFeedItem → Claude API → EventCard → Storage (events table)
```

**Prompt Structure:**
```python
system_prompt = """
You are a financial news analyst. Classify news events with:
- tickers: List of affected tickers
- category: earnings|FDA|M&A|guidance|partnership|regulatory|rumor|other
- sentiment: -1.0 (very negative) to +1.0 (very positive)
- reliability: 0.0 (rumor) to 1.0 (official)
- key_facts: Bullet points of important info
- session: pre|regular|after
"""
```

**Example Output:**
```json
{
  "tickers": ["AAPL"],
  "category": "earnings",
  "sentiment": 0.85,
  "reliability": 0.95,
  "key_facts": ["Beat EPS by 15%", "Strong iPhone sales"],
  "session": "after"
}
```

---

### 3. Market Scanner (`market_scanner.py`)

**Purpose**: Fetch real-time market data and calculate technical indicators

**Key Features:**
- Alpaca IEX feed (free tier compatible)
- Real-time quotes (bid/ask/mid/spread)
- Price momentum (1m, 5m changes)
- Volume ratios vs average
- Technical indicators: RSI(3), VWAP deviation

**Data Flow:**
```python
Ticker → Alpaca API → MarketState → Rule Engine
```

**Calculated Metrics:**
```python
MarketState:
  - mid: (bid + ask) / 2
  - spread_bp: (ask - bid) / mid * 10000
  - dP_1m: (current - 1min_ago) / 1min_ago * 100
  - dP_5m: (current - 5min_ago) / 5min_ago * 100
  - vol_ratio_1m: 1min_volume / avg_volume
  - rsi_3: RSI calculated on 3 periods
  - vwap_dev_bp: (mid - vwap) / vwap * 10000
```

**Important Notes:**
- Uses `feed='iex'` parameter for free tier
- Caches recent bars to avoid redundant API calls
- Returns None if no market data available (market closed)

---

### 4. Rule Engine (`rule_engine.py`)

**Purpose**: Evaluate entry conditions based on configurable rules

**Key Features:**
- YAML-based rule configuration
- Sentiment + impact filters
- Price momentum filters
- Volume and liquidity checks
- Category allowlist/blocklist
- Session restrictions

**Data Flow:**
```python
(EventCard, MarketState) → Rule Engine → PreSignal (ENTRY or SKIP)
```

**Evaluation Logic:**
```python
def evaluate(event: EventCard, market: MarketState) -> PreSignal:
    # 1. Check skip conditions (disqualify immediately)
    if should_skip(event, market):
        return PreSignal(action="SKIP", reasons=[...])

    # 2. Check entry conditions (all must pass)
    if meets_entry_criteria(event, market):
        return PreSignal(action="ENTRY", reasons=[...])

    # 3. Default to SKIP
    return PreSignal(action="SKIP", reasons=[...])
```

**Example Rules:**
```yaml
entry:
  min_sentiment: 0.70     # Bullish news only
  min_impact: 0.70        # High reliability only
  dp5m_min_pct: 1.0       # Min 1% move in 5min
  dp5m_max_pct: 4.0       # Max 4% move (avoid spikes)
  min_vol_ratio: 3.0      # 3x avg volume
  max_rsi3: 75            # Not overbought

skip:
  spike01_gt_pct: 5.0     # Skip if 1min spike > 5%
  disallow_categories: [rumor]
```

---

### 5. Risk Guard (`risk_guard.py`)

**Purpose**: Position sizing and portfolio risk management

**Key Features:**
- Volatility-based position sizing
- Daily loss limits
- Max concurrent positions
- Sector exposure limits
- Daily ticker limits (max 10/day)

**Data Flow:**
```python
(PreSignal, MarketState, PortfolioState) → Risk Guard → ApprovedSignal
```

**Position Sizing Logic:**
```python
# Risk per trade (0.4% of equity)
risk_amount = portfolio.equity * 0.004

# Stop distance (min 150bp, or 1.5x 5min volatility)
stop_bp = max(150, market.dP_5m * 100 * 1.5)

# Position size = Risk / Stop Distance
size_usd = risk_amount / (stop_bp / 10000)

# Apply limits
size_usd = min(
    size_usd,
    portfolio.equity * 0.15,  # Max 15% per position
    15000.0                   # Absolute max $15k
)

shares = int(size_usd / market.mid)
```

**Risk Checks:**
- ❌ Reject if daily loss limit exceeded
- ❌ Reject if max concurrent positions reached
- ❌ Reject if sector exposure limit exceeded
- ❌ Reject if daily ticker limit reached
- ✅ Approve if all checks pass

---

### 6. Trade Manager (`trade_manager.py`)

**Purpose**: Evaluate exit conditions for open positions

**Key Features:**
- 4-stage exit priority system
- Peak price tracking
- Partial profit taking
- Trailing stops
- Time-based exits

**Data Flow:**
```python
(Position, current_price) → Trade Manager → Exit Decision
```

**Exit Priority:**
```python
def manage_exit(position, market_price) -> Dict:
    # Priority 1: Hard Stop (-4%)
    if pnl_pct <= -4.0:
        return {"action": "FULL_SELL", "reason": "HARD_STOP"}

    # Priority 2: Partial Profit (+8%, once)
    if pnl_pct >= 8.0 and not position.partial_sold:
        return {"action": "PARTIAL_SELL", "reason": "LVL1_PROFIT"}

    # Priority 3: Trailing Stop (-5% from peak)
    if peak > entry and market_price <= peak * 0.95:
        return {"action": "FULL_SELL", "reason": "TRAILING_STOP"}

    # Priority 4: Time Limit (60 minutes)
    if hold_time >= 60:
        return {"action": "FULL_SELL", "reason": "TIME_LIMIT"}

    # Priority 5: Hold
    return {"action": "HOLD"}
```

See [EXIT_LOGIC.md](EXIT_LOGIC.md) for complete details.

---

### 7. Broker Executor (`broker_exec.py`)

**Purpose**: Execute trades via Alpaca API

**Key Features:**
- 3 run modes: DRYRUN, SEMI_AUTO, FULL_AUTO
- Entry orders (limit orders with slippage control)
- Exit orders (sell limit orders)
- Order monitoring and fill detection
- Retry logic on failures

**Data Flow:**
```python
ApprovedSignal → Broker Executor → Order → Alpaca API → Position
Position + Exit → Broker Executor → Sell Order → Closed Position
```

**Execution Modes:**

**DRYRUN:**
- No real API calls to Alpaca
- Simulates order placement and fills
- Safe for testing

**SEMI_AUTO:**
- Sends approval request to user
- Waits for confirmation
- Places real order if approved
- (In MVP: simulates 80% approval rate)

**FULL_AUTO:**
- Automatically places orders
- No user intervention
- **USE WITH CAUTION**

**Order Flow:**
```python
# Entry
1. Create LimitOrderRequest (side=BUY)
2. Submit to Alpaca API
3. Monitor order status (poll every 2s)
4. On fill: Create Position record
5. Set stop_loss and take_profit

# Exit
1. Create LimitOrderRequest (side=SELL)
2. Submit to Alpaca API
3. On fill: Close position, calculate P&L
```

---

### 8. Storage (`storage.py`)

**Purpose**: Persistent storage for all system data

**Key Features:**
- SQLite database for structured data
- Parquet files for time-series logs
- Atomic operations
- Event deduplication
- Position tracking

**Database Schema:**

**events table:**
```sql
CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    cluster_id TEXT NOT NULL,
    headline TEXT NOT NULL,
    category TEXT NOT NULL,
    sentiment REAL NOT NULL,
    reliability REAL NOT NULL,
    published_at TEXT NOT NULL,
    session TEXT NOT NULL,
    tickers TEXT NOT NULL,
    source TEXT,
    url TEXT,
    key_facts TEXT,
    created_at TEXT NOT NULL,
    processed INTEGER DEFAULT 0  -- For 24/7 processing
);
```

**signals table:**
```sql
CREATE TABLE signals (
    signal_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL,
    approved INTEGER NOT NULL,
    size_usd REAL,
    entry_price REAL,
    stop_bp INTEGER,
    take_profit_bp INTEGER,
    reasons TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);
```

**orders table:**
```sql
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    order_type TEXT NOT NULL,
    limit_price REAL,
    status TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    filled_at TEXT,
    filled_avg_price REAL,
    filled_qty INTEGER,
    error_message TEXT
);
```

**positions table:**
```sql
CREATE TABLE positions (
    position_id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    entry_price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    entry_time TEXT NOT NULL,
    exit_time TEXT,
    exit_price REAL,
    event_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    current_price REAL,        -- Peak price tracker
    partial_sold INTEGER DEFAULT 0,  -- Exit logic flag
    realized_pnl REAL,
    status TEXT NOT NULL DEFAULT 'open'
);
```

**runs table:**
```sql
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    mode TEXT NOT NULL,
    events_fetched INTEGER DEFAULT 0,
    signals_generated INTEGER DEFAULT 0,
    orders_placed INTEGER DEFAULT 0,
    errors TEXT
);
```

**Parquet Logs:**
- `data/events/date=YYYY-MM-DD/events_HHMMSS.parquet`
- `data/market/date=YYYY-MM-DD/market_HHMMSS.parquet`
- `data/signals/date=YYYY-MM-DD/signals_HHMMSS.parquet`

---

### 9. Notifier (`notifier.py`)

**Purpose**: Send Slack notifications for key events

**Key Features:**
- Entry signal notifications
- Exit notifications with P&L
- Error alerts
- Run completion summaries

**Notification Types:**

**Entry Signal:**
```
🚀 ENTRY SIGNAL - AAPL

Apple announces record earnings...

Category: earnings
Sentiment: 0.85 | Reliability: 0.95

Trade Details:
• Size: 5 shares @ $175.50 ≈ $877.50
• Stop: 150 bp | TP: 250 bp

Reasons:
• Strong positive sentiment (0.85 > 0.70)
• Good momentum (+2.3% in 5min)
```

**Exit Signal:**
```
🟢 FULL EXIT - TSLA (TRAILING STOP)

Reason: TRAILING STOP

Position Details:
• Entry Price: $100.00
• Exit Price: $190.00
• Quantity: 10 shares
• P&L: $900.00 (+90.00%)

• Position CLOSED
```

---

## Data Flow Diagrams

### Entry Flow

```
┌─────────────┐
│  RSS Feed   │
└──────┬──────┘
       │
       ▼
┌──────────────────┐
│  RSS Fetcher     │ ← Fetch items since last run
│  (rss_fetcher)   │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  Storage         │ ← Save unprocessed events
│  (event_exists)  │
└──────┬───────────┘
       │
       ▼
┌──────────────────────┐
│  LLM Interpreter     │ ← Classify news with Claude
│  (llm_interpreter)   │
└──────┬───────────────┘
       │
       ▼
┌──────────────────┐
│  EventCard       │ ← Structured event data
└──────┬───────────┘
       │
       ▼
┌──────────────────────┐
│  Market Scanner      │ ← Get real-time market data
│  (market_scanner)    │
└──────┬───────────────┘
       │
       ▼
┌──────────────────┐
│  MarketState     │ ← Price, volume, indicators
└──────┬───────────┘
       │
       ▼
┌──────────────────────┐
│  Rule Engine         │ ← Apply entry rules
│  (rule_engine)       │
└──────┬───────────────┘
       │
       ▼
┌──────────────────┐
│  PreSignal       │ ← ENTRY or SKIP
└──────┬───────────┘
       │
       ▼
┌──────────────────────┐
│  Risk Guard          │ ← Position sizing & limits
│  (risk_guard)        │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  ApprovedSignal      │ ← Final trade decision
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Broker Executor     │ ← Place order
│  (broker_exec)       │
└──────┬───────────────┘
       │
       ▼
┌──────────────────┐
│  Order/Position  │ ← Track in database
└──────────────────┘
```

### Exit Flow

```
┌──────────────────────────┐
│  Main Loop (every 5min)  │
└──────────┬───────────────┘
           │
           ▼
┌─────────────────────────┐
│  Get Open Positions     │ ← From database
│  (storage)              │
└──────────┬──────────────┘
           │
           ▼
     ┌─────────────┐
     │  For each   │
     │  position:  │
     └──────┬──────┘
            │
            ▼
┌──────────────────────────┐
│  Market Scanner          │ ← Get current price
│  (market_scanner)        │
└──────────┬───────────────┘
            │
            ▼
┌──────────────────────────┐
│  Update Peak Price       │ ← Track highest price
│  (storage.update_position)│
└──────────┬───────────────┘
            │
            ▼
┌──────────────────────────┐
│  Trade Manager           │ ← Evaluate exit conditions
│  (trade_manager)         │
└──────────┬───────────────┘
            │
            ▼
┌──────────────────────────┐
│  Exit Decision           │ ← HOLD, PARTIAL_SELL, FULL_SELL
└──────────┬───────────────┘
            │
            ▼
       ┌────────────┐
       │  Action?   │
       └──┬───┬───┬─┘
          │   │   │
     HOLD │   │   │ FULL_SELL
          │   │   │
          │   │   ▼
          │   │ ┌──────────────────────┐
          │   │ │  Broker Executor     │
          │   │ │  (close_position)    │
          │   │ └──────────┬───────────┘
          │   │            │
          │   │            ▼
          │   │ ┌──────────────────────┐
          │   │ │  Close Position      │
          │   │ │  Calculate P&L       │
          │   │ └──────────┬───────────┘
          │   │            │
          │   │ PARTIAL    │
          │   │ SELL       │
          │   │            │
          │   ▼            │
          │ ┌──────────────────────┐
          │ │  Broker Executor     │
          │ │  (close_position)    │
          │ └──────────┬───────────┘
          │            │
          │            ▼
          │ ┌──────────────────────┐
          │ │  Update Position     │
          │ │  (reduce qty, flag)  │
          │ └──────────┬───────────┘
          │            │
          ▼            ▼
┌─────────────────────────────┐
│  Notification               │
│  (Slack, logs)              │
└─────────────────────────────┘
```

---

## Performance Considerations

### Scalability

**Current System:**
- Single-threaded async Python
- ~5-10 news items per cycle
- ~1-3 concurrent positions
- SQLite database

**Bottlenecks:**
- LLM API calls (sequential, ~1s each)
- Market data fetching (sequential per ticker)

**Optimization Strategies:**
1. Batch LLM requests (if Anthropic supports)
2. Parallel market data fetching (already async)
3. Cache LLM responses for duplicate news
4. Reduce cycle frequency (5min → 10min)

**Scaling Up:**
- For >100 tickers: Use PostgreSQL instead of SQLite
- For >10 concurrent positions: Add position manager service
- For high-frequency: Migrate to WebSocket feeds

### Cost Optimization

**Monthly API Costs:**
- Claude Haiku: ~$20-30/month (5-10 calls per cycle)
- Alpaca Paper Trading: FREE

**Optimization:**
1. Filter news before LLM (keyword matching)
2. Use cheaper models for routine tasks
3. Increase CYCLE_MINUTES to reduce calls
4. Stricter TICKER_WHITELIST

---

## Security Architecture

### API Key Management

```python
# .env file (NOT committed to git)
ANTHROPIC_API_KEY=sk-ant-...
ALPACA_API_KEY=PK...
ALPACA_SECRET_KEY=...
SLACK_WEBHOOK_URL=https://hooks.slack.com/...

# Loading in config.py
class Settings(BaseSettings):
    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    alpaca_api_key: str = Field(..., alias="ALPACA_API_KEY")
    ...

    model_config = SettingsConfigDict(env_file=".env")
```

### Best Practices

1. **Never commit .env file**
2. **Use read-only Alpaca keys** (if possible)
3. **Enable IP whitelisting** on Alpaca account
4. **Rotate keys regularly**
5. **Use secrets manager** in production (AWS Secrets Manager, Azure Key Vault)

---

## Error Handling

### Strategy

1. **LLM Failures**: Return "NoTrade" EventCard
2. **Market Data Unavailable**: Skip ticker, retry next cycle
3. **Order Failures**: Retry once, then log error
4. **Database Errors**: Crash (fail-fast for data integrity)

### Monitoring

```python
# All errors logged to:
- data/autotrader.log
- Slack notifications
- runs.errors column in database

# Query errors:
SELECT * FROM runs WHERE status = 'failed';
```

---

## Deployment Architecture

### Local Development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m app.main --mode once
```

### Docker Deployment

```dockerfile
FROM python:3.13-slim
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
CMD ["python", "-m", "app.main", "--mode", "continuous"]
```

```yaml
# docker-compose.yml
services:
  autotrader:
    build: .
    env_file: .env
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

### Cloud Deployment (AWS)

```
┌──────────────┐
│  ECS Fargate │ ← Docker container
└──────┬───────┘
       │
       ├─────► S3 (Parquet logs)
       ├─────► RDS (PostgreSQL for production)
       ├─────► CloudWatch (logs & metrics)
       └─────► Secrets Manager (API keys)
```

---

## Testing Strategy

### Unit Tests

```bash
# Entry rules
pytest tests/test_rules.py -v

# Exit logic
pytest tests/test_exit_rules.py -v

# LLM contract
pytest tests/test_llm_contract.py -v
```

### Integration Tests

```bash
# Full pipeline in DRYRUN mode
pytest tests/test_integration_dryrun.py -v
```

### Manual Testing

```bash
# Single cycle with logging
RUN_MODE=DRYRUN python -m app.main --mode once

# Check database
sqlite3 data/autotrader.db "SELECT * FROM signals ORDER BY created_at DESC LIMIT 5"
```

---

## Future Architecture Improvements

1. **Event Streaming**: Replace polling with Kafka/Redis Streams
2. **Microservices**: Split into services (ingestion, analysis, execution)
3. **ML Model**: Replace rules with learned trading strategies
4. **Real-time WebSockets**: Use Alpaca WebSocket for live quotes
5. **Distributed Processing**: Use Celery for parallel LLM calls
6. **Advanced Monitoring**: Prometheus + Grafana dashboards

---

For questions or contributions, see [README.md](../README.md) or open a GitHub issue.
