"""
Main orchestration logic for the automated trading system.
Coordinates the entire pipeline from RSS fetching to order execution.
"""

import asyncio
import sys
from datetime import datetime, timedelta
from typing import Optional
import uuid

from app.rss_fetcher import RSSFetcher
from app.llm_interpreter import LLMInterpreter
from app.market_scanner import MarketScanner
from app.rule_engine import RuleEngine
from app.risk_guard import RiskGuard
from app.broker_exec import BrokerExecutor
from app.notifier import Notifier
from app.storage import Storage
from app.schemas import RunRecord
from app.config import get_settings
from app.utils import setup_logger, get_utc_now

# Setup logging
logger = setup_logger(__name__)


class AutoTrader:
    """
    Main orchestration class for automated trading system.
    """

    def __init__(self):
        self.settings = get_settings()

        # Initialize components
        self.storage = Storage(self.settings.db_path)
        self.rss_fetcher = RSSFetcher()
        self.llm_interpreter = LLMInterpreter()
        self.market_scanner = MarketScanner()
        self.rule_engine = RuleEngine()
        self.risk_guard = RiskGuard(self.storage)
        self.broker = BrokerExecutor(self.storage)
        self.notifier = Notifier()

    async def run_cycle(self) -> RunRecord:
        """
        Execute one complete trading cycle.

        Returns:
            RunRecord with cycle statistics
        """
        run_id = str(uuid.uuid4())
        started_at = get_utc_now()

        run_record = RunRecord(
            run_id=run_id,
            started_at=started_at,
            status="running",
            mode=self.settings.run_mode
        )

        logger.info(f"=== Starting run {run_id[:8]} in {self.settings.run_mode} mode ===")

        try:
            # Save run record
            self.storage.create_run(run_record)

            # Step 1: Fetch RSS items
            logger.info("Step 1: Fetching RSS feeds...")
            since_time = self._get_since_time()
            rss_items = await self.rss_fetcher.fetch_recent_items(
                since=since_time,
                delay_minutes=self.settings.cycle_minutes
            )
            logger.info(f"Fetched {len(rss_items)} RSS items")

            # Step 2: Interpret events with LLM
            logger.info("Step 2: Interpreting events with LLM...")
            events = []
            for item in rss_items:
                # Check if event already exists
                if self.storage.event_exists(item.cluster_id):
                    logger.debug(f"Event already exists: {item.cluster_id}")
                    continue

                # Interpret with LLM
                event = await self.llm_interpreter.interpret(item)
                if event:
                    events.append(event)
                    # Save to database
                    self.storage.save_event(event)

                # Rate limiting
                await asyncio.sleep(0.5)

            logger.info(f"Interpreted {len(events)} new events")
            run_record.events_fetched = len(events)

            # Step 3: Process each event
            signals_generated = 0
            orders_placed = 0

            for event in events:
                try:
                    await self._process_event(event)
                    signals_generated += 1

                except Exception as e:
                    logger.error(f"Error processing event {event.event_id}: {e}")
                    run_record.errors.append(f"Event {event.event_id[:8]}: {str(e)}")

            run_record.signals_generated = signals_generated
            run_record.orders_placed = orders_placed

            # Complete run
            run_record.completed_at = get_utc_now()
            run_record.status = "completed"

            logger.info(f"=== Run {run_id[:8]} completed successfully ===")
            logger.info(f"Events: {run_record.events_fetched} | "
                       f"Signals: {run_record.signals_generated} | "
                       f"Orders: {run_record.orders_placed}")

        except Exception as e:
            logger.error(f"Run failed: {e}", exc_info=True)
            run_record.status = "failed"
            run_record.completed_at = get_utc_now()
            run_record.errors.append(f"Fatal error: {str(e)}")

            # Send error notification
            await self.notifier.notify_error("Run Failed", str(e))

        finally:
            # Update run record
            self.storage.update_run(run_record)

            # Send completion notification
            await self.notifier.notify_run_complete(
                run_id=run_id,
                events_count=run_record.events_fetched,
                signals_count=run_record.signals_generated,
                orders_count=run_record.orders_placed,
                errors=run_record.errors
            )

        return run_record

    async def _process_event(self, event) -> None:
        """
        Process a single event through the entire pipeline.

        Args:
            event: EventCard to process
        """
        logger.info(f"Processing event: {event.headline[:60]}...")

        # For each ticker mentioned in the event
        for ticker in event.tickers:
            try:
                # Step 3a: Get market state
                logger.debug(f"Getting market state for {ticker}...")
                market_state = await self.market_scanner.get_market_state(ticker)

                if not market_state:
                    logger.warning(f"No market data for {ticker}, skipping")
                    continue

                # Step 3b: Evaluate with rule engine
                logger.debug(f"Evaluating rules for {ticker}...")
                pre_signal = self.rule_engine.evaluate(event, market_state)

                # Step 3c: Get portfolio state
                portfolio = await self.risk_guard.get_portfolio_state()

                # Step 3d: Apply risk management
                logger.debug(f"Applying risk management for {ticker}...")
                approved_signal = await self.risk_guard.approve_signal(
                    pre_signal, market_state, portfolio
                )

                # Save signal to database
                signal_id = self.storage.save_signal(pre_signal, approved_signal)

                # Step 3e: Execute if approved
                order = None
                if approved_signal.approved:
                    logger.info(f"Signal approved for {ticker}, executing...")
                    order = await self.broker.execute(
                        approved_signal, event.event_id, signal_id
                    )

                    if order:
                        logger.info(f"Order placed: {order.order_id}")

                # Step 3f: Send notification
                await self.notifier.notify_signal(
                    event, pre_signal, approved_signal, order
                )

                logger.debug(f"Completed processing {ticker}: "
                           f"action={pre_signal.action}, "
                           f"approved={approved_signal.approved}")

            except Exception as e:
                logger.error(f"Error processing {ticker} for event {event.event_id}: {e}")
                raise

    def _get_since_time(self) -> datetime:
        """
        Get the time to fetch news from.
        Based on last run time or cycle duration.
        """
        last_run = self.storage.get_last_run_time()

        if last_run:
            # Fetch since last run
            return last_run
        else:
            # First run: fetch from cycle_minutes ago
            return get_utc_now() - timedelta(minutes=self.settings.cycle_minutes * 2)


async def run_once():
    """Run a single cycle."""
    trader = AutoTrader()
    await trader.run_cycle()


async def run_continuous():
    """Run continuously with scheduled intervals."""
    trader = AutoTrader()

    cycle_seconds = trader.settings.cycle_minutes * 60

    logger.info(f"Starting continuous mode with {trader.settings.cycle_minutes} minute cycles")

    while True:
        try:
            await trader.run_cycle()

            # Wait for next cycle
            logger.info(f"Waiting {trader.settings.cycle_minutes} minutes until next cycle...")
            await asyncio.sleep(cycle_seconds)

        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
        except Exception as e:
            logger.error(f"Unexpected error in continuous loop: {e}")
            # Wait a bit before retrying
            await asyncio.sleep(60)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Automated Trading System")
    parser.add_argument(
        "--mode",
        choices=["once", "continuous"],
        default="once",
        help="Run mode: 'once' for single cycle or 'continuous' for scheduled runs"
    )

    args = parser.parse_args()

    # Print startup info
    settings = get_settings()
    logger.info("=" * 60)
    logger.info("Automated Trading System")
    logger.info("=" * 60)
    logger.info(f"Run Mode: {settings.run_mode}")
    logger.info(f"Cycle: {settings.cycle_minutes} minutes")
    logger.info(f"Tickers: {', '.join(settings.tickers)}")
    logger.info(f"Execution Mode: {args.mode}")
    logger.info("=" * 60)

    try:
        if args.mode == "once":
            asyncio.run(run_once())
        else:
            asyncio.run(run_continuous())

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
