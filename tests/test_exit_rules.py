"""
Test exit logic for position management.
Tests all exit scenarios: profit taking, trailing stops, time exits, and stop losses.
"""

import pytest
from datetime import datetime, timedelta, timezone
from app.trade_manager import TradeManager
from app.schemas import Position


@pytest.fixture
def trade_manager():
    """Create TradeManager instance for testing."""
    return TradeManager()


@pytest.fixture
def base_position():
    """Create base position for testing."""
    return Position(
        ticker="TSLA",
        entry_price=100.0,
        quantity=10,
        entry_time=datetime.now(timezone.utc) - timedelta(minutes=30),
        event_id="test123",
        order_id="order123",
        stop_loss=96.0,
        take_profit=110.0,
        current_price=100.0,
        partial_sold=False
    )


def test_hold_no_conditions_met(trade_manager, base_position):
    """Test HOLD action when no exit conditions are met."""
    # +2% profit, not enough for any trigger
    result = trade_manager.manage_exit(base_position, 102.0)

    assert result["action"] == "HOLD"
    assert "In position" in result["reason"]
    assert result["sell_qty"] == 0
    assert result["new_peak"] == 102.0  # Peak updated


def test_hard_stop_loss_trigger(trade_manager, base_position):
    """Test HARD_STOP at -4% loss triggers immediate full sell."""
    # -4% loss
    result = trade_manager.manage_exit(base_position, 96.0)

    assert result["action"] == "FULL_SELL"
    assert result["reason"] == "HARD_STOP"
    assert result["sell_qty"] == 10
    assert result["sell_price"] == 96.0


def test_partial_profit_at_8pct(trade_manager, base_position):
    """Test partial profit taking at +8% gain (40% of position)."""
    # +8% profit
    result = trade_manager.manage_exit(base_position, 108.0)

    assert result["action"] == "PARTIAL_SELL"
    assert result["reason"] == "LVL1_PROFIT"
    assert result["sell_qty"] == 4  # 40% of 10 shares
    assert result["sell_price"] == 108.0
    assert result["new_peak"] == 108.0


def test_partial_profit_only_once(trade_manager, base_position):
    """Test that partial profit taking only happens once."""
    # Set partial_sold flag
    base_position.partial_sold = True

    # +10% profit, but already partially sold
    result = trade_manager.manage_exit(base_position, 110.0)

    # Should NOT trigger partial sell again
    assert result["action"] != "PARTIAL_SELL"


def test_trailing_stop_from_peak_100pct_gain(trade_manager, base_position):
    """Test trailing stop after +100% gain, then -5% drop from peak."""
    # Position peaked at +100% ($200)
    base_position.current_price = 200.0
    # Already took partial profit earlier
    base_position.partial_sold = True

    # Now at $190 = -5% from peak
    result = trade_manager.manage_exit(base_position, 190.0)

    assert result["action"] == "FULL_SELL"
    assert result["reason"] == "TRAILING_STOP"
    assert result["sell_qty"] == 10
    assert result["sell_price"] == 190.0


def test_trailing_stop_only_in_profit(trade_manager, base_position):
    """Test that trailing stop only activates when in profit."""
    # Price went from $100 to $95 to $90
    # Even though this is -5% drop, should trigger hard stop instead
    # because never went into profit
    base_position.current_price = 95.0

    result = trade_manager.manage_exit(base_position, 90.0)

    # Should hit hard stop, not trailing stop
    assert result["reason"] == "HARD_STOP"


def test_time_based_exit_after_60min(trade_manager, base_position):
    """Test time-based exit after 60 minutes holding."""
    # Set entry time to 65 minutes ago
    base_position.entry_time = datetime.now(timezone.utc) - timedelta(minutes=65)

    # Small profit +3%
    result = trade_manager.manage_exit(base_position, 103.0)

    assert result["action"] == "FULL_SELL"
    assert result["reason"] == "TIME_LIMIT"
    assert result["sell_qty"] == 10
    assert result["sell_price"] == 103.0


def test_time_exit_not_before_60min(trade_manager, base_position):
    """Test that time exit does not trigger before 60 minutes."""
    # 55 minutes holding
    base_position.entry_time = datetime.now(timezone.utc) - timedelta(minutes=55)

    result = trade_manager.manage_exit(base_position, 103.0)

    # Should HOLD, not time exit yet
    assert result["action"] == "HOLD"
    assert result["reason"] != "TIME_LIMIT"


def test_priority_hard_stop_over_time(trade_manager, base_position):
    """Test that HARD_STOP takes priority over TIME_LIMIT."""
    # 70 minutes holding (exceeds time limit)
    base_position.entry_time = datetime.now(timezone.utc) - timedelta(minutes=70)

    # But also at -4% (hard stop)
    result = trade_manager.manage_exit(base_position, 96.0)

    # Should trigger HARD_STOP, not TIME_LIMIT
    assert result["reason"] == "HARD_STOP"


def test_priority_profit_over_trailing(trade_manager, base_position):
    """Test partial profit takes priority over trailing stop."""
    # At +8% for first time
    base_position.partial_sold = False

    result = trade_manager.manage_exit(base_position, 108.0)

    # Should take partial profit, not trailing stop
    assert result["reason"] == "LVL1_PROFIT"


def test_peak_price_tracking(trade_manager, base_position):
    """Test that peak price is correctly tracked and returned."""
    # Starting peak at $100
    base_position.current_price = 100.0

    # Price moves to $120
    result = trade_manager.manage_exit(base_position, 120.0)

    assert result["new_peak"] == 120.0

    # Price drops to $115 (still above old peak)
    base_position.current_price = 120.0
    result = trade_manager.manage_exit(base_position, 115.0)

    # Peak should stay at 120
    assert result["new_peak"] == 120.0


def test_large_gain_scenario(trade_manager, base_position):
    """
    Test scenario from user requirement:
    +100% gain, then -5% from peak triggers trailing stop.
    """
    # Position peaked at $200 (+100%)
    base_position.current_price = 200.0
    base_position.partial_sold = True  # Already took partial profit earlier

    # Price drops to $190 (-5% from peak)
    result = trade_manager.manage_exit(base_position, 190.0)

    assert result["action"] == "FULL_SELL"
    assert result["reason"] == "TRAILING_STOP"
    assert result["sell_price"] == 190.0

    # Verify P&L would be +90% ($90 profit per share)
    pnl_pct = ((result["sell_price"] - base_position.entry_price) / base_position.entry_price) * 100
    assert pnl_pct == pytest.approx(90.0, rel=0.01)


def test_edge_case_exactly_8pct(trade_manager, base_position):
    """Test edge case: exactly +8.0% profit."""
    result = trade_manager.manage_exit(base_position, 108.0)

    assert result["action"] == "PARTIAL_SELL"
    assert result["reason"] == "LVL1_PROFIT"


def test_edge_case_exactly_4pct_loss(trade_manager, base_position):
    """Test edge case: exactly -4.0% loss."""
    result = trade_manager.manage_exit(base_position, 96.0)

    assert result["action"] == "FULL_SELL"
    assert result["reason"] == "HARD_STOP"


def test_edge_case_exactly_60min(trade_manager, base_position):
    """Test edge case: exactly 60 minutes holding."""
    base_position.entry_time = datetime.now(timezone.utc) - timedelta(minutes=60)

    result = trade_manager.manage_exit(base_position, 103.0)

    assert result["action"] == "FULL_SELL"
    assert result["reason"] == "TIME_LIMIT"


def test_quantity_calculation_partial_sell(trade_manager, base_position):
    """Test that partial sell quantity is calculated correctly (40%)."""
    # Different position sizes
    test_cases = [
        (10, 4),   # 10 shares -> 4 shares (40%)
        (100, 40), # 100 shares -> 40 shares (40%)
        (7, 2),    # 7 shares -> 2 shares (40% = 2.8, rounded down)
    ]

    for quantity, expected_sell in test_cases:
        base_position.quantity = quantity
        base_position.partial_sold = False

        result = trade_manager.manage_exit(base_position, 108.0)

        assert result["sell_qty"] == expected_sell


@pytest.mark.skip(reason="System only supports long positions (buy on news)")
def test_negative_quantity_handling(trade_manager, base_position):
    """Test that negative quantities (short positions) are handled correctly."""
    # Note: This system only supports long positions (momentum trading on positive news)
    # Short positions are not supported in the current implementation
    # Short position: -10 shares
    base_position.quantity = -10

    # Price moved against us (-4% for short = +4% price move)
    result = trade_manager.manage_exit(base_position, 104.0)

    # Should still return absolute quantity
    assert result["sell_qty"] == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
