"""
Schema validation tests to prevent regression bugs.
Tests that database schema matches code expectations.
"""

import sqlite3
import pytest
import tempfile
import os
from app.storage import Storage


@pytest.fixture
def storage():
    """Create temporary file storage for testing."""
    # Use temporary file instead of :memory: to persist across connections
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    storage = Storage(db_path=db_path)

    yield storage

    # Cleanup
    try:
        os.remove(db_path)
    except:
        pass


def test_events_table_has_processed_column(storage):
    """Test that events table has processed column."""
    with sqlite3.connect(storage.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(events)")
        columns = {row[1] for row in cursor.fetchall()}

    assert "processed" in columns, "events table should have processed column"


def test_events_processed_index_exists(storage):
    """Test that index on events.processed exists."""
    with sqlite3.connect(storage.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_events_processed'")
        result = cursor.fetchone()

    assert result is not None, "idx_events_processed index should exist"


def test_positions_table_has_current_price_column(storage):
    """Test that positions table has current_price column."""
    with sqlite3.connect(storage.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(positions)")
        columns = {row[1] for row in cursor.fetchall()}

    assert "current_price" in columns, "positions table should have current_price column"


def test_positions_table_has_partial_sold_column(storage):
    """Test that positions table has partial_sold column."""
    with sqlite3.connect(storage.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(positions)")
        columns = {row[1] for row in cursor.fetchall()}

    assert "partial_sold" in columns, "positions table should have partial_sold column"


def test_all_required_indexes_exist(storage):
    """Test that all required indexes exist."""
    expected_indexes = {
        "idx_events_published",
        "idx_events_cluster",
        "idx_events_processed",
        "idx_signals_event",
        "idx_orders_signal",
        "idx_positions_status",
        "idx_runs_started"
    }

    with sqlite3.connect(storage.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        actual_indexes = {row[0] for row in cursor.fetchall() if not row[0].startswith("sqlite_")}

    missing_indexes = expected_indexes - actual_indexes
    assert not missing_indexes, f"Missing indexes: {missing_indexes}"


def test_events_table_schema_complete(storage):
    """Test that events table has all required columns."""
    required_columns = {
        "event_id", "cluster_id", "headline", "category", "sentiment",
        "reliability", "published_at", "session", "tickers", "source",
        "url", "key_facts", "created_at", "processed"
    }

    with sqlite3.connect(storage.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(events)")
        actual_columns = {row[1] for row in cursor.fetchall()}

    missing_columns = required_columns - actual_columns
    assert not missing_columns, f"Missing columns in events table: {missing_columns}"


def test_positions_table_schema_complete(storage):
    """Test that positions table has all required columns."""
    required_columns = {
        "position_id", "ticker", "entry_price", "quantity", "entry_time",
        "exit_time", "exit_price", "event_id", "order_id", "stop_loss",
        "take_profit", "current_price", "partial_sold", "realized_pnl", "status"
    }

    with sqlite3.connect(storage.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(positions)")
        actual_columns = {row[1] for row in cursor.fetchall()}

    missing_columns = required_columns - actual_columns
    assert not missing_columns, f"Missing columns in positions table: {missing_columns}"


def test_migration_idempotency(storage):
    """Test that running migrations multiple times doesn't cause errors."""
    # Create a new storage instance (which will run migrations again)
    storage2 = Storage(db_path=storage.db_path)

    # Should not raise any errors
    assert storage2 is not None

    # Verify schema is still correct
    with sqlite3.connect(storage2.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(events)")
        columns = {row[1] for row in cursor.fetchall()}

    assert "processed" in columns
