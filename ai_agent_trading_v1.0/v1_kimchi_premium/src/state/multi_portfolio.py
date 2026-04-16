"""4-balance portfolio model for rebalancing arbitrage.

Each coin tracks four independent balances:
  upbit_krw, upbit_coin, binance_usdt, binance_coin

Trades and rebalancing mutate these balances and record events
for later analysis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TradeEvent:
    ts: str
    coin: str
    event: str          # TRADE_KIMCHI | TRADE_REVERSE | REBALANCE | SKIP
    premium: float
    upbit_price_krw: float
    binance_price_usdt: float
    fx: float
    trade_qty: float = 0.0
    pnl_krw: float = 0.0
    fee_krw: float = 0.0
    round_trip_pnl_krw: float | None = None
    round_trip_premium: float | None = None
    hold_duration_sec: float | None = None
    actual_slippage_upbit: float | None = None
    actual_slippage_binance: float | None = None
    detail: str = ""


@dataclass
class CoinBalance:
    """4-balance state for a single coin."""
    symbol: str
    upbit_krw: float = 0.0       # 업비트 현금
    upbit_coin: float = 0.0      # 업비트 코인 수량
    binance_usdt: float = 0.0    # 바이낸스 USDT
    binance_coin: float = 0.0    # 바이낸스 코인 수량

    # Tracking
    total_trades: int = 0
    total_rebalances: int = 0
    daily_rebalances: int = 0
    realized_fee_krw: float = 0.0
    _last_trade_ts: float = 0.0
    open_position: dict | None = None

    def total_value_krw(self, upbit_price_krw: float, binance_price_usdt: float, fx: float) -> float:
        """Compute total portfolio value in KRW."""
        return (
            self.upbit_krw
            + self.upbit_coin * upbit_price_krw
            + self.binance_usdt * fx
            + self.binance_coin * binance_price_usdt * fx
        )

    def can_sell_upbit(self) -> bool:
        return self.upbit_coin > 1e-12

    def can_buy_upbit(self) -> bool:
        return self.upbit_krw > 1.0  # at least 1 KRW

    def can_sell_binance(self) -> bool:
        return self.binance_coin > 1e-12

    def can_buy_binance(self) -> bool:
        return self.binance_usdt > 0.01  # at least 0.01 USDT


@dataclass
class RebalancePortfolio:
    """Multi-coin portfolio with 4-balance tracking per coin."""
    balances: dict[str, CoinBalance] = field(default_factory=dict)
    events: list[TradeEvent] = field(default_factory=list)
    realized_pnl_krw: float = 0.0

    @staticmethod
    def _notional_krw_for_kimchi(
        b: CoinBalance,
        upbit_price_krw: float,
        fx: float,
    ) -> float:
        return min(b.upbit_coin * upbit_price_krw, b.binance_usdt * fx)

    @staticmethod
    def _notional_krw_for_reverse(
        b: CoinBalance,
        binance_price_usdt: float,
        fx: float,
    ) -> float:
        return min(b.upbit_krw, b.binance_coin * binance_price_usdt * fx)

    @staticmethod
    def _close_round_trip(
        b: CoinBalance,
        close_type: str,
        close_premium: float,
        close_fee_krw: float,
        close_ts: str,
        reopen_notional_krw: float,
        reopen_fee_krw: float,
    ) -> dict[str, float] | None:
        pos = b.open_position
        if not pos:
            return None
        if pos.get("type") == close_type:
            # Same-direction re-entry: refresh the opening leg to current trade snapshot.
            b.open_position = {
                "type": close_type,
                "open_ts": close_ts,
                "open_premium": close_premium,
                "notional_krw": max(reopen_notional_krw, 0.0),
                "open_fee_krw": max(reopen_fee_krw, 0.0),
            }
            return None

        round_trip_premium = abs(float(pos.get("open_premium", 0.0))) + abs(close_premium)
        notional_krw = float(pos.get("notional_krw", 0.0))
        gross_pnl = notional_krw * round_trip_premium
        total_fee = float(pos.get("open_fee_krw", 0.0)) + close_fee_krw
        net_pnl = gross_pnl - total_fee

        hold_sec = 0.0
        open_ts_raw = pos.get("open_ts")
        if isinstance(open_ts_raw, str) and open_ts_raw:
            try:
                opened = datetime.fromisoformat(open_ts_raw)
                closed = datetime.fromisoformat(close_ts)
                hold_sec = max((closed - opened).total_seconds(), 0.0)
            except Exception:
                hold_sec = 0.0

        b.open_position = None
        return {
            "round_trip_pnl_krw": net_pnl,
            "round_trip_premium": round_trip_premium,
            "hold_duration_sec": hold_sec,
        }

    @staticmethod
    def _open_round_trip(
        b: CoinBalance,
        trade_type: str,
        premium: float,
        notional_krw: float,
        fee_krw: float,
        ts: str,
    ) -> None:
        b.open_position = {
            "type": trade_type,
            "open_ts": ts,
            "open_premium": premium,
            "notional_krw": max(notional_krw, 0.0),
            "open_fee_krw": max(fee_krw, 0.0),
        }

    def init_coin(
        self,
        symbol: str,
        upbit_krw: float,
        upbit_coin: float,
        binance_usdt: float,
        binance_coin: float,
    ) -> None:
        """Initialize coin balances."""
        self.balances[symbol] = CoinBalance(
            symbol=symbol,
            upbit_krw=upbit_krw,
            upbit_coin=upbit_coin,
            binance_usdt=binance_usdt,
            binance_coin=binance_coin,
        )

    def get(self, symbol: str) -> CoinBalance:
        return self.balances[symbol]

    def execute_kimchi_trade(
        self,
        symbol: str,
        upbit_price_krw: float,
        binance_price_usdt: float,
        fx: float,
        fee_upbit_rate: float,
        fee_binance_rate: float,
        slippage_upbit_rate: float,
        slippage_binance_rate: float,
        trade_fraction: float = 1.0,
        ts: str = "",
    ) -> TradeEvent:
        """Kim-chi premium trade: sell ALL upbit coin, buy ALL with binance USDT.

        Premium > 0 → Upbit is expensive → sell coin at Upbit, buy coin at Binance.
        """
        b = self.balances[symbol]
        if not ts:
            ts = datetime.now(tz=timezone.utc).isoformat()

        premium = (upbit_price_krw - binance_price_usdt * fx) / (binance_price_usdt * fx)
        before_coin_krw = (b.upbit_coin * upbit_price_krw) + (b.binance_coin * binance_price_usdt * fx)
        before_cash_krw = b.upbit_krw + (b.binance_usdt * fx)

        fraction = max(0.0, min(float(trade_fraction), 1.0))
        round_trip_notional = 0.0

        # Split sell from Upbit coin side.
        sell_qty = b.upbit_coin * fraction
        effective_sell_price = upbit_price_krw * (1 - fee_upbit_rate - slippage_upbit_rate)
        krw_received = sell_qty * effective_sell_price
        upbit_fee_krw = sell_qty * upbit_price_krw * (fee_upbit_rate + slippage_upbit_rate)

        # Split buy from Binance USDT side.
        quote_usdt = b.binance_usdt * fraction
        effective_buy_price_usdt = binance_price_usdt * (1 + fee_binance_rate + slippage_binance_rate)
        buy_qty = quote_usdt / effective_buy_price_usdt if effective_buy_price_usdt > 0 else 0.0
        binance_fee_krw = quote_usdt * (fee_binance_rate + slippage_binance_rate) * fx
        round_trip_notional = min(sell_qty * upbit_price_krw, quote_usdt * fx)

        # Update balances
        b.upbit_krw += krw_received
        b.upbit_coin = max(b.upbit_coin - sell_qty, 0.0)
        b.binance_coin += buy_qty
        b.binance_usdt = max(b.binance_usdt - quote_usdt, 0.0)

        total_fee = upbit_fee_krw + binance_fee_krw
        b.realized_fee_krw += total_fee
        b.total_trades += 1

        after_coin_krw = (b.upbit_coin * upbit_price_krw) + (b.binance_coin * binance_price_usdt * fx)
        after_cash_krw = b.upbit_krw + (b.binance_usdt * fx)
        pnl = (after_cash_krw + after_coin_krw) - (before_cash_krw + before_coin_krw)

        event = TradeEvent(
            ts=ts, coin=symbol, event="TRADE_KIMCHI",
            premium=premium, upbit_price_krw=upbit_price_krw,
            binance_price_usdt=binance_price_usdt, fx=fx,
            trade_qty=sell_qty, pnl_krw=pnl, fee_krw=total_fee,
            detail=(
                f"split={fraction:.2f}, sell {sell_qty:.6f} on upbit, "
                f"buy {buy_qty:.6f} on binance (quote={quote_usdt:.4f} USDT)"
            ),
        )
        closed = self._close_round_trip(
            b=b,
            close_type="TRADE_KIMCHI",
            close_premium=premium,
            close_fee_krw=total_fee,
            close_ts=ts,
            reopen_notional_krw=round_trip_notional,
            reopen_fee_krw=total_fee,
        )
        if closed:
            event.round_trip_pnl_krw = closed["round_trip_pnl_krw"]
            event.round_trip_premium = closed["round_trip_premium"]
            event.hold_duration_sec = closed["hold_duration_sec"]
        else:
            self._open_round_trip(
                b=b,
                trade_type="TRADE_KIMCHI",
                premium=premium,
                notional_krw=round_trip_notional,
                fee_krw=total_fee,
                ts=ts,
            )
        self.events.append(event)
        self.realized_pnl_krw += pnl
        return event

    def execute_reverse_trade(
        self,
        symbol: str,
        upbit_price_krw: float,
        binance_price_usdt: float,
        fx: float,
        fee_upbit_rate: float,
        fee_binance_rate: float,
        slippage_upbit_rate: float,
        slippage_binance_rate: float,
        trade_fraction: float = 1.0,
        ts: str = "",
    ) -> TradeEvent:
        """Reverse premium trade: buy ALL with upbit KRW, sell ALL binance coin.

        Premium < 0 → Binance is expensive → sell coin at Binance, buy coin at Upbit.
        """
        b = self.balances[symbol]
        if not ts:
            ts = datetime.now(tz=timezone.utc).isoformat()

        premium = (upbit_price_krw - binance_price_usdt * fx) / (binance_price_usdt * fx)
        before_coin_krw = (b.upbit_coin * upbit_price_krw) + (b.binance_coin * binance_price_usdt * fx)
        before_cash_krw = b.upbit_krw + (b.binance_usdt * fx)

        fraction = max(0.0, min(float(trade_fraction), 1.0))
        round_trip_notional = 0.0

        # Split buy from Upbit KRW side.
        spend_krw = b.upbit_krw * fraction
        effective_buy_price = upbit_price_krw * (1 + fee_upbit_rate + slippage_upbit_rate)
        buy_qty = spend_krw / effective_buy_price if effective_buy_price > 0 else 0.0
        upbit_fee_krw = spend_krw * (fee_upbit_rate + slippage_upbit_rate)

        # Split sell from Binance coin side.
        sell_qty = b.binance_coin * fraction
        effective_sell_price_usdt = binance_price_usdt * (1 - fee_binance_rate - slippage_binance_rate)
        usdt_received = sell_qty * effective_sell_price_usdt
        binance_fee_krw = sell_qty * binance_price_usdt * (fee_binance_rate + slippage_binance_rate) * fx
        round_trip_notional = min(spend_krw, sell_qty * binance_price_usdt * fx)

        # Update balances
        b.upbit_coin += buy_qty
        b.upbit_krw = max(b.upbit_krw - spend_krw, 0.0)
        b.binance_usdt += usdt_received
        b.binance_coin = max(b.binance_coin - sell_qty, 0.0)

        total_fee = upbit_fee_krw + binance_fee_krw
        b.realized_fee_krw += total_fee
        b.total_trades += 1

        after_coin_krw = (b.upbit_coin * upbit_price_krw) + (b.binance_coin * binance_price_usdt * fx)
        after_cash_krw = b.upbit_krw + (b.binance_usdt * fx)
        pnl = (after_cash_krw + after_coin_krw) - (before_cash_krw + before_coin_krw)

        event = TradeEvent(
            ts=ts, coin=symbol, event="TRADE_REVERSE",
            premium=premium, upbit_price_krw=upbit_price_krw,
            binance_price_usdt=binance_price_usdt, fx=fx,
            trade_qty=sell_qty, pnl_krw=pnl, fee_krw=total_fee,
            detail=(
                f"split={fraction:.2f}, buy {buy_qty:.6f} on upbit (spend={spend_krw:.0f} KRW), "
                f"sell {sell_qty:.6f} on binance"
            ),
        )
        closed = self._close_round_trip(
            b=b,
            close_type="TRADE_REVERSE",
            close_premium=premium,
            close_fee_krw=total_fee,
            close_ts=ts,
            reopen_notional_krw=round_trip_notional,
            reopen_fee_krw=total_fee,
        )
        if closed:
            event.round_trip_pnl_krw = closed["round_trip_pnl_krw"]
            event.round_trip_premium = closed["round_trip_premium"]
            event.hold_duration_sec = closed["hold_duration_sec"]
        else:
            self._open_round_trip(
                b=b,
                trade_type="TRADE_REVERSE",
                premium=premium,
                notional_krw=round_trip_notional,
                fee_krw=total_fee,
                ts=ts,
            )
        self.events.append(event)
        self.realized_pnl_krw += pnl
        return event

    def execute_rebalance(
        self,
        symbol: str,
        upbit_price_krw: float,
        binance_price_usdt: float,
        fx: float,
        transfer_fee_coin_base: float,
        fx_conversion_fee_rate: float,
        direction: str,  # "binance_to_upbit" | "upbit_to_binance"
        ts: str = "",
    ) -> TradeEvent:
        """Execute 100% asset rebalancing between exchanges.

        direction="binance_to_upbit": coin from Binance → Upbit, cash from Upbit → Binance
        direction="upbit_to_binance": coin from Upbit → Binance, cash from Binance → Upbit
        """
        b = self.balances[symbol]
        if not ts:
            ts = datetime.now(tz=timezone.utc).isoformat()

        premium = (upbit_price_krw - binance_price_usdt * fx) / (binance_price_usdt * fx)
        val_before = b.total_value_krw(upbit_price_krw, binance_price_usdt, fx)
        total_fee_krw = 0.0

        target_ratio = 0.25
        target_value = max(val_before * target_ratio, 0.0)

        if direction == "binance_to_upbit":
            # Move only excess Binance coin value to Upbit.
            bn_coin_val = b.binance_coin * binance_price_usdt * fx
            excess_coin_val = max(bn_coin_val - target_value, 0.0)
            coin_to_transfer = (excess_coin_val / (binance_price_usdt * fx)) if (binance_price_usdt > 0 and fx > 0) else 0.0
            coin_transfer_amount = min(b.binance_coin, max(coin_to_transfer, 0.0))
            coin_fee = min(transfer_fee_coin_base, coin_transfer_amount)
            coin_transferred = max(coin_transfer_amount - coin_fee, 0.0)
            transfer_fee_krw = coin_fee * binance_price_usdt * fx
            b.binance_coin -= coin_transfer_amount
            b.upbit_coin += coin_transferred
            total_fee_krw += transfer_fee_krw

            # Move only excess Upbit KRW cash to Binance USDT.
            excess_upbit_krw = max(b.upbit_krw - target_value, 0.0)
            krw_to_convert = min(b.upbit_krw, excess_upbit_krw)
            usdt_received = (krw_to_convert / fx) * (1 - fx_conversion_fee_rate) if fx > 0 else 0.0
            fx_fee_krw = krw_to_convert * fx_conversion_fee_rate
            b.upbit_krw -= krw_to_convert
            b.binance_usdt += usdt_received
            total_fee_krw += fx_fee_krw

            detail = (
                f"transfer {coin_transferred:.6f}/{coin_transfer_amount:.6f} coin B→U (fee coin {coin_fee:.6f}), "
                f"transfer {krw_to_convert:.0f} KRW U→B as {usdt_received:.2f} USDT"
            )

        elif direction == "upbit_to_binance":
            # Move only excess Upbit coin value to Binance.
            up_coin_val = b.upbit_coin * upbit_price_krw
            excess_coin_val = max(up_coin_val - target_value, 0.0)
            coin_to_transfer = (excess_coin_val / upbit_price_krw) if upbit_price_krw > 0 else 0.0
            coin_transfer_amount = min(b.upbit_coin, max(coin_to_transfer, 0.0))
            coin_fee = min(transfer_fee_coin_base, coin_transfer_amount)
            coin_transferred = max(coin_transfer_amount - coin_fee, 0.0)
            transfer_fee_krw = coin_fee * upbit_price_krw
            b.upbit_coin -= coin_transfer_amount
            b.binance_coin += coin_transferred
            total_fee_krw += transfer_fee_krw

            # Move only excess Binance USDT cash to Upbit KRW.
            bn_cash_krw = b.binance_usdt * fx
            excess_bn_cash_krw = max(bn_cash_krw - target_value, 0.0)
            usdt_to_convert = min(b.binance_usdt, (excess_bn_cash_krw / fx) if fx > 0 else 0.0)
            krw_received = usdt_to_convert * fx * (1 - fx_conversion_fee_rate)
            fx_fee_krw = usdt_to_convert * fx * fx_conversion_fee_rate
            b.binance_usdt -= usdt_to_convert
            b.upbit_krw += krw_received
            total_fee_krw += fx_fee_krw

            detail = (
                f"transfer {coin_transferred:.6f}/{coin_transfer_amount:.6f} coin U→B (fee coin {coin_fee:.6f}), "
                f"transfer {usdt_to_convert:.2f} USDT B→U as {krw_received:.0f} KRW"
            )
        else:
            raise ValueError(f"unknown rebalance direction: {direction}")

        b.realized_fee_krw += total_fee_krw
        b.total_rebalances += 1
        b.daily_rebalances += 1

        val_after = b.total_value_krw(upbit_price_krw, binance_price_usdt, fx)
        pnl = val_after - val_before

        event = TradeEvent(
            ts=ts, coin=symbol, event="REBALANCE",
            premium=premium, upbit_price_krw=upbit_price_krw,
            binance_price_usdt=binance_price_usdt, fx=fx,
            pnl_krw=pnl, fee_krw=total_fee_krw, detail=detail,
        )
        self.events.append(event)
        self.realized_pnl_krw += pnl
        return event

    def reset_daily_counters(self) -> None:
        """Reset daily counters (call at start of each day)."""
        for b in self.balances.values():
            b.daily_rebalances = 0
