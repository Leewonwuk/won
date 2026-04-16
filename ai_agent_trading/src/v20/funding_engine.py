"""v2.0 펀딩비 차익거래 엔진.

상태머신: IDLE → ENTERING → HOLDING → EXITING → IDLE
"""
from __future__ import annotations

import csv
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from src.exchanges.binance_futures_client import BinanceFuturesClient
from src.exchanges.binance_trading_client import BinanceTradingClient

from .config_v20 import FundingArbConfig
from .funding_strategy import (
    annualized_yield,
    calc_position_size,
    should_enter,
    should_exit,
)
from .position_state import EngineState, ExitReason, PositionState

log = logging.getLogger(__name__)


class FundingEngine:
    """코인 1개 담당 엔진. main.py에서 스레드당 1개 생성."""

    def __init__(
        self,
        cfg: FundingArbConfig,
        spot: BinanceTradingClient,
        futures: BinanceFuturesClient,
        notifier=None,
    ):
        self.cfg = cfg
        self.spot = spot
        self.futures = futures
        self._notify = notifier or (lambda msg: None)

        self.state = EngineState.IDLE
        self.position = PositionState(symbol=cfg.symbol)

        self._last_exit_time: float = 0.0
        self._last_exit_reason: ExitReason | None = None
        self._last_summary_time: float = 0.0
        self._last_funding_rate: float = 0.0
        self._next_funding_time_ms: int = 0

        # CSV 경로
        log_dir = Path(cfg.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._csv_path = log_dir / f"funding_{cfg.symbol}_{date_str}.csv"
        self._init_csv()

    # ── 초기화 ─────────────────────────────────────────────────────────────

    def _init_csv(self):
        with open(self._csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "시각", "종류", "symbol", "현물수량", "현물진입가",
                "선물수량", "선물진입가", "펀딩비(8h)", "수취펀딩비합계",
                "net_pnl_usd", "보유시간(h)", "사유",
            ])

    def _log_trade(self, kind: str, reason: str = ""):
        spot_price = self.position.spot_entry_price
        fut_price = self.position.futures_entry_price
        net = self.position.net_pnl(spot_price, fut_price) if self.state == EngineState.IDLE else 0.0
        with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                self._now_str(), kind, self.cfg.symbol,
                f"{self.position.spot_qty:.6f}", f"{self.position.spot_entry_price:.6f}",
                f"{self.position.futures_qty:.6f}", f"{self.position.futures_entry_price:.6f}",
                f"{self._last_funding_rate:.6f}",
                f"{self.position.collected_funding_usdt:.4f}",
                f"{net:.4f}",
                f"{self.position.hold_hours():.2f}",
                reason,
            ])

    def _now_str(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # ── 선물 초기 설정 ─────────────────────────────────────────────────────

    def setup_futures(self):
        """레버리지 / 마진 모드 설정 (봇 시작 시 1회)."""
        try:
            self.futures.set_margin_type(self.cfg.futures_symbol, "ISOLATED")
            log.info(f"[{self.cfg.symbol}] 마진 모드: ISOLATED")
        except Exception as e:
            log.warning(f"[{self.cfg.symbol}] 마진 모드 설정: {e}")
        try:
            self.futures.set_leverage(self.cfg.futures_symbol, self.cfg.leverage)
            log.info(f"[{self.cfg.symbol}] 레버리지: {self.cfg.leverage}x")
        except Exception as e:
            log.warning(f"[{self.cfg.symbol}] 레버리지 설정: {e}")

    # ── 펀딩비 조회 ────────────────────────────────────────────────────────

    def _fetch_funding_info(self) -> tuple[float, int]:
        """(현재 펀딩비, 다음 정산 ms timestamp) 반환."""
        data = self.futures.get_premium_index(self.cfg.futures_symbol)
        rate = float(data.get("lastFundingRate", 0))
        next_ts = int(data.get("nextFundingTime", 0))
        return rate, next_ts

    def _is_pre_funding(self) -> bool:
        """다음 정산까지 pre_funding_check_sec 이내인지 확인."""
        if self._next_funding_time_ms == 0:
            return False
        remaining = (self._next_funding_time_ms / 1000) - time.time()
        return 0 < remaining < self.cfg.pre_funding_check_sec

    # ── 현물 / 선물 가격 조회 ─────────────────────────────────────────────

    def _get_prices(self) -> tuple[float, float]:
        """(현물 ask, 선물 ask) 반환."""
        spot_ticker = self.spot.get_book_ticker(self.cfg.spot_symbol)
        fut_ticker = self.futures.get_book_ticker(self.cfg.futures_symbol)
        return float(spot_ticker["askPrice"]), float(fut_ticker["askPrice"])

    # ── 증거금 비율 조회 ───────────────────────────────────────────────────

    def _get_margin_ratio(self) -> float | None:
        try:
            pos = self.futures.get_position(self.cfg.futures_symbol)
            if pos is None:
                return None
            maint = float(pos.get("maintMargin", 0) or 0)
            wallet = float(pos.get("isolatedWallet", 0) or 0)
            if wallet <= 0:
                return None
            return maint / wallet
        except Exception as e:
            log.debug(f"[{self.cfg.symbol}] 증거금 비율 조회 실패: {e}")
            return None

    # ── 진입 ───────────────────────────────────────────────────────────────

    def _enter(self, funding_rate: float, spot_ask: float, fut_ask: float):
        cfg = self.cfg
        self.state = EngineState.ENTERING

        # 수량 계산
        raw_qty = calc_position_size(cfg.capital_usdt, spot_ask, cfg)
        spot_qty = self.spot.normalize_market_quantity(cfg.spot_symbol, raw_qty)
        fut_qty = self.futures.normalize_quantity(cfg.futures_symbol, raw_qty)

        if spot_qty <= 0 or fut_qty <= 0:
            log.warning(f"[{cfg.symbol}] 수량 계산 실패 (qty={raw_qty:.6f}) → 진입 취소")
            self.state = EngineState.IDLE
            return

        log.info(
            f"[{cfg.symbol}] 진입 시작 | 펀딩비 {funding_rate:.4%} (연 {annualized_yield(funding_rate):.1%}) | "
            f"현물 {spot_qty} @ {spot_ask} | 선물 SHORT {fut_qty} @ {fut_ask}"
        )

        if cfg.dry_run:
            # Dry run: 실제 주문 없이 상태만 업데이트
            self._set_position(spot_qty, spot_ask, fut_qty, fut_ask, funding_rate, cfg.dry_run)
            return

        # 1단계: 현물 시장가 매수
        try:
            spot_result = self.spot.place_market_order(cfg.spot_symbol, "BUY", spot_qty)
            actual_spot_qty = float(spot_result.get("executedQty", spot_qty))
            actual_spot_price = (
                float(spot_result.get("cummulativeQuoteQty", 0)) / actual_spot_qty
                if actual_spot_qty > 0 else spot_ask
            )
            spot_fee = actual_spot_qty * actual_spot_price * cfg.spot_fee_rate
            log.info(f"[{cfg.symbol}] 현물 매수 완료: {actual_spot_qty} @ {actual_spot_price:.6f}")
        except Exception as e:
            log.error(f"[{cfg.symbol}] 현물 매수 실패: {e} → 진입 취소")
            self._notify(f"❌ [{cfg.symbol}] 현물 매수 실패: {e}")
            self.state = EngineState.IDLE
            return

        # 2단계: 선물 시장가 공매도 (현물 체결 확인 후)
        try:
            # 선물 수량을 실제 현물 체결 수량에 맞춤
            fut_qty_adj = self.futures.normalize_quantity(cfg.futures_symbol, actual_spot_qty)
            fut_result = self.futures.place_market_order(
                cfg.futures_symbol, "SELL", fut_qty_adj, reduce_only=False
            )
            actual_fut_price = float(fut_result.get("avgPrice", fut_ask))
            fut_fee = fut_qty_adj * actual_fut_price * cfg.futures_fee_rate
            log.info(f"[{cfg.symbol}] 선물 공매도 완료: {fut_qty_adj} SHORT @ {actual_fut_price:.6f}")
        except Exception as e:
            log.error(f"[{cfg.symbol}] 선물 공매도 실패: {e} → 현물 즉시 청산")
            self._notify(f"⚠️ [{cfg.symbol}] 선물 진입 실패 → 현물 청산 중")
            try:
                self.spot.place_market_order(cfg.spot_symbol, "SELL", actual_spot_qty)
            except Exception as e2:
                log.error(f"[{cfg.symbol}] 현물 청산도 실패!: {e2}")
                self._notify(f"🚨 [{cfg.symbol}] 현물 청산 실패! 수동 개입 필요")
            self.state = EngineState.IDLE
            return

        self._set_position(
            actual_spot_qty, actual_spot_price,
            fut_qty_adj, actual_fut_price,
            funding_rate,
            dry_run=False,
            spot_fee=spot_fee,
            futures_fee=fut_fee,
        )

    def _set_position(
        self,
        spot_qty: float, spot_price: float,
        fut_qty: float, fut_price: float,
        funding_rate: float,
        dry_run: bool,
        spot_fee: float = 0.0,
        futures_fee: float = 0.0,
    ):
        cfg = self.cfg
        basis = fut_price - spot_price

        self.position = PositionState(
            symbol=cfg.symbol,
            spot_qty=spot_qty,
            spot_entry_price=spot_price,
            spot_entry_cost=spot_fee if not dry_run else spot_qty * spot_price * cfg.spot_fee_rate,
            futures_qty=fut_qty,
            futures_entry_price=fut_price,
            futures_entry_cost=futures_fee if not dry_run else fut_qty * fut_price * cfg.futures_fee_rate,
            entry_funding_rate=funding_rate,
            entry_basis=basis,
        )
        self.state = EngineState.HOLDING

        tag = "[DRY] " if dry_run else ""
        msg = (
            f"✅ {tag}<b>[{cfg.symbol}] 진입 완료</b>\n"
            f"현물 {spot_qty:.4f} @ {spot_price:.6f}\n"
            f"선물 SHORT {fut_qty:.4f} @ {fut_price:.6f}\n"
            f"펀딩비 {funding_rate:.4%} (연 {annualized_yield(funding_rate):.1%})\n"
            f"basis {basis:.6f} ({basis/spot_price:.4%})\n"
            f"진입비용 ${self.position.total_entry_cost():.3f}"
        )
        log.info(msg)
        self._notify(msg)
        self._log_trade("진입", f"펀딩비 {funding_rate:.4%}")

    # ── 펀딩비 수취 확인 ───────────────────────────────────────────────────

    def _check_funding_collected(self):
        """정산 직후 실제 수취 금액 확인 후 position에 반영."""
        if self.cfg.dry_run:
            # dry_run: 이론값으로 추정
            rate = self._last_funding_rate
            est = self.position.futures_qty * self.position.futures_entry_price * rate
            self.position.collected_funding_usdt += est
            self.position.funding_count += 1
            log.info(f"[{self.cfg.symbol}] [DRY] 펀딩비 수취 추정: ${est:.4f} (누계 ${self.position.collected_funding_usdt:.4f})")
            return

        try:
            since_entry_ms = int(self.position.entry_time * 1000)
            records = self.futures.get_income_history(
                income_type="FUNDING_FEE",
                symbol=self.cfg.futures_symbol,
                limit=10,
                start_time=since_entry_ms,
            )
            total_new = sum(float(r.get("income", 0)) for r in records)
            # 이미 기록된 것 중복 방지: 누계로 덮어쓰지 않고 마지막 값과 비교
            if total_new > self.position.collected_funding_usdt:
                diff = total_new - self.position.collected_funding_usdt
                self.position.collected_funding_usdt = total_new
                self.position.funding_count += 1
                log.info(f"[{self.cfg.symbol}] 펀딩비 수취: ${diff:.4f} (누계 ${total_new:.4f})")
                self._notify(
                    f"💰 <b>[{self.cfg.symbol}] 펀딩비 수취</b>\n"
                    f"이번 회차: ${diff:.4f}\n"
                    f"누계: ${total_new:.4f} ({self.position.funding_count}회)"
                )
        except Exception as e:
            log.warning(f"[{self.cfg.symbol}] 펀딩비 수취 조회 실패: {e}")

    # ── 청산 ───────────────────────────────────────────────────────────────

    def _exit(self, reason: ExitReason, reason_str: str):
        cfg = self.cfg
        self.state = EngineState.EXITING
        pos = self.position

        log.info(f"[{cfg.symbol}] 청산 시작: {reason.value} — {reason_str}")

        if cfg.dry_run:
            try:
                spot_ticker = self.spot.get_book_ticker(cfg.spot_symbol)
                fut_ticker = self.futures.get_book_ticker(cfg.futures_symbol)
                spot_price = float(spot_ticker["bidPrice"])
                fut_price = float(fut_ticker["bidPrice"])
            except Exception:
                spot_price = pos.spot_entry_price
                fut_price = pos.futures_entry_price
            net = pos.net_pnl(spot_price, fut_price)
            self._notify(
                f"📤 [DRY] <b>[{cfg.symbol}] 청산 완료</b>\n"
                f"사유: {reason.value}\n"
                f"Net PnL: ${net:.3f}\n"
                f"수취 펀딩비: ${pos.collected_funding_usdt:.3f} ({pos.funding_count}회)\n"
                f"보유시간: {pos.hold_hours():.1f}h"
            )
            self._log_trade("청산", reason.value)
            self._reset(reason)
            return

        # 1단계: 선물 SHORT 청산 (BUY)
        fut_ok = False
        try:
            self.futures.place_market_order(
                cfg.futures_symbol, "BUY", pos.futures_qty, reduce_only=True
            )
            log.info(f"[{cfg.symbol}] 선물 청산 완료")
            fut_ok = True
        except Exception as e:
            log.error(f"[{cfg.symbol}] 선물 청산 실패: {e}")
            self._notify(f"🚨 [{cfg.symbol}] 선물 청산 실패!: {e}")

        # 2단계: 현물 매도
        try:
            spot_result = self.spot.place_market_order(cfg.spot_symbol, "SELL", pos.spot_qty)
            actual_spot_price = (
                float(spot_result.get("cummulativeQuoteQty", 0)) / pos.spot_qty
                if pos.spot_qty > 0 else 0.0
            )
            log.info(f"[{cfg.symbol}] 현물 매도 완료 @ {actual_spot_price:.6f}")
        except Exception as e:
            log.error(f"[{cfg.symbol}] 현물 매도 실패: {e}")
            self._notify(f"🚨 [{cfg.symbol}] 현물 매도 실패!: {e}")
            actual_spot_price = pos.spot_entry_price

        try:
            fut_ticker = self.futures.get_book_ticker(cfg.futures_symbol)
            fut_exit_price = float(fut_ticker["bidPrice"])
        except Exception:
            fut_exit_price = pos.futures_entry_price

        net = pos.net_pnl(actual_spot_price, fut_exit_price)
        self._notify(
            f"📤 <b>[{cfg.symbol}] 청산 완료</b>\n"
            f"사유: {reason.value}\n"
            f"Net PnL: ${net:.3f}\n"
            f"수취 펀딩비: ${pos.collected_funding_usdt:.3f} ({pos.funding_count}회)\n"
            f"보유시간: {pos.hold_hours():.1f}h"
        )
        self._log_trade("청산", reason.value)
        self._reset(reason)

    def _reset(self, reason: ExitReason):
        self._last_exit_time = time.time()
        self._last_exit_reason = reason
        self.position = PositionState(symbol=self.cfg.symbol)
        self.state = EngineState.IDLE

    # ── 쿨다운 체크 ────────────────────────────────────────────────────────

    def _in_cooldown(self) -> bool:
        if self._last_exit_time == 0:
            return False
        elapsed = time.time() - self._last_exit_time
        if self._last_exit_reason == ExitReason.STOP_LOSS:
            return elapsed < self.cfg.emergency_cooldown_sec
        return elapsed < self.cfg.reentry_cooldown_sec

    # ── 텔레그램 주기 요약 ─────────────────────────────────────────────────

    def _maybe_send_summary(self):
        now = time.time()
        if now - self._last_summary_time < self.cfg.telegram_summary_sec:
            return
        self._last_summary_time = now

        if self.state == EngineState.HOLDING:
            try:
                spot_ticker = self.spot.get_book_ticker(self.cfg.spot_symbol)
                fut_ticker = self.futures.get_book_ticker(self.cfg.futures_symbol)
                sp = float(spot_ticker["bidPrice"])
                fp = float(fut_ticker["bidPrice"])
                net = self.position.net_pnl(sp, fp)
            except Exception:
                net = 0.0
            msg = (
                f"📊 <b>[{self.cfg.symbol}] 운영 현황</b>\n"
                f"{self.position.summary()}\n"
                f"현재 펀딩비: {self._last_funding_rate:.4%}\n"
                f"추정 Net PnL: ${net:.3f}"
            )
        else:
            cooldown_str = ""
            if self._in_cooldown():
                remain = self.cfg.reentry_cooldown_sec - (time.time() - self._last_exit_time)
                cooldown_str = f"\n쿨다운 잔여: {remain:.0f}s"
            msg = (
                f"📊 <b>[{self.cfg.symbol}] 대기 중</b>\n"
                f"펀딩비: {self._last_funding_rate:.4%}{cooldown_str}"
            )
        self._notify(msg)

    # ── 메인 루프 틱 ───────────────────────────────────────────────────────

    def tick(self):
        """외부(main.py)에서 주기적으로 호출."""
        try:
            self._tick_inner()
        except Exception as e:
            log.exception(f"[{self.cfg.symbol}] tick 에러: {e}")

    def _tick_inner(self):
        # 펀딩비 조회
        funding_rate, next_ts = self._fetch_funding_info()
        self._last_funding_rate = funding_rate
        self._next_funding_time_ms = next_ts

        log.debug(
            f"[{self.cfg.symbol}] 상태={self.state.name} | "
            f"펀딩비={funding_rate:.4%} | 다음정산={next_ts}"
        )

        if self.state == EngineState.IDLE:
            self._tick_idle(funding_rate)

        elif self.state == EngineState.HOLDING:
            self._tick_holding(funding_rate)

        self._maybe_send_summary()

    def _tick_idle(self, funding_rate: float):
        if self._in_cooldown():
            return

        # 정산 직후(다음 정산 직전 5분)이면 새 사이클 시작 타이밍
        try:
            spot_ask, fut_ask = self._get_prices()
        except Exception as e:
            log.warning(f"[{self.cfg.symbol}] 가격 조회 실패: {e}")
            return

        ok, reason = should_enter(funding_rate, spot_ask, fut_ask, self.cfg)
        if ok:
            self._enter(funding_rate, spot_ask, fut_ask)
        else:
            log.debug(f"[{self.cfg.symbol}] 진입 보류: {reason}")

    def _tick_holding(self, funding_rate: float):
        # 정산 시각 직후 펀딩비 수취 확인
        now_ms = int(time.time() * 1000)
        if self._next_funding_time_ms > 0 and now_ms >= self._next_funding_time_ms:
            self._check_funding_collected()

        # 청산 조건 체크
        try:
            spot_ticker = self.spot.get_book_ticker(self.cfg.spot_symbol)
            fut_ticker = self.futures.get_book_ticker(self.cfg.futures_symbol)
            spot_price = float(spot_ticker["bidPrice"])
            fut_price = float(fut_ticker["bidPrice"])
        except Exception as e:
            log.warning(f"[{self.cfg.symbol}] 가격 조회 실패: {e}")
            return

        margin_ratio = self._get_margin_ratio()
        exit_reason, reason_str = should_exit(
            self.position, funding_rate, spot_price, fut_price, margin_ratio, self.cfg
        )
        if exit_reason:
            self._exit(exit_reason, reason_str)
