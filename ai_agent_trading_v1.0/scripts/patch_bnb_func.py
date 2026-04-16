"""서버 live_v2_main.py 의 _check_bnb_recharge 함수를 교체하는 패치 스크립트."""
path = "/home/ubuntu/arb/src/v12/live_v2_main.py"

NEW_FUNC = '''\
def _check_bnb_recharge(engines: list, min_bnb: float = 0.1, target_bnb: float = 0.5) -> None:
    """BNB 잔고가 min_bnb 미만이면 target_bnb까지 지정가(GTC) 매수.
    engines[0]의 BinanceTradingClient를 재사용. 30분 요약 루프마다 1회 체크."""
    if not engines:
        return
    try:
        client = engines[0].binance
        account = client.get_account()
        bnb_free = next(
            (float(b["free"]) for b in account["balances"] if b["asset"] == "BNB"), 0.0
        )
        if bnb_free >= min_bnb:
            return  # 충분함

        need = target_bnb - bnb_free
        logging.warning(
            "[BNB 자동충전] 현재 BNB=%.4f < %.2f, BNB %.4f개 지정가 매수 시도...",
            bnb_free, min_bnb, need,
        )
        from src.notifications.telegram_notifier import send_telegram
        send_telegram(
            "\U0001f50b <b>BNB 자동충전</b>\\n"
            "현재 BNB: %.4f개 (임계값 %.2f개)\\n"
            "목표: %.1f개 (%.4f개 추가 지정가 매수)" % (bnb_free, min_bnb, target_bnb, need)
        )

        import math
        import requests as _req
        import hmac as _hmac
        import hashlib as _hs
        import time as _time
        from urllib.parse import urlencode as _ue

        API_KEY    = engines[0].binance.api_key
        API_SECRET = engines[0].binance.api_secret
        BASE_URL   = "https://api.binance.com"

        def _signed(params):
            p = {**params, "timestamp": int(_time.time() * 1000), "recvWindow": 5000}
            q = _ue(p)
            sig = _hmac.new(API_SECRET.encode(), q.encode(), _hs.sha256).hexdigest()
            return {**p, "signature": sig}

        def _hdr():
            return {"X-MBX-APIKEY": API_KEY}

        def _get_book(sym):
            r = _req.get(f"{BASE_URL}/api/v3/ticker/bookTicker",
                         params={"symbol": sym}, timeout=5)
            r.raise_for_status()
            return r.json()

        def _floor_qty(qty, step):
            prec = max(0, round(-math.log10(step)))
            return round(math.floor(qty / step) * step, prec)

        def _ceil_price(price, tick):
            prec = max(0, round(-math.log10(tick)))
            return round(math.ceil(price / tick) * tick, prec)

        # BNBUSDT 심볼 규칙 조회
        r = _req.get(f"{BASE_URL}/api/v3/exchangeInfo",
                     params={"symbol": "BNBUSDT"}, timeout=10)
        r.raise_for_status()
        info = r.json()["symbols"][0]
        lot  = next(f for f in info["filters"] if f["filterType"] == "LOT_SIZE")
        pf   = next(f for f in info["filters"] if f["filterType"] == "PRICE_FILTER")
        min_qty  = float(lot["minQty"])
        step_qty = float(lot["stepSize"])
        tick     = float(pf["tickSize"])

        # 현재 ask 가격 + 0.1% 버퍼로 지정가 (빠른 체결 유도)
        book = _get_book("BNBUSDT")
        ask  = float(book["askPrice"])
        buy_price = _ceil_price(ask * 1.001, tick)
        cost = need * buy_price

        # USDT 잔고 확인 / 부족하면 USDC -> USDT 전환
        usdt_free = next(
            (float(b["free"]) for b in account["balances"] if b["asset"] == "USDT"), 0.0
        )
        if usdt_free < cost * 1.02:
            extra = cost * 1.05 - usdt_free
            r2 = _req.get(f"{BASE_URL}/api/v3/exchangeInfo",
                          params={"symbol": "USDCUSDT"}, timeout=10)
            r2.raise_for_status()
            lot2  = next(f for f in r2.json()["symbols"][0]["filters"]
                         if f["filterType"] == "LOT_SIZE")
            step2 = float(lot2["stepSize"])
            sell_qty = _floor_qty(extra, step2)
            if sell_qty >= float(lot2["minQty"]):
                client.place_market_order("USDCUSDT", "SELL", sell_qty)
                _time.sleep(1)
                logging.info("[BNB 자동충전] USDC %.1f -> USDT 전환 완료", sell_qty)

        qty = _floor_qty(need, step_qty)
        if qty < min_qty:
            logging.warning("[BNB 자동충전] qty=%.4f < minQty=%.4f, 스킵", qty, min_qty)
            return

        # 지정가(GTC) 매수
        params = _signed({
            "symbol":    "BNBUSDT",
            "side":      "BUY",
            "type":      "LIMIT",
            "timeInForce": "GTC",
            "quantity":  f"{qty:.8f}",
            "price":     f"{buy_price:.8f}",
        })
        resp = _req.post(f"{BASE_URL}/api/v3/order",
                         params=params, headers=_hdr(), timeout=10)
        resp.raise_for_status()
        result = resp.json()
        send_telegram(
            "\u2705 <b>BNB 자동충전 주문 접수</b>\\n"
            "%.4f개 @ $%.2f (GTC 지정가)\\n"
            "orderId: %s" % (qty, buy_price, result.get("orderId"))
        )
        logging.info("[BNB 자동충전] %.4f개 @ $%.2f GTC 접수: %s",
                     qty, buy_price, result.get("orderId"))
    except Exception as e:
        logging.error("[BNB 자동충전] 실패: %s", e)

'''

with open(path, encoding="utf-8") as f:
    content = f.read()

# Find the old function boundaries
start_marker = "def _check_bnb_recharge("
end_marker   = "\ndef main() -> None:"

s = content.find(start_marker)
e = content.find(end_marker)
assert s >= 0, "start marker not found"
assert e >= 0, "end marker not found"
assert e > s,  "end before start?"

content = content[:s] + NEW_FUNC + content[e:]

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("Patched OK: _check_bnb_recharge replaced with limit-order version")
