"""v1.2 backtest: BTCUSDT vs BTCUSDC dual-quote simulation (USDT-equivalent)."""
from __future__ import annotations

import csv
import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.strategy.capital_allocator import Action
from src.v12.allocator import DecisionV12, decide_v12
from src.v12.config import V12Config
from src.v12.portfolio import DualQuotePortfolio, DualQuoteTradeEvent
from src.v12.price_util import v12_leg_mids


@dataclass
class BacktestV12Result:
    symbol: str
    total_return_rate: float
    total_pnl_usd: float
    total_fee_usd: float
    trade_count: int
    rebalance_count: int
    win_count: int
    win_rate: float
    max_drawdown_rate: float
    wall_reject_count: int
    pnl_7d_usd: float
    pnl_14d_usd: float
    buy_hold_pnl_usd: float
    buy_hold_return_rate: float
    arbitrage_alpha_usd: float
    arbitrage_alpha_rate: float
    start_equity_usd: float
    end_equity_usd: float
    rows_processed: int
    events: list[DualQuoteTradeEvent] = field(default_factory=list)
    reason_counts: dict[str, int] = field(default_factory=dict)
    # premium 값 수집: fee에 막혀 HOLD된 봉들 (분포 분석용)
    premium_blocked_kimchi: list[float] = field(default_factory=list)
    premium_blocked_reverse: list[float] = field(default_factory=list)


def _load_rows(csv_path: str) -> list[dict]:
    with Path(csv_path).open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def run_backtest_v12(csv_path: str, cfg: V12Config) -> BacktestV12Result:
    rows = _load_rows(csv_path)
    if not rows:
        raise ValueError(f"No data in {csv_path}")

    first = rows[0]
    mid_ut0, mid_uc0 = v12_leg_mids(first, cfg)
    if mid_ut0 <= 0 or mid_uc0 <= 0:
        raise ValueError("First row has zero prices")

    btc_ut_qty = cfg.initial_btc_usdt_leg_usd / mid_ut0
    btc_uc_qty = cfg.initial_btc_usdc_leg_usd / mid_uc0

    portfolio = DualQuotePortfolio()
    portfolio.init_symbol(
        symbol=cfg.symbol,
        usdt=cfg.initial_usdt,
        btc_usdt_leg=btc_ut_qty,
        usdc=cfg.initial_usdc,
        btc_usdc_leg=btc_uc_qty,
    )

    start_equity = (
        cfg.initial_usdt
        + cfg.initial_usdc
        + cfg.initial_btc_usdt_leg_usd
        + cfg.initial_btc_usdc_leg_usd
    )
    peak_equity = start_equity
    max_dd = 0.0
    wins = 0
    wall_reject_count = 0
    reason_counts: dict[str, int] = {}
    premium_blocked_kimchi: list[float] = []
    premium_blocked_reverse: list[float] = []

    # maker fee 지원: use_maker_fees=True 면 maker rate 사용
    eff_fee_ut = cfg.fee_usdt_leg_maker_rate if cfg.use_maker_fees else cfg.fee_usdt_leg_rate
    eff_fee_uc = cfg.fee_usdc_leg_maker_rate if cfg.use_maker_fees else cfg.fee_usdc_leg_rate

    vol_ut_hist: list[float] = []
    vol_uc_hist: list[float] = []
    equity_timeline: list[tuple[datetime, float]] = []
    last_utc_date: datetime | None = None

    b = portfolio.get(cfg.symbol)

    for row in rows:
        mid_ut, mid_uc = v12_leg_mids(row, cfg)
        if mid_ut <= 0 or mid_uc <= 0:
            continue

        ts_raw = row.get("ts", "")
        try:
            ts_dt = datetime.fromisoformat(ts_raw)
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=timezone.utc)
            ts_dt = ts_dt.astimezone(timezone.utc)
            d = ts_dt.date()
            if last_utc_date is not None and d != last_utc_date:
                portfolio.reset_daily_counters()
            last_utc_date = d
        except Exception:
            pass

        vol_ut = float(row.get("btc_usdt_volume", 0.0) or 0.0)
        vol_uc = float(row.get("btc_usdc_volume", 0.0) or 0.0)
        taker_uc = float(row.get("btc_usdc_taker_buy_volume", 0.0) or 0.0)

        liq_ut: float | None = None
        liq_uc: float | None = None
        if len(vol_ut_hist) >= 20:
            med_ut = statistics.median(vol_ut_hist[-120:])
            med_uc = statistics.median(vol_uc_hist[-120:])
            if med_ut > 0:
                liq_ut = vol_ut / med_ut
            if med_uc > 0:
                liq_uc = vol_uc / med_uc

        taker_buy_ratio_uc = (taker_uc / vol_uc) if vol_uc > 0 else None

        decision = decide_v12(
            symbol=cfg.symbol,
            mid_usdt=mid_ut,
            mid_usdc=mid_uc,
            usdt=b.usdt,
            btc_ut=b.btc_usdt_leg,
            usdc=b.usdc,
            btc_uc=b.btc_usdc_leg,
            entry_threshold_rate=cfg.entry_threshold_rate,
            fee_usdt_leg_rate=eff_fee_ut,
            fee_usdc_leg_rate=eff_fee_uc,
            slippage_usdt_leg_rate=cfg.slippage_usdt_leg_rate,
            slippage_usdc_leg_rate=cfg.slippage_usdc_leg_rate,
            transfer_fee_btc=cfg.internal_transfer_btc_fee,
            stable_move_fee_rate=cfg.internal_stable_move_fee_rate,
            rebalance_profit_multiplier=cfg.rebalance_profit_multiplier,
            rebalance_imbalance_threshold=cfg.rebalance_imbalance_threshold,
            target_portfolio_ratio=cfg.target_portfolio_ratio,
            daily_rebalances=b.daily_rebalances,
            max_daily_rebalances=cfg.max_daily_rebalances,
            emergency_cash_ratio=cfg.emergency_cash_ratio,
            emergency_coin_ratio=cfg.emergency_coin_ratio,
            reverse_entry_threshold_rate=cfg.reverse_entry_threshold_rate,
        )
        reason_counts[decision.reason] = reason_counts.get(decision.reason, 0) + 1
        if decision.reason == "kimchi_premium_fee_exceeds_profit":
            premium_blocked_kimchi.append(decision.premium)
        elif decision.reason == "reverse_premium_fee_exceeds_profit":
            premium_blocked_reverse.append(abs(decision.premium))

        if cfg.wall_filter_enabled and decision.action in (
            Action.TRADE_KIMCHI,
            Action.TRADE_REVERSE,
        ):
            allow = True
            if liq_ut is not None and liq_ut < cfg.wall_min_liquidity_ratio:
                allow = False
            if liq_uc is not None and liq_uc < cfg.wall_min_liquidity_ratio:
                allow = False
            if allow and taker_buy_ratio_uc is not None:
                if (
                    decision.action == Action.TRADE_KIMCHI
                    and taker_buy_ratio_uc > cfg.wall_buy_usdc_leg_taker_buy_ratio_max
                ):
                    allow = False
                if (
                    decision.action == Action.TRADE_REVERSE
                    and taker_buy_ratio_uc < cfg.wall_sell_usdc_leg_taker_buy_ratio_min
                ):
                    allow = False
            if not allow:
                wall_reject_count += 1
                decision = DecisionV12(Action.HOLD, cfg.symbol, decision.premium, "wall_filter_reject")

        if decision.action == Action.TRADE_KIMCHI:
            ev = portfolio.execute_kimchi_trade(
                symbol=cfg.symbol,
                mid_usdt=mid_ut,
                mid_usdc=mid_uc,
                fee_usdt_leg_rate=eff_fee_ut,
                fee_usdc_leg_rate=eff_fee_uc,
                slip_usdt_leg_rate=cfg.slippage_usdt_leg_rate,
                slip_usdc_leg_rate=cfg.slippage_usdc_leg_rate,
                trade_fraction=cfg.entry_split_fraction,
                ts=ts_raw,
            )
            if ev.pnl_usd > 0:
                wins += 1

        elif decision.action == Action.TRADE_REVERSE:
            ev = portfolio.execute_reverse_trade(
                symbol=cfg.symbol,
                mid_usdt=mid_ut,
                mid_usdc=mid_uc,
                fee_usdt_leg_rate=eff_fee_ut,
                fee_usdc_leg_rate=eff_fee_uc,
                slip_usdt_leg_rate=cfg.slippage_usdt_leg_rate,
                slip_usdc_leg_rate=cfg.slippage_usdc_leg_rate,
                trade_fraction=cfg.entry_split_fraction,
                ts=ts_raw,
            )
            if ev.pnl_usd > 0:
                wins += 1

        elif decision.action == Action.REBALANCE_U_TO_B:
            portfolio.execute_rebalance_dt_to_dc(
                symbol=cfg.symbol,
                mid_usdt=mid_ut,
                mid_usdc=mid_uc,
                transfer_fee_btc=cfg.internal_transfer_btc_fee,
                stable_move_fee_rate=cfg.internal_stable_move_fee_rate,
                target_portfolio_ratio=cfg.target_portfolio_ratio,
                ts=ts_raw,
            )

        elif decision.action == Action.REBALANCE_B_TO_U:
            portfolio.execute_rebalance_dc_to_dt(
                symbol=cfg.symbol,
                mid_usdt=mid_ut,
                mid_usdc=mid_uc,
                transfer_fee_btc=cfg.internal_transfer_btc_fee,
                stable_move_fee_rate=cfg.internal_stable_move_fee_rate,
                target_portfolio_ratio=cfg.target_portfolio_ratio,
                ts=ts_raw,
            )

        equity = b.total_value_usd(mid_ut, mid_uc)
        if equity > peak_equity:
            peak_equity = equity
        dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

        vol_ut_hist.append(vol_ut)
        vol_uc_hist.append(vol_uc)

        try:
            ts_dt2 = datetime.fromisoformat(ts_raw)
            if ts_dt2.tzinfo is None:
                ts_dt2 = ts_dt2.replace(tzinfo=timezone.utc)
            equity_timeline.append((ts_dt2.astimezone(timezone.utc), equity))
        except Exception:
            pass

    last = rows[-1]
    mid_ut_f, mid_uc_f = v12_leg_mids(last, cfg)
    end_equity = b.total_value_usd(mid_ut_f, mid_uc_f)

    trade_count = b.total_trades
    rebalance_count = b.total_rebalances

    init_ut_coin = cfg.initial_btc_usdt_leg_usd / mid_ut0
    init_uc_coin = cfg.initial_btc_usdc_leg_usd / mid_uc0
    buy_hold_end = (
        cfg.initial_usdt
        + cfg.initial_usdc
        + init_ut_coin * mid_ut_f
        + init_uc_coin * mid_uc_f
    )
    buy_hold_pnl = buy_hold_end - start_equity
    buy_hold_return = (buy_hold_pnl / start_equity) if start_equity > 0 else 0.0

    total_pnl = end_equity - start_equity
    alpha_pnl = total_pnl - buy_hold_pnl
    alpha_rate = (alpha_pnl / start_equity) if start_equity > 0 else 0.0

    pnl_7d = 0.0
    pnl_14d = 0.0
    if equity_timeline:
        end_ts = equity_timeline[-1][0]
        end_eq = equity_timeline[-1][1]
        cutoff_7d = end_ts - timedelta(days=7)
        cutoff_14d = end_ts - timedelta(days=14)
        eq_7d = next((eq for ts, eq in equity_timeline if ts >= cutoff_7d), None)
        eq_14d = next((eq for ts, eq in equity_timeline if ts >= cutoff_14d), None)
        if eq_7d is not None:
            pnl_7d = end_eq - eq_7d
        if eq_14d is not None:
            pnl_14d = end_eq - eq_14d

    return BacktestV12Result(
        symbol=cfg.symbol,
        total_return_rate=(end_equity - start_equity) / start_equity if start_equity > 0 else 0.0,
        total_pnl_usd=total_pnl,
        total_fee_usd=b.realized_fee_usd,
        trade_count=trade_count,
        rebalance_count=rebalance_count,
        win_count=wins,
        win_rate=wins / trade_count if trade_count > 0 else 0.0,
        max_drawdown_rate=max_dd,
        wall_reject_count=wall_reject_count,
        pnl_7d_usd=pnl_7d,
        pnl_14d_usd=pnl_14d,
        buy_hold_pnl_usd=buy_hold_pnl,
        buy_hold_return_rate=buy_hold_return,
        arbitrage_alpha_usd=alpha_pnl,
        arbitrage_alpha_rate=alpha_rate,
        start_equity_usd=start_equity,
        end_equity_usd=end_equity,
        rows_processed=len(rows),
        events=portfolio.events,
        reason_counts=reason_counts,
        premium_blocked_kimchi=premium_blocked_kimchi,
        premium_blocked_reverse=premium_blocked_reverse,
    )


def save_v12_report(result: BacktestV12Result, path: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "symbol": result.symbol,
        "total_return_rate": result.total_return_rate,
        "total_pnl_usd": result.total_pnl_usd,
        "total_fee_usd": result.total_fee_usd,
        "trade_count": result.trade_count,
        "rebalance_count": result.rebalance_count,
        "win_count": result.win_count,
        "win_rate": result.win_rate,
        "max_drawdown_rate": result.max_drawdown_rate,
        "wall_reject_count": result.wall_reject_count,
        "pnl_7d_usd": result.pnl_7d_usd,
        "pnl_14d_usd": result.pnl_14d_usd,
        "buy_hold_pnl_usd": result.buy_hold_pnl_usd,
        "buy_hold_return_rate": result.buy_hold_return_rate,
        "arbitrage_alpha_usd": result.arbitrage_alpha_usd,
        "arbitrage_alpha_rate": result.arbitrage_alpha_rate,
        "start_equity_usd": result.start_equity_usd,
        "end_equity_usd": result.end_equity_usd,
        "rows_processed": result.rows_processed,
        "reason_counts": dict(sorted(result.reason_counts.items(), key=lambda x: -x[1])),
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def save_v12_events_csv(result: BacktestV12Result, path: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not result.events:
        p.write_text("", encoding="utf-8")
        return str(p)
    keys = [
        "ts",
        "symbol",
        "event",
        "premium",
        "mid_usdt",
        "mid_usdc",
        "trade_qty",
        "pnl_usd",
        "fee_usd",
        "detail",
    ]
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for ev in result.events:
            writer.writerow({k: getattr(ev, k, "") for k in keys})
    return str(p)
