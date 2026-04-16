from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import json

from src.models import OrderBookTop, SpreadInput
from src.state.portfolio import PortfolioState
from src.strategy.signal import SignalEngine
from src.strategy.spread_calc import calc_edge


@dataclass(slots=True)
class BacktestResult:
    total_return_rate: float
    total_pnl_krw: float
    trade_count: int
    win_rate: float
    max_drawdown_rate: float
    start_equity_krw: float
    end_equity_krw: float
    rows: int
    trade_events: list[dict]


def _load_rows(csv_path: str) -> list[dict]:
    with Path(csv_path).open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def run_backtest_from_csv(
    csv_path: str,
    symbol: str,
    trade_size_base: float,
    entry_threshold_rate: float,
    exit_threshold_rate: float,
    fee_upbit_rate: float,
    fee_binance_rate: float,
    slippage_upbit_rate: float,
    slippage_binance_rate: float,
    transfer_fee_upbit_to_binance_base: float,
    transfer_fee_binance_to_upbit_base: float,
    initial_upbit_krw: float = 1_000_000,
    initial_binance_krw: float = 1_000_000,
    use_full_capital_per_trade: bool = False,
) -> BacktestResult:
    rows = _load_rows(csv_path)
    signal = SignalEngine(entry_threshold_rate=entry_threshold_rate, exit_threshold_rate=exit_threshold_rate, cooldown_sec=0)
    portfolio = PortfolioState()
    start_equity = initial_upbit_krw + initial_binance_krw
    equity = start_equity
    peak_equity = equity
    max_dd = 0.0
    trades = 0
    wins = 0
    trade_events: list[dict] = []

    for r in rows:
        up = float(r["upbit_close_krw"])
        bn_u = float(r["binance_close_usdt"])
        fx = float(r["usdtkrw_close"])
        dynamic_trade_size_base = trade_size_base
        if use_full_capital_per_trade:
            # Use 100% of each side's KRW notional on every trade decision.
            max_by_upbit = initial_upbit_krw / up if up > 0 else 0.0
            max_by_binance = initial_binance_krw / (bn_u * fx) if (bn_u * fx) > 0 else 0.0
            dynamic_trade_size_base = min(max_by_upbit, max_by_binance)

        snapshot = SpreadInput(
            upbit_krw=OrderBookTop(exchange="upbit", symbol=f"KRW-{symbol}", bid=up, ask=up, ts=r["ts"]),
            binance_usdt=OrderBookTop(exchange="binance", symbol=f"{symbol}USDT", bid=bn_u, ask=bn_u, ts=r["ts"]),
            fx_krw_per_usdt=fx,
            fee_upbit_rate=fee_upbit_rate,
            fee_binance_rate=fee_binance_rate,
            slippage_upbit_rate=slippage_upbit_rate,
            slippage_binance_rate=slippage_binance_rate,
        )
        edge = calc_edge(
            snapshot=snapshot,
            symbol=symbol,
            trade_size_base=dynamic_trade_size_base,
            transfer_fee_upbit_to_binance_base=transfer_fee_upbit_to_binance_base,
            transfer_fee_binance_to_upbit_base=transfer_fee_binance_to_upbit_base,
        )
        decision = signal.decide(
            edge=edge,
            has_open_position=portfolio.is_open,
            position_open_at=portfolio.open_timestamp if portfolio.is_open else None,
        )
        if decision.action == "OPEN_UPBIT_SHORT_BINANCE_LONG":
            portfolio.open_position("UPBIT_SHORT_BINANCE_LONG", dynamic_trade_size_base, up, bn_u * fx)
            trade_events.append(
                {
                    "ts": r["ts"],
                    "event": "OPEN",
                    "direction": "UPBIT_SHORT_BINANCE_LONG",
                    "edge_rate": round(decision.edge_rate, 8),
                    "entry_threshold_rate": entry_threshold_rate,
                    "exit_threshold_rate": exit_threshold_rate,
                    "trade_size_base": round(dynamic_trade_size_base, 8),
                    "upbit_price_krw": up,
                    "binance_price_usdt": bn_u,
                    "fx_krw_per_usdt": fx,
                }
            )
        elif decision.action == "OPEN_UPBIT_LONG_BINANCE_SHORT":
            portfolio.open_position("UPBIT_LONG_BINANCE_SHORT", dynamic_trade_size_base, up, bn_u * fx)
            trade_events.append(
                {
                    "ts": r["ts"],
                    "event": "OPEN",
                    "direction": "UPBIT_LONG_BINANCE_SHORT",
                    "edge_rate": round(decision.edge_rate, 8),
                    "entry_threshold_rate": entry_threshold_rate,
                    "exit_threshold_rate": exit_threshold_rate,
                    "trade_size_base": round(dynamic_trade_size_base, 8),
                    "upbit_price_krw": up,
                    "binance_price_usdt": bn_u,
                    "fx_krw_per_usdt": fx,
                }
            )
        elif decision.action == "CLOSE":
            pnl = portfolio.close_position(up, bn_u * fx)
            trades += 1
            if pnl > 0:
                wins += 1
            trade_events.append(
                {
                    "ts": r["ts"],
                    "event": "CLOSE",
                    "direction": "NONE",
                    "edge_rate": round(decision.edge_rate, 8),
                    "entry_threshold_rate": entry_threshold_rate,
                    "exit_threshold_rate": exit_threshold_rate,
                    "trade_size_base": round(dynamic_trade_size_base, 8),
                    "upbit_price_krw": up,
                    "binance_price_usdt": bn_u,
                    "fx_krw_per_usdt": fx,
                    "pnl_krw": round(pnl, 2),
                    "cum_pnl_krw": round(portfolio.realized_pnl_krw, 2),
                }
            )

        equity = start_equity + portfolio.realized_pnl_krw
        if equity > peak_equity:
            peak_equity = equity
        dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    total_pnl = portfolio.realized_pnl_krw
    end_equity = start_equity + total_pnl
    return BacktestResult(
        total_return_rate=(end_equity - start_equity) / start_equity,
        total_pnl_krw=total_pnl,
        trade_count=trades,
        win_rate=(wins / trades) if trades > 0 else 0.0,
        max_drawdown_rate=max_dd,
        start_equity_krw=start_equity,
        end_equity_krw=end_equity,
        rows=len(rows),
        trade_events=trade_events,
    )


def save_report_json(result: BacktestResult, path: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "total_return_rate": result.total_return_rate,
        "total_pnl_krw": result.total_pnl_krw,
        "trade_count": result.trade_count,
        "win_rate": result.win_rate,
        "max_drawdown_rate": result.max_drawdown_rate,
        "start_equity_krw": result.start_equity_krw,
        "end_equity_krw": result.end_equity_krw,
        "rows": result.rows,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def save_trade_events_csv(result: BacktestResult, path: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not result.trade_events:
        p.write_text("", encoding="utf-8")
        return str(p)
    keys = [
        "ts",
        "event",
        "direction",
        "edge_rate",
        "entry_threshold_rate",
        "exit_threshold_rate",
        "trade_size_base",
        "upbit_price_krw",
        "binance_price_usdt",
        "fx_krw_per_usdt",
        "pnl_krw",
        "cum_pnl_krw",
    ]
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in result.trade_events:
            writer.writerow(row)
    return str(p)

