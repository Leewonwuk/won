"""Compatibility shim — v1.2 데이터 수집은 ``src.v12.historical_data``."""
from src.v12.historical_data import (
    OHLCVBar,
    V12_DUAL_FIELDNAMES,
    align_binance_dual_btc_ohlc,
    collect_v12_btc_dual,
    fetch_binance_klines_ohlc,
    save_v12_dual_csv,
)

__all__ = [
    "OHLCVBar",
    "V12_DUAL_FIELDNAMES",
    "align_binance_dual_btc_ohlc",
    "collect_v12_btc_dual",
    "fetch_binance_klines_ohlc",
    "save_v12_dual_csv",
]
