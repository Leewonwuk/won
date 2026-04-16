"""Pick entry_threshold_rate that maximizes combined PnL on multi-day CSVs per coin.

각 임계값에 대해 `--windows`에 지정한 일수(기본 7·14·21) 데이터를 **각각** 전 구간 백테스트하고,
`total_pnl_krw`(순실현) 합을 최대화하는 후보를 고른다.
`--balanced`면 각 윈도 **거래 수 밴드** 안에서만 sum_pnl을 최대화.

Usage:
    python -m src.backtest_v2_main --config configs/multi.yaml --days 21 --resolution 1
    python -m src.tools.autotune_dual_window_pnl --config configs/multi.yaml --dry-run
    python -m src.tools.autotune_dual_window_pnl --windows 7,14 --balanced --dry-run
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.backtest.backtest_v2 import run_backtest_v2
from src.config import CoinConfig, load_multi_config
from src.tools.autotune_entry_threshold import CANDIDATE_THRESHOLDS, DEFAULT_CANDIDATES, _find_latest_csv


def _parse_windows(s: str) -> list[int]:
    out: list[int] = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        d = int(part)
        if d <= 0:
            raise ValueError(f"invalid window days: {d}")
        out.append(d)
    if not out:
        raise ValueError("empty --windows")
    # stable unique order
    seen: set[int] = set()
    uniq: list[int] = []
    for d in out:
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Maximize sum of total_pnl_krw across 7d/14d/21d (configurable) CSVs per threshold"
    )
    p.add_argument("--config", default="configs/multi.yaml")
    p.add_argument(
        "--windows",
        default="7,14,21",
        help="Comma-separated lookback days (default: 7,14,21). Example: 7,14 if no 21d CSV yet",
    )
    p.add_argument("--dry-run", action="store_true", help="Print only; do not write multi.yaml")
    p.add_argument(
        "--min-trades-each",
        type=int,
        default=1,
        help="Require at least this many trades on EVERY window run (0 = disable)",
    )
    p.add_argument(
        "--max-mdd-each",
        type=float,
        default=0.15,
        help="Require max_drawdown <= this on EVERY run (e.g. 0.15 = 15%%)",
    )
    p.add_argument(
        "--strict-only",
        action="store_true",
        help="If no row passes min-trades/mdd filters, abort coin (keep yaml value)",
    )
    p.add_argument(
        "--balanced",
        action="store_true",
        help="Prefer thresholds where trade counts sit in per-window bands, then max sum_pnl",
    )
    p.add_argument("--min-trades-7d", type=int, default=3, help="Balanced: min trades on 7d run")
    p.add_argument("--max-trades-7d", type=int, default=30, help="Balanced: max trades on 7d (0=no cap)")
    p.add_argument("--min-trades-14d", type=int, default=8, help="Balanced: min trades on 14d run")
    p.add_argument("--max-trades-14d", type=int, default=70, help="Balanced: max trades on 14d (0=no cap)")
    p.add_argument("--min-trades-21d", type=int, default=12, help="Balanced: min trades on 21d run")
    p.add_argument("--max-trades-21d", type=int, default=105, help="Balanced: max trades on 21d (0=no cap)")
    return p.parse_args()


def _grid_for_symbol(symbol: str) -> list[float]:
    return CANDIDATE_THRESHOLDS.get(symbol.upper(), DEFAULT_CANDIDATES)


def _trade_key(d: int) -> str:
    return f"trade_{d}d"


def _mdd_key(d: int) -> str:
    return f"mdd_{d}d"


def _pnl_key(d: int) -> str:
    return f"pnl_{d}d_total_krw"


def _run_multi_window_row(
    coin: CoinConfig,
    threshold: float,
    csv_by_day: dict[int, str],
    windows: list[int],
    fx_fallback: float,
) -> dict[str, Any]:
    cfg = replace(coin, entry_threshold_rate=threshold)
    row: dict[str, Any] = {"entry_threshold_rate": threshold}
    sum_pnl = 0.0
    sum_alpha = 0.0
    for d in windows:
        path = csv_by_day[d]
        r = run_backtest_v2(csv_path=path, coin_cfg=cfg, fx_fallback=fx_fallback)
        row[_pnl_key(d)] = r.total_pnl_krw
        row[_trade_key(d)] = r.trade_count
        row[_mdd_key(d)] = r.max_drawdown_rate
        row[f"fee_{d}d"] = r.total_fee_krw
        sum_pnl += r.total_pnl_krw
        sum_alpha += r.arbitrage_alpha_krw
    row["sum_pnl_krw"] = sum_pnl
    row["sum_alpha_krw"] = sum_alpha
    return row


def _band_specs_for_windows(args: argparse.Namespace, windows: list[int]) -> dict[int, tuple[int, int]]:
    """day -> (min_trades, max_trades)."""
    m: dict[int, tuple[int, int]] = {}
    if 7 in windows:
        m[7] = (args.min_trades_7d, args.max_trades_7d)
    if 14 in windows:
        m[14] = (args.min_trades_14d, args.max_trades_14d)
    if 21 in windows:
        m[21] = (args.min_trades_21d, args.max_trades_21d)
    for d in windows:
        if d not in m:
            # 윈도가 7/14/21이 아닐 때: 14d 밴드를 길이 비율로 스케일
            scale = d / 14.0
            lo = max(1, int(round(args.min_trades_14d * scale)))
            hi = int(round(args.max_trades_14d * scale)) if args.max_trades_14d > 0 else 0
            m[d] = (lo, hi)
    return m


def _mdd_ok_row(r: dict[str, Any], max_mdd_each: float, windows: list[int]) -> bool:
    return all(float(r[_mdd_key(d)]) <= max_mdd_each for d in windows)


def _trades_in_band_row(r: dict[str, Any], bands: dict[int, tuple[int, int]], windows: list[int]) -> bool:
    for d in windows:
        lo, hi = bands[d]
        t = int(r[_trade_key(d)])
        if t < lo:
            return False
        if hi > 0 and t > hi:
            return False
    return True


def _band_violation_row(r: dict[str, Any], bands: dict[int, tuple[int, int]], windows: list[int]) -> int:
    def dist(t: int, lo: int, hi: int) -> int:
        if t < lo:
            return lo - t
        if hi > 0 and t > hi:
            return t - hi
        return 0

    total = 0
    for d in windows:
        lo, hi = bands[d]
        total += dist(int(r[_trade_key(d)]), lo, hi)
    return total


def _pick_best(
    rows: list[dict[str, Any]],
    *,
    windows: list[int],
    min_trades_each: int,
    max_mdd_each: float,
    strict_only: bool,
    balanced: bool,
    bands: dict[int, tuple[int, int]],
) -> tuple[dict[str, Any] | None, bool, str]:
    def ok_pnl_only(r: dict[str, Any]) -> bool:
        if min_trades_each > 0:
            for d in windows:
                if int(r[_trade_key(d)]) < min_trades_each:
                    return False
        return _mdd_ok_row(r, max_mdd_each, windows)

    if balanced:
        banded = [
            r
            for r in rows
            if _mdd_ok_row(r, max_mdd_each, windows)
            and _trades_in_band_row(r, bands, windows)
        ]
        if banded:
            return max(banded, key=lambda r: float(r["sum_pnl_krw"])), False, "balanced_band"
        if strict_only:
            return None, False, "strict_empty"
        mdd_pass = [r for r in rows if _mdd_ok_row(r, max_mdd_each, windows)]
        if not mdd_pass:
            best = max(rows, key=lambda r: float(r["sum_pnl_krw"]))
            return best, True, "balanced_mdd_fail"
        best = max(
            mdd_pass,
            key=lambda r: (
                -_band_violation_row(r, bands, windows),
                float(r["sum_pnl_krw"]),
            ),
        )
        viol = _band_violation_row(best, bands, windows)
        return best, viol > 0, "balanced_relaxed"

    filtered = [r for r in rows if ok_pnl_only(r)]
    if filtered:
        return max(filtered, key=lambda r: float(r["sum_pnl_krw"])), False, "pnl_only"
    if strict_only:
        return None, False, "strict_empty"
    return max(rows, key=lambda r: float(r["sum_pnl_krw"])), True, "pnl_only_relaxed"


def _update_config_thresholds(config_path: str, selected: dict[str, float]) -> None:
    path = Path(config_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    coins = data.get("coins", [])
    for coin in coins:
        sym = str(coin.get("symbol", "")).upper()
        if sym in selected:
            coin["entry_threshold_rate"] = float(selected[sym])
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _format_pnl_parts(best: dict[str, Any], windows: list[int]) -> str:
    parts = [f"{d}d={float(best[_pnl_key(d)]):,.0f}" for d in windows]
    return " + ".join(parts)


def _format_trade_parts(best: dict[str, Any], windows: list[int]) -> str:
    parts = [f"{d}d={best[_trade_key(d)]}" for d in windows]
    return " ".join(parts)


def main() -> None:
    args = parse_args()
    try:
        windows = _parse_windows(args.windows)
    except ValueError as e:
        raise SystemExit(str(e)) from e

    cfg = load_multi_config(args.config)
    selected: dict[str, float] = {}
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path("data/backtest")
    out_dir.mkdir(parents=True, exist_ok=True)
    bands = _band_specs_for_windows(args, windows) if args.balanced else {}

    for coin in cfg.coins:
        sym = coin.symbol.upper()
        csv_by_day: dict[int, str] = {}
        missing: list[int] = []
        for d in windows:
            p = _find_latest_csv(coin.symbol, d)
            if not p:
                missing.append(d)
            else:
                csv_by_day[d] = p
        if missing:
            lines = [
                f"[{sym}] 일부 윈도 CSV 없음: days={missing}",
                f"  패턴: data/backtest/{coin.symbol.lower()}_<N>d_1m_*.csv",
                f"  수집 예: python -m src.backtest_v2_main --config {args.config} --days <N> --resolution 1",
                "  21일 파일이 없으면: python -m src.tools.autotune_dual_window_pnl --windows 7,14 ...",
            ]
            raise SystemExit("\n".join(lines))

        print(f"\n=== MULTI-WINDOW PnL MAX ({sym}) windows={windows} ===")
        if args.balanced:
            parts = [f"{d}d [{bands[d][0]},{bands[d][1] or 'inf'}]" for d in windows]
            print(f"  [balanced] trades " + ", ".join(parts))
        for d in windows:
            print(f"  {d}d CSV: {csv_by_day[d]}")

        thresholds = _grid_for_symbol(sym)
        rows: list[dict[str, Any]] = []
        for th in thresholds:
            row = _run_multi_window_row(coin, th, csv_by_day, windows, cfg.fx_krw_per_usdt)
            rows.append(row)

        csv_out = out_dir / f"{coin.symbol.lower()}_multi_window_pnl_grid_{ts}.csv"
        with csv_out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"  [GRID] {csv_out}")

        best, relaxed, tag = _pick_best(
            rows,
            windows=windows,
            min_trades_each=args.min_trades_each,
            max_mdd_each=args.max_mdd_each,
            strict_only=args.strict_only,
            balanced=args.balanced,
            bands=bands,
        )
        if best is None:
            print(f"  [WARN] strict 모드에서 후보 없음 -> {sym} threshold 유지: {coin.entry_threshold_rate}")
            selected[sym] = float(coin.entry_threshold_rate)
            continue

        if relaxed:
            if tag == "balanced_relaxed":
                print("  [WARN] 거래 수 밴드 밖 → MDD 통과 행 중 밴드에 가장 가깝고 sum_pnl 큰 값 사용")
            elif tag == "balanced_mdd_fail":
                print("  [WARN] MDD 통과 행 없음 → 전 그리드 중 sum_pnl 최대(리스크 큼)")
            else:
                print("  [WARN] min-trades/mdd 필터 미충족 → 전 그리드 중 sum_pnl 최대값 사용")
        elif args.balanced and tag == "balanced_band":
            print("  [OK] 거래 수 밴드 + MDD 만족")

        print(
            f"  [BEST] threshold={best['entry_threshold_rate']:.6f}  "
            f"sum_pnl={float(best['sum_pnl_krw']):,.0f} KRW  "
            f"({_format_pnl_parts(best, windows)})  "
            f"trades {_format_trade_parts(best, windows)}  "
            f"sum_alpha={float(best['sum_alpha_krw']):,.0f}"
        )
        selected[sym] = float(best["entry_threshold_rate"])

    log_path = out_dir / f"multi_window_threshold_apply_{ts}.txt"
    with log_path.open("w", encoding="utf-8") as f:
        f.write(f"multi_window_pnl max windows={windows}\n")
        f.write(f"balanced={args.balanced} min_trades_each={args.min_trades_each} max_mdd_each={args.max_mdd_each}\n")
        if args.balanced:
            for d in windows:
                lo, hi = bands[d]
                f.write(f"band_{d}d=[{lo},{hi}]\n")
        for sym, th in selected.items():
            f.write(f"{sym}={th}\n")
    print(f"\n[LOG] {log_path}")

    if args.dry_run:
        print("\n[APPLY] dry-run: multi.yaml 미수정")
    else:
        _update_config_thresholds(args.config, selected)
        print(f"\n[APPLY] {args.config} entry_threshold_rate 갱신 완료")


if __name__ == "__main__":
    main()
