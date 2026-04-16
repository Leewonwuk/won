"""Arb v1.2 — Binance BTCUSDT vs BTCUSDC dual-quote (바이낸스만, v1.1과 코드 경로 분리).

권장 진입:
  [v2 - 3-balance, 단순화]
  python -m src.v12.v2 --config configs/v12/v12_btc_v2.yaml --days 30

  [v1 - 4-balance 레거시]
  python -m src.v12 --config configs/v12/v12_btc_dual.yaml --days 7
  python -m src.v12.entry_grid --config configs/v12/v12_btc_dual.yaml --days 14

레거시(동일 동작):
  python -m src.backtest_v12_main ...
  python -m src.tools.v12_entry_threshold_grid ...
"""
from __future__ import annotations

from src.v12.backtest import (
    BacktestV12Result,
    run_backtest_v12,
    save_v12_events_csv,
    save_v12_report,
)
from src.v12.config import V12Config, load_v12_config, slippage_pair_from_multi_yaml

__all__ = [
    "V12Config",
    "load_v12_config",
    "slippage_pair_from_multi_yaml",
    "BacktestV12Result",
    "run_backtest_v12",
    "save_v12_report",
    "save_v12_events_csv",
]
