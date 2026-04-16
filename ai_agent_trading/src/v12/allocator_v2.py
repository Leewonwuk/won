"""v1.2 v2 allocator: DT/DC 프리미엄 결정 (BTC 보유 불필요, 스테이블 기반).

거래 구조:
  DT: USDC → BTC@USDC시장 → USDT@USDT시장  (USDC↓ USDT↑ BTC변화없음)
  DC: USDT → BTC@USDT시장 → USDC@USDC시장  (USDT↓ USDC↑ BTC변화없음)

거래량 기준: 총 스테이블(USDT+USDC) × entry_split_fraction
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ActionV2(str, Enum):
    HOLD = "HOLD"
    TRADE_DT = "TRADE_DT"  # DT 프리미엄: USDC→BTC→USDT
    TRADE_DC = "TRADE_DC"  # DC 프리미엄: USDT→BTC→USDC


@dataclass
class DecisionV2:
    action: ActionV2
    premium: float       # 실행가능 스프레드 (bid/ask 기반, 제공 시) 또는 mid 기반
    reason: str
    expected_profit_usd: float = 0.0


def decide_v2(
    mid_usdt: float,
    mid_usdc: float,
    usdt: float,
    usdc: float,
    dt_entry_threshold_rate: float,
    dc_entry_threshold_rate: float,
    fee_rate: float,
    slippage_rate: float,
    entry_split_fraction: float = 0.25,
    exec_dc_premium: float | None = None,
    exec_dt_premium: float | None = None,
) -> DecisionV2:
    """매 봉 거래 결정. BTC 잔고 불필요.

    exec_dc_premium: (bid_USDC - ask_USDT) / ask_USDT — DC 방향 실행가능 스프레드
    exec_dt_premium: (bid_USDT - ask_USDC) / ask_USDC — DT 방향 실행가능 스프레드
    제공 시 mid 기반 대신 bid/ask 기반으로 진입 여부를 결정한다.
    """
    if mid_usdc <= 0 or mid_usdt <= 0:
        return DecisionV2(ActionV2.HOLD, 0.0, "zero_price")

    mid_premium = (mid_usdt - mid_usdc) / mid_usdc
    total_fee_rate = 2.0 * (fee_rate + slippage_rate)
    total_stable = usdt + usdc

    # ── DT 프리미엄: USDT 레그 비쌈 ──
    # 실행가능 스프레드 우선 사용, 없으면 mid 기반으로 fallback
    dt_prem = exec_dt_premium if exec_dt_premium is not None else (mid_premium if mid_premium > 0 else 0.0)
    if dt_prem > dt_entry_threshold_rate:
        if total_stable < 0.01:
            return DecisionV2(ActionV2.HOLD, dt_prem, "dt_no_stable")
        notional = total_stable * entry_split_fraction
        expected = notional * (dt_prem - total_fee_rate)
        if expected > 0:
            return DecisionV2(ActionV2.TRADE_DT, dt_prem, "dt_premium_profitable", expected)
        return DecisionV2(ActionV2.HOLD, dt_prem, "dt_premium_fee_exceeds_profit")

    # ── DC 프리미엄: USDC 레그 비쌈 ──
    dc_prem = exec_dc_premium if exec_dc_premium is not None else (-mid_premium if mid_premium < 0 else 0.0)
    if dc_prem > dc_entry_threshold_rate:
        if total_stable < 0.01:
            return DecisionV2(ActionV2.HOLD, dc_prem, "dc_no_stable")
        notional = total_stable * entry_split_fraction
        expected = notional * (dc_prem - total_fee_rate)
        if expected > 0:
            return DecisionV2(ActionV2.TRADE_DC, dc_prem, "dc_premium_profitable", expected)
        return DecisionV2(ActionV2.HOLD, dc_prem, "dc_premium_fee_exceeds_profit")

    return DecisionV2(ActionV2.HOLD, mid_premium, "below_threshold")
