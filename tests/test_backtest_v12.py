"""v1.2 dual-quote backtest smoke tests."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.backtest.backtest_v12 import run_backtest_v12
from src.backtest.v12_config import V12Config


def _write_minimal_csv(path: Path, rows: list[dict]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ts",
        "btc_usdt_open",
        "btc_usdt_high",
        "btc_usdt_low",
        "btc_usdt_close",
        "btc_usdc_open",
        "btc_usdc_high",
        "btc_usdc_low",
        "btc_usdc_close",
        "btc_usdt_volume",
        "btc_usdc_volume",
        "btc_usdt_taker_buy_volume",
        "btc_usdc_taker_buy_volume",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return str(path)


def _ohlc_row(
    ts: str,
    ut: str,
    uc: str,
    vol: str = "100",
) -> dict[str, str]:
    return {
        "ts": ts,
        "btc_usdt_open": ut,
        "btc_usdt_high": ut,
        "btc_usdt_low": ut,
        "btc_usdt_close": ut,
        "btc_usdc_open": uc,
        "btc_usdc_high": uc,
        "btc_usdc_low": uc,
        "btc_usdc_close": uc,
        "btc_usdt_volume": vol,
        "btc_usdc_volume": vol,
        "btc_usdt_taker_buy_volume": "50",
        "btc_usdc_taker_buy_volume": "50",
    }


def test_no_trade_when_premium_below_threshold(tmp_path: Path) -> None:
    base = "2026-01-01T00:00:00+00:00"
    rows = []
    for i in range(5):
        rows.append(
            _ohlc_row(f"2026-01-01T00:{i:02d}:00+00:00", "100000", "100000")
        )
    p = tmp_path / "v12_flat.csv"
    _write_minimal_csv(p, rows)
    cfg = V12Config(
        entry_threshold_rate=0.01,
        wall_filter_enabled=False,
    )
    r = run_backtest_v12(str(p), cfg)
    assert r.trade_count == 0


def test_kimchi_trade_when_premium_spike(tmp_path: Path) -> None:
    rows = [
        _ohlc_row("2026-01-01T00:00:00+00:00", "100000", "100000", vol="200"),
        {
            **_ohlc_row("2026-01-01T00:01:00+00:00", "101000", "100000", vol="200"),
        },
    ]
    p = tmp_path / "v12_spike.csv"
    _write_minimal_csv(p, rows)
    cfg = V12Config(
        entry_threshold_rate=0.0005,
        entry_split_fraction=1.0,
        wall_filter_enabled=False,
        initial_usdt=1000,
        initial_usdc=5000,
        initial_btc_usdt_leg_usd=2500,
        initial_btc_usdc_leg_usd=2500,
    )
    r = run_backtest_v12(str(p), cfg)
    assert r.trade_count >= 1


# Live data smoke (manual): python -m src.v12 --config configs/v12/v12_btc_dual.yaml --days 7 --resolution 1
