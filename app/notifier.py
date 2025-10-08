"""
Notification module for Slack alerts.
Sends concise trading summaries and error alerts.
"""

import json
from typing import Optional
import httpx

from app.schemas import EventCard, PreSignal, ApprovedSignal, OrderRecord, Position
from app.config import get_settings
from app.utils import setup_logger, format_money, format_percentage, truncate_text

logger = setup_logger(__name__)


class Notifier:
    """
    Sends notifications via Slack webhook.
    """

    def __init__(self):
        self.settings = get_settings()
        self.enabled = self.settings.slack_enabled

    async def notify_signal(
        self,
        event: EventCard,
        pre_signal: PreSignal,
        approved: ApprovedSignal,
        order: Optional[OrderRecord] = None
    ) -> None:
        """
        Send notification about a trading signal.

        Args:
            event: News event
            pre_signal: Initial signal from rule engine
            approved: Approved signal from risk guard
            order: Order record (if executed)
        """
        if not self.enabled:
            logger.debug("Slack notifications disabled")
            return

        # Build message
        if pre_signal.action == "SKIP":
            message = self._build_skip_message(event, pre_signal)
        elif approved.approved:
            message = self._build_entry_message(event, pre_signal, approved, order)
        else:
            message = self._build_rejected_message(event, pre_signal, approved)

        # Send to Slack
        await self._send_slack(message)

    async def notify_exit(
        self,
        position: Position,
        exit_price: float,
        quantity: int,
        reason: str,
        partial: bool = False
    ) -> None:
        """
        Send notification about position exit.

        Args:
            position: Position being closed
            exit_price: Exit price
            quantity: Quantity sold
            reason: Exit reason (HARD_STOP, LVL1_PROFIT, TRAILING_STOP, TIME_LIMIT)
            partial: Whether this is a partial exit
        """
        if not self.enabled:
            logger.debug("Slack notifications disabled")
            return

        # Calculate P&L
        pnl_per_share = exit_price - position.entry_price
        total_pnl = pnl_per_share * quantity
        pnl_pct = (pnl_per_share / position.entry_price) * 100

        # Determine emoji based on reason and P&L
        if reason == "HARD_STOP":
            emoji = ":red_circle:"
            reason_text = "STOP LOSS"
        elif reason == "LVL1_PROFIT":
            emoji = ":large_green_circle:"
            reason_text = "PROFIT TAKING (Partial)"
        elif reason == "TRAILING_STOP":
            emoji = ":green_circle:"
            reason_text = "TRAILING STOP"
        elif reason == "TIME_LIMIT":
            emoji = ":clock3:"
            reason_text = "TIME EXIT"
        else:
            emoji = ":white_circle:"
            reason_text = reason

        exit_type = "PARTIAL EXIT" if partial else "FULL EXIT"
        text = f"{emoji} *{exit_type}* - {position.ticker} ({reason_text})"

        # Build details
        details = [
            f"*{exit_type}: {position.ticker}*",
            f"*Reason:* {reason_text}",
            "",
            "*Position Details:*",
            f"• Entry Price: ${position.entry_price:.2f}",
            f"• Exit Price: ${exit_price:.2f}",
            f"• Quantity: {quantity} shares",
            f"• P&L: {format_money(total_pnl)} ({format_percentage(pnl_pct / 100)})",
            ""
        ]

        if partial:
            remaining = position.quantity - quantity
            details.append(f"• Remaining: {remaining} shares")
        else:
            details.append(f"• Position CLOSED")

        message = {
            "text": text,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join(details)
                    }
                }
            ]
        }

        await self._send_slack(message)

    async def notify_error(self, error_type: str, details: str) -> None:
        """Send error notification."""
        if not self.enabled:
            return

        message = {
            "text": f":warning: *{error_type}*",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f":warning: *{error_type}*\n```{details}```"
                    }
                }
            ]
        }

        await self._send_slack(message)

    async def notify_run_complete(
        self,
        run_id: str,
        events_count: int,
        signals_count: int,
        orders_count: int,
        errors: list[str]
    ) -> None:
        """Send run completion summary."""
        if not self.enabled:
            return

        status_emoji = ":white_check_mark:" if not errors else ":warning:"
        text = f"{status_emoji} *Run {run_id[:8]} completed*"

        fields = [
            f"Events fetched: {events_count}",
            f"Signals generated: {signals_count}",
            f"Orders placed: {orders_count}"
        ]

        if errors:
            fields.append(f"Errors: {len(errors)}")

        message = {
            "text": text,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{text}\n" + "\n".join(f"• {f}" for f in fields)
                    }
                }
            ]
        }

        await self._send_slack(message)

    def _build_skip_message(self, event: EventCard, signal: PreSignal) -> dict:
        """Build message for SKIP signal."""
        headline = truncate_text(event.headline, 80)

        text = f":no_entry: *SKIP* - {event.tickers[0] if event.tickers else 'Unknown'}"

        details = [
            f"*Headline:* {headline}",
            f"*Category:* {event.category} | *Sentiment:* {event.sentiment:.2f} | *Reliability:* {event.reliability:.2f}",
            f"*Reason:* {signal.reasons[0] if signal.reasons else 'N/A'}"
        ]

        return {
            "text": text,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join(details)
                    }
                }
            ]
        }

    def _build_entry_message(
        self,
        event: EventCard,
        signal: PreSignal,
        approved: ApprovedSignal,
        order: Optional[OrderRecord]
    ) -> dict:
        """Build message for ENTRY signal."""
        headline = truncate_text(event.headline, 80)
        ticker = approved.ticker

        # Determine status
        if not order:
            status_emoji = ":rocket:"
            status_text = "ENTRY SIGNAL"
        elif order.status == "filled":
            status_emoji = ":white_check_mark:"
            status_text = "FILLED"
        elif order.status == "submitted":
            status_emoji = ":hourglass:"
            status_text = "SUBMITTED"
        else:
            status_emoji = ":x:"
            status_text = f"{order.status.upper()}"

        text = f"{status_emoji} *{status_text}* - {ticker}"

        # Event info
        details = [
            f"*{headline}*",
            "",
            f"*Category:* {event.category}",
            f"*Sentiment:* {event.sentiment:.2f} | *Reliability:* {event.reliability:.2f}",
            "",
            "*Market Metrics:*"
        ]

        # Add metrics
        for key, value in signal.metrics.items():
            if isinstance(value, float):
                details.append(f"• {key}: {value:.2f}")
            else:
                details.append(f"• {key}: {value}")

        details.append("")
        details.append("*Trade Details:*")
        details.append(f"• Size: {approved.shares} shares @ ${approved.entry_price_target:.2f} ≈ {format_money(approved.size_final_usd)}")
        details.append(f"• Stop: {approved.hard_stop_bp} bp | TP: {approved.take_profit_bp} bp")

        if order and order.status == "filled":
            details.append(f"• Fill Price: ${order.filled_avg_price:.2f}")

        # Add reasons
        if signal.reasons:
            details.append("")
            details.append("*Reasons:*")
            for reason in signal.reasons[:3]:  # Top 3 reasons
                details.append(f"• {reason}")

        return {
            "text": text,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join(details)
                    }
                }
            ]
        }

    def _build_rejected_message(
        self,
        event: EventCard,
        signal: PreSignal,
        approved: ApprovedSignal
    ) -> dict:
        """Build message for rejected signal."""
        headline = truncate_text(event.headline, 80)
        ticker = signal.ticker

        text = f":x: *REJECTED* - {ticker}"

        details = [
            f"*{headline}*",
            "",
            f"*Category:* {event.category} | *Sentiment:* {event.sentiment:.2f}",
            "",
            "*Rejection Reasons:*"
        ]

        for note in approved.notes[:3]:
            details.append(f"• {note}")

        return {
            "text": text,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join(details)
                    }
                }
            ]
        }

    async def _send_slack(self, message: dict) -> None:
        """Send message to Slack webhook."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.settings.slack_webhook_url,
                    json=message,
                    timeout=10.0
                )
                response.raise_for_status()
                logger.debug("Slack notification sent successfully")

        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")


async def main():
    """Test notifier."""
    from datetime import datetime, timezone

    notifier = Notifier()

    # Test event
    event = EventCard(
        event_id="test123",
        tickers=["AAPL"],
        headline="Apple announces record Q4 earnings, beats estimates by 15%",
        published_at=datetime.now(timezone.utc),
        category="earnings",
        sentiment=0.85,
        reliability=0.90,
        key_facts=["Beat estimates", "Strong iPhone sales"],
        session="regular",
        cluster_id="cluster123",
        source="Test"
    )

    # Test signal
    pre_signal = PreSignal(
        action="ENTRY",
        window_hint="[1,5]m",
        metrics={"sentiment": 0.85, "dP_5m": 2.3, "vol_ratio": 4.2},
        reasons=["Strong positive sentiment", "Good momentum"],
        event_id="test123",
        ticker="AAPL"
    )

    # Test approved signal
    approved = ApprovedSignal(
        approved=True,
        size_final_usd=1000.0,
        hard_stop_bp=150,
        take_profit_bp=250,
        max_slippage_bp=40,
        notes=["Approved"],
        ticker="AAPL",
        entry_price_target=175.50,
        shares=5
    )

    # Send notification
    await notifier.notify_signal(event, pre_signal, approved)
    print("Notification sent (check Slack if configured)")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
