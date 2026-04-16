"""Backtest runner v2 – 4-balance rebalancing arb simulation.

Reads 1m (or 5m) CSV data, applies the capital allocator logic per tick,
and produces a BacktestV2Result with all trade/rebalance events.

CSV expected columns: ts, upbit_close_krw, binance_close_usdt, usdtkrw_close
"""
from __future__ import annotations

import csv
import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.config import CoinConfig
from src.state.multi_portfolio import RebalancePortfolio, TradeEvent
from src.strategy.capital_allocator import Action, Decision, decide


@dataclass
class BacktestV2Result:
    symbol: str
    total_return_rate: float
    total_pnl_krw: float
    total_fee_krw: float
    trade_count: int
    rebalance_count: int
    win_count: int
    win_rate: float
    max_drawdown_rate: float
    wall_reject_count: int
    pnl_7d_krw: float
    pnl_14d_krw: float
    buy_hold_pnl_krw: float
    buy_hold_return_rate: float
    arbitrage_alpha_krw: float
    arbitrage_alpha_rate: float
    start_equity_krw: float
    end_equity_krw: float
    rows_processed: int
    events: list[TradeEvent] = field(default_factory=list)


def _load_rows(csv_path: str) -> list[dict]:
    with Path(csv_path).open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def run_backtest_v2(
    csv_path: str,
    coin_cfg: CoinConfig,
    fx_fallback: float = 1350.0,
) -> BacktestV2Result:
    """Run 4-balance backtest from CSV data."""
    rows = _load_rows(csv_path)
    if not rows:
        raise ValueError(f"No data in {csv_path}")

    # Determine initial coin quantities from first row prices
    first = rows[0]
    upbit_price_0 = float(first["upbit_close_krw"])
    binance_price_0 = float(first["binance_close_usdt"])
    fx_0 = float(first.get("usdtkrw_close", fx_fallback))

    if upbit_price_0 <= 0 or binance_price_0 <= 0:
        raise ValueError("First row has zero prices")

    upbit_coin_qty = coin_cfg.initial_upbit_coin_krw / upbit_price_0
    binance_coin_qty = coin_cfg.initial_binance_coin_krw / (binance_price_0 * fx_0)
    binance_usdt = coin_cfg.initial_binance_usdt_krw / fx_0

    portfolio = RebalancePortfolio()
    portfolio.init_coin(
        symbol=coin_cfg.symbol,
        upbit_krw=coin_cfg.initial_upbit_krw,
        upbit_coin=upbit_coin_qty,
        binance_usdt=binance_usdt,
        binance_coin=binance_coin_qty,
    )

    start_equity = (
        coin_cfg.initial_upbit_krw
        + coin_cfg.initial_upbit_coin_krw
        + coin_cfg.initial_binance_usdt_krw
        + coin_cfg.initial_binance_coin_krw
    )
    peak_equity = start_equity
    max_dd = 0.0
    wins = 0
    wall_reject_count = 0
    upbit_vol_hist: list[float] = []
    binance_vol_hist: list[float] = []
    equity_timeline: list[tuple[datetime, float]] = []

    for row in rows:
        up = float(row["upbit_close_krw"])
        bn_u = float(row["binance_close_usdt"])
        fx = float(row.get("usdtkrw_close", fx_fallback))

        if up <= 0 or bn_u <= 0 or fx <= 0:
            continue

        b = portfolio.get(coin_cfg.symbol)
        upbit_vol = float(row.get("upbit_volume", 0.0) or 0.0)
        binance_vol = float(row.get("binance_volume", 0.0) or 0.0)
        binance_taker_buy = float(row.get("binance_taker_buy_volume", 0.0) or 0.0)

        decision = decide(
            symbol=coin_cfg.symbol,
            upbit_price_krw=up,
            binance_bid_price_usdt=bn_u,
            binance_ask_price_usdt=bn_u,
            fx=fx,
            upbit_krw=b.upbit_krw,
            upbit_coin=b.upbit_coin,
            binance_usdt=b.binance_usdt,
            binance_coin=b.binance_coin,
            entry_threshold_rate=coin_cfg.entry_threshold_rate,
            fee_upbit_rate=coin_cfg.fee_upbit_rate,
            fee_binance_rate=coin_cfg.fee_binance_rate,
            slippage_upbit_rate=coin_cfg.slippage_upbit_rate,
            slippage_binance_rate=coin_cfg.slippage_binance_rate,
            transfer_fee_coin_base_utob=coin_cfg.transfer_fee_upbit_to_binance_base,
            transfer_fee_coin_base_btou=coin_cfg.transfer_fee_binance_to_upbit_base,
            fx_conversion_fee_rate=coin_cfg.fx_conversion_fee_rate,
            rebalance_profit_multiplier=coin_cfg.rebalance_profit_multiplier,
            rebalance_imbalance_threshold=coin_cfg.rebalance_imbalance_threshold,
            daily_rebalances=b.daily_rebalances,
            max_daily_rebalances=coin_cfg.max_daily_rebalances,
            emergency_cash_ratio=coin_cfg.emergency_cash_ratio,
            emergency_coin_ratio=coin_cfg.emergency_coin_ratio,
            target_portfolio_ratio=coin_cfg.target_portfolio_ratio,
        )

        # Optional wall/orderflow proxy filter:
        # - liquidity guard from rolling median volume
        # - directional guard from binance taker-buy ratio
        if coin_cfg.wall_filter_enabled and decision.action in (Action.TRADE_KIMCHI, Action.TRADE_REVERSE):
            allow = True

            if len(upbit_vol_hist) >= 20 and len(binance_vol_hist) >= 20:
                up_median = statistics.median(upbit_vol_hist[-120:])
                bn_median = statistics.median(binance_vol_hist[-120:])
                if up_median > 0 and upbit_vol < (up_median * coin_cfg.wall_min_liquidity_ratio):
                    allow = False
                if bn_median > 0 and binance_vol < (bn_median * coin_cfg.wall_min_liquidity_ratio):
                    allow = False

            taker_buy_ratio = (binance_taker_buy / binance_vol) if binance_vol > 0 else 0.5
            if decision.action == Action.TRADE_KIMCHI and taker_buy_ratio > coin_cfg.wall_buy_binance_taker_buy_ratio_max:
                allow = False
            if decision.action == Action.TRADE_REVERSE and taker_buy_ratio < coin_cfg.wall_sell_binance_taker_buy_ratio_min:
                allow = False

            if not allow:
                wall_reject_count += 1
                # Treat as hold when wall filter rejects this entry.
                decision = Decision(
                    action=Action.HOLD,
                    symbol=decision.symbol,
                    premium=decision.premium,
                    reason="wall_filter_reject",
                )

        ts = row.get("ts", "")

        if decision.action == Action.TRADE_KIMCHI:
            event = portfolio.execute_kimchi_trade(
                symbol=coin_cfg.symbol,
                upbit_price_krw=up, binance_price_usdt=bn_u, fx=fx,
                fee_upbit_rate=coin_cfg.fee_upbit_rate,
                fee_binance_rate=coin_cfg.fee_binance_rate,
                slippage_upbit_rate=coin_cfg.slippage_upbit_rate,
                slippage_binance_rate=coin_cfg.slippage_binance_rate,
                trade_fraction=coin_cfg.entry_split_fraction,
                ts=ts,
            )
            if event.pnl_krw > 0:
                wins += 1

        elif decision.action == Action.TRADE_REVERSE:
            event = portfolio.execute_reverse_trade(
                symbol=coin_cfg.symbol,
                upbit_price_krw=up, binance_price_usdt=bn_u, fx=fx,
                fee_upbit_rate=coin_cfg.fee_upbit_rate,
                fee_binance_rate=coin_cfg.fee_binance_rate,
                slippage_upbit_rate=coin_cfg.slippage_upbit_rate,
                slippage_binance_rate=coin_cfg.slippage_binance_rate,
                trade_fraction=coin_cfg.entry_split_fraction,
                ts=ts,
            )
            if event.pnl_krw > 0:
                wins += 1

        elif decision.action in (Action.REBALANCE_B_TO_U, Action.REBALANCE_U_TO_B):
            direction = "binance_to_upbit" if decision.action == Action.REBALANCE_B_TO_U else "upbit_to_binance"
            transfer_fee = (coin_cfg.transfer_fee_binance_to_upbit_base
                            if direction == "binance_to_upbit"
                            else coin_cfg.transfer_fee_upbit_to_binance_base)
            portfolio.execute_rebalance(
                symbol=coin_cfg.symbol,
                upbit_price_krw=up, binance_price_usdt=bn_u, fx=fx,
                transfer_fee_coin_base=transfer_fee,
                fx_conversion_fee_rate=coin_cfg.fx_conversion_fee_rate,
                direction=direction, ts=ts,
            )

        # Track equity and drawdown
        equity = b.total_value_krw(up, bn_u, fx)
        if equity > peak_equity:
            peak_equity = equity
        dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

        upbit_vol_hist.append(upbit_vol)
        binance_vol_hist.append(binance_vol)

        ts_raw = row.get("ts", "")
        try:
            ts_dt = datetime.fromisoformat(ts_raw)
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=timezone.utc)
            equity_timeline.append((ts_dt.astimezone(timezone.utc), equity))
        except Exception:
            # Skip malformed timestamps in window-pnl calculation.
            pass

    # Final values
    last = rows[-1]
    up_final = float(last["upbit_close_krw"])
    bn_final = float(last["binance_close_usdt"])
    fx_final = float(last.get("usdtkrw_close", fx_fallback))
    b = portfolio.get(coin_cfg.symbol)
    end_equity = b.total_value_krw(up_final, bn_final, fx_final)

    trade_count = b.total_trades
    rebalance_count = b.total_rebalances

    # Benchmark: buy-and-hold from initial allocation to final prices
    initial_upbit_coin = coin_cfg.initial_upbit_coin_krw / upbit_price_0
    initial_binance_coin = coin_cfg.initial_binance_coin_krw / (binance_price_0 * fx_0)
    initial_binance_usdt = coin_cfg.initial_binance_usdt_krw / fx_0
    buy_hold_end_equity = (
        coin_cfg.initial_upbit_krw
        + initial_upbit_coin * up_final
        + initial_binance_coin * (bn_final * fx_final)
        + initial_binance_usdt * fx_final
    )
    buy_hold_pnl = buy_hold_end_equity - start_equity
    buy_hold_return = (buy_hold_pnl / start_equity) if start_equity > 0 else 0.0

    total_pnl = end_equity - start_equity
    alpha_pnl = total_pnl - buy_hold_pnl
    alpha_rate = (alpha_pnl / start_equity) if start_equity > 0 else 0.0

    pnl_7d_krw = 0.0
    pnl_14d_krw = 0.0
    if equity_timeline:
        end_ts = equity_timeline[-1][0]
        end_eq = equity_timeline[-1][1]
        cutoff_7d = end_ts - timedelta(days=7)
        cutoff_14d = end_ts - timedelta(days=14)

        eq_7d = next((eq for ts, eq in equity_timeline if ts >= cutoff_7d), None)
        eq_14d = next((eq for ts, eq in equity_timeline if ts >= cutoff_14d), None)

        if eq_7d is not None:
            pnl_7d_krw = end_eq - eq_7d
        if eq_14d is not None:
            pnl_14d_krw = end_eq - eq_14d

    return BacktestV2Result(
        symbol=coin_cfg.symbol,
        total_return_rate=(end_equity - start_equity) / start_equity if start_equity > 0 else 0.0,
        total_pnl_krw=total_pnl,
        total_fee_krw=b.realized_fee_krw,
        trade_count=trade_count,
        rebalance_count=rebalance_count,
        win_count=wins,
        win_rate=wins / trade_count if trade_count > 0 else 0.0,
        max_drawdown_rate=max_dd,
        wall_reject_count=wall_reject_count,
        pnl_7d_krw=pnl_7d_krw,
        pnl_14d_krw=pnl_14d_krw,
        buy_hold_pnl_krw=buy_hold_pnl,
        buy_hold_return_rate=buy_hold_return,
        arbitrage_alpha_krw=alpha_pnl,
        arbitrage_alpha_rate=alpha_rate,
        start_equity_krw=start_equity,
        end_equity_krw=end_equity,
        rows_processed=len(rows),
        events=portfolio.events,
    )


def save_v2_report(result: BacktestV2Result, path: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "symbol": result.symbol,
        "total_return_rate": result.total_return_rate,
        "total_pnl_krw": result.total_pnl_krw,
        "total_fee_krw": result.total_fee_krw,
        "trade_count": result.trade_count,
        "rebalance_count": result.rebalance_count,
        "win_count": result.win_count,
        "win_rate": result.win_rate,
        "max_drawdown_rate": result.max_drawdown_rate,
        "wall_reject_count": result.wall_reject_count,
        "pnl_7d_krw": result.pnl_7d_krw,
        "pnl_14d_krw": result.pnl_14d_krw,
        "buy_hold_pnl_krw": result.buy_hold_pnl_krw,
        "buy_hold_return_rate": result.buy_hold_return_rate,
        "arbitrage_alpha_krw": result.arbitrage_alpha_krw,
        "arbitrage_alpha_rate": result.arbitrage_alpha_rate,
        "start_equity_krw": result.start_equity_krw,
        "end_equity_krw": result.end_equity_krw,
        "rows_processed": result.rows_processed,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def save_v2_events_csv(result: BacktestV2Result, path: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not result.events:
        p.write_text("", encoding="utf-8")
        return str(p)
    keys = [
        "ts", "coin", "event", "premium", "upbit_price_krw",
        "binance_price_usdt", "fx", "trade_qty", "pnl_krw",
        "fee_krw", "detail",
    ]
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for ev in result.events:
            writer.writerow({k: getattr(ev, k, "") for k in keys})
    return str(p)
