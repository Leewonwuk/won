from __future__ import annotations

from dataclasses import dataclass
import requests

from src.models import OrderBookTop, utc_now_iso


BINANCE_BOOK_URL = "https://api.binance.com/api/v3/ticker/bookTicker"


@dataclass(slots=True)
class BinanceClient:
    timeout_sec: float = 3.0

    def fetch_top(self, symbol: str) -> OrderBookTop:
        response = requests.get(
            BINANCE_BOOK_URL,
            params={"symbol": symbol},
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        payload = response.json()
        return OrderBookTop(
            exchange="binance",
            symbol=symbol,
            bid=float(payload["bidPrice"]),
            ask=float(payload["askPrice"]),
            ts=utc_now_iso(),
        )

