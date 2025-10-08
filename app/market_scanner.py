"""
Market scanner for real-time price and volume data.
Uses Alpaca Market Data API to calculate technical indicators.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
import numpy as np
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame

from app.schemas import MarketState
from app.config import get_settings
from app.utils import (
    get_utc_now, get_market_session, calculate_spread_bp,
    calculate_price_change_pct, setup_logger
)

logger = setup_logger(__name__)


class MarketScanner:
    """
    Scans market data and calculates technical indicators.
    """

    def __init__(self):
        self.settings = get_settings()
        self.client = StockHistoricalDataClient(
            api_key=self.settings.alpaca_api_key,
            secret_key=self.settings.alpaca_secret_key
        )

    async def get_market_state(self, ticker: str) -> Optional[MarketState]:
        """
        Get current market state for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            MarketState object or None if failed
        """
        try:
            # Get latest quote
            quote = await self._get_latest_quote(ticker)
            if not quote:
                logger.warning(f"No quote data for {ticker}")
                return None

            # Get recent bars for calculations
            bars = await self._get_recent_bars(ticker, minutes=10)
            if len(bars) < 5:
                logger.warning(f"Insufficient bar data for {ticker}: {len(bars)} bars")
                return None

            # Calculate metrics
            bid = quote['bid']
            ask = quote['ask']
            mid = (bid + ask) / 2
            spread_bp = calculate_spread_bp(bid, ask)

            # Price changes
            dp_1m = calculate_price_change_pct(bars[-2]['close'], bars[-1]['close'])
            dp_5m = calculate_price_change_pct(bars[-6]['close'] if len(bars) > 5 else bars[0]['close'], bars[-1]['close'])

            # Volume ratio (recent vs average)
            recent_vol = bars[-1]['volume']
            avg_vol = np.mean([b['volume'] for b in bars[:-1]])
            vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

            # RSI (3-period)
            rsi_3 = self._calculate_rsi([b['close'] for b in bars], period=3)

            # VWAP deviation
            vwap = self._calculate_vwap(bars)
            vwap_dev_bp = int(((mid - vwap) / vwap) * 10000) if vwap > 0 else 0

            # Session
            session = get_market_session(get_utc_now())

            return MarketState(
                ticker=ticker,
                ts=get_utc_now(),
                mid=mid,
                spread_bp=spread_bp,
                dP_1m=dp_1m,
                dP_5m=dp_5m,
                vol_ratio_1m=vol_ratio,
                rsi_3=rsi_3,
                vwap_dev_bp=vwap_dev_bp,
                session=session,
                bid=bid,
                ask=ask,
                volume=recent_vol
            )

        except Exception as e:
            logger.error(f"Error getting market state for {ticker}: {e}")
            return None

    async def _get_latest_quote(self, ticker: str) -> Optional[dict]:
        """Get latest bid/ask quote."""
        try:
            request = StockLatestQuoteRequest(
                symbol_or_symbols=ticker,
                feed='iex'  # Use IEX feed (free tier compatible)
            )
            # Run in thread to avoid blocking event loop
            quotes = await asyncio.to_thread(
                self.client.get_stock_latest_quote,
                request
            )

            if ticker not in quotes:
                return None

            quote = quotes[ticker]
            return {
                'bid': float(quote.bid_price),
                'ask': float(quote.ask_price),
                'bid_size': int(quote.bid_size),
                'ask_size': int(quote.ask_size),
            }

        except Exception as e:
            logger.error(f"Error fetching quote for {ticker}: {e}")
            return None

    async def _get_recent_bars(self, ticker: str, minutes: int = 10) -> list[dict]:
        """Get recent minute bars."""
        try:
            end = get_utc_now()
            start = end - timedelta(minutes=minutes)

            request = StockBarsRequest(
                symbol_or_symbols=ticker,
                timeframe=TimeFrame.Minute,
                start=start,
                end=end,
                feed='iex'  # Use IEX feed (free tier compatible)
            )

            # Run in thread to avoid blocking event loop
            bars_response = await asyncio.to_thread(
                self.client.get_stock_bars,
                request
            )

            if ticker not in bars_response:
                return []

            bars = []
            for bar in bars_response[ticker]:
                bars.append({
                    'timestamp': bar.timestamp,
                    'open': float(bar.open),
                    'high': float(bar.high),
                    'low': float(bar.low),
                    'close': float(bar.close),
                    'volume': int(bar.volume),
                    'vwap': float(bar.vwap) if bar.vwap else None
                })

            return bars

        except Exception as e:
            logger.error(f"Error fetching bars for {ticker}: {e}")
            return []

    def _calculate_rsi(self, prices: list[float], period: int = 3) -> float:
        """
        Calculate RSI (Relative Strength Index).

        Args:
            prices: List of closing prices
            period: RSI period (default 3)

        Returns:
            RSI value (0-100)
        """
        if len(prices) < period + 1:
            return 50.0  # Neutral default

        # Calculate price changes
        deltas = np.diff(prices)

        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Calculate average gains and losses
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return float(rsi)

    def _calculate_vwap(self, bars: list[dict]) -> float:
        """
        Calculate VWAP (Volume Weighted Average Price).

        Args:
            bars: List of bar data

        Returns:
            VWAP value
        """
        if not bars:
            return 0.0

        # Use bar vwap if available
        if bars[-1].get('vwap'):
            return bars[-1]['vwap']

        # Otherwise calculate from bars
        total_volume = sum(b['volume'] for b in bars)
        if total_volume == 0:
            return bars[-1]['close']

        vwap = sum(b['close'] * b['volume'] for b in bars) / total_volume
        return float(vwap)


async def main():
    """Test market scanner."""
    scanner = MarketScanner()

    test_tickers = ["AAPL", "TSLA"]

    for ticker in test_tickers:
        print(f"\n=== {ticker} ===")
        state = await scanner.get_market_state(ticker)

        if state:
            print(f"Mid: ${state.mid:.2f}")
            print(f"Spread: {state.spread_bp} bp")
            print(f"dP_1m: {state.dP_1m:.2f}%")
            print(f"dP_5m: {state.dP_5m:.2f}%")
            print(f"Vol Ratio: {state.vol_ratio_1m:.2f}x")
            print(f"RSI(3): {state.rsi_3:.1f}")
            print(f"VWAP Dev: {state.vwap_dev_bp} bp")
            print(f"Session: {state.session}")
        else:
            print("Failed to get market state")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
