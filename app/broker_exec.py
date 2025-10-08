"""
Broker execution module for placing orders via Alpaca API.
Supports DRYRUN, SEMI_AUTO, and FULL_AUTO modes.
"""

import asyncio
from typing import Optional
from datetime import datetime
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from app.schemas import ApprovedSignal, OrderRecord, OrderStatus, Position
from app.config import get_settings, get_rules
from app.storage import Storage
from app.utils import setup_logger, get_utc_now

logger = setup_logger(__name__)


class BrokerExecutor:
    """
    Executes trades via Alpaca broker API.
    """

    def __init__(self, storage: Storage):
        self.settings = get_settings()
        self.rules = get_rules()
        self.storage = storage
        self.client = None

        # Initialize Alpaca client only if not in DRYRUN mode
        if self.settings.run_mode != "DRYRUN":
            self.client = TradingClient(
                api_key=self.settings.alpaca_api_key,
                secret_key=self.settings.alpaca_secret_key,
                paper=True  # Always use paper trading
            )

    async def execute(
        self,
        signal: ApprovedSignal,
        event_id: str,
        signal_id: str
    ) -> Optional[OrderRecord]:
        """
        Execute trade based on run mode.

        Args:
            signal: Approved signal
            event_id: Related event ID
            signal_id: Signal ID

        Returns:
            OrderRecord if order was placed, None otherwise
        """
        if not signal.approved:
            logger.info(f"Signal not approved for {signal.ticker}, skipping execution")
            return None

        # Execute based on mode
        if self.settings.run_mode == "DRYRUN":
            return await self._execute_dryrun(signal, event_id, signal_id)
        elif self.settings.run_mode == "SEMI_AUTO":
            return await self._execute_semi_auto(signal, event_id, signal_id)
        elif self.settings.run_mode == "FULL_AUTO":
            return await self._execute_full_auto(signal, event_id, signal_id)
        else:
            logger.error(f"Unknown run mode: {self.settings.run_mode}")
            return None

    async def _execute_dryrun(
        self,
        signal: ApprovedSignal,
        event_id: str,
        signal_id: str
    ) -> OrderRecord:
        """Execute in DRYRUN mode (simulation only)."""
        logger.info(f"[DRYRUN] Would place order: {signal.shares} shares of {signal.ticker} "
                   f"@ ${signal.entry_price_target:.2f}")

        order = OrderRecord(
            order_id=f"DRYRUN_{signal_id}",
            ticker=signal.ticker,
            event_id=event_id,
            signal_id=signal_id,
            side="buy",
            quantity=signal.shares,
            order_type="limit",
            limit_price=signal.entry_price_target,
            status=OrderStatus.PENDING,
            submitted_at=get_utc_now()
        )

        # Save to database
        self.storage.save_order(order)

        return order

    async def _execute_semi_auto(
        self,
        signal: ApprovedSignal,
        event_id: str,
        signal_id: str
    ) -> OrderRecord:
        """
        Execute in SEMI_AUTO mode (requires manual approval).

        In a real implementation, this would:
        1. Send notification to user (Slack/email/web UI)
        2. Wait for user approval
        3. Execute if approved

        For this MVP, we'll simulate approval after a delay.
        """
        logger.info(f"[SEMI_AUTO] Requesting approval for: {signal.shares} shares of {signal.ticker}")

        # In production, this would wait for actual user input
        # For now, simulate approval after brief delay
        await asyncio.sleep(1)

        # Simulate 80% approval rate
        import random
        approved = random.random() < 0.8

        if not approved:
            logger.info(f"[SEMI_AUTO] Order rejected by user for {signal.ticker}")
            order = OrderRecord(
                order_id=f"SEMI_{signal_id}_REJECTED",
                ticker=signal.ticker,
                event_id=event_id,
                signal_id=signal_id,
                side="buy",
                quantity=signal.shares,
                order_type="limit",
                limit_price=signal.entry_price_target,
                status=OrderStatus.CANCELLED,
                submitted_at=get_utc_now(),
                error_message="Rejected by user"
            )
            self.storage.save_order(order)
            return order

        # Execute the order
        logger.info(f"[SEMI_AUTO] Order approved, executing...")
        return await self._place_limit_order(signal, event_id, signal_id)

    async def _execute_full_auto(
        self,
        signal: ApprovedSignal,
        event_id: str,
        signal_id: str
    ) -> OrderRecord:
        """Execute in FULL_AUTO mode (automatic execution)."""
        logger.info(f"[FULL_AUTO] Placing order: {signal.shares} shares of {signal.ticker}")
        return await self._place_limit_order(signal, event_id, signal_id)

    async def _place_limit_order(
        self,
        signal: ApprovedSignal,
        event_id: str,
        signal_id: str
    ) -> OrderRecord:
        """
        Place actual limit order via Alpaca API.

        Args:
            signal: Approved signal
            event_id: Related event ID
            signal_id: Signal ID

        Returns:
            OrderRecord
        """
        try:
            # Create limit order request
            order_request = LimitOrderRequest(
                symbol=signal.ticker,
                qty=signal.shares,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                limit_price=signal.entry_price_target
            )

            # Submit order
            alpaca_order = self.client.submit_order(order_request)

            logger.info(f"Order placed: {alpaca_order.id} for {signal.ticker}")

            # Create order record
            order = OrderRecord(
                order_id=alpaca_order.id,
                ticker=signal.ticker,
                event_id=event_id,
                signal_id=signal_id,
                side="buy",
                quantity=signal.shares,
                order_type="limit",
                limit_price=signal.entry_price_target,
                status=OrderStatus.SUBMITTED,
                submitted_at=get_utc_now()
            )

            # Save to database
            self.storage.save_order(order)

            # Monitor order (simplified - in production would be async task)
            await self._monitor_order(order, signal)

            return order

        except Exception as e:
            logger.error(f"Order placement failed: {e}")

            # Retry once
            max_retries = self.rules.execution.get("max_retries", 1)
            if max_retries > 0:
                retry_delay = self.rules.execution.get("retry_delay_seconds", 2)
                logger.info(f"Retrying order in {retry_delay}s...")
                await asyncio.sleep(retry_delay)

                try:
                    alpaca_order = self.client.submit_order(order_request)
                    logger.info(f"Retry successful: {alpaca_order.id}")

                    order = OrderRecord(
                        order_id=alpaca_order.id,
                        ticker=signal.ticker,
                        event_id=event_id,
                        signal_id=signal_id,
                        side="buy",
                        quantity=signal.shares,
                        order_type="limit",
                        limit_price=signal.entry_price_target,
                        status=OrderStatus.SUBMITTED,
                        submitted_at=get_utc_now()
                    )
                    self.storage.save_order(order)
                    return order

                except Exception as e2:
                    logger.error(f"Retry failed: {e2}")

            # Both attempts failed
            order = OrderRecord(
                order_id=f"FAILED_{signal_id}",
                ticker=signal.ticker,
                event_id=event_id,
                signal_id=signal_id,
                side="buy",
                quantity=signal.shares,
                order_type="limit",
                limit_price=signal.entry_price_target,
                status=OrderStatus.FAILED,
                submitted_at=get_utc_now(),
                error_message=str(e)
            )
            self.storage.save_order(order)
            return order

    async def _monitor_order(self, order: OrderRecord, signal: ApprovedSignal) -> None:
        """
        Monitor order for fill (simplified).

        In production, this would be a separate async task that:
        1. Polls order status
        2. Updates database
        3. Places stop-loss/take-profit orders when filled
        4. Sends notifications
        """
        timeout = self.rules.execution.get("order_timeout_seconds", 30)

        try:
            # Poll order status
            for _ in range(int(timeout / 2)):
                await asyncio.sleep(2)

                alpaca_order = self.client.get_order_by_id(order.order_id)

                if alpaca_order.status == "filled":
                    logger.info(f"Order {order.order_id} filled @ ${alpaca_order.filled_avg_price}")

                    # Update order record
                    order.status = OrderStatus.FILLED
                    order.filled_at = get_utc_now()
                    order.filled_avg_price = float(alpaca_order.filled_avg_price)
                    order.filled_qty = int(alpaca_order.filled_qty)
                    self.storage.save_order(order)

                    # Create position record
                    position = Position(
                        ticker=signal.ticker,
                        entry_price=order.filled_avg_price,
                        quantity=order.filled_qty,
                        entry_time=order.filled_at,
                        event_id=order.event_id,
                        order_id=order.order_id,
                        stop_loss=order.filled_avg_price * (1 - signal.hard_stop_bp / 10000),
                        take_profit=order.filled_avg_price * (1 + signal.take_profit_bp / 10000)
                    )
                    self.storage.save_position(position)

                    logger.info(f"Position opened: {position.quantity} shares @ ${position.entry_price:.2f}")
                    break

                elif alpaca_order.status in ["cancelled", "rejected", "expired"]:
                    logger.warning(f"Order {order.order_id} status: {alpaca_order.status}")
                    order.status = OrderStatus.CANCELLED
                    order.error_message = f"Order {alpaca_order.status}"
                    self.storage.save_order(order)
                    break

            else:
                # Timeout - cancel order
                logger.warning(f"Order {order.order_id} timeout, cancelling...")
                try:
                    self.client.cancel_order_by_id(order.order_id)
                    order.status = OrderStatus.CANCELLED
                    order.error_message = "Timeout"
                    self.storage.save_order(order)
                except Exception as e:
                    logger.error(f"Failed to cancel order: {e}")

        except Exception as e:
            logger.error(f"Error monitoring order: {e}")

    async def close_position(
        self,
        position: Position,
        quantity: int,
        price: float,
        reason: str
    ) -> Optional[OrderRecord]:
        """
        Close position (full or partial).

        Args:
            position: Position to close
            quantity: Number of shares to sell
            price: Limit price for sell order
            reason: Reason for closing (e.g., "HARD_STOP", "TRAILING_STOP")

        Returns:
            OrderRecord if order was placed, None otherwise
        """
        logger.info(f"[CLOSE] {position.ticker}: {quantity} shares @ ${price:.2f} ({reason})")

        # Execute based on mode
        if self.settings.run_mode == "DRYRUN":
            return await self._close_dryrun(position, quantity, price, reason)
        elif self.settings.run_mode in ["SEMI_AUTO", "FULL_AUTO"]:
            return await self._place_sell_order(position, quantity, price, reason)
        else:
            logger.error(f"Unknown run mode: {self.settings.run_mode}")
            return None

    async def _close_dryrun(
        self,
        position: Position,
        quantity: int,
        price: float,
        reason: str
    ) -> OrderRecord:
        """Close position in DRYRUN mode."""
        pnl = (price - position.entry_price) * quantity
        pnl_pct = ((price - position.entry_price) / position.entry_price) * 100

        logger.info(f"[DRYRUN] Would sell: {quantity} shares of {position.ticker} "
                   f"@ ${price:.2f} | P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")

        order = OrderRecord(
            order_id=f"DRYRUN_SELL_{position.order_id}_{int(get_utc_now().timestamp())}",
            ticker=position.ticker,
            event_id=position.event_id,
            signal_id=f"exit_{reason}",
            side="sell",
            quantity=quantity,
            order_type="limit",
            limit_price=price,
            status=OrderStatus.FILLED,  # Simulate immediate fill in DRYRUN
            submitted_at=get_utc_now(),
            filled_at=get_utc_now(),
            filled_avg_price=price,
            filled_qty=quantity
        )

        # Save to database
        self.storage.save_order(order)

        return order

    async def _place_sell_order(
        self,
        position: Position,
        quantity: int,
        price: float,
        reason: str
    ) -> OrderRecord:
        """Place actual sell order via Alpaca API."""
        try:
            # Create sell limit order request
            order_request = LimitOrderRequest(
                symbol=position.ticker,
                qty=quantity,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
                limit_price=price
            )

            # Submit order
            alpaca_order = self.client.submit_order(order_request)

            logger.info(f"Sell order placed: {alpaca_order.id} for {position.ticker} ({reason})")

            # Create order record
            order = OrderRecord(
                order_id=alpaca_order.id,
                ticker=position.ticker,
                event_id=position.event_id,
                signal_id=f"exit_{reason}",
                side="sell",
                quantity=quantity,
                order_type="limit",
                limit_price=price,
                status=OrderStatus.SUBMITTED,
                submitted_at=get_utc_now()
            )

            # Save to database
            self.storage.save_order(order)

            return order

        except Exception as e:
            logger.error(f"Sell order placement failed: {e}")

            order = OrderRecord(
                order_id=f"FAILED_SELL_{position.order_id}",
                ticker=position.ticker,
                event_id=position.event_id,
                signal_id=f"exit_{reason}",
                side="sell",
                quantity=quantity,
                order_type="limit",
                limit_price=price,
                status=OrderStatus.FAILED,
                submitted_at=get_utc_now(),
                error_message=str(e)
            )
            self.storage.save_order(order)
            return order


async def main():
    """Test broker executor."""
    from datetime import datetime, timezone

    storage = Storage()
    executor = BrokerExecutor(storage)

    signal = ApprovedSignal(
        approved=True,
        size_final_usd=1000.0,
        hard_stop_bp=150,
        take_profit_bp=250,
        max_slippage_bp=40,
        notes=["Test order"],
        ticker="AAPL",
        entry_price_target=175.50,
        shares=5
    )

    order = await executor.execute(signal, "event123", "signal123")

    if order:
        print("\n=== Order Placed ===")
        print(f"Order ID: {order.order_id}")
        print(f"Ticker: {order.ticker}")
        print(f"Quantity: {order.quantity}")
        print(f"Limit Price: ${order.limit_price:.2f}")
        print(f"Status: {order.status}")
    else:
        print("No order placed")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
