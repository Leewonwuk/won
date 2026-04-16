from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import csv
import json

from src.config import load_config
from src.backtest.historical_data import collect_last_nd_5m
from src.backtest.backtest_runner import run_backtest_from_csv, save_report_json, save_trade_events_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="N-day 5m backtest runner")
    parser.add_argument("--config", default="configs/sol.yaml", help="Config path")
    parser.add_argument("--days", type=int, default=30, help="Backtest window in days")
    parser.add_argument(
        "--out-prefix",
        default="data/backtest",
        help="Output file prefix directory",
    )
    parser.add_argument("--sweep", action="store_true", help="Run threshold sweep and keep trade_count>0 rows")
    return parser.parse_args()


def _save_sweep_csv(path: str, rows: list[dict]) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "entry_threshold_rate",
                "exit_threshold_rate",
                "trade_count",
                "total_return_rate",
                "total_pnl_krw",
                "win_rate",
                "max_drawdown_rate",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return str(p)


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = f"{args.out_prefix}/{cfg.symbol.lower()}_{args.days}d_5m_{stamp}.csv"
    report_path = f"{args.out_prefix}/{cfg.symbol.lower()}_{args.days}d_report_{stamp}.json"
    trades_path = f"{args.out_prefix}/{cfg.symbol.lower()}_{args.days}d_trades_{stamp}.csv"

    data_path = collect_last_nd_5m(
        upbit_market=cfg.upbit_market,
        binance_symbol=cfg.binance_symbol,
        out_csv=csv_path,
        days=args.days,
    )
    result = run_backtest_from_csv(
        csv_path=data_path,
        symbol=cfg.symbol,
        trade_size_base=cfg.trade_size_base,
        entry_threshold_rate=cfg.entry_threshold_rate,
        exit_threshold_rate=cfg.exit_threshold_rate,
        fee_upbit_rate=cfg.fee_upbit_rate,
        fee_binance_rate=cfg.fee_binance_rate,
        slippage_upbit_rate=cfg.slippage_upbit_rate,
        slippage_binance_rate=cfg.slippage_binance_rate,
        transfer_fee_upbit_to_binance_base=cfg.transfer_fee_upbit_to_binance_base,
        transfer_fee_binance_to_upbit_base=cfg.transfer_fee_binance_to_upbit_base,
        initial_upbit_krw=1_000_000,
        initial_binance_krw=1_000_000,
        use_full_capital_per_trade=True,
    )
    out = save_report_json(result, report_path)
    trades_out = save_trade_events_csv(result, trades_path)
    print(f"data_csv={data_path}")
    print(f"report_json={out}")
    print(f"trades_csv={trades_out}")
    print(
        "summary:",
        {
            "symbol": cfg.symbol,
            "timeframe": "5m",
            "days": args.days,
            "initial_upbit_krw": 1_000_000,
            "initial_binance_krw": 1_000_000,
            "use_full_capital_per_trade": True,
            "entry_threshold_rate": cfg.entry_threshold_rate,
            "exit_threshold_rate": cfg.exit_threshold_rate,
            "total_return_rate": round(result.total_return_rate, 6),
            "total_pnl_krw": round(result.total_pnl_krw, 2),
            "trade_count": result.trade_count,
            "win_rate": round(result.win_rate, 4),
            "max_drawdown_rate": round(result.max_drawdown_rate, 4),
        },
    )

    if args.sweep:
        # Keep a compact range around practical thresholds for early-stage tuning.
        if cfg.symbol.upper() == "SOL":
            entries = [0.0012, 0.0015, 0.0018, 0.0021, 0.0024, 0.0027, 0.0030]
        else:
            entries = [0.0010, 0.0013, 0.0016, 0.0019, 0.0022, 0.0025]

        sweep_rows: list[dict] = []
        for entry in entries:
            exit_thr = round(entry * 0.3, 6)
            r = run_backtest_from_csv(
                csv_path=data_path,
                symbol=cfg.symbol,
                trade_size_base=cfg.trade_size_base,
                entry_threshold_rate=entry,
                exit_threshold_rate=exit_thr,
                fee_upbit_rate=cfg.fee_upbit_rate,
                fee_binance_rate=cfg.fee_binance_rate,
                slippage_upbit_rate=cfg.slippage_upbit_rate,
                slippage_binance_rate=cfg.slippage_binance_rate,
                transfer_fee_upbit_to_binance_base=cfg.transfer_fee_upbit_to_binance_base,
                transfer_fee_binance_to_upbit_base=cfg.transfer_fee_binance_to_upbit_base,
                initial_upbit_krw=1_000_000,
                initial_binance_krw=1_000_000,
                use_full_capital_per_trade=True,
            )
            if r.trade_count > 0:
                sweep_rows.append(
                    {
                        "entry_threshold_rate": entry,
                        "exit_threshold_rate": exit_thr,
                        "trade_count": r.trade_count,
                        "total_return_rate": round(r.total_return_rate, 6),
                        "total_pnl_krw": round(r.total_pnl_krw, 2),
                        "win_rate": round(r.win_rate, 4),
                        "max_drawdown_rate": round(r.max_drawdown_rate, 4),
                    }
                )

        sweep_rows.sort(key=lambda x: (x["total_return_rate"], x["trade_count"]), reverse=True)
        sweep_path = f"{args.out_prefix}/{cfg.symbol.lower()}_{args.days}d_sweep_gt0_{stamp}.csv"
        sweep_out = _save_sweep_csv(sweep_path, sweep_rows)
        print(f"sweep_csv={sweep_out}")
        print("sweep_rows_gt0=", len(sweep_rows))
        if sweep_rows:
            print("best_sweep=", json.dumps(sweep_rows[0], ensure_ascii=False))


if __name__ == "__main__":
    main()

