# Exit Logic Documentation

## Overview

The automated trading system implements a sophisticated 4-stage exit logic that maximizes profits while protecting against losses. The exit logic is evaluated **every cycle** (default: 5 minutes) for all open positions.

## Exit Strategy Priority

Exit conditions are evaluated in the following order (highest priority first):

```
1. HARD_STOP      (-4% loss)           → FULL SELL (immediate)
2. LVL1_PROFIT    (+8% gain)           → PARTIAL SELL (40%)
3. TRAILING_STOP  (-5% from peak)      → FULL SELL
4. TIME_LIMIT     (60 minutes)         → FULL SELL
5. HOLD           (no conditions met)  → Continue holding
```

## Detailed Exit Conditions

### 1. Hard Stop Loss (-4%)

**Trigger**: Price drops to -4% from entry price
**Action**: Immediately sell entire position
**Priority**: **HIGHEST** (overrides all other conditions)

**Purpose**: Protect capital from large losses

**Example:**
- Entry: $100.00
- Hard Stop: $96.00 (-4%)
- Current Price: $96.00 → **FULL SELL**

**Configuration:**
```yaml
exit:
  hard_stop_pct: 4.0  # Sell all at -4% loss
```

---

### 2. Partial Profit Taking (+8%)

**Trigger**: Price reaches +8% gain from entry (first time only)
**Action**: Sell 40% of position, keep 60%
**Priority**: 2nd (after hard stop)

**Purpose**: Lock in profits while keeping upside potential

**Example:**
- Entry: $100.00 @ 10 shares
- Profit Target: $108.00 (+8%)
- Current Price: $108.00 → **PARTIAL SELL 4 shares** (40%)
- Remaining: 6 shares (60%)

**Important Notes:**
- Only executes **once per position** (tracked via `partial_sold` flag)
- If price drops below +8% after partial sale, no additional partial sales occur
- Remaining 60% is subject to trailing stop, time exit, or hard stop

**Configuration:**
```yaml
exit:
  take_profit_lvl1_pct: 8.0   # Trigger at +8% gain
  take_profit_lvl1_part: 0.4  # Sell 40% of position
```

---

### 3. Trailing Stop (-5% from Peak)

**Trigger**: Price drops -5% from the highest price reached (peak)
**Action**: Sell entire remaining position
**Priority**: 3rd (after hard stop and partial profit)

**Purpose**: Protect profits during large rallies, exit gracefully when momentum fades

**Example - Large Gain Scenario:**
- Entry: $100.00 @ 10 shares
- Peak: $200.00 (+100% gain)
- Trailing Stop: $190.00 (-5% from peak $200)
- Current Price: $190.00 → **FULL SELL 10 shares**

**Peak Tracking:**
- Peak price is tracked and updated every cycle
- Stored in database: `positions.current_price`
- Peak can only increase, never decrease
- Trailing stop only activates when **in profit** (peak > entry price)

**Example - No Trailing Stop if Not in Profit:**
- Entry: $100.00
- Peak: $100.00 (never went higher)
- Current Price: $95.00 → **HARD_STOP** (not trailing stop)

**Configuration:**
```yaml
exit:
  trailing_stop_pct: 5.0  # Sell all at -5% from peak
```

---

### 4. Time-Based Exit (60 minutes)

**Trigger**: Position held for 60 minutes or more
**Action**: Sell entire position (at current market price)
**Priority**: 4th (lowest priority)

**Purpose**: Avoid overnight risk, capitalize on momentum trades only

**Example:**
- Entry Time: 10:00 AM
- Current Time: 11:00 AM (60 minutes elapsed)
- Current Price: $103.00 (+3%)
- Action: **FULL SELL** due to time limit

**Important Notes:**
- Time is calculated from `position.entry_time` (UTC)
- Time exit executes regardless of profit/loss (except if hard stop triggered first)
- Designed for intraday momentum trading only

**Configuration:**
```yaml
exit:
  hold_minutes: 60  # Max hold time: 60 minutes
```

---

## Complete Example Scenarios

### Scenario 1: Small Gain → Time Exit

```
Entry:      $100.00 @ 10 shares (10:00 AM)
+5 min:     $102.00 (+2%) → HOLD
+10 min:    $103.00 (+3%) → HOLD
+60 min:    $104.00 (+4%) → TIME_LIMIT → FULL SELL
Exit:       $104.00 @ 10 shares
P&L:        +$40 (+4%)
```

### Scenario 2: Medium Gain → Partial Profit + Time Exit

```
Entry:      $100.00 @ 10 shares (10:00 AM)
+10 min:    $108.00 (+8%) → LVL1_PROFIT → PARTIAL SELL 4 shares
            Remaining: 6 shares
+30 min:    $110.00 (+10%) → HOLD (peak = $110)
+50 min:    $109.00 (+9%) → HOLD (still within trailing stop)
+60 min:    $108.50 (+8.5%) → TIME_LIMIT → FULL SELL 6 shares
Exit 1:     $108.00 @ 4 shares = +$32
Exit 2:     $108.50 @ 6 shares = +$51
Total P&L:  +$83 (+8.3%)
```

### Scenario 3: Large Gain → Partial Profit + Trailing Stop

```
Entry:      $100.00 @ 10 shares (10:00 AM)
+5 min:     $108.00 (+8%) → LVL1_PROFIT → PARTIAL SELL 4 shares
            Remaining: 6 shares
+15 min:    $150.00 (+50%) → HOLD (peak = $150)
+20 min:    $200.00 (+100%) → HOLD (peak = $200)
+25 min:    $190.00 (+90%) → TRAILING_STOP → FULL SELL 6 shares
Exit 1:     $108.00 @ 4 shares = +$32 (+8%)
Exit 2:     $190.00 @ 6 shares = +$540 (+90%)
Total P&L:  +$572 (+57.2%)
```

### Scenario 4: Loss → Hard Stop

```
Entry:      $100.00 @ 10 shares (10:00 AM)
+5 min:     $98.00 (-2%) → HOLD
+10 min:    $96.00 (-4%) → HARD_STOP → FULL SELL
Exit:       $96.00 @ 10 shares
P&L:        -$40 (-4%)
```

---

## Implementation Details

### Database Schema

**positions table:**
```sql
CREATE TABLE positions (
    position_id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    entry_price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    entry_time TEXT NOT NULL,
    event_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    current_price REAL,           -- Peak price tracker
    partial_sold INTEGER DEFAULT 0, -- Boolean flag (0 or 1)
    realized_pnl REAL,
    status TEXT NOT NULL DEFAULT 'open'
);
```

### Position Monitoring Flow

```python
# Called every cycle in main.py
async def _monitor_positions(self) -> None:
    positions = storage.get_open_positions()

    for position in positions:
        # Get current market price
        market_state = await market_scanner.get_market_state(position.ticker)
        current_price = market_state.mid

        # Update peak price
        new_peak = max(position.current_price, current_price)
        if new_peak > position.current_price:
            storage.update_position(order_id, current_price=new_peak)

        # Evaluate exit conditions
        exit_decision = trade_manager.manage_exit(position, current_price)

        if exit_decision["action"] == "PARTIAL_SELL":
            # Sell partial position
            await broker.close_position(
                position,
                quantity=exit_decision["sell_qty"],
                price=exit_decision["sell_price"],
                reason=exit_decision["reason"]
            )
            # Update position
            storage.update_position(
                order_id,
                quantity=remaining_qty,
                partial_sold=True
            )

        elif exit_decision["action"] == "FULL_SELL":
            # Sell entire position
            await broker.close_position(...)
            # Close position in database
            storage.close_position(order_id, ...)
```

### Trade Manager Logic

```python
class TradeManager:
    def manage_exit(self, position: Position, market_price: float, now: datetime) -> Dict:
        # Calculate metrics
        pnl_pct = ((market_price - entry_price) / entry_price) * 100
        hold_time_minutes = (now - position.entry_time).total_seconds() / 60

        # Priority 1: Hard Stop
        if pnl_pct <= -4.0:
            return {"action": "FULL_SELL", "reason": "HARD_STOP", ...}

        # Priority 2: Partial Profit (only if not already sold)
        if pnl_pct >= 8.0 and not position.partial_sold:
            return {"action": "PARTIAL_SELL", "reason": "LVL1_PROFIT", ...}

        # Priority 3: Trailing Stop (only if in profit)
        peak = position.current_price or entry_price
        if peak > entry_price:
            trail_trigger = peak * (1 - 5.0/100)
            if market_price <= trail_trigger:
                return {"action": "FULL_SELL", "reason": "TRAILING_STOP", ...}

        # Priority 4: Time Limit
        if hold_time_minutes >= 60:
            return {"action": "FULL_SELL", "reason": "TIME_LIMIT", ...}

        # Priority 5: Hold
        return {"action": "HOLD", ...}
```

---

## Notification Examples

### Partial Exit Notification (Slack)

```
🟢 PARTIAL EXIT - TSLA (PROFIT TAKING (Partial))

Reason: PROFIT TAKING (Partial)

Position Details:
• Entry Price: $100.00
• Exit Price: $108.00
• Quantity: 4 shares
• P&L: $32.00 (+8.00%)

• Remaining: 6 shares
```

### Full Exit Notification (Slack)

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

### Hard Stop Notification (Slack)

```
🔴 FULL EXIT - AAPL (STOP LOSS)

Reason: STOP LOSS

Position Details:
• Entry Price: $175.00
• Exit Price: $168.00
• Quantity: 5 shares
• P&L: -$35.00 (-4.00%)

• Position CLOSED
```

---

## Testing

Comprehensive test suite with 16 tests covering all exit scenarios:

```bash
pytest tests/test_exit_rules.py -v
```

**Test Coverage:**
- ✅ Hold condition (no exit triggers)
- ✅ Hard stop at exactly -4%
- ✅ Partial profit at exactly +8%
- ✅ Partial profit only once (flag check)
- ✅ Trailing stop from +100% gain
- ✅ Trailing stop only in profit
- ✅ Time exit after exactly 60 minutes
- ✅ Time exit not before 60 minutes
- ✅ Priority: hard stop > time limit
- ✅ Priority: partial profit > trailing stop
- ✅ Peak price tracking
- ✅ Large gain scenario (+100% → -5% trailing)
- ✅ Edge cases (exactly 8%, -4%, 60min)
- ✅ Quantity calculations for partial sells

---

## Configuration Reference

Complete exit configuration in `configs/rules.yaml`:

```yaml
exit:
  # Partial profit taking (1st level)
  take_profit_lvl1_pct: 8.0      # Trigger at +8% gain
  take_profit_lvl1_part: 0.4     # Sell 40% of position

  # Trailing stop (2nd level)
  trailing_stop_pct: 5.0         # Sell all at -5% from peak

  # Time-based exit
  hold_minutes: 60               # Max hold time: 60 minutes

  # Hard stop loss
  hard_stop_pct: 4.0             # Sell all at -4% loss
```

---

## Best Practices

1. **Always start in DRYRUN mode** to test exit logic with simulated trades
2. **Monitor Slack notifications** to understand when and why exits occur
3. **Review exit performance** in database:
   ```sql
   SELECT
       ticker,
       entry_price,
       exit_price,
       realized_pnl,
       (exit_price - entry_price) / entry_price * 100 as pnl_pct
   FROM positions
   WHERE status = 'closed'
   ORDER BY exit_time DESC
   LIMIT 20;
   ```
4. **Adjust exit rules** based on backtesting and live performance
5. **Consider market conditions** - volatile markets may need tighter stops

---

## Troubleshooting

### Position not exiting when expected

**Check:**
1. Market data available: `market_scanner.get_market_state(ticker)`
2. Position tracking correct: `SELECT * FROM positions WHERE status = 'open'`
3. Peak price updated: `positions.current_price` should reflect highest price seen
4. Partial sold flag: If stuck, may need to reset `partial_sold = 0`

### Exit order failed

**Possible causes:**
- Alpaca API error (check logs)
- Insufficient shares (quantity mismatch)
- Market closed (orders rejected)

**Solution:**
- Check `orders` table for error messages
- Retry manually via Alpaca dashboard
- Verify RUN_MODE (DRYRUN won't place real orders)

---

## Future Enhancements

Potential improvements to exit logic:

1. **Multi-level profit taking**: Add 2nd partial exit at +15%
2. **Dynamic trailing stop**: Tighten trailing % as profits increase
3. **Volatility-adjusted stops**: Use ATR for stop distance
4. **News-based exits**: Exit on negative news for same ticker
5. **Market regime detection**: Adjust exits for trending vs choppy markets

---

For questions or issues, check logs in `data/autotrader.log` or open a GitHub issue.
