"""Grid-search entry_threshold_rate for v1.2 (BTCUSDT + BTCUSDC) on fixed 1m CSV.

권장: ``python -m src.v12.entry_grid --config configs/v12/v12_btc_dual.yaml --days 14``
호환: ``python -m src.tools.v12_entry_threshold_grid`` (동일 구현 위임).
"""
from __future__ import annotations

import argparse
import csv
import glob
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.v12.backtest import run_backtest_v12
from src.v12.config import V12Config, load_v12_config
from src.v12.historical_data import collect_v12_btc_dual
from src.v12.price_util import v12_leg_mids

_DEFAULT_CONFIG = "configs/v12/v12_btc_dual.yaml"


def _fee_slippage_stack(cfg: V12Config) -> float:
    return (
        cfg.fee_usdt_leg_rate
        + cfg.fee_usdc_leg_rate
        + cfg.slippage_usdt_leg_rate
        + cfg.slippage_usdc_leg_rate
    )


def diagnose_premium_range(csv_path: str, cfg: V12Config | None = None) -> tuple[float, float]:
    import csv as _csv
    from pathlib import Path as _Path

    mn, mx = 0.0, 0.0
    first = True
    with _Path(csv_path).open(encoding="utf-8", newline="") as f:
        for row in _csv.DictReader(f):
            if cfg is not None:
                ut, uc = v12_leg_mids(row, cfg)
            else:
                ut = float(row["btc_usdt_close"])
                uc = float(row["btc_usdc_close"])
            if uc <= 0:
                continue
            p = (ut - uc) / uc
            if first:
                mn = mx = p
                first = False
            else:
                mn = min(mn, p)
                mx = max(mx, p)
    return mn, mx


# v1.2: no FX; fee+slip stack ≈ 2*(fee+slip) per leg — grid from below to above that band.
DEFAULT_CANDIDATES: list[float] = [
    0.00005,
    0.0001,
    0.00015,
    0.0002,
    0.00025,
    0.0003,
    0.00035,
    0.0004,
    0.00045,
    0.0005,
    0.00055,
    0.0006,
    0.0007,
    0.0008,
    0.0009,
    0.001,
    0.0012,
    0.0015,
    0.002,
    0.0025,
    0.003,
    0.0035,
    0.004,
    0.005,
    0.006,
    0.008,
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="v1.2 entry_threshold_rate grid (1m)")
    p.add_argument("--config", default=_DEFAULT_CONFIG)
    p.add_argument("--days", type=int, default=14, help="Lookback days (must match CSV pattern)")
    p.add_argument("--resolution", type=int, default=1, help="1 or 5 (default 1)")
    p.add_argument("--skip-collect", action="store_true", help="Reuse latest v12_btc_*d_1m_*.csv")
    p.add_argument("--csv", default="", help="Explicit CSV path")
    p.add_argument(
        "--candidates",
        default="",
        help="Comma-separated thresholds (overrides default grid)",
    )
    p.add_argument(
        "--wall-off",
        action="store_true",
        help="Force wall_filter_enabled=false for tuning",
    )
    p.add_argument("--mdd-max", type=float, default=0.08, help="Max drawdown filter for 'best' pick")
    p.add_argument("--min-trades", type=int, default=3, help="Min trades filter for 'best' pick")
    p.add_argument(
        "--no-short-pnl-filter",
        action="store_true",
        help="Do not require pnl_7d>0 and pnl_14d>0 when picking BEST",
    )
    p.add_argument(
        "--multi-slippage-yaml",
        default="configs/multi.yaml",
        help="Slippage from multi.yaml v12_binance_dual_quote (else coins[0] legacy); --no-multi-slippage to disable",
    )
    p.add_argument(
        "--no-multi-slippage",
        action="store_true",
        help="Use v12 YAML slippage only",
    )
    return p.parse_args()


def _parse_candidates(s: str) -> list[float]:
    out: list[float] = []
    for part in s.split(","):
        part = part.strip()
        if part:
            out.append(float(part))
    return out


def _find_latest_v12_csv(days: int, resolution: int) -> str | None:
    pattern = f"data/backtest/v12_btc_{days}d_{resolution}m_*.csv"
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def _collect_or_get_csv(base: V12Config, days: int, resolution: int, skip_collect: bool) -> str:
    if skip_collect:
        latest = _find_latest_v12_csv(days, resolution)
        if latest:
            return latest
    ts_tag = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    return collect_v12_btc_dual(
        symbol_usdt=base.binance_symbol_usdt,
        symbol_usdc=base.binance_symbol_usdc,
        n_days=days,
        out_dir="data/backtest",
        tag=ts_tag,
        minutes=resolution,
    )


def run_grid(
    csv_path: str,
    base: V12Config,
    candidates: list[float],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for th in candidates:
        cfg = replace(base, entry_threshold_rate=th)
        r = run_backtest_v12(csv_path=csv_path, cfg=cfg)
        rows.append(
            {
                "entry_threshold_rate": th,
                "total_pnl_usd": r.total_pnl_usd,
                "total_fee_usd": r.total_fee_usd,
                "total_return_rate": r.total_return_rate,
                "max_drawdown_rate": r.max_drawdown_rate,
                "trade_count": r.trade_count,
                "rebalance_count": r.rebalance_count,
                "pnl_7d_usd": r.pnl_7d_usd,
                "pnl_14d_usd": r.pnl_14d_usd,
                "buy_hold_pnl_usd": r.buy_hold_pnl_usd,
                "arbitrage_alpha_usd": r.arbitrage_alpha_usd,
                "arbitrage_alpha_rate": r.arbitrage_alpha_rate,
                "win_rate": r.win_rate,
            }
        )
    return rows


def select_best(
    rows: list[dict[str, Any]],
    *,
    min_trades: int,
    mdd_max: float,
    prev_threshold: float,
    short_pnl_filter: bool = True,
) -> dict[str, Any] | None:
    cands = [r for r in rows if int(r["trade_count"]) >= min_trades]
    cands = [r for r in cands if float(r["max_drawdown_rate"]) <= mdd_max]
    cands = [r for r in cands if float(r["arbitrage_alpha_usd"]) > 0]
    if short_pnl_filter:
        cands = [r for r in cands if float(r["pnl_7d_usd"]) > 0 and float(r["pnl_14d_usd"]) > 0]

    if not cands:
        return None
    return max(cands, key=lambda r: float(r["arbitrage_alpha_usd"]))


def select_best_relaxed(rows: list[dict[str, Any]], prev_threshold: float) -> dict[str, Any] | None:
    """If strict filters empty: best alpha among rows with at least 1 trade."""
    cands = [r for r in rows if int(r["trade_count"]) >= 1]
    if not cands:
        return None
    return max(cands, key=lambda r: float(r["arbitrage_alpha_usd"]))


def select_best_any_trades(rows: list[dict[str, Any]], min_trades: int = 1) -> dict[str, Any] | None:
    """Maximize alpha among rows that actually traded (alpha may be negative)."""
    cands = [r for r in rows if int(r["trade_count"]) >= min_trades]
    if not cands:
        return None
    return max(cands, key=lambda r: float(r["arbitrage_alpha_usd"]))


def main() -> None:
    args = parse_args()
    cfg_path = args.config
    if not Path(cfg_path).is_file() and cfg_path == _DEFAULT_CONFIG:
        legacy = "configs/v12_btc_dual.yaml"
        if Path(legacy).is_file():
            print(f"[NOTE] using legacy config path {legacy} (move to {_DEFAULT_CONFIG})")
            cfg_path = legacy

    multi_slip = None if args.no_multi_slippage else (args.multi_slippage_yaml or None)
    base = load_v12_config(cfg_path, multi_slippage_yaml=multi_slip)
    if args.wall_off:
        base = replace(base, wall_filter_enabled=False)

    candidates = _parse_candidates(args.candidates) if args.candidates else DEFAULT_CANDIDATES

    if args.csv:
        csv_path = args.csv
    else:
        csv_path = _collect_or_get_csv(
            base, days=args.days, resolution=args.resolution, skip_collect=args.skip_collect
        )

    print(f"[DATA] csv={csv_path}")
    stack = _fee_slippage_stack(base)
    pmin, pmax = diagnose_premium_range(csv_path, cfg=base)
    print(
        f"[DIAG] price_mode={base.price_mode} premium min={pmin:.6f} max={pmax:.6f} | "
        f"fee+slip stack (both legs) ~ {stack:.6f}; need |premium| above this after threshold"
    )
    print(f"[GRID] candidates={len(candidates)} (1m resolution={args.resolution})")

    rows = run_grid(csv_path, base, candidates)

    out_dir = Path("data/backtest")
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"v12_entry_grid_{args.days}d_{args.resolution}m_{tag}.csv"
    fieldnames = list(rows[0].keys()) if rows else []
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"[GRID] saved: {out_path}")

    best_path = out_dir / f"v12_entry_grid_{args.days}d_{args.resolution}m_best_{tag}.csv"
    sorted_rows = sorted(rows, key=lambda r: float(r["arbitrage_alpha_usd"]), reverse=True)
    with best_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(sorted_rows[:5])
    print(f"[GRID] top5 alpha: {best_path}")

    best = select_best(
        rows,
        min_trades=args.min_trades,
        mdd_max=args.mdd_max,
        prev_threshold=base.entry_threshold_rate,
        short_pnl_filter=not args.no_short_pnl_filter,
    )
    if best is None:
        print("\n[BEST] strict filters -> no row (try --min-trades 1, longer --days, --wall-off, --no-short-pnl-filter)")
        relaxed = select_best_relaxed(rows, base.entry_threshold_rate)
        if relaxed:
            print(
                f"[BEST:relaxed] entry_threshold_rate={relaxed['entry_threshold_rate']:.6f}  "
                f"alpha_usd={float(relaxed['arbitrage_alpha_usd']):,.2f}  "
                f"trades={int(relaxed['trade_count'])}  MDD={float(relaxed['max_drawdown_rate']):.2%}"
            )
        else:
            any_tr = select_best_any_trades(rows, min_trades=1)
            if any_tr:
                print(
                    f"[BEST:any_trades] entry_threshold_rate={any_tr['entry_threshold_rate']:.6f}  "
                    f"alpha_usd={float(any_tr['arbitrage_alpha_usd']):,.2f}  "
                    f"trades={int(any_tr['trade_count'])} (alpha may be ≤0; compare to buy-hold)"
                )
            else:
                print(
                    "[BEST] no trades in grid - dislocation rarely clears fee+slip; "
                    "try longer --days, looser slippage in YAML, or live tick data."
                )
    else:
        print(
            f"\n[BEST] entry_threshold_rate={best['entry_threshold_rate']:.6f}  "
            f"alpha_usd={float(best['arbitrage_alpha_usd']):,.2f}  "
            f"total_pnl_usd={float(best['total_pnl_usd']):,.2f}  "
            f"trades={int(best['trade_count'])}  MDD={float(best['max_drawdown_rate']):.2%}"
        )


if __name__ == "__main__":
    main()
