"""v1.2 v2 포트폴리오: 스테이블코인 전용 (USDT + USDC), BTC 보유 없음.

거래 메커니즘:
  DT 프리미엄 (USDT > USDC):
    1. USDC로 BTC 매수 (BTCUSDC 시장)
    2. 그 BTC를 USDT로 매도 (BTCUSDT 시장)
    → USDC↓  USDT↑  BTC 잔고 변화 없음

  DC 프리미엄 (USDC > USDT):
    1. USDT로 BTC 매수 (BTCUSDT 시장)
    2. 그 BTC를 USDC로 매도 (BTCUSDC 시장)
    → USDT↓  USDC↑  BTC 잔고 변화 없음

USDT↔USDC 선스왑: 바이낸스 내 무료·즉시.
거래량: (usdt + usdc) × entry_split_fraction
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TradeEventV2:
    ts: str
    symbol: str
    action: str         # TRADE_DT | TRADE_DC
    premium: float
    mid_usdt: float
    mid_usdc: float
    notional_usd: float  # 거래에 투입한 스테이블 규모 (USDC or USDT)
    btc_qty: float       # 경유한 BTC 수량
    pnl_usd: float       # 수취 스테이블 - 투입 스테이블
    fee_usd: float
    detail: str = ""


@dataclass
class BalanceV2:
    usdt: float = 0.0
    usdc: float = 0.0
    total_trades: int = 0
    realized_fee_usd: float = 0.0

    def total_value_usd(self, _mid_usdt: float = 0.0, _mid_usdc: float = 0.0) -> float:
        """스테이블코인만 보유 → 단순 합산."""
        return self.usdt + self.usdc

    # ── 무료 스테이블 선스왑 ────────────────────────────────────

    def _ensure_usdc(self, needed: float) -> None:
        shortfall = max(needed - self.usdc, 0.0)
        swap = min(self.usdt, shortfall)
        self.usdt -= swap
        self.usdc += swap

    def _ensure_usdt(self, needed: float) -> None:
        shortfall = max(needed - self.usdt, 0.0)
        swap = min(self.usdc, shortfall)
        self.usdc -= swap
        self.usdt += swap

    # ── 거래 실행 ────────────────────────────────────────────────

    def execute_dt_trade(
        self,
        symbol: str,
        mid_usdt: float,
        mid_usdc: float,
        fee_rate: float,
        slippage_rate: float,
        fraction: float,
        ts: str = "",
        leg_a_fee_rate: float | None = None,
        leg_b_fee_rate: float | None = None,
    ) -> TradeEventV2:
        """DT 프리미엄: USDC→BTC(USDC시장)→USDT(USDT시장).

        leg_a_fee_rate / leg_b_fee_rate: 페어별 fee 미지정 시 fee_rate fallback.
        DT의 LegA는 USDC pair (Taker promo 0.07125% 적용 가능), LegB는 USDT pair.
        notional = (usdt + usdc) × fraction (USDC로 충당)
        """
        if not ts:
            ts = datetime.now(tz=timezone.utc).isoformat()

        premium = (mid_usdt - mid_usdc) / mid_usdc if mid_usdc > 0 else 0.0
        fraction = max(0.0, min(float(fraction), 1.0))
        leg_a = leg_a_fee_rate if leg_a_fee_rate is not None else fee_rate
        leg_b = leg_b_fee_rate if leg_b_fee_rate is not None else fee_rate

        notional = (self.usdt + self.usdc) * fraction
        self._ensure_usdc(notional)

        # LegA: notional USDC → BTC (BTCUSDC 시장)
        eff_buy = mid_usdc * (1.0 + leg_a + slippage_rate)
        btc_qty = notional / eff_buy
        fee_buy = btc_qty * mid_usdc * (leg_a + slippage_rate)

        # LegB: BTC → USDT (BTCUSDT 시장)
        eff_sell = mid_usdt * (1.0 - leg_b - slippage_rate)
        usdt_received = btc_qty * eff_sell
        fee_sell = btc_qty * mid_usdt * (leg_b + slippage_rate)

        self.usdc = max(self.usdc - notional, 0.0)
        self.usdt += usdt_received

        total_fee = fee_buy + fee_sell
        pnl = usdt_received - notional
        self.realized_fee_usd += total_fee
        self.total_trades += 1

        return TradeEventV2(
            ts=ts,
            symbol=symbol,
            action="TRADE_DT",
            premium=premium,
            mid_usdt=mid_usdt,
            mid_usdc=mid_usdc,
            notional_usd=notional,
            btc_qty=btc_qty,
            pnl_usd=pnl,
            fee_usd=total_fee,
            detail=(
                f"fraction={fraction:.2f} notional={notional:.2f}USDC "
                f"btc={btc_qty:.8f} → usdt={usdt_received:.4f}"
            ),
        )

    def execute_dc_trade(
        self,
        symbol: str,
        mid_usdt: float,
        mid_usdc: float,
        fee_rate: float,
        slippage_rate: float,
        fraction: float,
        ts: str = "",
        leg_a_fee_rate: float | None = None,
        leg_b_fee_rate: float | None = None,
    ) -> TradeEventV2:
        """DC 프리미엄: USDT→BTC(USDT시장)→USDC(USDC시장).

        DC의 LegA는 USDT pair, LegB는 USDC pair (Maker는 promo 없음).
        notional = (usdt + usdc) × fraction (USDT로 충당)
        """
        if not ts:
            ts = datetime.now(tz=timezone.utc).isoformat()

        premium = (mid_usdt - mid_usdc) / mid_usdc if mid_usdc > 0 else 0.0
        fraction = max(0.0, min(float(fraction), 1.0))
        leg_a = leg_a_fee_rate if leg_a_fee_rate is not None else fee_rate
        leg_b = leg_b_fee_rate if leg_b_fee_rate is not None else fee_rate

        notional = (self.usdt + self.usdc) * fraction
        self._ensure_usdt(notional)

        # LegA: USDT → BTC (BTCUSDT 시장)
        eff_buy = mid_usdt * (1.0 + leg_a + slippage_rate)
        btc_qty = notional / eff_buy
        fee_buy = btc_qty * mid_usdt * (leg_a + slippage_rate)

        # LegB: BTC → USDC (BTCUSDC 시장)
        eff_sell = mid_usdc * (1.0 - leg_b - slippage_rate)
        usdc_received = btc_qty * eff_sell
        fee_sell = btc_qty * mid_usdc * (leg_b + slippage_rate)

        self.usdt = max(self.usdt - notional, 0.0)
        self.usdc += usdc_received

        total_fee = fee_buy + fee_sell
        pnl = usdc_received - notional
        self.realized_fee_usd += total_fee
        self.total_trades += 1

        return TradeEventV2(
            ts=ts,
            symbol=symbol,
            action="TRADE_DC",
            premium=premium,
            mid_usdt=mid_usdt,
            mid_usdc=mid_usdc,
            notional_usd=notional,
            btc_qty=btc_qty,
            pnl_usd=pnl,
            fee_usd=total_fee,
            detail=(
                f"fraction={fraction:.2f} notional={notional:.2f}USDT "
                f"btc={btc_qty:.8f} → usdc={usdc_received:.4f}"
            ),
        )

    # ── 비상 청산 (타임아웃 시 한 레그만 체결된 경우) ──────────────

    def execute_dt_emergency(
        self,
        symbol: str,
        mid_uc_fill: float,   # 시그널 봉 USDC 가격 (Leg A 체결 기준)
        mid_ut_em: float,     # 역전 봉 USDT 가격 (비상 청산 기준)
        limit_fee_rate: float,
        emergency_fee_rate: float,
        emergency_slip_rate: float,
        fraction: float,
        ts: str = "",
    ) -> TradeEventV2:
        """DT 비상 청산: Leg A(USDC→BTC) 지정가 체결 후 Leg B 미체결.

        스프레드가 역전되어 타임아웃 전에 Leg B를 시장가로 청산.
        Leg A: USDC notional → BTC (지정가, mid_uc_fill 기준)
        Emergency: BTC → USDT (시장가, mid_ut_em 기준, taker fee + slip)
        """
        if not ts:
            ts = datetime.now(tz=timezone.utc).isoformat()

        premium_fill = (mid_ut_em - mid_uc_fill) / mid_uc_fill if mid_uc_fill > 0 else 0.0
        fraction = max(0.0, min(float(fraction), 1.0))

        notional = (self.usdt + self.usdc) * fraction
        self._ensure_usdc(notional)

        # Leg A: USDC → BTC (지정가 체결)
        eff_buy_uc = mid_uc_fill * (1.0 + limit_fee_rate)
        btc_qty = notional / eff_buy_uc
        fee_leg_a = btc_qty * mid_uc_fill * limit_fee_rate

        # Emergency: BTC → USDT (시장가, 역전 봉 가격)
        eff_sell_ut = mid_ut_em * (1.0 - emergency_fee_rate - emergency_slip_rate)
        usdt_received = btc_qty * eff_sell_ut
        fee_em = btc_qty * mid_ut_em * (emergency_fee_rate + emergency_slip_rate)

        self.usdc = max(self.usdc - notional, 0.0)
        self.usdt += usdt_received

        total_fee = fee_leg_a + fee_em
        pnl = usdt_received - notional
        self.realized_fee_usd += total_fee
        self.total_trades += 1

        return TradeEventV2(
            ts=ts,
            symbol=symbol,
            action="TRADE_DT_EMERGENCY",
            premium=premium_fill,
            mid_usdt=mid_ut_em,
            mid_usdc=mid_uc_fill,
            notional_usd=notional,
            btc_qty=btc_qty,
            pnl_usd=pnl,
            fee_usd=total_fee,
            detail=(
                f"LegA@{mid_uc_fill:.2f}USDC(limit) "
                f"EmClose@{mid_ut_em:.2f}USDT(market) pnl={pnl:.4f}"
            ),
        )

    def execute_dc_emergency(
        self,
        symbol: str,
        mid_ut_fill: float,   # 시그널 봉 USDT 가격 (Leg A 체결 기준)
        mid_uc_em: float,     # 역전 봉 USDC 가격 (비상 청산 기준)
        limit_fee_rate: float,
        emergency_fee_rate: float,
        emergency_slip_rate: float,
        fraction: float,
        ts: str = "",
    ) -> TradeEventV2:
        """DC 비상 청산: Leg A(USDT→BTC) 지정가 체결 후 Leg B 미체결.

        Leg A: USDT notional → BTC (지정가, mid_ut_fill 기준)
        Emergency: BTC → USDC (시장가, mid_uc_em 기준, taker fee + slip)
        """
        if not ts:
            ts = datetime.now(tz=timezone.utc).isoformat()

        premium_fill = (mid_ut_fill - mid_uc_em) / mid_uc_em if mid_uc_em > 0 else 0.0
        fraction = max(0.0, min(float(fraction), 1.0))

        notional = (self.usdt + self.usdc) * fraction
        self._ensure_usdt(notional)

        # Leg A: USDT → BTC (지정가 체결)
        eff_buy_ut = mid_ut_fill * (1.0 + limit_fee_rate)
        btc_qty = notional / eff_buy_ut
        fee_leg_a = btc_qty * mid_ut_fill * limit_fee_rate

        # Emergency: BTC → USDC (시장가, 역전 봉 가격)
        eff_sell_uc = mid_uc_em * (1.0 - emergency_fee_rate - emergency_slip_rate)
        usdc_received = btc_qty * eff_sell_uc
        fee_em = btc_qty * mid_uc_em * (emergency_fee_rate + emergency_slip_rate)

        self.usdt = max(self.usdt - notional, 0.0)
        self.usdc += usdc_received

        total_fee = fee_leg_a + fee_em
        pnl = usdc_received - notional
        self.realized_fee_usd += total_fee
        self.total_trades += 1

        return TradeEventV2(
            ts=ts,
            symbol=symbol,
            action="TRADE_DC_EMERGENCY",
            premium=premium_fill,
            mid_usdt=mid_ut_fill,
            mid_usdc=mid_uc_em,
            notional_usd=notional,
            btc_qty=btc_qty,
            pnl_usd=pnl,
            fee_usd=total_fee,
            detail=(
                f"LegA@{mid_ut_fill:.2f}USDT(limit) "
                f"EmClose@{mid_uc_em:.2f}USDC(market) pnl={pnl:.4f}"
            ),
        )
