"""USDC pair Taker promo (BNB 25% + USDC 0.005% promo) 반영 검증.

Binance Spot VIP0 fee 모델:
  - USDT pair Taker:  0.10% × 0.75 (BNB) = 0.075%
  - USDT pair Maker:  0.10% × 0.75 (BNB) = 0.075%
  - USDC pair Taker:  0.095% × 0.75 (BNB) = 0.07125%   ← USDC promo
  - USDC pair Maker:  0.10% × 0.75 (BNB) = 0.075%      ← Maker promo 없음

방향별 fee_stack:
  - DT (LegA=USDC pair taker, LegB=USDT pair maker): 0.07125% + 0.075% = 0.14625%
  - DC (LegA=USDT pair taker, LegB=USDC pair maker): 0.075%   + 0.075% = 0.15000%
"""
from __future__ import annotations

import math

import pytest

from src.allocator_v2 import ActionV2, decide_v2
from src.config_v2 import V12ConfigV2


def _approx(a: float, b: float, tol: float = 1e-9) -> bool:
    return math.isclose(a, b, abs_tol=tol)


def test_directional_fee_stack_usdt_pair_only():
    """fee_usdc_pair_* 미설정 → legacy 동작 (양방향 fee_rate*2 동일)."""
    dt_fs = None
    dc_fs = None
    decision = decide_v2(
        mid_usdt=100.0, mid_usdc=99.85,
        usdt=1000.0, usdc=1000.0,
        dt_entry_threshold_rate=0.0017,
        dc_entry_threshold_rate=0.0017,
        fee_rate=0.00075, slippage_rate=0.0,
        entry_split_fraction=0.25,
        dt_fee_stack=dt_fs, dc_fee_stack=dc_fs,
    )
    # mid_premium = (100 - 99.85)/99.85 ≈ 0.001503 < 0.0017 → HOLD or below_threshold
    # legacy fee_stack = 2 × 0.00075 = 0.0015 → above-threshold만 비교
    assert decision.action in (ActionV2.HOLD,)


def test_dt_promo_lower_threshold_passes():
    """DT 방향 fee_stack 0.14625% — 0.0017 임계 통과 시 expected > 0."""
    # mid_premium = 0.18% > dt_threshold 0.17% → DT 진입 검토
    decision = decide_v2(
        mid_usdt=100.18, mid_usdc=100.0,
        usdt=1000.0, usdc=1000.0,
        dt_entry_threshold_rate=0.0017,
        dc_entry_threshold_rate=0.0017,
        fee_rate=0.00075, slippage_rate=0.0,
        entry_split_fraction=0.25,
        dt_fee_stack=0.0014625,  # USDC promo 적용
        dc_fee_stack=0.00150,
    )
    assert decision.action == ActionV2.TRADE_DT
    assert decision.expected_profit_usd > 0.0


def test_dc_no_promo():
    """DC 방향 fee_stack 0.150% — promo 없음."""
    # mid_usdc > mid_usdt → DC 방향 (USDC 비쌈)
    decision = decide_v2(
        mid_usdt=100.0, mid_usdc=100.18,
        usdt=1000.0, usdc=1000.0,
        dt_entry_threshold_rate=0.0017,
        dc_entry_threshold_rate=0.0017,
        fee_rate=0.00075, slippage_rate=0.0,
        entry_split_fraction=0.25,
        dt_fee_stack=0.0014625,
        dc_fee_stack=0.00150,
    )
    assert decision.action == ActionV2.TRADE_DC


def test_config_loads_usdc_pair_fee_fields(tmp_path):
    """yaml에 fee_usdc_pair_* 있으면 V12ConfigV2가 읽는다."""
    from src.config_v2 import load_v12_config_v2
    p = tmp_path / "test.yaml"
    p.write_text(
        "symbol: TEST\n"
        "binance_symbol_usdt: TESTUSDT\n"
        "binance_symbol_usdc: TESTUSDC\n"
        "fee_rate: 0.00075\n"
        "fee_maker_rate: 0.00075\n"
        "fee_usdc_pair_taker: 0.0007125\n"
        "fee_usdc_pair_maker: 0.00075\n"
        "use_maker_fees: true\n",
        encoding="utf-8",
    )
    cfg = load_v12_config_v2(str(p))
    assert _approx(cfg.fee_usdc_pair_taker, 0.0007125)
    assert _approx(cfg.fee_usdc_pair_maker, 0.00075)


def test_config_default_usdc_pair_fields_none():
    """yaml에 미지정 시 None (legacy fallback)."""
    cfg = V12ConfigV2()
    assert cfg.fee_usdc_pair_taker is None
    assert cfg.fee_usdc_pair_maker is None


def test_directional_fee_stack_calculation():
    """페어별 fee 가산 산식 검증."""
    usdt_taker = 0.00075
    usdt_maker = 0.00075
    usdc_taker = 0.0007125
    usdc_maker = 0.00075
    slip = 0.0

    dt_stack = usdc_taker + usdt_maker + 2 * slip
    dc_stack = usdt_taker + usdc_maker + 2 * slip

    assert _approx(dt_stack, 0.0014625)
    assert _approx(dc_stack, 0.00150)
    # DT 방향이 0.00375%p 더 싸다
    assert _approx(dc_stack - dt_stack, 0.0000375)
