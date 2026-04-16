from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha512
from urllib.parse import urlencode
import uuid

import jwt
import requests


@dataclass(slots=True)
class UpbitTradingClient:
    access_key: str
    secret_key: str
    timeout_sec: float = 3.0
    base_url: str = "https://api.upbit.com"

    def _headers(self, params: dict | None = None) -> dict[str, str]:
        payload = {"access_key": self.access_key, "nonce": str(uuid.uuid4())}
        if params:
            query_string = urlencode(params)
            payload["query_hash"] = sha512(query_string.encode("utf-8")).hexdigest()
            payload["query_hash_alg"] = "SHA512"
        token = jwt.encode(payload, self.secret_key)
        return {"Authorization": f"Bearer {token}"}

    def get_accounts(self) -> list[dict]:
        response = requests.get(
            f"{self.base_url}/v1/accounts",
            headers=self._headers(),
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        return response.json()

    def place_market_buy(self, market: str, quote_amount_krw: float) -> dict:
        params = {"market": market, "side": "bid", "ord_type": "price", "price": str(quote_amount_krw)}
        response = requests.post(
            f"{self.base_url}/v1/orders",
            params=params,
            headers=self._headers(params),
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        return response.json()

    def place_market_sell(self, market: str, base_volume: float) -> dict:
        params = {"market": market, "side": "ask", "ord_type": "market", "volume": str(base_volume)}
        response = requests.post(
            f"{self.base_url}/v1/orders",
            params=params,
            headers=self._headers(params),
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        return response.json()

    def get_order(self, uuid_value: str) -> dict:
        params = {"uuid": uuid_value}
        response = requests.get(
            f"{self.base_url}/v1/order",
            params=params,
            headers=self._headers(params),
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        return response.json()

    def withdraw_coin(
        self,
        currency: str,
        amount: float,
        address: str,
        secondary_address: str | None = None,
        net_type: str | None = None,
        transaction_type: str = "default",
    ) -> dict:
        params: dict[str, str] = {
            "currency": currency.upper(),
            "amount": f"{amount:.8f}",
            "address": address,
            "transaction_type": transaction_type,
        }
        if secondary_address:
            params["secondary_address"] = secondary_address
        if net_type:
            params["net_type"] = net_type

        response = requests.post(
            f"{self.base_url}/v1/withdraws/coin",
            params=params,
            headers=self._headers(params),
            timeout=self.timeout_sec,
        )
        if not (200 <= response.status_code < 300):
            raise RuntimeError(
                f"Upbit withdraw_coin failed ({response.status_code}): {response.text}"
            )
        return response.json()

