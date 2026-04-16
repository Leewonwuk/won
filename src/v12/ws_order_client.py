"""Binance WebSocket Order API 클라이언트.

단일 WS 연결에서 주문을 발행하여 REST 대비 ~50-80ms 절약.
URL: wss://ws-api.binance.com:443/ws-api/v3

엔진(동기 스레드)에서 place_limit_order() / place_market_order() 호출 →
asyncio 이벤트 루프에 코루틴 제출 → WS 프레임 송신 → 응답 수신 후 반환.
연결 실패/오류 시 RuntimeError raise → 호출자가 REST fallback 처리.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlencode

log = logging.getLogger(__name__)

_WS_API_URL      = "wss://ws-api.binance.com:443/ws-api/v3"
_RECONNECT_DELAY = 2.0
_REQUEST_TIMEOUT = 4.0   # 개별 주문 응답 대기 최대 시간(초)


@dataclass
class BinanceTradingWsClient:
    """WebSocket 기반 주문 발행 클라이언트."""

    api_key: str
    api_secret: str

    _loop: asyncio.AbstractEventLoop | None = field(default=None, init=False)
    _ws: object | None = field(default=None, init=False)           # websockets connection
    _pending: dict = field(default_factory=dict, init=False)       # {req_id: asyncio.Future}
    _ready: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)

    # ── 공개 API ──────────────────────────────────────────────────────

    def start(self, wait_timeout: float = 8.0) -> bool:
        """백그라운드 daemon thread 시작. True=연결 완료."""
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="WsOrderClient"
        )
        self._thread.start()
        ok = self._ready.wait(timeout=wait_timeout)
        if not ok:
            log.warning("[WsOrder] WS API 연결 타임아웃 — REST fallback 사용")
        return ok

    def is_ready(self) -> bool:
        return self._ready.is_set()

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        time_in_force: str = "IOC",
    ) -> dict:
        """지정가 주문 발행. 실패 시 RuntimeError raise."""
        params = self._signed_params({
            "symbol":      symbol.upper(),
            "side":        side.upper(),
            "type":        "LIMIT",
            "timeInForce": time_in_force,
            "quantity":    f"{quantity:.8f}",
            "price":       f"{price:.8f}".rstrip("0").rstrip(".") or "0",
        })
        return self._request_sync("order.place", params)

    def place_market_order(self, symbol: str, side: str, quantity: float) -> dict:
        """시장가 주문 발행. 실패 시 RuntimeError raise."""
        params = self._signed_params({
            "symbol":   symbol.upper(),
            "side":     side.upper(),
            "type":     "MARKET",
            "quantity": f"{quantity:.8f}",
        })
        return self._request_sync("order.place", params)

    def cancel_order(self, symbol: str, order_id: str) -> dict:
        """주문 취소. 실패 시 RuntimeError raise."""
        params = self._signed_params({
            "symbol":  symbol.upper(),
            "orderId": int(order_id),
        })
        return self._request_sync("order.cancel", params)

    # ── 내부 ──────────────────────────────────────────────────────────

    def _signed_params(self, params: dict) -> dict:
        params["apiKey"]    = self.api_key
        params["timestamp"] = int(time.time() * 1000)
        query = urlencode(sorted(params.items()))
        params["signature"] = hmac.new(
            self.api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        return params

    def _request_sync(self, method: str, params: dict) -> dict:
        if self._loop is None or not self._ready.is_set():
            raise RuntimeError("WsOrderClient not ready")
        req_id = str(uuid.uuid4())
        frame  = {"id": req_id, "method": method, "params": params}
        fut = asyncio.run_coroutine_threadsafe(
            self._request_async(req_id, frame), self._loop
        )
        msg = fut.result(timeout=_REQUEST_TIMEOUT + 1.0)
        status = msg.get("status", 0)
        if status != 200:
            raise RuntimeError(f"WS Order API error {status}: {msg.get('error')}")
        return msg["result"]

    async def _request_async(self, req_id: str, frame: dict) -> dict:
        ws = self._ws
        if ws is None:
            raise RuntimeError("WS not connected")
        fut = self._loop.create_future()
        self._pending[req_id] = fut
        try:
            await ws.send(json.dumps(frame))
            return await asyncio.wait_for(asyncio.shield(fut), timeout=_REQUEST_TIMEOUT)
        except Exception:
            self._pending.pop(req_id, None)
            raise

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        loop.run_until_complete(self._ws_loop())

    async def _ws_loop(self) -> None:
        try:
            import websockets  # type: ignore
        except ImportError:
            log.error("[WsOrder] websockets 패키지 없음")
            return

        while True:
            try:
                async with websockets.connect(
                    _WS_API_URL, ping_interval=20, ping_timeout=10
                ) as ws:
                    self._ws = ws
                    self._ready.set()
                    log.info("[WsOrder] WS API 연결됨")
                    async for raw in ws:
                        try:
                            msg    = json.loads(raw)
                            req_id = msg.get("id")
                            if req_id and req_id in self._pending:
                                fut = self._pending.pop(req_id)
                                if not fut.done():
                                    fut.set_result(msg)
                        except Exception as e:
                            log.debug(f"[WsOrder] 응답 파싱 오류: {e}")
            except Exception as e:
                self._ready.clear()
                self._ws = None
                log.warning(f"[WsOrder] WS 끊김: {e} — {_RECONNECT_DELAY}s 후 재연결")
                await asyncio.sleep(_RECONNECT_DELAY)
