#!/usr/bin/env python3
"""Binance API: BTCUSDT / BTCUSDC symbol whitelist smoke test (order/test, no execution)."""
from __future__ import annotations

import hashlib
import hmac
import math
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

BASE = "https://api.binance.com"


def _signed(secret: str, params: dict) -> dict:
    p = {**params, "timestamp": int(time.time() * 1000), "recvWindow": 5000}
    q = urlencode(p)
    sig = hmac.new(secret.encode("utf-8"), q.encode("utf-8"), hashlib.sha256).hexdigest()
    return {**p, "signature": sig}


def _normalize_price(tick: float, price: float) -> float:
    if tick <= 0:
        tick = 0.01
    floored = math.floor(price / tick) * tick
    decimals = max(0, -int(math.floor(math.log10(tick)))) if tick < 1 else 0
    return round(floored, decimals)


def _rules(symbol: str) -> tuple[float, float, float]:
    r = requests.get(f"{BASE}/api/v3/exchangeInfo", params={"symbol": symbol}, timeout=10)
    r.raise_for_status()
    syms = r.json().get("symbols") or []
    if not syms:
        raise RuntimeError(f"no symbol {symbol}")
    tick, step, min_q = 0.01, 0.00001, 0.0
    for f in syms[0].get("filters", []):
        t = f.get("filterType")
        if t == "PRICE_FILTER":
            tick = float(f.get("tickSize", 0.01) or 0.01)
        elif t == "LOT_SIZE":
            step = float(f.get("stepSize", 0) or 0)
            min_q = float(f.get("minQty", 0) or 0)
    return tick, step, min_q


def test_symbol(api_key: str, api_secret: str, symbol: str) -> None:
    tick, step, min_q = _rules(symbol)
    book = requests.get(
        f"{BASE}/api/v3/ticker/bookTicker", params={"symbol": symbol}, timeout=10
    )
    book.raise_for_status()
    bid = float(book.json()["bidPrice"])
    # Slightly below best bid — within PERCENT_PRICE corridor; order/test does not execute.
    raw_price = bid * 0.999
    price = _normalize_price(tick, raw_price)
    target_notional = 10.0
    qty = target_notional / price
    if step > 0:
        qty = math.floor(qty / step) * step
    if qty < min_q:
        qty = min_q
    params = _signed(
        api_secret,
        {
            "symbol": symbol.upper(),
            "side": "BUY",
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": f"{qty:.8f}",
            "price": f"{price:.8f}".rstrip("0").rstrip(".") or "0",
        },
    )
    resp = requests.post(
        f"{BASE}/api/v3/order/test",
        params=params,
        headers={"X-MBX-APIKEY": api_key},
        timeout=10,
    )
    if resp.status_code == 200:
        print(f"OK  {symbol}  (whitelist allows this symbol; test order accepted)")
    else:
        print(f"FAIL {symbol}  HTTP {resp.status_code}  {resp.text[:400]}")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    key = os.getenv("BINANCE_API_KEY", "").strip()
    secret = os.getenv("BINANCE_API_SECRET", "").strip()
    if not key or not secret:
        print("BINANCE_API_KEY / BINANCE_API_SECRET missing (.env)", file=sys.stderr)
        return 1
    for sym in ("BTCUSDT", "BTCUSDC", "SOLUSDT", "SOLUSDC", "XRPUSDT", "XRPUSDC"):
        try:
            test_symbol(key, secret, sym)
        except Exception as e:
            print(f"FAIL {sym}  {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
