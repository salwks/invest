"""
Integration test for full pipeline in DRYRUN mode.
Tests end-to-end flow without placing real orders.
"""

import pytest
import os
from datetime import datetime, timezone

from app.main import AutoTrader
from app.schemas import RunRecord


@pytest.fixture
def setup_dryrun_env(monkeypatch):
    """Set up environment for DRYRUN testing."""
    monkeypatch.setenv("RUN_MODE", "DRYRUN")
    monkeypatch.setenv("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY", "test_key"))
    monkeypatch.setenv("ALPACA_API_KEY", "test_alpaca_key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test_alpaca_secret")
    monkeypatch.setenv("TICKER_WHITELIST", "AAPL,TSLA")
    monkeypatch.setenv("CYCLE_MINUTES", "5")
    monkeypatch.setenv("DB_PATH", "data/test_autotrader.db")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_pipeline_dryrun(setup_dryrun_env):
    """
    Test complete pipeline in DRYRUN mode.

    This test:
    1. Initializes AutoTrader
    2. Runs one complete cycle
    3. Verifies no errors occurred
    4. Checks that run record was created
    """
    trader = AutoTrader()

    # Run one cycle
    run_record = await trader.run_cycle()

    # Verify run completed
    assert run_record is not None
    assert isinstance(run_record, RunRecord)
    assert run_record.status in ["completed", "running"]
    assert run_record.mode == "DRYRUN"

    # Should have fetched some events (or 0 if no news in timeframe)
    assert run_record.events_fetched >= 0

    # Should not have critical errors
    assert run_record.status != "failed"


@pytest.mark.asyncio
async def test_trader_initialization(setup_dryrun_env):
    """Test that AutoTrader initializes all components."""
    trader = AutoTrader()

    assert trader.storage is not None
    assert trader.rss_fetcher is not None
    assert trader.llm_interpreter is not None
    assert trader.market_scanner is not None
    assert trader.rule_engine is not None
    assert trader.risk_guard is not None
    assert trader.broker is not None
    assert trader.notifier is not None


@pytest.mark.asyncio
async def test_since_time_calculation(setup_dryrun_env):
    """Test that since time is calculated correctly."""
    trader = AutoTrader()

    since_time = trader._get_since_time()

    assert since_time is not None
    assert isinstance(since_time, datetime)
    assert since_time < datetime.now(timezone.utc)


def test_storage_initialization(setup_dryrun_env):
    """Test that storage initializes database correctly."""
    from app.storage import Storage

    storage = Storage("data/test_autotrader.db")

    # Verify tables exist
    import sqlite3
    conn = sqlite3.connect("data/test_autotrader.db")
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]

    assert "events" in tables
    assert "signals" in tables
    assert "orders" in tables
    assert "positions" in tables
    assert "runs" in tables

    conn.close()
