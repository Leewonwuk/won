from __future__ import annotations

from dataclasses import dataclass
import requests

from src.models import OrderBookTop, utc_now_iso


UPBIT_ORDERBOOK_URL = "https://api.upbit.com/v1/orderbook"


@dataclass(slots=True)
class UpbitClient:
    timeout_sec: float = 3.0

    def fetch_top(self, market: str) -> OrderBookTop:
        response = requests.get(
            UPBIT_ORDERBOOK_URL,
            params={"markets": market},
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload:
            raise RuntimeError("empty upbit orderbook response")
        unit = payload[0]["orderbook_units"][0]
        return OrderBookTop(
            exchange="upbit",
            symbol=market,
            bid=float(unit["bid_price"]),
            ask=float(unit["ask_price"]),
            ts=utc_now_iso(),
        )

