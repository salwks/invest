"""
Unit tests for rule engine.
Tests ENTRY and SKIP conditions with various market states.
"""

import pytest
from datetime import datetime, timezone

from app.rule_engine import RuleEngine
from app.schemas import EventCard, MarketState


@pytest.fixture
def rule_engine():
    """Create rule engine instance."""
    return RuleEngine()


@pytest.fixture
def good_event():
    """Create a high-quality news event."""
    return EventCard(
        event_id="test123",
        tickers=["AAPL"],
        headline="Apple beats Q4 earnings estimates by 15%",
        published_at=datetime.now(timezone.utc),
        category="earnings",
        sentiment=0.85,
        reliability=0.90,
        key_facts=["Beat estimates", "Strong iPhone sales"],
        session="regular",
        cluster_id="cluster123",
        source="Test"
    )


@pytest.fixture
def good_market():
    """Create favorable market conditions."""
    return MarketState(
        ticker="AAPL",
        ts=datetime.now(timezone.utc),
        mid=175.50,
        spread_bp=5,
        dP_1m=0.5,
        dP_5m=2.3,
        vol_ratio_1m=4.2,
        rsi_3=65.0,
        vwap_dev_bp=15,
        session="regular"
    )


def test_entry_signal_good_conditions(rule_engine, good_event, good_market):
    """Test that good conditions generate ENTRY signal."""
    signal = rule_engine.evaluate(good_event, good_market)

    assert signal.action == "ENTRY"
    assert signal.ticker == "AAPL"
    assert signal.event_id == "test123"
    assert len(signal.reasons) > 0
    assert len(signal.metrics) > 0


def test_skip_low_sentiment(rule_engine, good_event, good_market):
    """Test that low sentiment triggers SKIP."""
    bad_event = good_event.model_copy()
    bad_event.sentiment = 0.3  # Below threshold

    signal = rule_engine.evaluate(bad_event, good_market)

    assert signal.action == "SKIP"
    assert any("sentiment" in r.lower() for r in signal.reasons)


def test_skip_low_reliability(rule_engine, good_event, good_market):
    """Test that low reliability triggers SKIP."""
    bad_event = good_event.model_copy()
    bad_event.reliability = 0.5  # Below threshold

    signal = rule_engine.evaluate(bad_event, good_market)

    assert signal.action == "SKIP"
    assert any("reliability" in r.lower() for r in signal.reasons)


def test_skip_rumor_category(rule_engine, good_event, good_market):
    """Test that rumor category is skipped."""
    rumor_event = good_event.model_copy()
    rumor_event.category = "rumor"

    signal = rule_engine.evaluate(rumor_event, good_market)

    assert signal.action == "SKIP"
    assert any("rumor" in r.lower() for r in signal.reasons)


def test_skip_excessive_spike(rule_engine, good_event, good_market):
    """Test that excessive 1m spike triggers SKIP."""
    spiked_market = good_market.model_copy()
    spiked_market.dP_1m = 6.0  # Above threshold

    signal = rule_engine.evaluate(good_event, spiked_market)

    assert signal.action == "SKIP"
    assert any("spike" in r.lower() for r in signal.reasons)


def test_skip_wide_spread(rule_engine, good_event, good_market):
    """Test that wide spread triggers SKIP."""
    wide_spread_market = good_market.model_copy()
    wide_spread_market.spread_bp = 100  # Above threshold

    signal = rule_engine.evaluate(good_event, wide_spread_market)

    assert signal.action == "SKIP"
    assert any("spread" in r.lower() for r in signal.reasons)


def test_skip_low_volume(rule_engine, good_event, good_market):
    """Test that low volume triggers SKIP."""
    low_vol_market = good_market.model_copy()
    low_vol_market.vol_ratio_1m = 1.5  # Below threshold

    signal = rule_engine.evaluate(good_event, low_vol_market)

    assert signal.action == "SKIP"
    assert any("volume" in r.lower() for r in signal.reasons)


def test_skip_overbought_rsi(rule_engine, good_event, good_market):
    """Test that overbought RSI triggers SKIP."""
    overbought_market = good_market.model_copy()
    overbought_market.rsi_3 = 80  # Above threshold

    signal = rule_engine.evaluate(good_event, overbought_market)

    assert signal.action == "SKIP"
    assert any("rsi" in r.lower() for r in signal.reasons)


def test_skip_premarket_session(rule_engine, good_event, good_market):
    """Test that pre-market session is skipped."""
    premarket = good_market.model_copy()
    premarket.session = "pre"

    signal = rule_engine.evaluate(good_event, premarket)

    assert signal.action == "SKIP"
    assert any("session" in r.lower() for r in signal.reasons)


def test_skip_price_change_too_small(rule_engine, good_event, good_market):
    """Test that insufficient price movement triggers SKIP."""
    flat_market = good_market.model_copy()
    flat_market.dP_5m = 0.5  # Below minimum

    signal = rule_engine.evaluate(good_event, flat_market)

    assert signal.action == "SKIP"


def test_skip_price_change_too_large(rule_engine, good_event, good_market):
    """Test that excessive price movement triggers SKIP."""
    runaway_market = good_market.model_copy()
    runaway_market.dP_5m = 5.0  # Above maximum

    signal = rule_engine.evaluate(good_event, runaway_market)

    assert signal.action == "SKIP"


def test_metrics_populated(rule_engine, good_event, good_market):
    """Test that metrics dictionary is properly populated."""
    signal = rule_engine.evaluate(good_event, good_market)

    assert "sentiment" in signal.metrics
    assert "reliability" in signal.metrics
    assert "dP_5m" in signal.metrics
    assert "vol_ratio" in signal.metrics
    assert "spread_bp" in signal.metrics
    assert "rsi_3" in signal.metrics
