"""
Trade manager for position exit logic.
Handles partial profit taking, trailing stops, and time-based exits.
"""

from datetime import datetime, timedelta
from typing import Dict, Optional
from app.schemas import Position
from app.config import get_rules
from app.utils import setup_logger, get_utc_now

logger = setup_logger(__name__)


class TradeManager:
    """
    Manages open positions and determines exit timing.
    """

    def __init__(self):
        self.rules = get_rules()

    def manage_exit(
        self,
        position: Position,
        market_price: float,
        now: Optional[datetime] = None
    ) -> Dict:
        """
        Evaluate exit conditions for an open position.

        Args:
            position: Current position
            market_price: Current market price
            now: Current time (UTC), defaults to now

        Returns:
            {
                "action": "HOLD" | "PARTIAL_SELL" | "FULL_SELL",
                "reason": str,
                "sell_qty": int,
                "sell_price": float,
                "new_peak": float
            }
        """
        if now is None:
            now = get_utc_now()

        exit_rules = self.rules.exit

        # Update peak price
        current_peak = position.current_price or position.entry_price
        new_peak = max(current_peak, market_price)

        # Calculate metrics
        entry_price = position.entry_price
        pnl_pct = ((market_price - entry_price) / entry_price) * 100
        hold_time = (now - position.entry_time).total_seconds() / 60  # minutes

        # Get position quantity (considering partial sales)
        current_qty = position.quantity

        # 1. Check HARD STOP LOSS (highest priority)
        hard_stop_pct = exit_rules.get("hard_stop_pct", 4.0)
        if pnl_pct <= -hard_stop_pct:
            logger.warning(f"[EXIT] {position.ticker} {pnl_pct:.2f}% → HARD_STOP (-{hard_stop_pct}%) → FULL_SELL @{market_price:.2f}")
            return {
                "action": "FULL_SELL",
                "reason": "HARD_STOP",
                "sell_qty": abs(current_qty),
                "sell_price": market_price,
                "new_peak": new_peak
            }

        # 2. Check PARTIAL PROFIT TAKING (1st level)
        take_profit_lvl1_pct = exit_rules.get("take_profit_lvl1_pct", 8.0)
        take_profit_lvl1_part = exit_rules.get("take_profit_lvl1_part", 0.4)

        # Check if already partially sold
        if pnl_pct >= take_profit_lvl1_pct and current_qty > 0 and not position.partial_sold:
            # First time hitting this level - calculate partial sale quantity
            partial_qty = int(current_qty * take_profit_lvl1_part)
            if partial_qty > 0:
                logger.info(f"[EXIT] {position.ticker} +{pnl_pct:.1f}% → LVL1_PROFIT (+{take_profit_lvl1_pct}%) → PARTIAL_SELL {partial_qty} @{market_price:.2f}")
                return {
                    "action": "PARTIAL_SELL",
                    "reason": "LVL1_PROFIT",
                    "sell_qty": partial_qty,
                    "sell_price": market_price,
                    "new_peak": new_peak
                }

        # 3. Check TRAILING STOP (from peak)
        trailing_stop_pct = exit_rules.get("trailing_stop_pct", 5.0)
        if new_peak > entry_price:  # Only trail if in profit
            trail_trigger = new_peak * (1 - trailing_stop_pct / 100)
            if market_price <= trail_trigger:
                peak_drop_pct = ((market_price - new_peak) / new_peak) * 100
                logger.info(f"[EXIT] {position.ticker} +{pnl_pct:.1f}% → TRAIL_TRIGGER ({peak_drop_pct:.1f}% from peak ${new_peak:.2f}) → FULL_SELL @{market_price:.2f}")
                return {
                    "action": "FULL_SELL",
                    "reason": "TRAILING_STOP",
                    "sell_qty": abs(current_qty),
                    "sell_price": market_price,
                    "new_peak": new_peak
                }

        # 4. Check TIME EXIT
        hold_minutes = exit_rules.get("hold_minutes", 60)
        if hold_time >= hold_minutes:
            logger.info(f"[EXIT] {position.ticker} +{pnl_pct:.1f}% → TIME_LIMIT ({hold_time:.0f}m >= {hold_minutes}m) → FULL_SELL @{market_price:.2f}")
            return {
                "action": "FULL_SELL",
                "reason": "TIME_LIMIT",
                "sell_qty": abs(current_qty),
                "sell_price": market_price,
                "new_peak": new_peak
            }

        # 5. HOLD - no exit conditions met
        return {
            "action": "HOLD",
            "reason": f"In position: +{pnl_pct:.1f}%, {hold_time:.0f}m",
            "sell_qty": 0,
            "sell_price": 0.0,
            "new_peak": new_peak
        }


async def main():
    """Test trade manager."""
    from app.schemas import Position
    from datetime import timezone

    # Test case 1: Profit taking
    position = Position(
        ticker="TSLA",
        entry_price=100.0,
        quantity=10,
        entry_time=datetime.now(timezone.utc) - timedelta(minutes=30),
        event_id="test123",
        order_id="order123",
        stop_loss=96.0,
        take_profit=110.0,
        current_price=100.0
    )

    manager = TradeManager()

    print("\n=== Test 1: +8% Profit Taking ===")
    result = manager.manage_exit(position, 108.0)
    print(f"Action: {result['action']}")
    print(f"Reason: {result['reason']}")
    print(f"Sell Qty: {result['sell_qty']}")

    print("\n=== Test 2: +100% then -5% trailing ===")
    position.current_price = 200.0  # Peak at 200
    result = manager.manage_exit(position, 190.0)  # -5% from peak
    print(f"Action: {result['action']}")
    print(f"Reason: {result['reason']}")

    print("\n=== Test 3: -4% Stop Loss ===")
    result = manager.manage_exit(position, 96.0)
    print(f"Action: {result['action']}")
    print(f"Reason: {result['reason']}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
