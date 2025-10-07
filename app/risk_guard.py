"""
Risk management and position sizing module.
Enforces risk limits and calculates appropriate position sizes.
"""

from typing import Optional
from app.schemas import PreSignal, ApprovedSignal, MarketState, PortfolioState
from app.config import get_rules, get_settings, SECTOR_MAP
from app.storage import Storage
from app.utils import setup_logger, basis_points_to_pct, round_to_tick

logger = setup_logger(__name__)


class RiskGuard:
    """
    Enforces risk management rules and calculates position sizes.
    """

    def __init__(self, storage: Storage):
        self.rules = get_rules()
        self.settings = get_settings()
        self.storage = storage

    async def approve_signal(
        self,
        pre_signal: PreSignal,
        market: MarketState,
        portfolio: PortfolioState
    ) -> ApprovedSignal:
        """
        Approve or reject signal with position sizing.

        Args:
            pre_signal: Initial signal from rule engine
            market: Current market state
            portfolio: Current portfolio state

        Returns:
            ApprovedSignal with final decision and sizing
        """
        notes = []

        # If signal is already SKIP, return rejected approval
        if pre_signal.action == "SKIP":
            return ApprovedSignal(
                approved=False,
                size_final_usd=0.0,
                hard_stop_bp=0,
                take_profit_bp=0,
                max_slippage_bp=0,
                notes=["Signal was SKIP"],
                ticker=market.ticker
            )

        # Check portfolio-level limits
        if not self._check_portfolio_limits(portfolio, notes):
            return ApprovedSignal(
                approved=False,
                size_final_usd=0.0,
                hard_stop_bp=0,
                take_profit_bp=0,
                max_slippage_bp=0,
                notes=notes,
                ticker=market.ticker
            )

        # Check sector exposure
        if not self._check_sector_limit(market.ticker, portfolio, notes):
            return ApprovedSignal(
                approved=False,
                size_final_usd=0.0,
                hard_stop_bp=0,
                take_profit_bp=0,
                max_slippage_bp=0,
                notes=notes,
                ticker=market.ticker
            )

        # Calculate position size
        risk_rules = self.rules.risk
        exec_rules = self.rules.execution

        # Determine stop-loss distance
        min_stop_bp = risk_rules.get("min_stop_bp", 150)
        estimated_vol_bp = int(abs(market.dP_5m) * 100)  # Use 5m move as volatility proxy
        hard_stop_bp = max(min_stop_bp, int(estimated_vol_bp * 1.5))

        # Calculate position size based on risk
        per_trade_risk_pct = risk_rules.get("per_trade_risk_pct", 0.004)
        risk_amount = portfolio.equity * per_trade_risk_pct

        # Position size = Risk / Stop Distance
        stop_pct = basis_points_to_pct(hard_stop_bp) / 100
        size_usd = risk_amount / stop_pct if stop_pct > 0 else 0

        # Apply position size limits
        max_position_pct = risk_rules.get("max_position_size_pct", 0.15)
        max_position_usd = portfolio.equity * max_position_pct
        min_position_usd = risk_rules.get("min_position_size_usd", 100.0)
        max_limit_usd = risk_rules.get("max_position_size_usd", 15000.0)

        size_usd = min(size_usd, max_position_usd, max_limit_usd)

        # Check minimum size
        if size_usd < min_position_usd:
            notes.append(f"Position size ${size_usd:.2f} below minimum ${min_position_usd:.2f}")
            return ApprovedSignal(
                approved=False,
                size_final_usd=0.0,
                hard_stop_bp=0,
                take_profit_bp=0,
                max_slippage_bp=0,
                notes=notes,
                ticker=market.ticker
            )

        # Calculate shares
        shares = int(size_usd / market.mid)
        if shares == 0:
            notes.append("Calculated 0 shares - price too high for position size")
            return ApprovedSignal(
                approved=False,
                size_final_usd=0.0,
                hard_stop_bp=0,
                take_profit_bp=0,
                max_slippage_bp=0,
                notes=notes,
                ticker=market.ticker
            )

        # Recalculate actual size
        size_usd = shares * market.mid

        # Take profit target
        take_profit_bp = risk_rules.get("trail_take_profit_bp", 250)

        # Max slippage
        max_slippage_bp = exec_rules.get("max_slippage_bp", 40)

        # Calculate entry price target
        limit_offset_bp = exec_rules.get("limit_offset_bp", 10)
        entry_price_target = round_to_tick(
            market.mid * (1 + limit_offset_bp / 10000)
        )

        # Success notes
        notes.append(f"Risk per trade: ${risk_amount:.2f} ({per_trade_risk_pct * 100:.2f}% of equity)")
        notes.append(f"Position size: {shares} shares @ ~${market.mid:.2f} = ${size_usd:.2f}")
        notes.append(f"Stop: {hard_stop_bp} bp (${hard_stop_bp * size_usd / 10000:.2f})")
        notes.append(f"Take profit: {take_profit_bp} bp")

        return ApprovedSignal(
            approved=True,
            size_final_usd=size_usd,
            hard_stop_bp=hard_stop_bp,
            take_profit_bp=take_profit_bp,
            max_slippage_bp=max_slippage_bp,
            notes=notes,
            ticker=market.ticker,
            entry_price_target=entry_price_target,
            shares=shares
        )

    def _check_portfolio_limits(self, portfolio: PortfolioState, notes: list[str]) -> bool:
        """Check portfolio-level risk limits."""
        risk_rules = self.rules.risk

        # Check daily loss limit
        max_daily_loss_pct = risk_rules.get("max_daily_loss_pct", 0.02)
        if portfolio.daily_pnl_pct < -max_daily_loss_pct:
            notes.append(
                f"Daily loss limit exceeded: {portfolio.daily_pnl_pct * 100:.2f}% "
                f"(limit: {max_daily_loss_pct * 100:.2f}%)"
            )
            return False

        # Check max concurrent positions
        max_positions = risk_rules.get("max_concurrent_positions", 3)
        if portfolio.positions_count >= max_positions:
            notes.append(f"Max positions reached: {portfolio.positions_count}/{max_positions}")
            return False

        return True

    def _check_sector_limit(
        self,
        ticker: str,
        portfolio: PortfolioState,
        notes: list[str]
    ) -> bool:
        """Check sector exposure limit."""
        risk_rules = self.rules.risk
        max_sector_pct = risk_rules.get("max_sector_exposure_pct", 0.3)

        # Get sector for ticker
        sector = SECTOR_MAP.get(ticker, "Unknown")

        # Get current sector exposure
        current_sector_exposure = portfolio.sector_exposure.get(sector, 0.0)

        # Check if adding this position would exceed limit
        # (Simplified: assume we'd add max position size)
        max_position_pct = risk_rules.get("max_position_size_pct", 0.15)
        potential_exposure = current_sector_exposure + max_position_pct

        if potential_exposure > max_sector_pct:
            notes.append(
                f"Sector '{sector}' exposure would exceed limit: "
                f"{potential_exposure * 100:.1f}% (limit: {max_sector_pct * 100:.1f}%)"
            )
            return False

        return True

    async def get_portfolio_state(self) -> PortfolioState:
        """
        Get current portfolio state from broker and database.

        Returns:
            PortfolioState
        """
        # Get open positions from database
        open_positions = self.storage.get_open_positions()

        # Calculate metrics
        # (In production, this would query Alpaca for real-time account data)
        equity = self.settings.initial_equity  # Simplified
        cash = equity  # Simplified
        positions_count = len(open_positions)
        daily_pnl = 0.0  # Simplified
        daily_pnl_pct = 0.0  # Simplified

        # Calculate sector exposure
        sector_exposure = {}
        for pos in open_positions:
            sector = SECTOR_MAP.get(pos.ticker, "Unknown")
            exposure = abs(pos.quantity * pos.entry_price) / equity
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + exposure

        return PortfolioState(
            equity=equity,
            cash=cash,
            positions_count=positions_count,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            sector_exposure=sector_exposure,
            open_positions=open_positions
        )


async def main():
    """Test risk guard."""
    from datetime import datetime, timezone

    # Create test objects
    storage = Storage()
    guard = RiskGuard(storage)

    pre_signal = PreSignal(
        action="ENTRY",
        window_hint="[1,5]m",
        metrics={"sentiment": 0.85},
        reasons=["Strong positive sentiment"],
        event_id="test123",
        ticker="AAPL"
    )

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

    portfolio = await guard.get_portfolio_state()

    # Approve signal
    approved = await guard.approve_signal(pre_signal, market, portfolio)

    print("\n=== Risk Guard Approval ===")
    print(f"Approved: {approved.approved}")
    print(f"Size: ${approved.size_final_usd:.2f}")
    print(f"Shares: {approved.shares}")
    print(f"Entry Target: ${approved.entry_price_target:.2f}")
    print(f"Stop: {approved.hard_stop_bp} bp")
    print(f"Take Profit: {approved.take_profit_bp} bp")
    print(f"\nNotes:")
    for note in approved.notes:
        print(f"  - {note}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
