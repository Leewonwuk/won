"""v1.2 v2 config: 스테이블코인 전용 (USDT + USDC), BTC 보유 불필요."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class V12ConfigV2:
    symbol: str = "BTC"
    binance_symbol_usdt: str = "BTCUSDT"
    binance_symbol_usdc: str = "BTCUSDC"

    # 초기 자본 (스테이블코인만)
    initial_usdt: float = 5000.0
    initial_usdc: float = 5000.0

    # 진입 임계값
    # DT: BTCUSDT > BTCUSDC → USDC→BTC→USDT (USDT 수취)
    # DC: BTCUSDC > BTCUSDT → USDT→BTC→USDC (USDC 수취)
    dt_entry_threshold_rate: float = 0.0003
    dc_entry_threshold_rate: float = 0.0003

    entry_split_fraction: float = 0.25  # 매 시그널 당 총 스테이블의 몇 % 사용

    # 수수료 (레그 당) — Standard pair (USDT pair) 기준
    fee_rate: float = 0.0004
    fee_maker_rate: float = 0.0002
    # USDC pair 별도 수수료 (Binance USDC Taker promo 적용)
    # 미설정 시 fee_rate / fee_maker_rate 사용 (하위 호환)
    fee_usdc_pair_taker: Optional[float] = None
    fee_usdc_pair_maker: Optional[float] = None
    use_maker_fees: bool = False
    slippage_rate: float = 0.0
    # 지정가 체결률 (0.0~1.0). 1.0=항상 체결, 0.8=80%만 체결
    # 시장가(use_maker_fees=False)는 항상 1.0으로 간주
    fill_rate: float = 1.0

    # 타임아웃 & 방어 로직
    order_timeout_sec: int = 30          # 지정가 주문 최대 대기 시간 (초)
    emergency_taker_fee_rate: float = 0.0004   # 비상 시장가 청산 수수료
    emergency_slippage_rate: float = 0.0002    # 비상 시장가 슬리피지

    # Leg B abort 임계값: 이 값 미만일 때 시장가 긴급 청산
    # None = 기본값(fee_stack = 2 × eff_fee)
    # 0.0 = 프리미엄이 음수일 때만 abort
    # -0.0003 = 스프레드가 -0.03% 이하로 역전될 때만 abort (Leg B maker가 더 저렴한 구간 최대 활용)
    leg_b_abort_threshold_rate: Optional[float] = None

    # Leg B 대기 중 가격 방어 (5초마다 체크)
    # leg_b_stop_loss_rate: Leg A 진입가 대비 이 비율 이상 하락 시 즉시 시장가 청산
    #   예: 0.003 → 진입가에서 0.3% 하락 시 청산. None = 비활성
    leg_b_stop_loss_rate: Optional[float] = None
    # leg_b_reprice_on_drop: True이면 현재가가 Leg B 리밋보다 낮게 내려갔을 때
    #   수익 가능 구간이면 리밋을 현재가로 낮춰 즉시 체결 시도
    leg_b_reprice_on_drop: bool = True

    # Speculative Leg B: Leg A IOC 제출 직후 Leg B GTC도 즉시 제출
    # Leg A miss 시 Leg B 즉시 취소 → abort 시나리오 제거
    use_speculative_leg_b: bool = False

    # IOC Leg A 주문 가격 버퍼 (ask 위에 얼마나 더 올려 주문하는가)
    # WS → 거래소 도달 5~15ms 사이 ask 이동분을 커버. 기본 0 (BTC 등 유동성 높은 코인).
    # 저가/저유동성 코인(XRP, DOGE 등)은 0.0003~0.0005 권장.
    ioc_price_buffer_rate: float = 0.0

    # IOC miss 후 재시도 쿨다운 (초).
    # miss 감지 직후 이 시간 동안 새 시그널을 무시. 기본 5s.
    # BNBUSDC 등 유동성 낮은 페어에서 연속 miss 방지 목적으로 30s 이상 권장.
    ioc_miss_cooldown_sec: float = 5.0

    price_mode: str = "close"

    # Leg B 체결 지연 (봉 단위). 0=기존 동작, 1=1봉 후 체결.
    # 1초봉 데이터에서 sequential 지연 시뮬레이션: leg_b_lag_bars=1
    leg_b_lag_bars: int = 0

    # 잔고 리밸런싱 (USDT↔USDC Convert)
    # 한쪽 비율이 rebalance_skew_threshold 초과 시 50:50으로 Convert
    rebalance_skew_threshold: float = 0.80   # 0.80 = 한쪽이 80% 이상이면 리밸런싱
    rebalance_min_interval_sec: int = 0      # 최소 리밸런싱 간격 (초) — 0=쿨다운 없음, 80% 임계값이 과잉 방어

    # BNB 수수료 최소 보유량 (0.0 = 제한 없음)
    # 이 값 미만이면 진입 스킵 → BNB를 수수료용으로 보호
    min_bnb_fee_reserve: float = 0.0


def load_v12_config_v2(path: str) -> V12ConfigV2:
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return V12ConfigV2(
        symbol=str(data.get("symbol", "BTC")),
        binance_symbol_usdt=str(data.get("binance_symbol_usdt", "BTCUSDT")),
        binance_symbol_usdc=str(data.get("binance_symbol_usdc", "BTCUSDC")),
        initial_usdt=float(data.get("initial_usdt", 5000.0)),
        initial_usdc=float(data.get("initial_usdc", 5000.0)),
        dt_entry_threshold_rate=float(data.get("dt_entry_threshold_rate", 0.0003)),
        dc_entry_threshold_rate=float(data.get("dc_entry_threshold_rate", 0.0003)),
        entry_split_fraction=float(data.get("entry_split_fraction", 0.25)),
        fee_rate=float(data.get("fee_rate", 0.0004)),
        fee_maker_rate=float(data.get("fee_maker_rate", 0.0002)),
        fee_usdc_pair_taker=(
            float(data["fee_usdc_pair_taker"])
            if "fee_usdc_pair_taker" in data
            else None
        ),
        fee_usdc_pair_maker=(
            float(data["fee_usdc_pair_maker"])
            if "fee_usdc_pair_maker" in data
            else None
        ),
        use_maker_fees=bool(data.get("use_maker_fees", False)),
        slippage_rate=float(data.get("slippage_rate", 0.0)),
        fill_rate=float(data.get("fill_rate", 1.0)),
        order_timeout_sec=int(data.get("order_timeout_sec", 30)),
        emergency_taker_fee_rate=float(data.get("emergency_taker_fee_rate", 0.0004)),
        emergency_slippage_rate=float(data.get("emergency_slippage_rate", 0.0002)),
        ioc_price_buffer_rate=float(data.get("ioc_price_buffer_rate", 0.0)),
        ioc_miss_cooldown_sec=float(data.get("ioc_miss_cooldown_sec", 5.0)),
        price_mode=str(data.get("price_mode", "close")),
        rebalance_skew_threshold=float(data.get("rebalance_skew_threshold", 0.80)),
        rebalance_min_interval_sec=int(data.get("rebalance_min_interval_sec", 3600)),
        min_bnb_fee_reserve=float(data.get("min_bnb_fee_reserve", 0.0)),
        leg_b_abort_threshold_rate=(
            float(data["leg_b_abort_threshold_rate"])
            if "leg_b_abort_threshold_rate" in data
            else None
        ),
        leg_b_stop_loss_rate=(
            float(data["leg_b_stop_loss_rate"])
            if "leg_b_stop_loss_rate" in data
            else None
        ),
        leg_b_reprice_on_drop=bool(data.get("leg_b_reprice_on_drop", True)),
        use_speculative_leg_b=bool(data.get("use_speculative_leg_b", False)),
        leg_b_lag_bars=int(data.get("leg_b_lag_bars", 0)),
    )
