from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(slots=True)
class PortfolioState:
    is_open: bool = False
    direction: str = "NONE"
    size_base: float = 0.0
    entry_upbit_krw: float = 0.0
    entry_binance_krw: float = 0.0
    realized_pnl_krw: float = 0.0
    open_timestamp: float = 0.0

    def open_position(
        self,
        direction: str,
        size_base: float,
        upbit_price_krw: float,
        binance_price_krw: float,
    ) -> None:
        self.is_open = True
        self.direction = direction
        self.size_base = size_base
        self.entry_upbit_krw = upbit_price_krw
        self.entry_binance_krw = binance_price_krw
        self.open_timestamp = time.time()

    def close_position(self, upbit_price_krw: float, binance_price_krw: float) -> float:
        if not self.is_open:
            return 0.0
        pnl = 0.0
        if self.direction == "UPBIT_SHORT_BINANCE_LONG":
            pnl += (self.entry_upbit_krw - upbit_price_krw) * self.size_base
            pnl += (binance_price_krw - self.entry_binance_krw) * self.size_base
        elif self.direction == "UPBIT_LONG_BINANCE_SHORT":
            pnl += (upbit_price_krw - self.entry_upbit_krw) * self.size_base
            pnl += (self.entry_binance_krw - binance_price_krw) * self.size_base
        self.realized_pnl_krw += pnl
        self.is_open = False
        self.direction = "NONE"
        self.size_base = 0.0
        self.entry_upbit_krw = 0.0
        self.entry_binance_krw = 0.0
        self.open_timestamp = 0.0
        return pnl

