"""CLI for v1.2 v2 백테스트 (3-balance, 바이낸스 단일 거래소).

권장: python -m src.v12.v2 --config configs/v12/v12_btc_v2.yaml --days 30
"""
from __future__ import annotations

import argparse
import glob
from datetime import datetime, timezone
from pathlib import Path

from src.v12.backtest_v2 import (
    BacktestV2Result,
    run_backtest_v2,
    save_v2_events_csv,
    save_v2_report,
)
from src.v12.config_v2 import V12ConfigV2, load_v12_config_v2
from src.v12.historical_data import collect_v12_btc_dual

_DEFAULT_CONFIG = "configs/v12/v12_btc_v2.yaml"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="v1.2 v2 BTCUSDT/BTCUSDC 백테스트 (3-balance)")
    p.add_argument("--config", default=_DEFAULT_CONFIG)
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--resolution", type=int, default=1, help="캔들 단위 분 (1 or 5)")
    p.add_argument("--interval", default="", help="봉 간격 직접 지정 (예: 1s, 1m, 5m). 지정 시 --resolution 무시")
    p.add_argument("--skip-collect", action="store_true", help="기존 CSV 재사용")
    p.add_argument("--csv", default="", help="직접 CSV 경로 지정")
    p.add_argument("--lag-bars", type=int, default=0,
                   help="Leg B 체결 지연 봉 수 (1초봉에서 sequential 시뮬: 1)")
    p.add_argument("--slippage", type=float, default=None,
                   help="슬리피지 override (예: 0.0002 = 레그당 0.02%)")
    return p.parse_args()


def _print_summary(result: BacktestV2Result, report_path: str, events_path: str) -> None:
    roi_pct = result.total_return_rate * 100
    print("\n  === v1.2 v2 백테스트 결과 (3-balance, USDT 등가) ===")
    print(f"  처리 행 수:        {result.rows_processed:,}")
    print(f"  총 거래 횟수:      {result.trade_count}"
          f"  (DT: {result.dt_trade_count}  DC: {result.dc_trade_count})")
    print(f"  승률:              {result.win_rate:.1%}")
    print(f"  시작 자본:         {result.start_equity_usd:,.2f} USDT-eq")
    print(f"  ROI:               {roi_pct:.2f}%")
    print(f"  누적 수익 (fee 전): {result.total_pnl_usd + result.total_fee_usd:,.2f}")
    print(f"  거래 수수료:        {result.total_fee_usd:,.2f}")
    print(f"  순 수익:            {result.total_pnl_usd:,.2f}")
    print(f"  단순 보유 수익:     0.00 (스테이블코인 보유 → 가격 변동 없음)")
    print(f"  아비트리지 알파:    {result.arbitrage_alpha_usd:,.2f} ({result.arbitrage_alpha_rate*100:.2f}%)")
    print(f"  최대 낙폭 (MDD):    {result.max_drawdown_rate:.2%}")
    print(f"  종료 자본:          {result.end_equity_usd:,.2f}")
    print(f"  비상 청산 횟수:     {result.emergency_close_count}")
    print(f"  타임아웃 취소 횟수: {result.unfilled_timeout_count}")
    print(f"  리포트:  {report_path}")
    print(f"  거래 CSV: {events_path}")

    if result.reason_counts:
        total_bars = sum(result.reason_counts.values())
        print("\n  --- 의사결정 사유 분포 ---")
        for reason, cnt in sorted(result.reason_counts.items(), key=lambda x: -x[1]):
            print(f"    {reason:<42s} {cnt:>8,}  ({cnt/total_bars*100:5.1f}%)")

    def _pct_stats(vals: list[float], label: str) -> None:
        if not vals:
            return
        s = sorted(vals)
        n = len(s)
        p = lambda q: s[min(int(q * n), n - 1)]
        mean = sum(s) / n
        print(f"\n  --- {label} premium 분포 ({n:,}봉) ---")
        print(f"    min={s[0]*100:.4f}%  p25={p(0.25)*100:.4f}%  median={p(0.5)*100:.4f}%"
              f"  p75={p(0.75)*100:.4f}%  p95={p(0.95)*100:.4f}%  max={s[-1]*100:.4f}%")
        print(f"    mean={mean*100:.4f}%")

    _pct_stats(result.premium_blocked_dt, "DT fee-blocked")
    _pct_stats(result.premium_blocked_dc, "DC fee-blocked")


def main() -> None:
    args = parse_args()
    cfg_path = args.config
    if not Path(cfg_path).is_file():
        raise FileNotFoundError(f"Config not found: {cfg_path}")

    cfg = load_v12_config_v2(cfg_path)
    if args.lag_bars > 0:
        cfg.leg_b_lag_bars = args.lag_bars
    if args.slippage is not None:
        cfg.slippage_rate = args.slippage
    ts_tag = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")

    eff_fee = cfg.fee_maker_rate if cfg.use_maker_fees else cfg.fee_rate
    fee_stack = 2.0 * (eff_fee + cfg.slippage_rate)
    print(f"  자본: USDT={cfg.initial_usdt:,.0f}  USDC={cfg.initial_usdc:,.0f}  "
          f"(BTC 보유 없음, 스테이블 전용)")
    print(f"  fee={eff_fee:.4f}  slip={cfg.slippage_rate:.4f}  "
          f"fee_stack={fee_stack:.4f}  "
          f"DT_thr={cfg.dt_entry_threshold_rate:.4f}  "
          f"DC_thr={cfg.dc_entry_threshold_rate:.4f}")

    sym = cfg.symbol.lower()
    label = args.interval if args.interval else f"{args.resolution}m"

    if args.csv:
        csv_path = args.csv
    elif args.skip_collect:
        pattern = f"data/backtest/v12_{sym}_{args.days}d_{label}_*.csv"
        files = sorted(glob.glob(pattern))
        if files:
            csv_path = files[-1]
            print(f"  Using existing: {csv_path}")
        else:
            print("  기존 CSV 없음, 새로 수집합니다...")
            csv_path = collect_v12_btc_dual(
                symbol_usdt=cfg.binance_symbol_usdt,
                symbol_usdc=cfg.binance_symbol_usdc,
                n_days=args.days,
                out_dir="data/backtest",
                tag=ts_tag,
                minutes=args.resolution,
                interval=args.interval,
                coin=sym,
            )
    else:
        print(f"  {args.days}일 {label} 데이터 수집 중... ({cfg.binance_symbol_usdt} / {cfg.binance_symbol_usdc})")
        csv_path = collect_v12_btc_dual(
            symbol_usdt=cfg.binance_symbol_usdt,
            symbol_usdc=cfg.binance_symbol_usdc,
            n_days=args.days,
            out_dir="data/backtest",
            tag=ts_tag,
            minutes=args.resolution,
            interval=args.interval,
            coin=sym,
        )

    print(f"  CSV: {csv_path}")

    result = run_backtest_v2(csv_path=csv_path, cfg=cfg)

    report_path = save_v2_report(result, f"data/backtest/v2_{sym}_{args.days}d_report_{ts_tag}.json")
    events_path = save_v2_events_csv(result, f"data/backtest/v2_{sym}_{args.days}d_trades_{ts_tag}.csv")
    _print_summary(result, report_path, events_path)


if __name__ == "__main__":
    main()
