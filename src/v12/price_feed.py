"""실시간 호가 & 주문 체결 WebSocket 피드 (v1.2 전용).

두 WebSocket을 단일 asyncio 루프에서 관리:
  1. bookTicker combined stream  — SOLUSDT/SOLUSDC/XRPUSDT/... bid/ask 실시간 캐시
  2. User Data Stream            — 주문 체결/취소 이벤트 (listenToken 기반, WS API)
     ※ 구 listenKey 방식(POST /api/v3/userDataStream)은 2026-02-20 deprecated →
        새 방식: POST /sapi/v1/userListenToken + userDataStream.subscribe.listenToken

메인 엔진 스레드(동기)는 get_mid() / pop_fill() 로 결과를 즉시 읽는다.
REST get_book_ticker / get_order_status 호출이 사라지므로 레이턴시가 획기적으로 줄어든다.

Usage:
    feed = PriceFeed(api_key="...", api_secret="...", symbols=["SOLUSDT","SOLUSDC",...])
    feed.start()           # daemon thread 에서 asyncio 루프 실행
    feed.wait_ready(10)    # 최대 10s 대기

    mid  = feed.get_mid("SOLUSDT")      # 즉시, 0ms
    ev   = feed.pop_fill(order_id=123)  # executionReport dict or None
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
from typing import Callable
from urllib.parse import urlencode

import requests

log = logging.getLogger(__name__)

_BINANCE_REST    = "https://api.binance.com"
_BINANCE_WS      = "wss://stream.binance.com:9443"
_BINANCE_WS_API  = "wss://ws-api.binance.com:443/ws-api/v3"
_RECONNECT_DELAY = 2.0    # WS 재연결 대기(초)
_KEEPALIVE_SEC   = 43200  # listenToken 갱신 주기 (12시간; 유효기간 24시간)


@dataclass
class PriceFeed:
    """bookTicker + User Data Stream 통합 피드."""

    api_key: str
    api_secret: str = ""     # HMAC 서명용 (listenToken 발급에 필요)
    symbols: list[str] = field(default_factory=list)  # 대소문자 무관, 내부에서 upper() 처리
    stale_sec: float = 5.0   # 이 초 이상 업데이트 없으면 stale

    # ── 공유 상태 (WS 스레드 write, 엔진 스레드 read) ─────────────────
    # CPython dict 단일 키 읽기/쓰기는 GIL이 보호하므로 Lock 불필요
    _prices: dict[str, dict] = field(default_factory=dict, init=False)
    # {orderId(int): executionReport dict}
    _fills: dict[int, dict]   = field(default_factory=dict, init=False)

    _ready_evt: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _user_data_backoff_sec: float = field(default=_RECONNECT_DELAY + 1, init=False)
    _user_data_log_next_ts: float = field(default=0.0, init=False)
    _user_data_warned_rest_fallback: bool = field(default=False, init=False)

    # ── 콜백 (event-driven 모드) ──────────────────────────────────────
    _price_cb: Callable | None = field(default=None, init=False)
    _fill_cb: Callable | None = field(default=None, init=False)

    # ── 공개 API ──────────────────────────────────────────────────────

    def start(self) -> None:
        """백그라운드 daemon thread 에서 WS 루프 시작."""
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="PriceFeed-WS",
        )
        self._thread.start()

    def wait_ready(self, timeout: float = 10.0) -> bool:
        """모든 symbols의 첫 번째 tick 수신까지 대기. True=성공."""
        ok = self._ready_evt.wait(timeout=timeout)
        if not ok:
            log.warning("[PriceFeed] WS 연결 타임아웃 — REST fallback 으로 동작")
        return ok

    def get_mid(self, symbol: str) -> float | None:
        """최신 mid price. stale/미수신 시 None (REST fallback 필요)."""
        p = self._prices.get(symbol.upper())
        if p is None:
            return None
        age = time.monotonic() - p["ts"]
        if age > self.stale_sec:
            log.debug(f"[PriceFeed] {symbol} stale ({age:.1f}s)")
            return None
        return (p["bid"] + p["ask"]) / 2.0

    def get_bid_ask(self, symbol: str) -> tuple[float, float] | None:
        """최신 (bid, ask). stale/미수신 시 None."""
        p = self._prices.get(symbol.upper())
        if p is None:
            return None
        age = time.monotonic() - p["ts"]
        if age > self.stale_sec:
            return None
        return (float(p["bid"]), float(p["ask"]))

    def pop_fill(self, order_id: int) -> dict | None:
        """체결/취소 이벤트를 꺼내고 삭제 (소비형). 없으면 None."""
        return self._fills.pop(order_id, None)

    def is_price_ready(self, *symbols: str) -> bool:
        """지정 심볼이 모두 한 번 이상 수신됐는지."""
        return all(s.upper() in self._prices for s in symbols)

    def register_callbacks(
        self,
        on_price: Callable[[str, float, float], None] | None = None,
        on_fill: Callable[[int, dict], None] | None = None,
    ) -> None:
        """WS 이벤트 콜백 등록. 엔진 event-driven 루프에서 호출."""
        self._price_cb = on_price
        self._fill_cb = on_fill

    # ── 내부: 스레드 진입점 ───────────────────────────────────────────

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main())
        finally:
            loop.close()

    async def _main(self) -> None:
        await asyncio.gather(
            self._book_ticker_loop(),
            self._user_data_loop(),
        )

    # ── 1. bookTicker combined stream ─────────────────────────────────

    async def _book_ticker_loop(self) -> None:
        try:
            import websockets  # type: ignore
        except ImportError:
            log.error("[PriceFeed] 'websockets' 패키지 없음: pip install websockets")
            return

        streams = "/".join(f"{s.lower()}@bookTicker" for s in self.symbols)
        url = f"{_BINANCE_WS}/stream?streams={streams}"

        while True:
            try:
                async with websockets.connect(
                    url, ping_interval=20, ping_timeout=10
                ) as ws:
                    log.info(f"[PriceFeed] bookTicker WS 연결: {self.symbols}")
                    async for raw in ws:
                        try:
                            msg  = json.loads(raw)
                            data = msg.get("data", msg)   # combined stream 래핑 해제
                            sym  = data.get("s", "").upper()
                            if not sym:
                                continue
                            bid = float(data["b"])
                            ask = float(data["a"])
                            self._prices[sym] = {
                                "bid": bid,
                                "ask": ask,
                                "ts":  time.monotonic(),
                            }
                            # 등록 심볼 모두 수신 → ready
                            if (
                                not self._ready_evt.is_set()
                                and self.is_price_ready(*self.symbols)
                            ):
                                self._ready_evt.set()
                                log.info("[PriceFeed] 모든 심볼 수신 완료 → READY")
                            # 가격 콜백 (event-driven 모드)
                            if self._price_cb is not None:
                                try:
                                    self._price_cb(sym, bid, ask)
                                except Exception:
                                    pass
                        except Exception as e:
                            log.debug(f"[PriceFeed] bookTicker 파싱 오류: {e}")
            except Exception as e:
                log.warning(
                    f"[PriceFeed] bookTicker WS 끊김: {e} "
                    f"— {_RECONNECT_DELAY}s 후 재연결"
                )
                await asyncio.sleep(_RECONNECT_DELAY)

    # ── 2. User Data Stream (신규: userDataStream.subscribe.signature WS API) ──
    # 구 방식(POST /api/v3/userDataStream + listenKey)은 2026-02-20 deprecated.
    # 새 방식: WS API에서 userDataStream.subscribe.signature 메서드 + HMAC 서명.
    # REST 호출 없이 WS 연결 후 직접 서명된 구독 메시지 전송.

    def _uds_signed_params(self) -> dict:
        """userDataStream.subscribe.signature 용 HMAC 서명 파라미터 생성."""
        params = {
            "apiKey":    self.api_key,
            "timestamp": int(time.time() * 1000),
        }
        query = urlencode(sorted(params.items()))
        params["signature"] = hmac.new(
            self.api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        return params

    async def _user_data_loop(self) -> None:
        try:
            import websockets  # type: ignore
        except ImportError:
            return

        if not self.api_secret:
            log.warning("[PriceFeed] api_secret 미설정 — User Data Stream 비활성화 (REST fallback)")
            return

        while True:
            try:
                log.info("[PriceFeed] User Data Stream (WS API subscribe.signature) 연결 시도")
                self._user_data_backoff_sec = _RECONNECT_DELAY + 1
                self._user_data_warned_rest_fallback = False

                async with websockets.connect(
                    _BINANCE_WS_API, ping_interval=20, ping_timeout=10
                ) as ws:
                    sub_id = str(uuid.uuid4())
                    await ws.send(json.dumps({
                        "id":     sub_id,
                        "method": "userDataStream.subscribe.signature",
                        "params": self._uds_signed_params(),
                    }))

                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                            # 구독 ACK
                            if msg.get("id") == sub_id:
                                if msg.get("status") == 200:
                                    log.info("[PriceFeed] User Data Stream 연결 성공 (subscribe.signature)")
                                else:
                                    log.warning(f"[PriceFeed] UDS 구독 실패: {msg}")
                                continue
                            # 체결 이벤트: {"stream": "userDataStream", "data": {...}}
                            ev = msg.get("data", msg)
                            if ev.get("e") != "executionReport":
                                continue
                            order_id = int(ev.get("i", 0))
                            status   = ev.get("X", "")
                            if status in ("FILLED", "CANCELED", "EXPIRED"):
                                self._fills[order_id] = ev
                                log.debug(
                                    f"[PriceFeed] executionReport "
                                    f"orderId={order_id} status={status}"
                                )
                                if self._fill_cb is not None:
                                    try:
                                        self._fill_cb(order_id, ev)
                                    except Exception:
                                        pass
                        except Exception as e:
                            log.debug(f"[PriceFeed] User Data 파싱 오류: {e}")

            except Exception as e:
                self._user_data_backoff_sec = min(60.0, max(_RECONNECT_DELAY + 1, self._user_data_backoff_sec))
                now = time.monotonic()
                if now >= self._user_data_log_next_ts:
                    log.warning(
                        f"[PriceFeed] User Data Stream 끊김: {e} "
                        f"— {self._user_data_backoff_sec:.0f}s 후 재연결"
                    )
                    self._user_data_log_next_ts = now + 60.0

                await asyncio.sleep(self._user_data_backoff_sec)
