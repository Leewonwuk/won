"""CLI for v1.2 dual-quote backtest (BTCUSDT + BTCUSDC).

권장: ``python -m src.v12 --config configs/v12/v12_btc_dual.yaml ...``
호환: ``python -m src.backtest_v12_main`` (동일 구현 위임).
"""
from __future__ import annotations

import argparse
import glob
from datetime import datetime, timezone
from pathlib import Path

from src.v12.backtest import (
    BacktestV12Result,
    run_backtest_v12,
    save_v12_events_csv,
    save_v12_report,
)
from src.v12.config import load_v12_config, slippage_pair_from_multi_yaml
from src.v12.historical_data import collect_v12_btc_dual

_DEFAULT_CONFIG = "configs/v12/v12_btc_dual.yaml"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="v1.2 BTCUSDT/BTCUSDC backtest runner")
    p.add_argument("--config", default=_DEFAULT_CONFIG)
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--resolution", type=int, default=1, help="Candle minutes (1 or 5)")
    p.add_argument("--skip-collect", action="store_true")
    p.add_argument("--csv", default="", help="Use this CSV instead of collecting")
    p.add_argument(
        "--multi-slippage-yaml",
        default="configs/multi.yaml",
        help="Override v12 slippage from first coin (binance→USDT leg, upbit→USDC leg); "
        "set empty with --no-multi-slippage",
    )
    p.add_argument(
        "--no-multi-slippage",
        action="store_true",
        help="Use slippage from v12 YAML only (ignore multi.yaml)",
    )
    return p.parse_args()


def _print_summary(result: BacktestV12Result, report_path: str, events_path: str) -> None:
    roi_pct = result.total_return_rate * 100
    net = result.total_pnl_usd
    fees = result.total_fee_usd
    cumulative = net + fees
    print("\n  === v1.2 dual-quote 결과 (USDT 등가) ===")
    print(f"  처리 행 수:       {result.rows_processed:,}")
    print(f"  거래 횟수:        {result.trade_count}")
    print(f"  리밸런싱 횟수:    {result.rebalance_count}")
    print(f"  벽필터 거절 횟수: {result.wall_reject_count}")
    print(f"  승률:             {result.win_rate:.1%}")
    print(f"  시작자본:         {result.start_equity_usd:,.2f} USDT-eq")
    print(f"  ROI:              {roi_pct:.2f}%")
    print(f"  누적수익금:       {cumulative:,.2f} USDT-eq")
    print(f"  거래수수료:       {fees:,.2f} USDT-eq")
    print(f"  순수익:           {net:,.2f} USDT-eq")
    print(f"  단순보유 수익:    {result.buy_hold_pnl_usd:,.2f} ({result.buy_hold_return_rate*100:.2f}%)")
    print(f"  아비트리지 알파:  {result.arbitrage_alpha_usd:,.2f} ({result.arbitrage_alpha_rate*100:.2f}%)")
    print(f"  최대낙폭(MDD):    {result.max_drawdown_rate:.2%}")
    print(f"  종료자본:         {result.end_equity_usd:,.2f}")
    print(f"  리포트: {report_path}")
    print(f"  거래 CSV: {events_path}")
    if result.reason_counts:
        total_bars = sum(result.reason_counts.values())
        print("\n  --- 의사결정 사유 분포 (전체 봉 기준) ---")
        for reason, cnt in sorted(result.reason_counts.items(), key=lambda x: -x[1]):
            print(f"    {reason:<45s} {cnt:>7,}  ({cnt/total_bars*100:5.1f}%)")

    def _pct_stats(vals: list[float], label: str) -> None:
        if not vals:
            return
        s = sorted(vals)
        n = len(s)
        p = lambda q: s[min(int(q * n), n - 1)]
        print(f"\n  --- {label} premium 분포 ({n:,}봉) ---")
        print(f"    min={s[0]*100:.4f}%  p25={p(0.25)*100:.4f}%  median={p(0.5)*100:.4f}%"
              f"  p75={p(0.75)*100:.4f}%  p95={p(0.95)*100:.4f}%  max={s[-1]*100:.4f}%")
        mean = sum(s) / n
        print(f"    mean={mean*100:.4f}%   → fee stack 넘으려면 이 값 이상의 임계값 필요")

    _pct_stats(result.premium_blocked_kimchi, "kimchi fee-blocked (USDT>USDC)")
    _pct_stats(result.premium_blocked_reverse, "reverse fee-blocked (USDC>USDT)")


def main() -> None:
    args = parse_args()
    cfg_path = args.config
    if not Path(cfg_path).is_file() and cfg_path == _DEFAULT_CONFIG:
        legacy = "configs/v12_btc_dual.yaml"
        if Path(legacy).is_file():
            print(f"  Note: using legacy config path {legacy} (move to {_DEFAULT_CONFIG})")
            cfg_path = legacy

    multi_slip = None if args.no_multi_slippage else (args.multi_slippage_yaml or None)
    cfg = load_v12_config(cfg_path, multi_slippage_yaml=multi_slip)
    ts_tag = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    if multi_slip:
        triple = slippage_pair_from_multi_yaml(multi_slip)
        if triple is not None:
            su, sc, src = triple
            hint = (
                "multi.yaml → v12_binance_dual_quote.*"
                if src == "v12_binance_dual_quote"
                else "multi.yaml → coins[0] 레거시 매핑(바이낸스→USDT레그, 업비트→USDC레그)"
            )
            print(f"  Slippage from {multi_slip}: USDT leg={su:.6g}, USDC leg={sc:.6g} ({hint})")
        else:
            print("  Slippage: multi에 v12 블록·coins 없음; v12 YAML 기본 슬리피지 사용")

    if args.csv:
        csv_path = args.csv
    elif args.skip_collect:
        pattern = f"data/backtest/v12_btc_{args.days}d_{args.resolution}m_*.csv"
        files = sorted(glob.glob(pattern))
        if not files:
            print("  No existing v12 CSV; collecting...")
            csv_path = collect_v12_btc_dual(
                symbol_usdt=cfg.binance_symbol_usdt,
                symbol_usdc=cfg.binance_symbol_usdc,
                n_days=args.days,
                out_dir="data/backtest",
                tag=ts_tag,
                minutes=args.resolution,
            )
        else:
            csv_path = files[-1]
            print(f"  Using existing: {csv_path}")
    else:
        print(f"  Collecting {args.days}-day {args.resolution}m v12 data...")
        csv_path = collect_v12_btc_dual(
            symbol_usdt=cfg.binance_symbol_usdt,
            symbol_usdc=cfg.binance_symbol_usdc,
            n_days=args.days,
            out_dir="data/backtest",
            tag=ts_tag,
            minutes=args.resolution,
        )

    print(f"  CSV: {csv_path}")

    result = run_backtest_v12(csv_path=csv_path, cfg=cfg)

    sym = cfg.symbol.lower()
    report_path = save_v12_report(
        result,
        f"data/backtest/v12_{sym}_{args.days}d_report_{ts_tag}.json",
    )
    events_path = save_v12_events_csv(
        result,
        f"data/backtest/v12_{sym}_{args.days}d_trades_{ts_tag}.csv",
    )
    _print_summary(result, report_path, events_path)


if __name__ == "__main__":
    main()
