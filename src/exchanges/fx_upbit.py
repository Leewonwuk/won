"""Upbit KRW-USDT spot price as KRW per 1 USDT (live FX for v1 spread)."""
from __future__ import annotations

import requests

UPBIT_KRW_USDT_TICKER = "https://api.upbit.com/v1/ticker"


def fetch_fx_krw_per_usdt(fallback: float, timeout_sec: float = 3.0) -> float:
    """Return Upbit KRW-USDT trade_price. On failure, return fallback."""
    try:
        response = requests.get(
            UPBIT_KRW_USDT_TICKER,
            params={"markets": "KRW-USDT"},
            timeout=timeout_sec,
        )
        response.raise_for_status()
        data = response.json()
        if data and len(data) > 0:
            price = float(data[0]["trade_price"])
            if price > 0:
                return price
    except Exception:
        pass
    return fallback
