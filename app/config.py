"""
Configuration management for the automated trading system.
Loads settings from environment variables and YAML files.
"""

import os
from pathlib import Path
from typing import Literal
import yaml
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Anthropic API
    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-3-haiku-20240307", alias="ANTHROPIC_MODEL")

    # Alpaca Trading API
    alpaca_api_key: str = Field(..., alias="ALPACA_API_KEY")
    alpaca_secret_key: str = Field(..., alias="ALPACA_SECRET_KEY")
    alpaca_base_url: str = Field(
        default="https://paper-api.alpaca.markets",
        alias="ALPACA_BASE_URL"
    )
    alpaca_data_base_url: str = Field(
        default="https://data.alpaca.markets",
        alias="ALPACA_DATA_BASE_URL"
    )

    # Slack (optional)
    slack_webhook_url: str = Field(default="", alias="SLACK_WEBHOOK_URL")

    # Trading configuration
    run_mode: Literal["DRYRUN", "SEMI_AUTO", "FULL_AUTO"] = Field(
        default="DRYRUN",
        alias="RUN_MODE"
    )
    ticker_whitelist: str = Field(
        default="AAPL,TSLA,NVDA,MSFT,GOOGL,AMZN,META",
        alias="TICKER_WHITELIST"
    )
    cycle_minutes: int = Field(default=5, alias="CYCLE_MINUTES")

    # Database
    db_path: str = Field(default="data/autotrader.db", alias="DB_PATH")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str = Field(default="data/autotrader.log", alias="LOG_FILE")

    # Risk management
    initial_equity: float = Field(default=100000.0, alias="INITIAL_EQUITY")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @property
    def tickers(self) -> list[str]:
        """Parse ticker whitelist into list."""
        return [t.strip().upper() for t in self.ticker_whitelist.split(",") if t.strip()]

    @property
    def slack_enabled(self) -> bool:
        """Check if Slack notifications are enabled."""
        return bool(self.slack_webhook_url and self.slack_webhook_url.startswith("http"))


class RulesConfig:
    """Trading rules loaded from YAML configuration."""

    def __init__(self, config_path: str = "configs/rules.yaml"):
        self.config_path = Path(config_path)
        self._rules = self._load_rules()

    def _load_rules(self) -> dict:
        """Load rules from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Rules config not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            return yaml.safe_load(f)

    @property
    def entry(self) -> dict:
        """Entry rules."""
        return self._rules.get("entry", {})

    @property
    def skip(self) -> dict:
        """Skip rules."""
        return self._rules.get("skip", {})

    @property
    def risk(self) -> dict:
        """Risk management rules."""
        return self._rules.get("risk", {})

    @property
    def execution(self) -> dict:
        """Execution rules."""
        return self._rules.get("execution", {})

    @property
    def monitoring(self) -> dict:
        """Monitoring rules."""
        return self._rules.get("monitoring", {})

    def reload(self) -> None:
        """Reload rules from file."""
        self._rules = self._load_rules()


# Singleton instances
_settings: Settings | None = None
_rules: RulesConfig | None = None


def get_settings() -> Settings:
    """Get application settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def get_rules() -> RulesConfig:
    """Get rules configuration singleton."""
    global _rules
    if _rules is None:
        _rules = RulesConfig()
    return _rules


# RSS Feed sources
RSS_FEEDS = [
    {
        "name": "Yahoo Finance",
        "url": "https://finance.yahoo.com/news/rssindex",
        "delay_minutes": 3,
    },
    {
        "name": "Nasdaq News",
        "url": "https://www.nasdaq.com/feed/rssoutbound",
        "delay_minutes": 3,
    },
    {
        "name": "Seeking Alpha Market News",
        "url": "https://seekingalpha.com/feed.xml",
        "delay_minutes": 3,
    },
]


# Sector mapping (simplified)
SECTOR_MAP = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "GOOGL": "Technology",
    "META": "Technology",
    "NVDA": "Technology",
    "TSLA": "Automotive",
    "AMZN": "Consumer",
}
