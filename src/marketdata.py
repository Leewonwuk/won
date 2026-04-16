from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import Event, Lock, Thread
from typing import Callable

import json
import websockets

from src.exchanges.binance_client import BinanceClient
from src.exchanges.upbit_client import UpbitClient
from src.models import OrderBookTop, SpreadInput, utc_now_iso


class TickStreamCache:
    def __init__(self) -> None:
        self._upbit_top: OrderBookTop | None = None
        self._binance_top: OrderBookTop | None = None
        self._lock = Lock()
        self._event = Event()
        self._stop = Event()
        self._thread: Thread | None = None

    def _set_upbit(self, top: OrderBookTop) -> None:
        with self._lock:
            self._upbit_top = top
        self._event.set()

    def _set_binance(self, top: OrderBookTop) -> None:
        with self._lock:
            self._binance_top = top
        self._event.set()

    def latest(self) -> tuple[OrderBookTop | None, OrderBookTop | None]:
        with self._lock:
            return self._upbit_top, self._binance_top

    def wait_for_update(self, timeout_sec: float) -> bool:
        updated = self._event.wait(timeout=timeout_sec)
        self._event.clear()
        return updated

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def start(self, upbit_market: str, binance_symbol: str) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(
            target=self._run_thread,
            args=(upbit_market, binance_symbol),
            daemon=True,
        )
        self._thread.start()

    def _run_thread(self, upbit_market: str, binance_symbol: str) -> None:
        asyncio.run(self._run(upbit_market, binance_symbol))

    async def _run(self, upbit_market: str, binance_symbol: str) -> None:
        async def _reconnect_loop(coro_factory: Callable[[], asyncio.Future]) -> None:
            while not self._stop.is_set():
                try:
                    await coro_factory()
                except Exception:
                    await asyncio.sleep(1.0)

        await asyncio.gather(
            _reconnect_loop(lambda: self._upbit_loop(upbit_market)),
            _reconnect_loop(lambda: self._binance_loop(binance_symbol)),
        )

    async def _upbit_loop(self, upbit_market: str) -> None:
        async with websockets.connect("wss://api.upbit.com/websocket/v1", ping_interval=20) as ws:
            subscribe = [
                {"ticket": "arb-tick"},
                {"type": "orderbook", "codes": [upbit_market]},
            ]
            await ws.send(json.dumps(subscribe))
            while not self._stop.is_set():
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                payload = json.loads(raw)
                units = payload.get("orderbook_units", [])
                if not units:
                    continue
                top = units[0]
                self._set_upbit(
                    OrderBookTop(
                        exchange="upbit",
                        symbol=upbit_market,
                        bid=float(top["bid_price"]),
                        ask=float(top["ask_price"]),
                        ts=utc_now_iso(),
                    )
                )

    async def _binance_loop(self, binance_symbol: str) -> None:
        stream = f"wss://stream.binance.com:9443/ws/{binance_symbol.lower()}@bookTicker"
        async with websockets.connect(stream, ping_interval=20) as ws:
            while not self._stop.is_set():
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
                payload = json.loads(raw)
                self._set_binance(
                    OrderBookTop(
                        exchange="binance",
                        symbol=binance_symbol,
                        bid=float(payload["b"]),
                        ask=float(payload["a"]),
                        ts=utc_now_iso(),
                    )
                )


@dataclass(slots=True)
class MarketDataService:
    upbit: UpbitClient
    binance: BinanceClient
    _tick_cache: TickStreamCache | None = None

    def start_tick_streams(self, upbit_market: str, binance_symbol: str) -> None:
        if self._tick_cache is None:
            self._tick_cache = TickStreamCache()
        self._tick_cache.start(upbit_market=upbit_market, binance_symbol=binance_symbol)

    def stop_tick_streams(self) -> None:
        if self._tick_cache is not None:
            self._tick_cache.stop()

    def wait_tick(self, timeout_sec: float = 2.0) -> bool:
        if self._tick_cache is None:
            return False
        return self._tick_cache.wait_for_update(timeout_sec=timeout_sec)

    def snapshot(
        self,
        upbit_market: str,
        binance_symbol: str,
        fx_krw_per_usdt: float,
        fee_upbit_rate: float,
        fee_binance_rate: float,
        slippage_upbit_rate: float,
        slippage_binance_rate: float,
    ) -> SpreadInput:
        upbit_top: OrderBookTop | None = None
        binance_top: OrderBookTop | None = None
        if self._tick_cache is not None:
            upbit_top, binance_top = self._tick_cache.latest()
        if upbit_top is None:
            upbit_top = self.upbit.fetch_top(upbit_market)
        if binance_top is None:
            binance_top = self.binance.fetch_top(binance_symbol)
        return SpreadInput(
            upbit_krw=upbit_top,
            binance_usdt=binance_top,
            fx_krw_per_usdt=fx_krw_per_usdt,
            fee_upbit_rate=fee_upbit_rate,
            fee_binance_rate=fee_binance_rate,
            slippage_upbit_rate=slippage_upbit_rate,
            slippage_binance_rate=slippage_binance_rate,
        )

