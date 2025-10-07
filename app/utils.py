"""
Utility functions for the automated trading system.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any
import pytz


def get_utc_now() -> datetime:
    """Get current UTC time with timezone info."""
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC timezone."""
    if dt.tzinfo is None:
        # Assume naive datetimes are UTC
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def generate_event_id(source: str, headline: str, published_at: datetime) -> str:
    """
    Generate unique event ID from source and headline.

    Args:
        source: RSS feed source
        headline: News headline
        published_at: Publication timestamp

    Returns:
        Unique event ID (SHA-256 hash)
    """
    content = f"{source}|{headline}|{published_at.isoformat()}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def generate_cluster_id(source: str, headline: str) -> str:
    """
    Generate cluster ID for deduplication.

    Args:
        source: RSS feed source
        headline: News headline

    Returns:
        Cluster ID (SHA-1 hash)
    """
    content = f"{source}|{headline.lower().strip()}"
    return hashlib.sha1(content.encode()).hexdigest()[:12]


def basis_points_to_pct(bp: int) -> float:
    """Convert basis points to percentage."""
    return bp / 100.0


def pct_to_basis_points(pct: float) -> int:
    """Convert percentage to basis points."""
    return int(pct * 100)


def calculate_spread_bp(bid: float, ask: float) -> int:
    """
    Calculate bid-ask spread in basis points.

    Args:
        bid: Bid price
        ask: Ask price

    Returns:
        Spread in basis points
    """
    if bid <= 0 or ask <= 0:
        return 999999  # Invalid spread

    mid = (bid + ask) / 2
    spread_pct = ((ask - bid) / mid) * 100
    return pct_to_basis_points(spread_pct)


def calculate_price_change_pct(old_price: float, new_price: float) -> float:
    """
    Calculate percentage price change.

    Args:
        old_price: Old price
        new_price: New price

    Returns:
        Percentage change
    """
    if old_price <= 0:
        return 0.0
    return ((new_price - old_price) / old_price) * 100


def get_market_session(dt: datetime) -> str:
    """
    Determine market session based on time.

    Args:
        dt: Datetime (will be converted to US/Eastern)

    Returns:
        Session type: 'pre', 'regular', or 'after'
    """
    eastern = pytz.timezone('US/Eastern')
    et_time = dt.astimezone(eastern)
    hour = et_time.hour
    minute = et_time.minute

    # Pre-market: 4:00 AM - 9:30 AM ET
    if (hour == 4 and minute >= 0) or (4 < hour < 9) or (hour == 9 and minute < 30):
        return "pre"

    # Regular: 9:30 AM - 4:00 PM ET
    if (hour == 9 and minute >= 30) or (9 < hour < 16):
        return "regular"

    # After-hours: 4:00 PM - 8:00 PM ET
    if (hour == 16 and minute >= 0) or (16 < hour < 20):
        return "after"

    # Outside trading hours
    return "after"


def setup_logger(name: str, log_file: str = None, level: str = "INFO") -> logging.Logger:
    """
    Set up logger with console and file handlers.

    Args:
        name: Logger name
        log_file: Optional log file path
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to maximum length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers, returning default if denominator is zero."""
    if denominator == 0:
        return default
    return numerator / denominator


def round_to_tick(price: float, tick_size: float = 0.01) -> float:
    """Round price to nearest tick size."""
    return round(price / tick_size) * tick_size


def validate_ticker(ticker: str) -> bool:
    """Validate ticker symbol format."""
    if not ticker:
        return False
    # Basic validation: 1-5 uppercase letters
    return ticker.isupper() and 1 <= len(ticker) <= 5 and ticker.isalpha()


def format_money(amount: float) -> str:
    """Format amount as money string."""
    return f"${amount:,.2f}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """Format value as percentage string."""
    return f"{value:.{decimals}f}%"


def extract_tickers_from_text(text: str, whitelist: list[str]) -> list[str]:
    """
    Extract ticker symbols from text based on whitelist.

    Args:
        text: Text to search
        whitelist: List of valid ticker symbols

    Returns:
        List of found tickers (deduplicated)
    """
    text_upper = text.upper()
    found = []

    for ticker in whitelist:
        if ticker in text_upper:
            found.append(ticker)

    return list(set(found))  # Deduplicate


class ColoredFormatter(logging.Formatter):
    """Colored log formatter for console output."""

    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
    }
    RESET = '\033[0m'

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)
