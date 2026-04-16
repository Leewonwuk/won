"""
리밸런싱 개선 패치:
1. 시장가 → GTC 지정가(mid price) 먼저 시도, 10초 미체결 시 시장가 fallback
2. 리밸런싱 BNB 수수료를 total_pnl_usd에 반영
"""
import re

path = "/home/ubuntu/arb/src/v12/live_engine_v2.py"
with open(path, encoding="utf-8") as f:
    content = f.read()

# ─── 1. _try_limit_rebalance 헬퍼 메서드 추가 (def _check_rebalance 직전) ───
HELPER = '''
    def _try_limit_rebalance(
        self, symbol: str, side: str, qty: float, price: float, timeout: float = 10.0
    ) -> bool:
        """GTC 지정가 리밸런싱 시도.
        timeout 초 내 체결되면 True, 미체결이면 주문 취소 후 False.
        False 반환 시 호출자가 시장가 폴백 처리."""
        try:
            resp = self.binance.place_limit_order(symbol, side, qty, price)
            order_id = str(resp["orderId"])
            deadline = time.time() + timeout
            while time.time() < deadline:
                time.sleep(0.5)
                try:
                    status = self.binance.get_order_status(symbol, order_id)
                except Exception:
                    break
                if status.get("status") == "FILLED":
                    log.info(
                        f"[{self._now_str()}] 리밸런싱 지정가 체결: "
                        f"{symbol} {side} {qty:.4f} @ {price:.6f}"
                    )
                    return True
                if status.get("status") in ("CANCELED", "REJECTED", "EXPIRED"):
                    return False
            # 타임아웃 → 취소 후 시장가 폴백
            try:
                self.binance.cancel_order(symbol, order_id)
            except Exception:
                pass
            log.info(
                f"[{self._now_str()}] 리밸런싱 지정가 {timeout:.0f}s 미체결 → 시장가 폴백"
            )
            return False
        except Exception as e:
            log.warning(f"[{self._now_str()}] 리밸런싱 지정가 시도 실패: {e} → 시장가 폴백")
            return False

'''

MARKER = "\n    def _check_rebalance(self) -> None:"
assert MARKER in content, "marker not found"
content = content.replace(MARKER, HELPER + MARKER, 1)

# ─── 2. 리밸런싱 실행 블록 교체 ───
# 교체 대상: "if not self.dry_run:" 블록 내 try 전체 (BNB 추적 + 지정가 시도 포함)

OLD_BLOCK = """\
            if not self.dry_run:
                rebalance_ok = False
                method_used = "spot"
                # Convert는 ~0.125% 스프레드로 USDT+USDC 총액을 직접 감소시킴.
                # USDCUSDT 현물은 스프레드 ~0.001% + BNB 수수료만 발생 → 총액 변동 거의 없음.
                # → 현물을 기본으로 사용하고 Convert는 폴백으로.
                try:
                    if from_asset == "USDT":
                        # USDT → USDC: quoteOrderQty로 USDC 매수
                        result = self.binance.place_market_buy_quote(
                            "USDCUSDT", from_amount
                        )
                    else:
                        # USDC → USDT: 실 free 잔고 확인 후 USDC 매도
                        # 거래 직후 정산 딜레이로 self.usdc가 실제 free 잔고보다 클 수 있음
                        actual_free_usdc = self.binance.get_spot_balances().get("USDC", 0.0)
                        safe_amount = min(from_amount, actual_free_usdc)
                        log.info(
                            f"[{self._now_str()}] 리밸런싱 SELL: want={from_amount:.2f} USDC, "
                            f"free={actual_free_usdc:.2f} USDC, sell={safe_amount:.2f}"
                        )
                        qty = self.binance.normalize_market_quantity(
                            "USDCUSDT", safe_amount
                        )
                        if qty <= 0:
                            raise RuntimeError(
                                f"USDCUSDT SELL qty=0 "
                                f"(want={from_amount:.2f}, free_usdc={actual_free_usdc:.2f})"
                            )
                        result = self.binance.place_market_order(
                            "USDCUSDT", "SELL", qty
                        )
                    log.info(f"현물 리밸런싱 완료: {result}")
                    rebalance_ok = True
                except Exception as e_spot:
                    # 현물 실패 → 1분 쿨다운 후 재시도 (Convert API quoteId 버그로 폴백 비활성화)
                    # -2010 원인: 거래 직후 바이낸스 정산 딜레이로 free USDC 일시 부족
                    # 보통 1~2분 내 자연 해소됨
                    log.warning(
                        f"[{self._now_str()}] 현물 리밸런싱 실패: {e_spot} "
                        f"→ 1분 후 재시도"
                    )
                    self._notify(f"⚠️ 현물 리밸런싱 실패 (1분 후 재시도): {e_spot}")
                    self._last_rebalance_ts = now - self.cfg.rebalance_min_interval_sec + 60
                    if self.global_lock is not None:
                        self.global_lock.set_rebalance_cooldown(now + 60)"""

NEW_BLOCK = """\
            if not self.dry_run:
                rebalance_ok = False
                method_used = "spot"
                # BNB 수수료 추적: 리밸런싱 전후 BNB 잔고 차이를 P&L에 반영
                _bnb_before = self.binance.get_spot_balances().get("BNB", 0.0)
                try:
                    _bid, _ask = self._get_bid_ask("USDCUSDT")
                    _mid = (_bid + _ask) / 2.0
                    _limit_price = self.binance.normalize_price("USDCUSDT", _mid)

                    if from_asset == "USDT":
                        # USDT → USDC: mid 가격으로 USDC 지정가 매수
                        _usdc_qty = self.binance.normalize_market_quantity(
                            "USDCUSDT", from_amount / max(_mid, 0.0001)
                        )
                        _filled = self._try_limit_rebalance(
                            "USDCUSDT", "BUY", _usdc_qty, _limit_price, timeout=10.0
                        )
                        if not _filled:
                            result = self.binance.place_market_buy_quote(
                                "USDCUSDT", from_amount
                            )
                            method_used = "spot_market"
                        else:
                            method_used = "spot_limit"
                    else:
                        # USDC → USDT: 실 free 잔고 확인 후 mid 가격으로 지정가 매도
                        actual_free_usdc = self.binance.get_spot_balances().get("USDC", 0.0)
                        safe_amount = min(from_amount, actual_free_usdc)
                        log.info(
                            f"[{self._now_str()}] 리밸런싱 SELL: want={from_amount:.2f} USDC, "
                            f"free={actual_free_usdc:.2f} USDC, sell={safe_amount:.2f}"
                        )
                        qty = self.binance.normalize_market_quantity(
                            "USDCUSDT", safe_amount
                        )
                        if qty <= 0:
                            raise RuntimeError(
                                f"USDCUSDT SELL qty=0 "
                                f"(want={from_amount:.2f}, free_usdc={actual_free_usdc:.2f})"
                            )
                        _filled = self._try_limit_rebalance(
                            "USDCUSDT", "SELL", qty, _limit_price, timeout=10.0
                        )
                        if not _filled:
                            result = self.binance.place_market_order(
                                "USDCUSDT", "SELL", qty
                            )
                            method_used = "spot_market"
                        else:
                            method_used = "spot_limit"

                    # BNB 수수료 P&L 반영
                    _bnb_after = self.binance.get_spot_balances().get("BNB", 0.0)
                    _bnb_used = max(0.0, _bnb_before - _bnb_after)
                    if _bnb_used > 0.000001:
                        try:
                            _bnb_px = float(self.binance.get_book_ticker("BNBUSDT")["bidPrice"])
                            _reb_fee = _bnb_used * _bnb_px
                            self.total_pnl_usd -= _reb_fee
                            log.info(
                                f"[{self._now_str()}] 리밸런싱 BNB 수수료: "
                                f"{_bnb_used:.6f} BNB × ${_bnb_px:.2f} = ${_reb_fee:.4f} → P&L 반영"
                            )
                        except Exception as _e_bnb:
                            log.warning(f"BNB 가격 조회 실패 (P&L 미반영): {_e_bnb}")

                    log.info(f"현물 리밸런싱 완료 ({method_used})")
                    rebalance_ok = True
                except Exception as e_spot:
                    log.warning(
                        f"[{self._now_str()}] 현물 리밸런싱 실패: {e_spot} "
                        f"→ 1분 후 재시도"
                    )
                    self._notify(f"⚠️ 현물 리밸런싱 실패 (1분 후 재시도): {e_spot}")
                    self._last_rebalance_ts = now - self.cfg.rebalance_min_interval_sec + 60
                    if self.global_lock is not None:
                        self.global_lock.set_rebalance_cooldown(now + 60)"""

assert OLD_BLOCK in content, "OLD_BLOCK not found"
content = content.replace(OLD_BLOCK, NEW_BLOCK, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("Patched OK")
