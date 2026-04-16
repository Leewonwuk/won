"""Binance WebSocket client for real-time bookTicker data.

Subscribes to bookTicker streams for multiple symbols and updates a shared
price dict that the main loop reads.

Usage:
    prices: dict[str, dict] = {}
    task = asyncio.create_task(binance_ws_loop(["solusdt", "trxusdt"], prices))
"""
from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

BINANCE_WS_BASE = "wss://stream.binance.com:9443/ws"


def _build_stream_url(symbols: list[str]) -> str:
    """Build combined stream URL for multiple symbols.

    e.g. wss://stream.binance.com:9443/stream?streams=solusdt@bookTicker/trxusdt@bookTicker
    """
    streams = "/".join(f"{s.lower()}@bookTicker" for s in symbols)
    return f"wss://stream.binance.com:9443/stream?streams={streams}"


async def binance_ws_loop(
    symbols: list[str],
    prices: dict[str, dict],
    reconnect_delay: float = 3.0,
) -> None:
    """Persistent WebSocket loop for Binance bookTicker data.

    Updates `prices[SYMBOL]` (uppercase, e.g. "SOLUSDT") with latest bid/ask.
    """
    try:
        import websockets  # type: ignore
    except ImportError:
        logger.error("websockets package required: pip install websockets")
        return

    url = _build_stream_url(symbols)

    while True:
        try:
            async with websockets.connect(url, ping_interval=30) as ws:
                logger.info(f"Binance WS connected: {symbols}")

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        data = msg.get("data", msg)  # combined stream wraps in {"data": {...}}
                        symbol = data.get("s", "").upper()  # e.g. "SOLUSDT"
                        prices[symbol] = {
                            "bid_price": float(data.get("b", 0)),
                            "bid_qty": float(data.get("B", 0)),
                            "ask_price": float(data.get("a", 0)),
                            "ask_qty": float(data.get("A", 0)),
                            "timestamp": data.get("u", 0),  # update ID
                        }
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning(f"Binance WS parse error: {e}")

        except Exception as e:
            logger.warning(f"Binance WS disconnected: {e}, reconnecting in {reconnect_delay}s")
            await asyncio.sleep(reconnect_delay)
