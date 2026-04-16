from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import math
import time
from urllib.parse import urlencode

import requests


@dataclass(slots=True)
class BinanceTradingClient:
    api_key: str
    api_secret: str
    timeout_sec: float = 3.0
    recv_window: int = 5000
    base_url: str = "https://api.binance.com"
    _symbol_rules_cache: dict[str, dict] = field(default_factory=dict)

    def _signed_params(self, params: dict) -> dict:
        payload = {
            **params,
            "timestamp": int(time.time() * 1000),
            "recvWindow": self.recv_window,
        }
        query = urlencode(payload)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {**payload, "signature": signature}

    def _headers(self) -> dict[str, str]:
        return {"X-MBX-APIKEY": self.api_key}

    def get_account(self) -> dict:
        params = self._signed_params({})
        response = requests.get(
            f"{self.base_url}/api/v3/account",
            params=params,
            headers=self._headers(),
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        return response.json()

    def place_market_order(self, symbol: str, side: str, quantity: float) -> dict:
        params = self._signed_params(
            {"symbol": symbol, "side": side, "type": "MARKET", "quantity": f"{quantity:.8f}"}
        )
        response = requests.post(
            f"{self.base_url}/api/v3/order",
            params=params,
            headers=self._headers(),
            timeout=self.timeout_sec,
        )
        if not response.ok:
            raise RuntimeError(
                f"binance order failed ({response.status_code}): {response.text}"
            )
        return response.json()

    def place_market_buy_quote(self, symbol: str, quote_usdt: float) -> dict:
        """MARKET BUY spending `quote_usdt` USDT (quoteOrderQty)."""
        params = self._signed_params(
            {
                "symbol": symbol,
                "side": "BUY",
                "type": "MARKET",
                "quoteOrderQty": f"{quote_usdt:.8f}",
            }
        )
        response = requests.post(
            f"{self.base_url}/api/v3/order",
            params=params,
            headers=self._headers(),
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        return response.json()

    def _get_symbol_rules(self, symbol: str) -> dict:
        key = symbol.upper()
        cached = self._symbol_rules_cache.get(key)
        if cached:
            return cached
        response = requests.get(
            f"{self.base_url}/api/v3/exchangeInfo",
            params={"symbol": key},
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        payload = response.json()
        symbols = payload.get("symbols", [])
        if not symbols:
            raise RuntimeError(f"binance exchangeInfo missing symbol: {key}")
        lot_min = 0.0
        lot_step = 0.0
        min_notional = 0.0
        tick_size = 0.01
        for f in symbols[0].get("filters", []):
            t = f.get("filterType")
            if t == "LOT_SIZE":
                lot_min = float(f.get("minQty", 0) or 0)
                lot_step = float(f.get("stepSize", 0) or 0)
            elif t in ("NOTIONAL", "MIN_NOTIONAL"):
                min_notional = float(f.get("minNotional", 0) or 0)
            elif t == "PRICE_FILTER":
                tick_size = float(f.get("tickSize", 0.01) or 0.01)
        rules = {"min_qty": lot_min, "step_qty": lot_step, "min_notional": min_notional, "tick_size": tick_size}
        self._symbol_rules_cache[key] = rules
        return rules

    def normalize_market_quantity(self, symbol: str, quantity: float) -> float:
        """Floor quantity to LOT_SIZE step and enforce minQty."""
        q = float(quantity or 0.0)
        if q <= 0:
            return 0.0
        rules = self._get_symbol_rules(symbol)
        step = float(rules.get("step_qty", 0.0) or 0.0)
        min_qty = float(rules.get("min_qty", 0.0) or 0.0)
        if step > 0:
            q = math.floor(q / step) * step
        if q < min_qty:
            return 0.0
        return float(f"{q:.8f}")

    def get_spot_balances(self) -> dict[str, float]:
        """free 잔고만 반환 {asset: amount}."""
        account = self.get_account()
        return {
            b["asset"]: float(b["free"])
            for b in account.get("balances", [])
            if float(b["free"]) > 0
        }

    def get_book_ticker(self, symbol: str) -> dict:
        """최우선 호가 조회 {bidPrice, askPrice, ...}."""
        response = requests.get(
            f"{self.base_url}/api/v3/ticker/bookTicker",
            params={"symbol": symbol.upper()},
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        return response.json()

    def normalize_price(self, symbol: str, price: float) -> float:
        """tick_size에 맞춰 price를 내림."""
        rules = self._get_symbol_rules(symbol)
        tick = float(rules.get("tick_size", 0.01) or 0.01)
        if tick <= 0:
            tick = 0.01
        floored = math.floor(price / tick) * tick
        decimals = max(0, -int(math.floor(math.log10(tick)))) if tick < 1 else 0
        return round(floored, decimals)

    def normalize_price_ceil(self, symbol: str, price: float) -> float:
        """tick_size에 맞춰 price를 올림 (IOC 매수 등 호가에 닿게 할 때)."""
        rules = self._get_symbol_rules(symbol)
        tick = float(rules.get("tick_size", 0.01) or 0.01)
        if tick <= 0:
            tick = 0.01
        ceiled = math.ceil(price / tick - 1e-12) * tick
        decimals = max(0, -int(math.floor(math.log10(tick)))) if tick < 1 else 0
        return round(ceiled, decimals)

    def place_limit_order(
        self, symbol: str, side: str, quantity: float, price: float,
        time_in_force: str = "GTC",
    ) -> dict:
        """지정가 주문. time_in_force 기본값 GTC (IOC/FOK 지원)."""
        if side.upper() == "BUY":
            p = self.normalize_price_ceil(symbol, price)
        else:
            p = self.normalize_price(symbol, price)
        params = self._signed_params({
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": "LIMIT",
            "timeInForce": time_in_force,
            "quantity": f"{quantity:.8f}",
            "price": f"{p:.8f}".rstrip("0").rstrip(".") or "0",
        })
        response = requests.post(
            f"{self.base_url}/api/v3/order",
            params=params,
            headers=self._headers(),
            timeout=self.timeout_sec,
        )
        if not response.ok:
            raise RuntimeError(
                f"binance limit order failed ({response.status_code}): {response.text}"
            )
        return response.json()

    def cancel_order(self, symbol: str, order_id: int | str) -> dict:
        """주문 취소."""
        params = self._signed_params({
            "symbol": symbol.upper(),
            "orderId": int(order_id),
        })
        response = requests.delete(
            f"{self.base_url}/api/v3/order",
            params=params,
            headers=self._headers(),
            timeout=self.timeout_sec,
        )
        if not response.ok:
            raise RuntimeError(
                f"binance cancel order failed ({response.status_code}): {response.text}"
            )
        return response.json()

    def get_order_status(self, symbol: str, order_id: int | str) -> dict:
        """주문 상태 조회."""
        params = self._signed_params({
            "symbol": symbol.upper(),
            "orderId": int(order_id),
        })
        response = requests.get(
            f"{self.base_url}/api/v3/order",
            params=params,
            headers=self._headers(),
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        return response.json()

    def convert_stable(self, from_asset: str, to_asset: str, from_amount: float) -> dict:
        """USDT↔USDC 즉시 Convert (getQuote → acceptQuote).

        바이낸스 Convert는 스테이블 간 수수료 없음.
        API 키에 'Convert & Savings' 권한 필요.
        """
        # 1단계: 견적 조회
        quote_params = self._signed_params({
            "fromAsset": from_asset.upper(),
            "toAsset": to_asset.upper(),
            "fromAmount": f"{from_amount:.8f}",
            "walletType": "SPOT",
        })
        quote_resp = requests.post(
            f"{self.base_url}/sapi/v1/convert/getQuote",
            params=quote_params,
            headers=self._headers(),
            timeout=self.timeout_sec,
        )
        if not quote_resp.ok:
            raise RuntimeError(
                f"convert getQuote failed ({quote_resp.status_code}): {quote_resp.text}"
            )
        quote = quote_resp.json()
        # Binance Convert getQuote 응답의 ID 키는 버전/계정에 따라 다를 수 있음
        quote_id = (quote.get("quoteId") or quote.get("orderId")
                    or quote.get("id") or quote.get("convertOrderId"))
        if not quote_id:
            import logging as _log
            _log.getLogger(__name__).error(
                f"convert getQuote 응답 키 목록: {list(quote.keys())}  전체: {quote}"
            )
            raise RuntimeError(f"convert getQuote: quoteId 없음 {list(quote.keys())}")

        # 2단계: 견적 수락 (즉시 체결)
        accept_params = self._signed_params({"quoteId": quote_id})
        accept_resp = requests.post(
            f"{self.base_url}/sapi/v1/convert/acceptQuote",
            params=accept_params,
            headers=self._headers(),
            timeout=self.timeout_sec,
        )
        if not accept_resp.ok:
            raise RuntimeError(
                f"convert acceptQuote failed ({accept_resp.status_code}): {accept_resp.text}"
            )
        return accept_resp.json()

    def withdraw_coin(
        self,
        coin: str,
        amount: float,
        address: str,
        network: str | None = None,
        address_tag: str | None = None,
    ) -> dict:
        params: dict[str, str] = {
            "coin": coin.upper(),
            "amount": f"{amount:.8f}",
            "address": address,
        }
        if network:
            params["network"] = network
        if address_tag:
            params["addressTag"] = address_tag

        signed = self._signed_params(params)
        response = requests.post(
            f"{self.base_url}/sapi/v1/capital/withdraw/apply",
            params=signed,
            headers=self._headers(),
            timeout=self.timeout_sec,
        )
        if not response.ok:
            raise RuntimeError(
                f"binance withdraw failed ({response.status_code}): {response.text}"
            )
        return response.json()

