"""v2.0 펀딩비 차익거래 전략 판단 로직 (순수 함수).

사이드 이펙트 없음 — 테스트 가능하도록 분리.
"""
from __future__ import annotations

from .config_v20 import FundingArbConfig
from .position_state import ExitReason, PositionState


def should_enter(
    funding_rate: float,
    spot_price: float,
    futures_price: float,
    cfg: FundingArbConfig,
) -> tuple[bool, str]:
    """진입 조건 판단.

    Returns:
        (진입 여부, 사유 문자열)
    """
    # 펀딩비 조건
    if funding_rate < cfg.entry_funding_rate:
        return False, f"펀딩비 {funding_rate:.4%} < 임계값 {cfg.entry_funding_rate:.4%}"

    # basis 조건 (선물 프리미엄이 너무 크면 불리)
    if spot_price > 0:
        basis_rate = (futures_price - spot_price) / spot_price
        if basis_rate > cfg.max_basis_rate:
            return False, f"basis {basis_rate:.4%} > 최대허용 {cfg.max_basis_rate:.4%}"

    # 손익분기 도달 예상 (정보성 계산, 거부 조건 아님)
    round_trip_cost = (cfg.spot_fee_rate + cfg.futures_fee_rate) * 2
    breakeven_periods = round_trip_cost / funding_rate if funding_rate > 0 else float("inf")
    breakeven_hours = breakeven_periods * 8

    return True, (
        f"진입 조건 충족 | 펀딩비 {funding_rate:.4%}/8h (연 {funding_rate * 3 * 365:.1%}) | "
        f"수수료 회수 예상 {breakeven_hours:.1f}h"
    )


def should_exit(
    position: PositionState,
    funding_rate: float,
    spot_price: float,
    futures_price: float,
    margin_ratio: float | None,
    cfg: FundingArbConfig,
) -> tuple[ExitReason | None, str]:
    """청산 조건 판단.

    Returns:
        (청산 사유 or None, 설명 문자열)
    """
    # 1. 펀딩비 음수
    if funding_rate < 0:
        return ExitReason.FUNDING_NEGATIVE, f"펀딩비 음수 ({funding_rate:.4%}) → 비용 발생"

    # 2. 펀딩비 낮음
    if funding_rate < cfg.exit_funding_rate:
        return ExitReason.FUNDING_LOW, f"펀딩비 {funding_rate:.4%} < 청산임계값 {cfg.exit_funding_rate:.4%}"

    # 3. Net PnL stop_loss
    net = position.net_pnl(spot_price, futures_price)
    if net < cfg.stop_loss_usdt:
        return ExitReason.STOP_LOSS, f"Net PnL ${net:.2f} < stop_loss ${cfg.stop_loss_usdt:.2f}"

    # 4. 최대 보유 시간
    if position.hold_hours() > cfg.max_hold_hours:
        return ExitReason.MAX_HOLD, f"보유 {position.hold_hours():.1f}h > 최대 {cfg.max_hold_hours}h"

    # 5. 증거금 위험
    if margin_ratio is not None and margin_ratio < cfg.danger_margin_ratio:
        return ExitReason.DANGER_MARGIN, f"증거금 비율 {margin_ratio:.1%} < 위험선 {cfg.danger_margin_ratio:.1%}"

    return None, "보유 유지"


def calc_position_size(
    capital_usdt: float,
    spot_ask: float,
    cfg: FundingArbConfig,
) -> float:
    """진입 코인 수량 계산.

    자본의 position_fraction만큼 현물 매수.
    선물은 동일 수량 공매도 (별도 증거금은 선물 지갑에서 사용).
    """
    usdt_to_use = capital_usdt * cfg.position_fraction
    if spot_ask <= 0:
        return 0.0
    return usdt_to_use / spot_ask


def annualized_yield(funding_rate_8h: float) -> float:
    """8시간 펀딩비 → 연환산 수익률."""
    return funding_rate_8h * 3 * 365
