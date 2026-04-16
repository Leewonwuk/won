"""멀티코인 통합 운영용 글로벌 트레이드 락.

하나의 코인이 거래 중(LEG_A_PENDING ~ _reset())일 때
다른 코인의 신규 진입을 차단한다.

설계:
- threading.Lock  : 실제 진입 직렬화
- threading.Lock  : _holder / _acquired_at 원자적 갱신 보호 (meta)
- try_acquire()   : 논블로킹. 성공 → True
- release()       : 홀더 코인만 가능
- expire_sec 초 초과 시 자동 만료 (엔진 크래시 방어)
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger(__name__)


class GlobalTradeLock:
    """스레드 안전 글로벌 진입 락."""

    def __init__(self, expire_sec: float = 150.0) -> None:
        self._lock = threading.Lock()
        self._meta = threading.Lock()   # _holder / _acquired_at 보호
        self._holder: str = ""
        self._acquired_at: float = 0.0
        self.expire_sec = expire_sec
        # 리밸런싱 공유 쿨다운: 어느 엔진이든 시도 후 전체 엔진에 적용
        self._rebalance_cooldown_until: float = 0.0
        # 누적 리밸런싱 횟수 + 마지막 거래 정보 (텔레그램 로그용)
        self._rebalance_count: int = 0
        self._last_trade_symbol: str = ""
        self._last_trade_dir: str = ""

    # ── 공개 API ─────────────────────────────────────────────────────────

    def try_acquire(self, coin: str) -> bool:
        """논블로킹 락 획득. 성공 → True, 차단 → False."""
        with self._meta:
            if self._lock.locked():
                elapsed = time.time() - self._acquired_at
                if elapsed > self.expire_sec:
                    log.warning(
                        f"[GlobalLock] 만료 강제 해제 — 홀더={self._holder} "
                        f"경과={elapsed:.1f}s"
                    )
                    self._force_release()
                else:
                    log.debug(
                        f"[GlobalLock] {coin} 차단 — {self._holder} 홀딩 중 "
                        f"({elapsed:.1f}s / {self.expire_sec}s)"
                    )
                    return False

            acquired = self._lock.acquire(blocking=False)
            if acquired:
                self._holder = coin
                self._acquired_at = time.time()
                log.info(f"[GlobalLock] {coin} 락 획득")
            return acquired

    def release(self, coin: str) -> None:
        """홀더 코인만 락 해제 가능. 비홀더 호출은 조용히 무시."""
        with self._meta:
            if self._holder != coin:
                log.debug(
                    f"[GlobalLock] release 무시 — caller={coin} holder={self._holder}"
                )
                return
            self._force_release()
            log.info(f"[GlobalLock] {coin} 락 해제")

    def set_rebalance_cooldown(self, cooldown_until: float) -> None:
        """리밸런싱 공유 쿨다운 설정. 전체 엔진에 적용."""
        with self._meta:
            self._rebalance_cooldown_until = cooldown_until

    def is_rebalance_cooldown(self) -> bool:
        """리밸런싱 쿨다운 중이면 True (모든 엔진 공유)."""
        with self._meta:
            return time.time() < self._rebalance_cooldown_until

    def set_last_trade(self, symbol: str, direction: str) -> None:
        """거래 완료 시 마지막 거래 코인 + 방향 기록 (DC/DT)."""
        with self._meta:
            self._last_trade_symbol = symbol
            self._last_trade_dir = direction

    def increment_rebalance_count(self) -> int:
        """리밸런싱 성공 시 누적 횟수 증가. 새 횟수 반환."""
        with self._meta:
            self._rebalance_count += 1
            return self._rebalance_count

    @property
    def rebalance_count(self) -> int:
        with self._meta:
            return self._rebalance_count

    @property
    def last_trade_symbol(self) -> str:
        with self._meta:
            return self._last_trade_symbol

    @property
    def last_trade_dir(self) -> str:
        with self._meta:
            return self._last_trade_dir

    @property
    def holder(self) -> str:
        return self._holder

    @property
    def is_locked(self) -> bool:
        return self._lock.locked()

    # ── 내부 ─────────────────────────────────────────────────────────────

    def _force_release(self) -> None:
        """_meta 보유 상태에서만 호출."""
        try:
            self._lock.release()
        except RuntimeError:
            pass
        self._holder = ""
