"""Compatibility shim — v1.2 백테스트는 ``src.v12.backtest``."""
from src.v12.backtest import (
    BacktestV12Result,
    run_backtest_v12,
    save_v12_events_csv,
    save_v12_report,
)

__all__ = [
    "BacktestV12Result",
    "run_backtest_v12",
    "save_v12_report",
    "save_v12_events_csv",
]
