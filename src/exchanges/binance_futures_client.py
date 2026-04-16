"""Binance USDT-M Futures REST 클라이언트.

base_url: https://fapi.binance.com
현물(BinanceTradingClient)과 완전히 분리된 선물 전용 클라이언트.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode

import requests


@dataclass(slots=True)
class BinanceFuturesClient:
    api_key: str
    api_secret: str
    timeout_sec: float = 5.0
    recv_window: int = 5000
    base_url: str = "https://fapi.binance.com"
    _symbol_rules_cache: dict[str, dict] = field(default_factory=dict)

    # ── 인증 헬퍼 ─────────────────────────────────────────────────────────

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

    def _get(self, path: str, params: dict | None = None, signed: bool = False) -> dict:
        p = self._signed_params(params or {}) if signed else (params or {})
        resp = requests.get(
            f"{self.base_url}{path}",
            params=p,
            headers=self._headers(),
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, params: dict) -> dict:
        p = self._signed_params(params)
        resp = requests.post(
            f"{self.base_url}{path}",
            params=p,
            headers=self._headers(),
            timeout=self.timeout_sec,
        )
        if not resp.ok:
            raise RuntimeError(
                f"futures POST {path} failed ({resp.status_code}): {resp.text}"
            )
        return resp.json()

    def _delete(self, path: str, params: dict) -> dict:
        p = self._signed_params(params)
        resp = requests.delete(
            f"{self.base_url}{path}",
            params=p,
            headers=self._headers(),
            timeout=self.timeout_sec,
        )
        if not resp.ok:
            raise RuntimeError(
                f"futures DELETE {path} failed ({resp.status_code}): {resp.text}"
            )
        return resp.json()

    # ── 펀딩비 조회 ───────────────────────────────────────────────────────

    def get_premium_index(self, symbol: str) -> dict:
        """현재 펀딩비 + 다음 정산 시각 조회.

        반환 예시:
        {
            "symbol": "TRXUSDT",
            "markPrice": "0.12345",
            "lastFundingRate": "0.00010000",   ← 마지막 정산 펀딩비
            "nextFundingTime": 1713600000000,  ← ms timestamp
            "time": 1713596400000
        }
        """
        return self._get("/fapi/v1/premiumIndex", {"symbol": symbol.upper()})

    def get_funding_rate_history(
        self, symbol: str, limit: int = 100, start_time: int | None = None
    ) -> list[dict]:
        """펀딩비 히스토리 조회 (최신순).

        반환: [{"symbol", "fundingRate", "fundingTime", "markPrice"}, ...]
        """
        params: dict = {"symbol": symbol.upper(), "limit": limit}
        if start_time:
            params["startTime"] = start_time
        return self._get("/fapi/v1/fundingRate", params)

    # ── 잔고 / 포지션 조회 ────────────────────────────────────────────────

    def get_balance(self) -> list[dict]:
        """선물 지갑 잔고 조회.

        반환: [{"asset": "USDT", "balance": "...", "availableBalance": "..."}, ...]
        """
        return self._get("/fapi/v3/balance", signed=True)

    def get_usdt_balance(self) -> float:
        """선물 USDT 가용 잔고만 반환."""
        for b in self.get_balance():
            if b.get("asset") == "USDT":
                return float(b.get("availableBalance", 0))
        return 0.0

    def get_position_risk(self, symbol: str | None = None) -> list[dict]:
        """포지션 정보 조회.

        symbol 지정 시 해당 심볼만, None이면 전체.
        반환 필드: positionAmt, entryPrice, unrealizedProfit,
                   liquidationPrice, marginType, leverage, markPrice
        """
        params: dict = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return self._get("/fapi/v3/positionRisk", params=params, signed=True)

    def get_position(self, symbol: str) -> dict | None:
        """특정 심볼 포지션. 없으면 None."""
        positions = self.get_position_risk(symbol)
        for p in positions:
            if p.get("symbol") == symbol.upper():
                return p
        return None

    def get_income_history(
        self,
        income_type: str = "FUNDING_FEE",
        symbol: str | None = None,
        limit: int = 100,
        start_time: int | None = None,
    ) -> list[dict]:
        """펀딩비 수취 내역 조회.

        income_type: "FUNDING_FEE" | "REALIZED_PNL" | "COMMISSION" 등
        반환: [{"symbol", "incomeType", "income", "asset", "time"}, ...]
        """
        params: dict = {"incomeType": income_type, "limit": limit}
        if symbol:
            params["symbol"] = symbol.upper()
        if start_time:
            params["startTime"] = start_time
        return self._get("/fapi/v1/income", params=params, signed=True)

    # ── 계좌 설정 ─────────────────────────────────────────────────────────

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        """레버리지 설정 (진입 전 1회 호출)."""
        return self._post("/fapi/v1/leverage", {
            "symbol": symbol.upper(),
            "leverage": leverage,
        })

    def set_margin_type(self, symbol: str, margin_type: str = "ISOLATED") -> dict:
        """마진 모드 설정. margin_type: ISOLATED | CROSSED.

        이미 설정된 모드와 동일하면 -4046 에러 → 무시해도 됨.
        """
        try:
            return self._post("/fapi/v1/marginType", {
                "symbol": symbol.upper(),
                "marginType": margin_type.upper(),
            })
        except RuntimeError as e:
            if "-4046" in str(e):  # No need to change margin type
                return {"msg": "already set"}
            raise

    # ── 주문 ──────────────────────────────────────────────────────────────

    def place_market_order(
        self, symbol: str, side: str, quantity: float,
        reduce_only: bool = False,
    ) -> dict:
        """선물 시장가 주문.

        side: "BUY" | "SELL"
        reduce_only: True면 포지션 청산 전용 (신규 진입 불가)
        """
        params: dict = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": "MARKET",
            "quantity": f"{quantity:.8f}",
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        return self._post("/fapi/v1/order", params)

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
    ) -> dict:
        """선물 지정가 주문."""
        params: dict = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": "LIMIT",
            "timeInForce": time_in_force,
            "quantity": f"{quantity:.8f}",
            "price": f"{price:.8f}".rstrip("0").rstrip(".") or "0",
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        return self._post("/fapi/v1/order", params)

    def cancel_order(self, symbol: str, order_id: int | str) -> dict:
        """선물 주문 취소."""
        return self._delete("/fapi/v1/order", {
            "symbol": symbol.upper(),
            "orderId": int(order_id),
        })

    def get_order_status(self, symbol: str, order_id: int | str) -> dict:
        """선물 주문 상태 조회."""
        return self._get("/fapi/v1/order", {
            "symbol": symbol.upper(),
            "orderId": int(order_id),
        }, signed=True)

    def get_open_orders(self, symbol: str) -> list[dict]:
        """미체결 주문 목록."""
        return self._get("/fapi/v1/openOrders", {"symbol": symbol.upper()}, signed=True)

    def cancel_all_open_orders(self, symbol: str) -> dict:
        """미체결 주문 전체 취소."""
        return self._delete("/fapi/v1/allOpenOrders", {"symbol": symbol.upper()})

    # ── 호가 조회 ─────────────────────────────────────────────────────────

    def get_book_ticker(self, symbol: str) -> dict:
        """선물 최우선 호가 {bidPrice, askPrice, ...}."""
        return self._get("/fapi/v1/ticker/bookTicker", {"symbol": symbol.upper()})

    # ── LOT_SIZE 정규화 ───────────────────────────────────────────────────

    def _get_symbol_rules(self, symbol: str) -> dict:
        key = symbol.upper()
        if key in self._symbol_rules_cache:
            return self._symbol_rules_cache[key]
        data = self._get("/fapi/v1/exchangeInfo")
        for s in data.get("symbols", []):
            if s["symbol"] != key:
                continue
            lot_step = tick_size = min_qty = min_notional = 0.0
            for f in s.get("filters", []):
                ft = f.get("filterType")
                if ft == "LOT_SIZE":
                    lot_step = float(f.get("stepSize", 0) or 0)
                    min_qty = float(f.get("minQty", 0) or 0)
                elif ft == "MIN_NOTIONAL":
                    min_notional = float(f.get("notional", 0) or 0)
                elif ft == "PRICE_FILTER":
                    tick_size = float(f.get("tickSize", 0.01) or 0.01)
            rules = {
                "step_qty": lot_step,
                "min_qty": min_qty,
                "min_notional": min_notional,
                "tick_size": tick_size,
            }
            self._symbol_rules_cache[key] = rules
            return rules
        raise RuntimeError(f"futures exchangeInfo: symbol not found: {key}")

    def normalize_quantity(self, symbol: str, quantity: float) -> float:
        """LOT_SIZE step에 맞게 내림."""
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
        precision = max(0, -int(math.floor(math.log10(step)))) if step > 0 and step < 1 else 0
        return round(q, precision)

    def normalize_price(self, symbol: str, price: float) -> float:
        """tick_size에 맞게 내림."""
        rules = self._get_symbol_rules(symbol)
        tick = float(rules.get("tick_size", 0.0001) or 0.0001)
        floored = math.floor(price / tick) * tick
        decimals = max(0, -int(math.floor(math.log10(tick)))) if tick < 1 else 0
        return round(floored, decimals)
