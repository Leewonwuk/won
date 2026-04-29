"""v1.2 v2 백테스트: 스테이블코인 전용 (USDT + USDC), BTC 보유 없음."""
from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.v12.allocator_v2 import ActionV2, decide_v2
from src.v12.config_v2 import V12ConfigV2
from src.v12.portfolio_v2 import BalanceV2, TradeEventV2
from src.v12.price_util import v12_leg_mids


@dataclass
class BacktestV2Result:
    symbol: str
    total_return_rate: float
    total_pnl_usd: float
    total_fee_usd: float
    trade_count: int
    dt_trade_count: int
    dc_trade_count: int
    win_rate: float
    max_drawdown_rate: float
    pnl_7d_usd: float
    pnl_14d_usd: float
    arbitrage_alpha_usd: float   # buy-hold = 0 (스테이블), 전체 pnl = alpha
    arbitrage_alpha_rate: float
    start_equity_usd: float
    end_equity_usd: float
    rows_processed: int
    events: list[TradeEventV2] = field(default_factory=list)
    reason_counts: dict[str, int] = field(default_factory=dict)
    premium_blocked_dt: list[float] = field(default_factory=list)
    premium_blocked_dc: list[float] = field(default_factory=list)
    emergency_close_count: int = 0
    unfilled_timeout_count: int = 0


def _fill_outcome(
    rows: list[dict],
    idx: int,
    signal_premium: float,
    fee_stack: float,
    timeout_bars: int,
    cfg: V12ConfigV2,
    start_offset: int = 1,
) -> tuple[str, int]:
    """시그널 봉 이후 lookahead로 주문 체결 여부 판정.

    start_offset: 시그널 봉 기준 몇 봉 후부터 체크할지.
      1 (기본) = 다음 봉부터 즉시
      2       = 2초/2봉 지연 후 체크 (leg_b_lag_bars=2 시뮬)

    Returns:
        ('filled', bar_idx)    - 프리미엄 유지 → 정상 체결
        ('unfilled', idx)      - 프리미엄 소멸 → 타임아웃 취소
        ('emergency', bar_idx) - 프리미엄 역전 → Leg A 체결 후 비상 청산
    """
    for k in range(start_offset, timeout_bars + 1):
        j = idx + k
        if j >= len(rows):
            return ('filled', idx)   # 데이터 끝 → 마지막 가격으로 체결 간주

        mid_ut, mid_uc = v12_leg_mids(rows[j], cfg)
        if mid_ut <= 0 or mid_uc <= 0:
            continue
        premium = (mid_ut - mid_uc) / mid_uc

        if signal_premium > 0:   # DT 시그널
            if premium > fee_stack:
                return ('filled', j)     # 프리미엄 유지 → 지정가 체결
            if premium < 0:
                return ('emergency', j)  # 역전 → 비상 청산
        else:                    # DC 시그널
            if premium < -fee_stack:
                return ('filled', j)
            if premium > 0:
                return ('emergency', j)

    return ('unfilled', idx)  # 타임아웃 내 체결 조건 미달 → 취소


def _load_rows(csv_path: str) -> list[dict]:
    with Path(csv_path).open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def run_backtest_v2(csv_path: str, cfg: V12ConfigV2) -> BacktestV2Result:
    rows = _load_rows(csv_path)
    if not rows:
        raise ValueError(f"No data in {csv_path}")
    return run_backtest_v2_from_rows(rows, cfg)


def run_backtest_v2_from_rows(rows: list[dict], cfg: V12ConfigV2) -> BacktestV2Result:
    """WFO 등에서 재사용하는 rows 직접 입력 버전. 기존 run_backtest_v2와 동일 로직."""
    if not rows:
        raise ValueError("empty rows")

    bal = BalanceV2(usdt=cfg.initial_usdt, usdc=cfg.initial_usdc)
    start_equity = cfg.initial_usdt + cfg.initial_usdc

    peak_equity = start_equity
    max_dd = 0.0
    wins = 0
    dt_count = 0
    dc_count = 0
    reason_counts: dict[str, int] = {}
    premium_blocked_dt: list[float] = []
    premium_blocked_dc: list[float] = []
    events: list[TradeEventV2] = []
    equity_timeline: list[tuple[datetime, float]] = []

    eff_fee = cfg.fee_maker_rate if cfg.use_maker_fees else cfg.fee_rate
    # 페어별 fee (USDC pair Taker promo 반영). 미설정 시 legacy fee_rate fallback.
    usdc_taker = cfg.fee_usdc_pair_taker if cfg.fee_usdc_pair_taker is not None else cfg.fee_rate
    usdc_maker = (
        cfg.fee_usdc_pair_maker
        if (cfg.use_maker_fees and cfg.fee_usdc_pair_maker is not None)
        else eff_fee
    )
    # DT: LegA=USDC pair taker(promo), LegB=USDT pair maker
    dt_fee_stack = usdc_taker + eff_fee + 2.0 * cfg.slippage_rate
    # DC: LegA=USDT pair taker, LegB=USDC pair maker
    dc_fee_stack = cfg.fee_rate + usdc_maker + 2.0 * cfg.slippage_rate
    # legacy fee_stack: GTC fill outcome 비교용 (보수적으로 둘 중 큰 값)
    fee_stack = max(dt_fee_stack, dc_fee_stack)
    effective_fill_rate = 1.0 if not cfg.use_maker_fees else cfg.fill_rate
    rng = random.Random(42)

    # 타임아웃 봉 수 계산
    # lag_bars > 0 (1초봉 모드): order_timeout_sec = 초 단위 봉 수 그대로 사용
    # 그 외 (분봉 모드): 분으로 환산
    if cfg.leg_b_lag_bars > 0:
        timeout_bars = max(cfg.leg_b_lag_bars, cfg.order_timeout_sec)
    else:
        timeout_bars = max(1, math.ceil(cfg.order_timeout_sec / 60))
    use_timeout_sim = cfg.use_maker_fees  # 지정가일 때만 타임아웃 시뮬레이션

    emergency_count = 0
    unfilled_timeout_count = 0

    # lag_bars > 0 이면 순차 시뮬: 거래 체결 후 fill_idx까지 건너뜀
    # (실제 봇은 LEG_A → LEG_B → IDLE 상태머신 → 거래 중 새 진입 불가)
    sequential = cfg.leg_b_lag_bars > 0

    i = 0
    while i < len(rows):
        row = rows[i]
        mid_ut, mid_uc = v12_leg_mids(row, cfg)
        if mid_ut <= 0 or mid_uc <= 0:
            i += 1
            continue

        ts_raw = rows[i].get("ts", "")
        try:
            ts_dt = datetime.fromisoformat(ts_raw)
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=timezone.utc)
            ts_dt = ts_dt.astimezone(timezone.utc)
        except Exception:
            ts_dt = None

        decision = decide_v2(
            mid_usdt=mid_ut,
            mid_usdc=mid_uc,
            usdt=bal.usdt,
            usdc=bal.usdc,
            dt_entry_threshold_rate=cfg.dt_entry_threshold_rate,
            dc_entry_threshold_rate=cfg.dc_entry_threshold_rate,
            fee_rate=eff_fee,
            slippage_rate=cfg.slippage_rate,
            entry_split_fraction=cfg.entry_split_fraction,
            dt_fee_stack=dt_fee_stack,
            dc_fee_stack=dc_fee_stack,
        )

        reason_counts[decision.reason] = reason_counts.get(decision.reason, 0) + 1
        if decision.reason == "dt_premium_fee_exceeds_profit":
            premium_blocked_dt.append(decision.premium)
        elif decision.reason == "dc_premium_fee_exceeds_profit":
            premium_blocked_dc.append(abs(decision.premium))

        if decision.action in (ActionV2.TRADE_DT, ActionV2.TRADE_DC):
            is_dt = decision.action == ActionV2.TRADE_DT

            if cfg.leg_b_lag_bars > 0:
                # 1초봉 모드: lag_bars초 지연 후 체결 시도 → 이후 order_timeout_sec까지 대기
                # Leg A는 항상 체결 가정 (IOC miss 없음)
                # - lag_bars봉 후부터 프리미엄 체크 시작
                # - 프리미엄 유지(>fee_stack) → filled (체결)
                # - 프리미엄 역전(<0) → emergency (시장가 손절)
                # - timeout_bars 내 조건 미충족 → unfilled (GTC 취소)
                outcome, fill_idx = _fill_outcome(
                    rows, i, decision.premium, fee_stack, timeout_bars, cfg,
                    start_offset=cfg.leg_b_lag_bars,
                )
            elif use_timeout_sim:
                outcome, fill_idx = _fill_outcome(
                    rows, i, decision.premium, fee_stack, timeout_bars, cfg
                )
            else:
                outcome = 'filled'
                fill_idx = i

            if outcome == 'filled' and rng.random() <= effective_fill_rate:
                # Leg B는 실제 체결 봉(fill_idx)의 가격 사용
                # (Leg A 체결 후 Leg B 지정가를 새로 설정하는 라이브 동작 반영)
                if fill_idx > i:
                    fill_mid_ut, fill_mid_uc = v12_leg_mids(rows[fill_idx], cfg)
                else:
                    fill_mid_ut, fill_mid_uc = mid_ut, mid_uc

                if is_dt:
                    # DT: LegA=BTCUSDC(USDC pair, taker promo), LegB=BTCUSDT(maker)
                    ev = bal.execute_dt_trade(
                        symbol=cfg.symbol, mid_usdt=fill_mid_ut, mid_usdc=mid_uc,
                        fee_rate=eff_fee, slippage_rate=cfg.slippage_rate,
                        fraction=cfg.entry_split_fraction, ts=ts_raw,
                        leg_a_fee_rate=usdc_taker, leg_b_fee_rate=eff_fee,
                    )
                    dt_count += 1
                else:
                    # DC: LegA=BTCUSDT(taker), LegB=BTCUSDC(USDC pair maker, promo 없음)
                    ev = bal.execute_dc_trade(
                        symbol=cfg.symbol, mid_usdt=mid_ut, mid_usdc=fill_mid_uc,
                        fee_rate=eff_fee, slippage_rate=cfg.slippage_rate,
                        fraction=cfg.entry_split_fraction, ts=ts_raw,
                        leg_a_fee_rate=cfg.fee_rate, leg_b_fee_rate=usdc_maker,
                    )
                    dc_count += 1
                events.append(ev)
                if ev.pnl_usd > 0:
                    wins += 1

            elif outcome == 'emergency':
                em_mid_ut, em_mid_uc = v12_leg_mids(rows[fill_idx], cfg)
                if is_dt:
                    ev = bal.execute_dt_emergency(
                        symbol=cfg.symbol,
                        mid_uc_fill=mid_uc, mid_ut_em=em_mid_ut,
                        limit_fee_rate=eff_fee,
                        emergency_fee_rate=cfg.emergency_taker_fee_rate,
                        emergency_slip_rate=cfg.emergency_slippage_rate,
                        fraction=cfg.entry_split_fraction, ts=ts_raw,
                    )
                    dt_count += 1
                else:
                    ev = bal.execute_dc_emergency(
                        symbol=cfg.symbol,
                        mid_ut_fill=mid_ut, mid_uc_em=em_mid_uc,
                        limit_fee_rate=eff_fee,
                        emergency_fee_rate=cfg.emergency_taker_fee_rate,
                        emergency_slip_rate=cfg.emergency_slippage_rate,
                        fraction=cfg.entry_split_fraction, ts=ts_raw,
                    )
                    dc_count += 1
                events.append(ev)
                emergency_count += 1
                if ev.pnl_usd > 0:
                    wins += 1
                reason_counts["emergency_close"] = reason_counts.get("emergency_close", 0) + 1

            else:  # unfilled or fill_rate miss
                unfilled_timeout_count += 1
                reason_counts["unfilled_timeout"] = reason_counts.get("unfilled_timeout", 0) + 1

            # 순차 모드: 거래 종료 봉(fill_idx) 다음부터 재개 (중복 거래 방지)
            if sequential:
                equity = bal.total_value_usd()
                if equity > peak_equity:
                    peak_equity = equity
                dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
                if dd > max_dd:
                    max_dd = dd
                if ts_dt is not None:
                    equity_timeline.append((ts_dt, equity))
                i = fill_idx + 1
                continue

        equity = bal.total_value_usd()
        if equity > peak_equity:
            peak_equity = equity
        dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

        if ts_dt is not None:
            equity_timeline.append((ts_dt, equity))
        i += 1

    end_equity = bal.total_value_usd()
    total_pnl = end_equity - start_equity
    # 스테이블코인만 보유 → buy-hold pnl = 0, 전체 pnl = 아비트리지 알파
    alpha_rate = total_pnl / start_equity if start_equity > 0 else 0.0

    trade_count = dt_count + dc_count

    pnl_7d = pnl_14d = 0.0
    if equity_timeline:
        end_ts, end_eq = equity_timeline[-1]
        for cutoff, key in [(timedelta(days=7), "7d"), (timedelta(days=14), "14d")]:
            eq = next((e for t, e in equity_timeline if t >= end_ts - cutoff), None)
            if eq is not None:
                if key == "7d":
                    pnl_7d = end_eq - eq
                else:
                    pnl_14d = end_eq - eq

    return BacktestV2Result(
        symbol=cfg.symbol,
        total_return_rate=alpha_rate,
        total_pnl_usd=total_pnl,
        total_fee_usd=bal.realized_fee_usd,
        trade_count=trade_count,
        dt_trade_count=dt_count,
        dc_trade_count=dc_count,
        win_rate=wins / trade_count if trade_count > 0 else 0.0,
        max_drawdown_rate=max_dd,
        pnl_7d_usd=pnl_7d,
        pnl_14d_usd=pnl_14d,
        arbitrage_alpha_usd=total_pnl,
        arbitrage_alpha_rate=alpha_rate,
        start_equity_usd=start_equity,
        end_equity_usd=end_equity,
        rows_processed=len(rows),
        events=events,
        reason_counts=reason_counts,
        premium_blocked_dt=premium_blocked_dt,
        premium_blocked_dc=premium_blocked_dc,
        emergency_close_count=emergency_count,
        unfilled_timeout_count=unfilled_timeout_count,
    )


def save_v2_report(result: BacktestV2Result, path: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "symbol": result.symbol,
        "total_return_rate": result.total_return_rate,
        "total_pnl_usd": result.total_pnl_usd,
        "total_fee_usd": result.total_fee_usd,
        "trade_count": result.trade_count,
        "dt_trade_count": result.dt_trade_count,
        "dc_trade_count": result.dc_trade_count,
        "win_rate": result.win_rate,
        "max_drawdown_rate": result.max_drawdown_rate,
        "pnl_7d_usd": result.pnl_7d_usd,
        "pnl_14d_usd": result.pnl_14d_usd,
        "arbitrage_alpha_usd": result.arbitrage_alpha_usd,
        "arbitrage_alpha_rate": result.arbitrage_alpha_rate,
        "start_equity_usd": result.start_equity_usd,
        "end_equity_usd": result.end_equity_usd,
        "rows_processed": result.rows_processed,
        "reason_counts": dict(sorted(result.reason_counts.items(), key=lambda x: -x[1])),
        "emergency_close_count": result.emergency_close_count,
        "unfilled_timeout_count": result.unfilled_timeout_count,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def save_v2_events_csv(result: BacktestV2Result, path: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not result.events:
        p.write_text("", encoding="utf-8")
        return str(p)
    keys = ["ts", "symbol", "action", "premium", "mid_usdt", "mid_usdc",
            "notional_usd", "btc_qty", "pnl_usd", "fee_usd", "detail"]
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for ev in result.events:
            writer.writerow({k: getattr(ev, k, "") for k in keys})
    return str(p)
