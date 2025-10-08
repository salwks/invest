"""
Storage layer for the automated trading system.
Handles SQLite database operations and Parquet logging.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import pandas as pd

from app.schemas import (
    EventCard, MarketState, PreSignal, ApprovedSignal,
    OrderRecord, Position, RunRecord
)
from app.utils import get_utc_now, setup_logger

logger = setup_logger(__name__)


class Storage:
    """
    Storage manager for SQLite database and Parquet logs.
    """

    def __init__(self, db_path: str = "data/autotrader.db"):
        self.db_path = db_path
        self.data_dir = Path(db_path).parent
        self._ensure_directories()
        self._init_database()

    def _ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "events").mkdir(exist_ok=True)
        (self.data_dir / "market").mkdir(exist_ok=True)
        (self.data_dir / "signals").mkdir(exist_ok=True)

    def _init_database(self) -> None:
        """Initialize SQLite database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
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
                    created_at TEXT NOT NULL
                )
            """)

            # Signals table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signals (
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
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (event_id) REFERENCES events (event_id)
                )
            """)

            # Orders table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    signal_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    order_type TEXT NOT NULL,
                    limit_price REAL,
                    stop_price REAL,
                    status TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    filled_at TEXT,
                    filled_avg_price REAL,
                    filled_qty INTEGER,
                    error_message TEXT,
                    FOREIGN KEY (signal_id) REFERENCES signals (signal_id)
                )
            """)

            # Positions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    position_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                    realized_pnl REAL,
                    status TEXT NOT NULL DEFAULT 'open',
                    FOREIGN KEY (event_id) REFERENCES events (event_id),
                    FOREIGN KEY (order_id) REFERENCES orders (order_id)
                )
            """)

            # Runs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    events_fetched INTEGER DEFAULT 0,
                    signals_generated INTEGER DEFAULT 0,
                    orders_placed INTEGER DEFAULT 0,
                    errors TEXT
                )
            """)

            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_published ON events (published_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_cluster ON events (cluster_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_event ON signals (event_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_signal ON orders (signal_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_status ON positions (status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_started ON runs (started_at)")

            conn.commit()

        logger.info(f"Database initialized: {self.db_path}")

    def save_event(self, event: EventCard) -> None:
        """Save event to database with processed=0 (unprocessed)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO events
                (event_id, cluster_id, headline, category, sentiment, reliability,
                 published_at, session, tickers, source, url, key_facts, created_at, processed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                event.event_id,
                event.cluster_id,
                event.headline,
                event.category,
                event.sentiment,
                event.reliability,
                event.published_at.isoformat(),
                event.session,
                json.dumps(event.tickers),
                event.source,
                event.url,
                json.dumps(event.key_facts),
                get_utc_now().isoformat()
            ))
            conn.commit()

    def get_unprocessed_events(self, limit: int = 50) -> list[EventCard]:
        """Get unprocessed events from database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT event_id, cluster_id, headline, category, sentiment, reliability,
                       published_at, session, tickers, source, url, key_facts
                FROM events
                WHERE processed = 0
                ORDER BY published_at DESC
                LIMIT ?
            """, (limit,))

            events = []
            for row in cursor.fetchall():
                events.append(EventCard(
                    event_id=row[0],
                    cluster_id=row[1],
                    headline=row[2],
                    category=row[3],
                    sentiment=row[4],
                    reliability=row[5],
                    published_at=datetime.fromisoformat(row[6]),
                    session=row[7],
                    tickers=json.loads(row[8]),
                    source=row[9],
                    url=row[10],
                    key_facts=json.loads(row[11])
                ))
            return events

    def mark_event_processed(self, event_id: str) -> None:
        """Mark event as processed."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE events
                SET processed = 1
                WHERE event_id = ?
            """, (event_id,))
            conn.commit()
            logger.debug(f"Marked event {event_id[:8]} as processed")

    def save_signal(self, pre_signal: PreSignal, approved: ApprovedSignal) -> str:
        """Save signal to database and return signal_id."""
        signal_id = f"{pre_signal.event_id}_{pre_signal.ticker}_{int(pre_signal.timestamp.timestamp())}"

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO signals
                (signal_id, event_id, ticker, action, approved, size_usd,
                 entry_price, stop_bp, take_profit_bp, reasons, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal_id,
                pre_signal.event_id,
                pre_signal.ticker,
                pre_signal.action,
                1 if approved.approved else 0,
                approved.size_final_usd,
                approved.entry_price_target,
                approved.hard_stop_bp,
                approved.take_profit_bp,
                json.dumps(pre_signal.reasons),
                json.dumps(approved.notes),
                get_utc_now().isoformat()
            ))
            conn.commit()

        return signal_id

    def save_order(self, order: OrderRecord) -> None:
        """Save order to database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO orders
                (order_id, signal_id, event_id, ticker, side, quantity, order_type,
                 limit_price, stop_price, status, submitted_at, filled_at,
                 filled_avg_price, filled_qty, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order.order_id,
                order.signal_id,
                order.event_id,
                order.ticker,
                order.side,
                order.quantity,
                order.order_type,
                order.limit_price,
                order.stop_price,
                order.status,
                order.submitted_at.isoformat(),
                order.filled_at.isoformat() if order.filled_at else None,
                order.filled_avg_price,
                order.filled_qty,
                order.error_message
            ))
            conn.commit()

    def save_position(self, position: Position) -> None:
        """Save position to database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO positions
                (ticker, entry_price, quantity, entry_time, event_id, order_id,
                 stop_loss, take_profit, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')
            """, (
                position.ticker,
                position.entry_price,
                position.quantity,
                position.entry_time.isoformat(),
                position.event_id,
                position.order_id,
                position.stop_loss,
                position.take_profit
            ))
            conn.commit()

    def create_run(self, run: RunRecord) -> None:
        """Create new run record."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO runs
                (run_id, started_at, status, mode)
                VALUES (?, ?, ?, ?)
            """, (
                run.run_id,
                run.started_at.isoformat(),
                run.status,
                run.mode
            ))
            conn.commit()

    def update_run(self, run: RunRecord) -> None:
        """Update existing run record."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE runs
                SET completed_at = ?, status = ?, events_fetched = ?,
                    signals_generated = ?, orders_placed = ?, errors = ?
                WHERE run_id = ?
            """, (
                run.completed_at.isoformat() if run.completed_at else None,
                run.status,
                run.events_fetched,
                run.signals_generated,
                run.orders_placed,
                json.dumps(run.errors),
                run.run_id
            ))
            conn.commit()

    def get_last_run_time(self) -> Optional[datetime]:
        """Get timestamp of last completed run."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT started_at FROM runs
                WHERE status = 'completed'
                ORDER BY started_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()

            if row:
                return datetime.fromisoformat(row[0])
            return None

    def get_open_positions(self) -> list[Position]:
        """Get all open positions."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ticker, entry_price, quantity, entry_time, event_id,
                       order_id, stop_loss, take_profit
                FROM positions
                WHERE status = 'open'
            """)

            positions = []
            for row in cursor.fetchall():
                positions.append(Position(
                    ticker=row[0],
                    entry_price=row[1],
                    quantity=row[2],
                    entry_time=datetime.fromisoformat(row[3]),
                    event_id=row[4],
                    order_id=row[5],
                    stop_loss=row[6],
                    take_profit=row[7]
                ))

            return positions

    def event_exists(self, cluster_id: str) -> bool:
        """Check if event with cluster_id already exists."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM events WHERE cluster_id = ?",
                (cluster_id,)
            )
            count = cursor.fetchone()[0]
            return count > 0

    def log_to_parquet(self, data: list[dict], log_type: str) -> None:
        """
        Log data to Parquet file (partitioned by date).

        Args:
            data: List of dictionaries to log
            log_type: Type of log ('events', 'market', 'signals')
        """
        if not data:
            return

        df = pd.DataFrame(data)
        today = get_utc_now().strftime("%Y-%m-%d")

        output_dir = self.data_dir / log_type / f"date={today}"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = get_utc_now().strftime("%H%M%S")
        output_file = output_dir / f"{log_type}_{timestamp}.parquet"

        df.to_parquet(output_file, index=False)
        logger.debug(f"Logged {len(data)} records to {output_file}")
