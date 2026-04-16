from __future__ import annotations

import argparse
import csv
import glob
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.backtest.backtest_v2 import run_backtest_v2
from src.backtest.historical_data import collect_last_nd_with_tag
from src.config import CoinConfig, load_multi_config

# Lower bounds ~ fee+slip (~0.0025); short-window tuning needs finer low end for SOL/TRX.
CANDIDATE_THRESHOLDS: dict[str, list[float]] = {
    "SOL": [0.0025, 0.0026, 0.0028, 0.0030, 0.0035, 0.0040, 0.0045, 0.0050, 0.0060, 0.0070, 0.0080, 0.0100],
    "TRX": [0.0028, 0.0030, 0.0035, 0.0040, 0.0043, 0.0045, 0.0050, 0.0060, 0.0070, 0.0080],
}
DEFAULT_CANDIDATES = [0.0040, 0.0050, 0.0060, 0.0080, 0.0100]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Autotune entry_threshold_rate for v2 strategy")
    parser.add_argument("--config", default="configs/multi.yaml", help="Multi-coin config path")
    parser.add_argument("--days", type=int, default=30, help="Lookback days for base backtest")
    parser.add_argument("--dry-run", action="store_true", help="Recommend only, do not modify config")
    parser.add_argument(
        "--skip-collect",
        action="store_true",
        help="Reuse latest *_Nd_1m CSV if present",
    )
    return parser.parse_args()


def _find_latest_csv(symbol: str, days: int) -> str | None:
    pattern = f"data/backtest/{symbol.lower()}_{days}d_1m_*.csv"
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def _collect_or_get_csv(coin: CoinConfig, days: int, skip_collect: bool) -> str:
    if skip_collect:
        latest = _find_latest_csv(coin.symbol, days)
        if latest:
            return latest

    ts_tag = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    return collect_last_nd_with_tag(
        symbol=coin.symbol,
        upbit_market=coin.upbit_market,
        binance_symbol=coin.binance_symbol,
        n_days=days,
        out_dir="data/backtest",
        tag=f"{days}d_1m_{ts_tag}",
        minutes=1,
    )


def run_grid_search(symbol: str, csv_path: str, base_config: CoinConfig, fx_fallback: float) -> list[dict[str, Any]]:
    candidates = CANDIDATE_THRESHOLDS.get(symbol.upper(), DEFAULT_CANDIDATES)
    rows: list[dict[str, Any]] = []

    for threshold in candidates:
        cfg = replace(base_config, entry_threshold_rate=threshold)
        result = run_backtest_v2(csv_path=csv_path, coin_cfg=cfg, fx_fallback=fx_fallback)
        rows.append(
            {
                "entry_threshold_rate": threshold,
                "total_pnl_krw": result.total_pnl_krw,
                "total_fee_krw": result.total_fee_krw,
                "max_drawdown_rate": result.max_drawdown_rate,
                "trade_count": result.trade_count,
                "pnl_7d_krw": result.pnl_7d_krw,
                "pnl_14d_krw": result.pnl_14d_krw,
                "buy_hold_pnl_krw": result.buy_hold_pnl_krw,
                "arbitrage_alpha_krw": result.arbitrage_alpha_krw,
                "arbitrage_alpha_rate": result.arbitrage_alpha_rate,
            }
        )

    out_dir = Path("data/backtest")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{symbol.lower()}_grid_results_{datetime.now().strftime('%Y%m%d')}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "entry_threshold_rate",
                "total_pnl_krw",
                "total_fee_krw",
                "max_drawdown_rate",
                "trade_count",
                "pnl_7d_krw",
                "pnl_14d_krw",
                "buy_hold_pnl_krw",
                "arbitrage_alpha_krw",
                "arbitrage_alpha_rate",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"[GRID] 결과 저장: {out_path}")
    return rows


def select_best_threshold(results: list[dict[str, Any]], prev_threshold: float) -> float:
    candidates = [r for r in results if float(r["trade_count"]) >= 3]
    candidates = [r for r in candidates if float(r["max_drawdown_rate"]) <= 0.08]
    candidates = [r for r in candidates if float(r["arbitrage_alpha_krw"]) > 0]
    candidates = [
        r for r in candidates if float(r["pnl_7d_krw"]) > 0 and float(r["pnl_14d_krw"]) > 0
    ]

    if not candidates:
        print(f"[AUTOTUNE] 통과 후보 없음 -> 전일 threshold 유지: {prev_threshold}")
        return prev_threshold

    best_row = max(candidates, key=lambda r: float(r["arbitrage_alpha_krw"]))
    best_threshold = float(best_row["entry_threshold_rate"])

    print(f"[AUTOTUNE] 선택된 threshold: {best_threshold}")
    print(f"  -> 아비트리지 알파: {float(best_row['arbitrage_alpha_krw']):,.0f} KRW")
    print(f"  -> 단순보유 수익: {float(best_row['buy_hold_pnl_krw']):,.0f} KRW")
    print(f"  -> 전략 총수익: {float(best_row['total_pnl_krw']):,.0f} KRW")
    print(f"  -> MDD: {float(best_row['max_drawdown_rate']) * 100:.2f}%")
    print(f"  -> 거래횟수: {int(best_row['trade_count'])}건")
    return best_threshold


def _update_config_thresholds(config_path: str, selected: dict[str, float]) -> None:
    path = Path(config_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    coins = data.get("coins", [])
    for coin in coins:
        symbol = str(coin.get("symbol", "")).upper()
        if symbol in selected:
            coin["entry_threshold_rate"] = float(selected[symbol])
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> None:
    args = parse_args()
    cfg = load_multi_config(args.config)
    selected: dict[str, float] = {}
    log_lines: list[str] = []

    for coin in cfg.coins:
        print(f"\n=== AUTOTUNE {coin.symbol} ===")
        csv_path = _collect_or_get_csv(coin=coin, days=args.days, skip_collect=args.skip_collect)
        print(f"[DATA] csv={csv_path}")

        results = run_grid_search(
            symbol=coin.symbol,
            csv_path=csv_path,
            base_config=coin,
            fx_fallback=cfg.fx_krw_per_usdt,
        )
        best = select_best_threshold(results=results, prev_threshold=coin.entry_threshold_rate)
        selected[coin.symbol.upper()] = best
        log_lines.append(
            f"{coin.symbol}: prev={coin.entry_threshold_rate} -> selected={best} (csv={csv_path})"
        )

    if args.dry_run:
        print("\n[APPLY] dry-run 모드: config 미수정")
    else:
        _update_config_thresholds(args.config, selected)
        print(f"\n[APPLY] config 업데이트 완료: {args.config}")

    log_path = Path("data/backtest") / f"entry_threshold_apply_log_{datetime.now().strftime('%Y%m%d')}.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as f:
        f.write(f"dry_run={args.dry_run}\n")
        for line in log_lines:
            f.write(line + "\n")
    print(f"[LOG] 저장: {log_path}")


if __name__ == "__main__":
    main()

