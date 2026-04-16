"""Upbit WebSocket client for real-time ticker data.

Subscribes to ticker feed for multiple markets and updates a shared
price dict that the main loop reads.

Usage:
    prices: dict[str, dict] = {}
    task = asyncio.create_task(upbit_ws_loop(["KRW-SOL", "KRW-TRX", "KRW-USDT"], prices))
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

logger = logging.getLogger(__name__)

UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"


async def upbit_ws_loop(
    markets: list[str],
    prices: dict[str, dict],
    reconnect_delay: float = 3.0,
) -> None:
    """Persistent WebSocket loop for Upbit ticker data.

    Updates `prices[market]` with latest bid/ask/trade_price on each message.
    Reconnects automatically on disconnect.
    """
    try:
        import websockets  # type: ignore
    except ImportError:
        logger.error("websockets package required: pip install websockets")
        return

    subscribe_msg = json.dumps([
        {"ticket": str(uuid.uuid4())},
        {"type": "ticker", "codes": markets, "isOnlyRealtime": True},
        {"format": "SIMPLE"},
    ])

    while True:
        try:
            async with websockets.connect(UPBIT_WS_URL, ping_interval=30) as ws:
                await ws.send(subscribe_msg)
                logger.info(f"Upbit WS connected: {markets}")

                async for raw in ws:
                    try:
                        if isinstance(raw, bytes):
                            data = json.loads(raw.decode("utf-8"))
                        else:
                            data = json.loads(raw)

                        market = data.get("cd", "")  # code (e.g. "KRW-SOL")
                        prices[market] = {
                            "trade_price": data.get("tp", 0.0),       # 체결가
                            "opening_price": data.get("op", 0.0),     # 시가
                            "high_price": data.get("hp", 0.0),        # 고가
                            "low_price": data.get("lp", 0.0),         # 저가
                            "bid_price": data.get("bp", 0.0),         # 매수 호가 (placeholder; ticker may not have)
                            "ask_price": data.get("ap", 0.0),         # 매도 호가
                            "trade_volume": data.get("tv", 0.0),
                            "timestamp": data.get("tms", 0),
                        }
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Upbit WS parse error: {e}")

        except Exception as e:
            logger.warning(f"Upbit WS disconnected: {e}, reconnecting in {reconnect_delay}s")
            await asyncio.sleep(reconnect_delay)
