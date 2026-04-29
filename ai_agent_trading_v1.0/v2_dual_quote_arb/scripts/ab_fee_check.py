"""USDC promo 패치 A/B 검증 스크립트.

기존 (legacy fee, USDC promo 미반영) vs 신규 (페어별 fee) 백테스트 비교.

Usage:
  python scripts/ab_fee_check.py --csv data/backtest/1s/SOLUSDT_20260419.parquet \
      --csv-uc data/backtest/1s/SOLUSDC_20260419.parquet --config configs/v12_sol_v2.yaml
"""
from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# src 패키지 stub (src/__init__.py 우회)
_stub = types.ModuleType("src")
_stub.__path__ = [str(ROOT / "src")]
sys.modules["src"] = _stub
# src.v12 alias → src/ 평탄 (allocator_v2/portfolio_v2/config_v2/price_util)
_v12_stub = types.ModuleType("src.v12")
_v12_stub.__path__ = [str(ROOT / "src")]
sys.modules["src.v12"] = _v12_stub

import importlib

# pre-load alias modules
for name in ("allocator_v2", "portfolio_v2", "config_v2", "price_util"):
    real = importlib.import_module(f"src.{name}")
    sys.modules[f"src.v12.{name}"] = real

from src.config_v2 import load_v12_config_v2  # noqa
from src.backtest_v2 import run_backtest_v2_from_rows  # noqa


def _load_parquet_pair(ut_path: Path, uc_path: Path) -> list[dict]:
    import pandas as pd
    from datetime import datetime, timezone as tz
    ut = pd.read_parquet(ut_path)[["open_time", "close"]].rename(columns={"close": "close_ut"})
    uc = pd.read_parquet(uc_path)[["open_time", "close"]].rename(columns={"close": "close_uc"})
    merged = ut.merge(uc, on="open_time")
    rows: list[dict] = []
    for _, r in merged.iterrows():
        ts_iso = datetime.fromtimestamp(int(r["open_time"]) / 1000.0, tz=tz.utc).isoformat()
        rows.append({
            "ts": ts_iso,
            "btc_usdt_close": float(r["close_ut"]),
            "btc_usdc_close": float(r["close_uc"]),
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--csv-ut", required=True, help="USDT pair parquet/csv")
    ap.add_argument("--csv-uc", required=True, help="USDC pair parquet/csv")
    args = ap.parse_args()

    cfg = load_v12_config_v2(args.config)

    rows = _load_parquet_pair(Path(args.csv_ut), Path(args.csv_uc))
    print(f"loaded {len(rows)} rows")

    # B: 신규 (페어별 fee, USDC promo 적용)
    res_new = run_backtest_v2_from_rows(rows, cfg)

    # A: legacy (USDC promo 무효화)
    cfg_legacy = load_v12_config_v2(args.config)
    cfg_legacy.fee_usdc_pair_taker = None
    cfg_legacy.fee_usdc_pair_maker = None
    cfg_legacy.dt_entry_threshold_rate = 0.0017  # 임계값도 원복
    cfg_legacy.dc_entry_threshold_rate = 0.0017
    res_old = run_backtest_v2_from_rows(rows, cfg_legacy)

    print("\n=== A/B 비교 ===")
    print(f"{'metric':<25} {'legacy':>14} {'new':>14}  delta")
    for label, get in [
        ("trade_count",          lambda r: r.trade_count),
        ("dt_count",             lambda r: r.dt_trade_count),
        ("dc_count",             lambda r: r.dc_trade_count),
        ("total_pnl_usd",        lambda r: r.total_pnl_usd),
        ("win_rate",             lambda r: r.win_rate),
        ("total_fee_usd",        lambda r: r.total_fee_usd),
        ("emergency_close",      lambda r: r.emergency_close_count),
        ("unfilled_timeout",     lambda r: r.unfilled_timeout_count),
    ]:
        a = get(res_old)
        b = get(res_new)
        d = b - a
        print(f"{label:<25} {a:>14.4f} {b:>14.4f}  {d:+.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
