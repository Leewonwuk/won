"""Virtual 4-balance portfolio: USDT + BTC(USDT leg) + USDC + BTC(USDC leg)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class DualQuoteTradeEvent:
    ts: str
    symbol: str
    event: str
    premium: float
    mid_usdt: float
    mid_usdc: float
    trade_qty: float = 0.0
    pnl_usd: float = 0.0
    fee_usd: float = 0.0
    detail: str = ""


@dataclass
class DualQuoteBalance:
    symbol: str
    usdt: float = 0.0
    btc_usdt_leg: float = 0.0
    usdc: float = 0.0
    btc_usdc_leg: float = 0.0
    total_trades: int = 0
    total_rebalances: int = 0
    daily_rebalances: int = 0
    realized_fee_usd: float = 0.0

    def total_value_usd(self, mid_usdt: float, mid_usdc: float) -> float:
        return (
            self.usdt
            + self.usdc
            + self.btc_usdt_leg * mid_usdt
            + self.btc_usdc_leg * mid_usdc
        )


@dataclass
class DualQuotePortfolio:
    balances: dict[str, DualQuoteBalance] = field(default_factory=dict)
    events: list[DualQuoteTradeEvent] = field(default_factory=list)
    realized_pnl_usd: float = 0.0

    def init_symbol(
        self,
        symbol: str,
        usdt: float,
        btc_usdt_leg: float,
        usdc: float,
        btc_usdc_leg: float,
    ) -> None:
        self.balances[symbol] = DualQuoteBalance(
            symbol=symbol,
            usdt=usdt,
            btc_usdt_leg=btc_usdt_leg,
            usdc=usdc,
            btc_usdc_leg=btc_usdc_leg,
        )

    def get(self, symbol: str) -> DualQuoteBalance:
        return self.balances[symbol]

    def execute_kimchi_trade(
        self,
        symbol: str,
        mid_usdt: float,
        mid_usdc: float,
        fee_usdt_leg_rate: float,
        fee_usdc_leg_rate: float,
        slip_usdt_leg_rate: float,
        slip_usdc_leg_rate: float,
        trade_fraction: float = 1.0,
        ts: str = "",
    ) -> DualQuoteTradeEvent:
        """Premium > 0: BTC rich on USDT leg → sell BTCUSDT leg, buy BTCUSDC leg."""
        b = self.balances[symbol]
        if not ts:
            ts = datetime.now(tz=timezone.utc).isoformat()

        premium = (mid_usdt - mid_usdc) / mid_usdc if mid_usdc > 0 else 0.0
        before = b.total_value_usd(mid_usdt, mid_usdc)
        fraction = max(0.0, min(float(trade_fraction), 1.0))

        sell_qty = b.btc_usdt_leg * fraction
        eff_sell = mid_usdt * (1 - fee_usdt_leg_rate - slip_usdt_leg_rate)
        usdt_from_sell = sell_qty * eff_sell
        fee_sell_usd = sell_qty * mid_usdt * (fee_usdt_leg_rate + slip_usdt_leg_rate)

        spend_usdc = b.usdc * fraction
        eff_buy = mid_usdc * (1 + fee_usdc_leg_rate + slip_usdc_leg_rate)
        buy_qty = spend_usdc / eff_buy if eff_buy > 0 else 0.0
        fee_buy_usd = spend_usdc * (fee_usdc_leg_rate + slip_usdc_leg_rate)

        b.btc_usdt_leg = max(b.btc_usdt_leg - sell_qty, 0.0)
        b.usdt += usdt_from_sell
        b.usdc = max(b.usdc - spend_usdc, 0.0)
        b.btc_usdc_leg += buy_qty

        total_fee = fee_sell_usd + fee_buy_usd
        b.realized_fee_usd += total_fee
        b.total_trades += 1
        after = b.total_value_usd(mid_usdt, mid_usdc)
        pnl = after - before

        ev = DualQuoteTradeEvent(
            ts=ts,
            symbol=symbol,
            event="TRADE_KIMCHI",
            premium=premium,
            mid_usdt=mid_usdt,
            mid_usdc=mid_usdc,
            trade_qty=sell_qty,
            pnl_usd=pnl,
            fee_usd=total_fee,
            detail=(
                f"fraction={fraction:.2f} sell {sell_qty:.8f} BTC@USDT leg, "
                f"buy {buy_qty:.8f} BTC@USDC leg (spend {spend_usdc:.2f} USDC)"
            ),
        )
        self.events.append(ev)
        self.realized_pnl_usd += pnl
        return ev

    def execute_reverse_trade(
        self,
        symbol: str,
        mid_usdt: float,
        mid_usdc: float,
        fee_usdt_leg_rate: float,
        fee_usdc_leg_rate: float,
        slip_usdt_leg_rate: float,
        slip_usdc_leg_rate: float,
        trade_fraction: float = 1.0,
        ts: str = "",
    ) -> DualQuoteTradeEvent:
        """Premium < 0: BTC rich on USDC leg → buy BTCUSDT leg, sell BTCUSDC leg."""
        b = self.balances[symbol]
        if not ts:
            ts = datetime.now(tz=timezone.utc).isoformat()

        premium = (mid_usdt - mid_usdc) / mid_usdc if mid_usdc > 0 else 0.0
        before = b.total_value_usd(mid_usdt, mid_usdc)
        fraction = max(0.0, min(float(trade_fraction), 1.0))

        spend_usdt = b.usdt * fraction
        eff_buy_ut = mid_usdt * (1 + fee_usdt_leg_rate + slip_usdt_leg_rate)
        buy_qty_ut = spend_usdt / eff_buy_ut if eff_buy_ut > 0 else 0.0
        fee_buy_ut = spend_usdt * (fee_usdt_leg_rate + slip_usdt_leg_rate)

        sell_qty_uc = b.btc_usdc_leg * fraction
        eff_sell_uc = mid_usdc * (1 - fee_usdc_leg_rate - slip_usdc_leg_rate)
        usdc_from_sell = sell_qty_uc * eff_sell_uc
        fee_sell_uc = sell_qty_uc * mid_usdc * (fee_usdc_leg_rate + slip_usdc_leg_rate)

        b.usdt = max(b.usdt - spend_usdt, 0.0)
        b.btc_usdt_leg += buy_qty_ut
        b.btc_usdc_leg = max(b.btc_usdc_leg - sell_qty_uc, 0.0)
        b.usdc += usdc_from_sell

        total_fee = fee_buy_ut + fee_sell_uc
        b.realized_fee_usd += total_fee
        b.total_trades += 1
        after = b.total_value_usd(mid_usdt, mid_usdc)
        pnl = after - before

        ev = DualQuoteTradeEvent(
            ts=ts,
            symbol=symbol,
            event="TRADE_REVERSE",
            premium=premium,
            mid_usdt=mid_usdt,
            mid_usdc=mid_usdc,
            trade_qty=sell_qty_uc,
            pnl_usd=pnl,
            fee_usd=total_fee,
            detail=(
                f"fraction={fraction:.2f} buy {buy_qty_ut:.8f} BTC@USDT (spend {spend_usdt:.2f} USDT), "
                f"sell {sell_qty_uc:.8f} BTC@USDC leg"
            ),
        )
        self.events.append(ev)
        self.realized_pnl_usd += pnl
        return ev

    def execute_rebalance_dt_to_dc(
        self,
        symbol: str,
        mid_usdt: float,
        mid_usdc: float,
        transfer_fee_btc: float,
        stable_move_fee_rate: float,
        target_portfolio_ratio: float = 0.25,
        ts: str = "",
    ) -> DualQuoteTradeEvent:
        """Move excess BTC from USDT leg → USDC leg; move excess USDC → USDT."""
        b = self.balances[symbol]
        if not ts:
            ts = datetime.now(tz=timezone.utc).isoformat()

        premium = (mid_usdt - mid_usdc) / mid_usdc if mid_usdc > 0 else 0.0
        val_before = b.total_value_usd(mid_usdt, mid_usdc)
        total_fee_usd = 0.0
        target_value = max(val_before * target_portfolio_ratio, 0.0)

        ut_coin_val = b.btc_usdt_leg * mid_usdt
        excess_coin_val = max(ut_coin_val - target_value, 0.0)
        coin_to_transfer = (excess_coin_val / mid_usdt) if mid_usdt > 0 else 0.0
        coin_transfer_amount = min(b.btc_usdt_leg, max(coin_to_transfer, 0.0))
        coin_fee = min(transfer_fee_btc, coin_transfer_amount)
        coin_transferred = max(coin_transfer_amount - coin_fee, 0.0)
        transfer_fee_usd = coin_fee * mid_usdt
        b.btc_usdt_leg -= coin_transfer_amount
        b.btc_usdc_leg += coin_transferred
        total_fee_usd += transfer_fee_usd

        excess_usdc = max(b.usdc - target_value, 0.0)
        usdc_to_convert = min(b.usdc, excess_usdc)
        usdt_received = usdc_to_convert * (1 - stable_move_fee_rate)
        fx_fee_usd = usdc_to_convert * stable_move_fee_rate
        b.usdc -= usdc_to_convert
        b.usdt += usdt_received
        total_fee_usd += fx_fee_usd

        detail = (
            f"DT→DC: BTC {coin_transferred:.8f}/{coin_transfer_amount:.8f} (fee {coin_fee:.8f}), "
            f"USDC→USDT {usdc_to_convert:.2f} → {usdt_received:.2f} USDT"
        )

        b.realized_fee_usd += total_fee_usd
        b.total_rebalances += 1
        b.daily_rebalances += 1
        val_after = b.total_value_usd(mid_usdt, mid_usdc)
        pnl = val_after - val_before

        ev = DualQuoteTradeEvent(
            ts=ts,
            symbol=symbol,
            event="REBALANCE_DT_DC",
            premium=premium,
            mid_usdt=mid_usdt,
            mid_usdc=mid_usdc,
            pnl_usd=pnl,
            fee_usd=total_fee_usd,
            detail=detail,
        )
        self.events.append(ev)
        self.realized_pnl_usd += pnl
        return ev

    def execute_rebalance_dc_to_dt(
        self,
        symbol: str,
        mid_usdt: float,
        mid_usdc: float,
        transfer_fee_btc: float,
        stable_move_fee_rate: float,
        target_portfolio_ratio: float = 0.25,
        ts: str = "",
    ) -> DualQuoteTradeEvent:
        """Move excess BTC from USDC leg → USDT leg; move excess USDT → USDC."""
        b = self.balances[symbol]
        if not ts:
            ts = datetime.now(tz=timezone.utc).isoformat()

        premium = (mid_usdt - mid_usdc) / mid_usdc if mid_usdc > 0 else 0.0
        val_before = b.total_value_usd(mid_usdt, mid_usdc)
        total_fee_usd = 0.0
        target_value = max(val_before * target_portfolio_ratio, 0.0)

        uc_coin_val = b.btc_usdc_leg * mid_usdc
        excess_coin_val = max(uc_coin_val - target_value, 0.0)
        coin_to_transfer = (excess_coin_val / mid_usdc) if mid_usdc > 0 else 0.0
        coin_transfer_amount = min(b.btc_usdc_leg, max(coin_to_transfer, 0.0))
        coin_fee = min(transfer_fee_btc, coin_transfer_amount)
        coin_transferred = max(coin_transfer_amount - coin_fee, 0.0)
        transfer_fee_usd = coin_fee * mid_usdc
        b.btc_usdc_leg -= coin_transfer_amount
        b.btc_usdt_leg += coin_transferred
        total_fee_usd += transfer_fee_usd

        excess_usdt = max(b.usdt - target_value, 0.0)
        usdt_to_convert = min(b.usdt, excess_usdt)
        usdc_received = usdt_to_convert * (1 - stable_move_fee_rate)
        fx_fee_usd = usdt_to_convert * stable_move_fee_rate
        b.usdt -= usdt_to_convert
        b.usdc += usdc_received
        total_fee_usd += fx_fee_usd

        detail = (
            f"DC→DT: BTC {coin_transferred:.8f}/{coin_transfer_amount:.8f} (fee {coin_fee:.8f}), "
            f"USDT→USDC {usdt_to_convert:.2f} → {usdc_received:.2f} USDC"
        )

        b.realized_fee_usd += total_fee_usd
        b.total_rebalances += 1
        b.daily_rebalances += 1
        val_after = b.total_value_usd(mid_usdt, mid_usdc)
        pnl = val_after - val_before

        ev = DualQuoteTradeEvent(
            ts=ts,
            symbol=symbol,
            event="REBALANCE_DC_DT",
            premium=premium,
            mid_usdt=mid_usdt,
            mid_usdc=mid_usdc,
            pnl_usd=pnl,
            fee_usd=total_fee_usd,
            detail=detail,
        )
        self.events.append(ev)
        self.realized_pnl_usd += pnl
        return ev

    def reset_daily_counters(self) -> None:
        for b in self.balances.values():
            b.daily_rebalances = 0
