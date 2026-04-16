"""Threshold + split/slippage sweep utility for v2 backtests.

Usage:
    python -m src.tools.threshold_sweep
    python -m src.tools.threshold_sweep --days 7 --thresholds 0.004,0.005
"""
from __future__ import annotations

import argparse
import copy
import csv
from collections import defaultdict
from pathlib import Path

from src.backtest.backtest_v2 import BacktestV2Result, run_backtest_v2
from src.backtest.historical_data import collect_last_nd_with_tag
from src.config import CoinConfig, load_multi_config

DEFAULT_THRESHOLDS = [0.0030, 0.0035, 0.0040, 0.0043, 0.0045, 0.0050, 0.0055, 0.0060, 0.0070]
DEFAULT_SPLIT_FRACTIONS = [0.20, 0.25, 0.35]
DEFAULT_UPBIT_SLIPPAGES = [0.0015, 0.0020, 0.0030]
DEFAULT_DAYS = [7, 14, 21]
DEFAULT_RESOLUTION = 1
OUT_CSV = Path("data/backtest/threshold_sweep_result.csv")


def _parse_int_list(raw: str) -> list[int]:
    out: list[int] = []
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        out.append(int(tok))
    return out


def _parse_float_list(raw: str) -> list[float]:
    out: list[float] = []
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        out.append(float(tok))
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Sweep threshold + split_fraction + upbit_slippage for TRX/SOL v2 backtests"
    )
    p.add_argument("--config", default="configs/multi.yaml")
    p.add_argument("--days", default="7,14,21", help="Comma-separated day windows")
    p.add_argument("--thresholds", default=",".join(f"{x:.4f}" for x in DEFAULT_THRESHOLDS))
    p.add_argument("--split-fractions", default=",".join(f"{x:.2f}" for x in DEFAULT_SPLIT_FRACTIONS))
    p.add_argument("--upbit-slippages", default=",".join(f"{x:.4f}" for x in DEFAULT_UPBIT_SLIPPAGES))
    p.add_argument("--resolution", type=int, default=DEFAULT_RESOLUTION, choices=[1, 5])
    p.add_argument("--symbols", default="TRX,SOL", help="Comma-separated symbols")
    return p.parse_args()


def _collect_data(coin_cfg: CoinConfig, days: int, minutes: int) -> str:
    return collect_last_nd_with_tag(
        symbol=coin_cfg.symbol,
        upbit_market=coin_cfg.upbit_market,
        binance_symbol=coin_cfg.binance_symbol,
        n_days=days,
        out_dir="data/backtest",
        tag=f"{days}d_{minutes}m_sweep",
        minutes=minutes,
    )


def _format_money(v: float) -> str:
    return f"{v:,.0f}"


def _print_symbol_summary(rows: list[dict], symbol: str) -> None:
    print(f"\n=== {symbol} sweep summary (best alpha per day) ===")
    days_order = sorted({int(r["days"]) for r in rows})
    hdr = ["days", "threshold", "split", "upbit_slip", "trades", "alpha", "net", "roi", "mdd"]
    print(" | ".join(hdr))
    print("-" * (len(" | ".join(hdr)) + 4))
    for d in days_order:
        day_rows = [r for r in rows if int(r["days"]) == d]
        if not day_rows:
            continue
        best = max(day_rows, key=lambda x: float(x["alpha_pnl_krw"]))
        cells = [
            str(d),
            str(best["threshold_pct"]),
            f"{float(best['split_fraction']):.2f}",
            f"{float(best['slippage_upbit_rate'])*100:.2f}%",
            str(best["trade_count"]),
            _format_money(float(best["alpha_pnl_krw"])),
            _format_money(float(best["net_profit_krw"])),
            f"{float(best['roi_pct']):.3f}%",
            f"{float(best['mdd_pct']):.2f}%",
        ]
        print(" | ".join(cells))


def _to_row(
    symbol: str,
    days: int,
    threshold: float,
    split_fraction: float,
    slippage_upbit_rate: float,
    result: BacktestV2Result,
) -> dict:
    return {
        "symbol": symbol,
        "days": days,
        "threshold_rate": threshold,
        "threshold_pct": f"{threshold*100:.2f}%",
        "split_fraction": split_fraction,
        "slippage_upbit_rate": slippage_upbit_rate,
        "trade_count": int(result.trade_count),
        "net_profit_krw": round(float(result.total_pnl_krw), 1),
        "alpha_pnl_krw": round(float(result.arbitrage_alpha_krw), 1),
        "roi_pct": round(float(result.total_return_rate) * 100.0, 3),
        "mdd_pct": round(float(result.max_drawdown_rate) * 100.0, 2),
    }


def main() -> None:
    args = parse_args()
    cfg = load_multi_config(args.config)
    days_list = _parse_int_list(args.days)
    thresholds = _parse_float_list(args.thresholds)
    split_fractions = _parse_float_list(args.split_fractions)
    upbit_slippages = _parse_float_list(args.upbit_slippages)
    symbols = {s.strip().upper() for s in args.symbols.split(",") if s.strip()}

    coin_cfgs = [c for c in cfg.coins if c.symbol.upper() in symbols]
    if not coin_cfgs:
        raise SystemExit("No matching symbols found in config")

    data_cache: dict[tuple[str, int], str] = {}
    for coin_cfg in coin_cfgs:
        for days in days_list:
            key = (coin_cfg.symbol, days)
            data_cache[key] = _collect_data(coin_cfg, days=days, minutes=args.resolution)

    rows: list[dict] = []
    for coin_cfg in coin_cfgs:
        for days in days_list:
            csv_path = data_cache[(coin_cfg.symbol, days)]
            for threshold in thresholds:
                for split_fraction in split_fractions:
                    for upbit_slippage in upbit_slippages:
                        test_cfg = copy.deepcopy(coin_cfg)
                        test_cfg.entry_threshold_rate = float(threshold)
                        test_cfg.entry_split_fraction = float(split_fraction)
                        test_cfg.slippage_upbit_rate = float(upbit_slippage)
                        result = run_backtest_v2(
                            csv_path=csv_path,
                            coin_cfg=test_cfg,
                            fx_fallback=float(cfg.fx_krw_per_usdt),
                        )
                        rows.append(
                            _to_row(
                                coin_cfg.symbol,
                                days,
                                float(threshold),
                                float(split_fraction),
                                float(upbit_slippage),
                                result,
                            )
                        )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "symbol",
                "days",
                "threshold_rate",
                "threshold_pct",
                "split_fraction",
                "slippage_upbit_rate",
                "trade_count",
                "net_profit_krw",
                "alpha_pnl_krw",
                "roi_pct",
                "mdd_pct",
            ],
        )
        w.writeheader()
        for r in rows:
            w.writerow(r)

    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_symbol[str(r["symbol"])].append(r)
    for symbol in sorted(by_symbol):
        _print_symbol_summary(by_symbol[symbol], symbol)

    # Print global top candidates (alpha>0, then net, then trade count).
    ranked = sorted(
        rows,
        key=lambda r: (
            float(r["alpha_pnl_krw"]) > 0,
            float(r["alpha_pnl_krw"]),
            float(r["net_profit_krw"]),
            int(r["trade_count"]),
        ),
        reverse=True,
    )
    print("\n=== Top 10 candidates ===")
    print("symbol | days | threshold | split | upbit_slip | trades | alpha | net")
    for r in ranked[:10]:
        print(
            f"{r['symbol']} | {r['days']} | {r['threshold_pct']} | "
            f"{float(r['split_fraction']):.2f} | {float(r['slippage_upbit_rate'])*100:.2f}% | "
            f"{r['trade_count']} | {_format_money(float(r['alpha_pnl_krw']))} | {_format_money(float(r['net_profit_krw']))}"
        )

    print(f"\nSaved CSV: {OUT_CSV}")


if __name__ == "__main__":
    main()
