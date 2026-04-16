"""v1.2 entry threshold grid tool."""
from __future__ import annotations

from pathlib import Path

from src.backtest.v12_config import V12Config
from src.tools.v12_entry_threshold_grid import run_grid, select_best


def test_run_grid_two_thresholds(tmp_path: Path) -> None:
    from tests.test_backtest_v12 import _ohlc_row, _write_minimal_csv

    rows = [
        _ohlc_row("2026-01-01T00:00:00+00:00", "100000", "100000", vol="200"),
        _ohlc_row("2026-01-01T00:01:00+00:00", "101000", "100000", vol="200"),
    ]
    p = tmp_path / "g.csv"
    _write_minimal_csv(p, rows)
    base = V12Config(
        wall_filter_enabled=False,
        initial_usdt=1000,
        initial_usdc=5000,
        initial_btc_usdt_leg_usd=2500,
        initial_btc_usdc_leg_usd=2500,
    )
    out = run_grid(str(p), base, [0.01, 0.0005])
    assert len(out) == 2
    assert out[0]["trade_count"] == 0
    assert out[1]["trade_count"] >= 1


def test_select_best_respects_min_trades() -> None:
    rows = [
        {
            "entry_threshold_rate": 0.001,
            "trade_count": 1,
            "max_drawdown_rate": 0.01,
            "arbitrage_alpha_usd": 100.0,
            "pnl_7d_usd": 10.0,
            "pnl_14d_usd": 10.0,
            "total_pnl_usd": 0.0,
            "total_fee_usd": 0.0,
            "total_return_rate": 0.0,
            "rebalance_count": 0,
            "buy_hold_pnl_usd": 0.0,
            "arbitrage_alpha_rate": 0.0,
            "win_rate": 0.0,
        },
        {
            "entry_threshold_rate": 0.002,
            "trade_count": 5,
            "max_drawdown_rate": 0.01,
            "arbitrage_alpha_usd": 50.0,
            "pnl_7d_usd": 10.0,
            "pnl_14d_usd": 10.0,
            "total_pnl_usd": 0.0,
            "total_fee_usd": 0.0,
            "total_return_rate": 0.0,
            "rebalance_count": 0,
            "buy_hold_pnl_usd": 0.0,
            "arbitrage_alpha_rate": 0.0,
            "win_rate": 0.0,
        },
    ]
    b = select_best(rows, min_trades=3, mdd_max=0.08, prev_threshold=0.001, short_pnl_filter=True)
    assert b is not None
    assert b["entry_threshold_rate"] == 0.002
