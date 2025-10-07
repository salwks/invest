"""
Rule-based decision engine for trade signals.
Evaluates events and market conditions against configured rules.
"""

from typing import Optional
from app.schemas import EventCard, MarketState, PreSignal, ActionType
from app.config import get_rules
from app.utils import setup_logger, get_utc_now

logger = setup_logger(__name__)


class RuleEngine:
    """
    Evaluates trading opportunities based on rules.
    """

    def __init__(self):
        self.rules = get_rules()

    def evaluate(self, event: EventCard, market: MarketState) -> PreSignal:
        """
        Evaluate event and market state to generate trading signal.

        Args:
            event: News event
            market: Current market state

        Returns:
            PreSignal with ENTRY or SKIP decision
        """
        reasons = []
        metrics = {}

        # First check SKIP conditions (highest priority)
        skip_result = self._check_skip_conditions(event, market, reasons, metrics)
        if skip_result:
            return PreSignal(
                action=ActionType.SKIP,
                window_hint="N/A",
                metrics=metrics,
                reasons=reasons,
                event_id=event.event_id,
                ticker=market.ticker
            )

        # Then check ENTRY conditions
        entry_result = self._check_entry_conditions(event, market, reasons, metrics)
        if entry_result:
            return PreSignal(
                action=ActionType.ENTRY,
                window_hint="[1,5]m",
                metrics=metrics,
                reasons=reasons,
                event_id=event.event_id,
                ticker=market.ticker
            )

        # Default: SKIP
        reasons.append("Did not meet entry criteria")
        return PreSignal(
            action=ActionType.SKIP,
            window_hint="N/A",
            metrics=metrics,
            reasons=reasons,
            event_id=event.event_id,
            ticker=market.ticker
        )

    def _check_skip_conditions(
        self,
        event: EventCard,
        market: MarketState,
        reasons: list[str],
        metrics: dict
    ) -> bool:
        """
        Check SKIP conditions. Return True if should skip.
        """
        skip_rules = self.rules.skip

        # Check 0-1 minute spike
        spike_threshold = skip_rules.get("spike01_gt_pct", 5.0)
        if abs(market.dP_1m) > spike_threshold:
            reasons.append(f"Excessive 1m spike: {market.dP_1m:.2f}% (limit: {spike_threshold}%)")
            metrics["spike_1m"] = market.dP_1m
            return True

        # Check session restrictions
        disallowed_sessions = skip_rules.get("disallow_session", [])
        if market.session in disallowed_sessions:
            reasons.append(f"Session '{market.session}' is disallowed")
            metrics["session"] = market.session
            return True

        # Check category blocklist
        disallowed_categories = skip_rules.get("disallow_categories", [])
        if event.category in disallowed_categories:
            reasons.append(f"Category '{event.category}' is disallowed")
            metrics["category"] = event.category
            return True

        # Check minimum reliability
        min_reliability = skip_rules.get("min_reliability", 0.60)
        if event.reliability < min_reliability:
            reasons.append(f"Low reliability: {event.reliability:.2f} (min: {min_reliability})")
            metrics["reliability"] = event.reliability
            return True

        return False

    def _check_entry_conditions(
        self,
        event: EventCard,
        market: MarketState,
        reasons: list[str],
        metrics: dict
    ) -> bool:
        """
        Check ENTRY conditions. Return True if should enter.
        """
        entry_rules = self.rules.entry
        passed = True

        # Sentiment check
        min_sentiment = entry_rules.get("min_sentiment", 0.70)
        metrics["sentiment"] = event.sentiment
        if event.sentiment < min_sentiment:
            reasons.append(f"Sentiment too low: {event.sentiment:.2f} (min: {min_sentiment})")
            passed = False

        # Impact/reliability check
        min_impact = entry_rules.get("min_impact", 0.70)
        metrics["reliability"] = event.reliability
        if event.reliability < min_impact:
            reasons.append(f"Impact/reliability too low: {event.reliability:.2f} (min: {min_impact})")
            passed = False

        # 5-minute price change check
        dp5m_min = entry_rules.get("dp5m_min_pct", 1.0)
        dp5m_max = entry_rules.get("dp5m_max_pct", 4.0)
        metrics["dP_5m"] = market.dP_5m

        if market.dP_5m < dp5m_min:
            reasons.append(f"5m price change too small: {market.dP_5m:.2f}% (min: {dp5m_min}%)")
            passed = False
        elif market.dP_5m > dp5m_max:
            reasons.append(f"5m price change too large: {market.dP_5m:.2f}% (max: {dp5m_max}%)")
            passed = False

        # Volume ratio check
        min_vol_ratio = entry_rules.get("min_vol_ratio", 3.0)
        metrics["vol_ratio"] = market.vol_ratio_1m
        if market.vol_ratio_1m < min_vol_ratio:
            reasons.append(f"Volume ratio too low: {market.vol_ratio_1m:.2f}x (min: {min_vol_ratio}x)")
            passed = False

        # Spread check
        max_spread_bp = entry_rules.get("max_spread_bp", 50)
        metrics["spread_bp"] = market.spread_bp
        if market.spread_bp > max_spread_bp:
            reasons.append(f"Spread too wide: {market.spread_bp} bp (max: {max_spread_bp} bp)")
            passed = False

        # RSI check (avoid overbought)
        max_rsi = entry_rules.get("max_rsi3", 75)
        metrics["rsi_3"] = market.rsi_3
        if market.rsi_3 > max_rsi:
            reasons.append(f"RSI too high (overbought): {market.rsi_3:.1f} (max: {max_rsi})")
            passed = False

        # Category allowlist check (if configured)
        allowed_categories = entry_rules.get("allowed_categories", [])
        if allowed_categories and event.category not in allowed_categories:
            reasons.append(f"Category '{event.category}' not in allowlist")
            passed = False

        # If all checks passed, add positive reasons
        if passed:
            reasons.clear()  # Clear any warnings
            reasons.append(f"Strong positive sentiment: {event.sentiment:.2f}")
            reasons.append(f"Good price momentum: {market.dP_5m:.2f}% (5m)")
            reasons.append(f"High volume: {market.vol_ratio_1m:.1f}x average")
            reasons.append(f"Category: {event.category}")

        return passed


async def main():
    """Test rule engine."""
    from datetime import datetime, timezone

    # Create test event
    event = EventCard(
        event_id="test123",
        tickers=["AAPL"],
        headline="Apple announces record Q4 earnings",
        published_at=datetime.now(timezone.utc),
        category="earnings",
        sentiment=0.85,
        reliability=0.90,
        key_facts=["Beat estimates by 15%", "Strong iPhone sales"],
        session="regular",
        cluster_id="cluster123",
        source="Test"
    )

    # Create test market state
    market = MarketState(
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

    # Evaluate
    engine = RuleEngine()
    signal = engine.evaluate(event, market)

    print("\n=== Rule Engine Evaluation ===")
    print(f"Action: {signal.action}")
    print(f"Window: {signal.window_hint}")
    print(f"\nMetrics:")
    for key, value in signal.metrics.items():
        print(f"  {key}: {value}")
    print(f"\nReasons:")
    for reason in signal.reasons:
        print(f"  - {reason}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
