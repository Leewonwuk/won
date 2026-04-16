"""v2.0 포지션 상태 관리."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto


class EngineState(Enum):
    IDLE = auto()       # 대기 중 (포지션 없음)
    ENTERING = auto()   # 진입 중 (현물/선물 주문 실행 중)
    HOLDING = auto()    # 보유 중 (펀딩비 수취 대기)
    EXITING = auto()    # 청산 중


class ExitReason(Enum):
    FUNDING_LOW = "펀딩비 낮음"          # exit_funding_rate 미만
    FUNDING_NEGATIVE = "펀딩비 음수"      # 음수 반전
    STOP_LOSS = "손절"                    # net PnL stop_loss 도달
    MAX_HOLD = "최대 보유 시간 초과"       # max_hold_hours 초과
    DANGER_MARGIN = "증거금 위험"         # margin_ratio < danger_margin_ratio
    MANUAL = "수동 청산"


@dataclass
class PositionState:
    """현재 보유 중인 현물+선물 포지션 정보."""
    symbol: str = ""

    # 현물
    spot_qty: float = 0.0           # 보유 코인 수량
    spot_entry_price: float = 0.0   # 현물 진입 평균가
    spot_entry_cost: float = 0.0    # 현물 진입 비용 (USDT, 수수료 포함)

    # 선물
    futures_qty: float = 0.0        # 공매도 수량 (양수 저장, 방향은 SHORT)
    futures_entry_price: float = 0.0
    futures_entry_cost: float = 0.0  # 선물 진입 수수료 (USDT)

    # 진입 시점 정보
    entry_time: float = field(default_factory=time.time)
    entry_funding_rate: float = 0.0   # 진입 시점 펀딩비
    entry_basis: float = 0.0          # 진입 시점 basis (선물가 - 현물가)

    # 누적 수취 펀딩비
    collected_funding_usdt: float = 0.0
    funding_count: int = 0            # 수취 횟수

    def total_entry_cost(self) -> float:
        """총 진입 비용 (현물 수수료 + 선물 수수료)."""
        return self.spot_entry_cost + self.futures_entry_cost

    def hold_hours(self) -> float:
        return (time.time() - self.entry_time) / 3600.0

    def net_pnl(
        self,
        spot_current_price: float,
        futures_current_price: float,
    ) -> float:
        """현재 시점 net PnL 추정.

        현물 평가손익 + 선물 미실현손익 + 수취 펀딩비 - 진입비용
        """
        spot_pnl = (spot_current_price - self.spot_entry_price) * self.spot_qty
        # SHORT 포지션: 가격 하락 시 이익
        futures_pnl = (self.futures_entry_price - futures_current_price) * self.futures_qty
        return spot_pnl + futures_pnl + self.collected_funding_usdt - self.total_entry_cost()

    def summary(self) -> str:
        return (
            f"{self.symbol} | "
            f"현물 {self.spot_qty:.4f}@{self.spot_entry_price:.6f} | "
            f"선물 SHORT {self.futures_qty:.4f}@{self.futures_entry_price:.6f} | "
            f"수취 펀딩비 ${self.collected_funding_usdt:.4f}({self.funding_count}회) | "
            f"보유 {self.hold_hours():.1f}h"
        )
