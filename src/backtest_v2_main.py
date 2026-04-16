"""Entry point for v2 backtest (4-balance rebalancing arb).

Collects 1-minute (or 5-minute) historical data then runs backtest.

Usage:
    python -m src.backtest_v2_main --config configs/multi.yaml --days 30 --resolution 1
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from src.config import load_multi_config
from src.backtest.historical_data import collect_last_nd_with_tag
from src.backtest.backtest_v2 import run_backtest_v2, save_v2_report, save_v2_events_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V2 backtest runner")
    parser.add_argument("--config", default="configs/multi.yaml")
    parser.add_argument("--days", type=int, default=30, help="Lookback days")
    parser.add_argument("--resolution", type=int, default=1, help="Candle minutes (1 or 5)")
    parser.add_argument("--skip-collect", action="store_true", help="Skip data collection, use existing CSV")
    parser.add_argument("--csv", default="", help="Use specific CSV file (overrides collection)")
    return parser.parse_args()


def _save_markdown_summary(
    rows: list[dict],
    days: int,
    resolution: int,
    ts_tag: str,
) -> tuple[str, str]:
    out_dir = Path("data/backtest")
    out_dir.mkdir(parents=True, exist_ok=True)
    dated_path = out_dir / f"v2_summary_{days}d_{resolution}m_{ts_tag}.md"
    latest_path = out_dir / "v2_summary_latest.md"

    lines: list[str] = []
    lines.append(f"# v2 백테스트 요약 ({days}일, {resolution}분봉)")
    lines.append("")
    lines.append(f"- 생성시각(UTC): `{datetime.now(tz=timezone.utc).isoformat()}`")
    lines.append("")
    lines.append("| 코인 | 거래횟수 | 리밸런싱횟수 | 벽필터거절 | 시작자본 | ROI | 누적수익금 | 거래수수료 | 순수익 | 단순보유수익 | 아비트리지알파 | MDD |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        lines.append(
            f"| {r['symbol']} | {r['trade_count']} | {r['rebalance_count']} | {r['wall_reject_count']} | "
            f"{r['start_capital']:,.0f} KRW | {r['roi_pct']:.2f}% | {r['cumulative_profit']:,.0f} KRW | "
            f"{r['trading_fees']:,.0f} KRW | {r['net_profit']:,.0f} KRW | "
            f"{r['buy_hold_pnl']:,.0f} KRW | {r['alpha_pnl']:,.0f} KRW | {r['mdd_pct']:.2f}% |"
        )

    content = "\n".join(lines) + "\n"
    dated_path.write_text(content, encoding="utf-8")
    latest_path.write_text(content, encoding="utf-8")
    return str(dated_path), str(latest_path)


def main() -> None:
    args = parse_args()
    cfg = load_multi_config(args.config)
    ts_tag = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    summary_rows: list[dict] = []

    for coin_cfg in cfg.coins:
        print(f"\n{'='*60}")
        print(f" Backtest: {coin_cfg.symbol} ({args.days}d, {args.resolution}m)")
        print(f"{'='*60}")

        # Step 1: Collect data (or use existing)
        if args.csv:
            csv_path = args.csv
        elif args.skip_collect:
            # Find latest CSV for this symbol
            import glob
            pattern = f"data/backtest/{coin_cfg.symbol.lower()}_{args.days}d_{args.resolution}m_*.csv"
            files = sorted(glob.glob(pattern))
            if not files:
                print(f"  No existing CSV found for {coin_cfg.symbol}, collecting...")
                csv_path = collect_last_nd_with_tag(
                    symbol=coin_cfg.symbol,
                    upbit_market=coin_cfg.upbit_market,
                    binance_symbol=coin_cfg.binance_symbol,
                    n_days=args.days,
                    out_dir="data/backtest",
                    tag=f"{args.days}d_{args.resolution}m_{ts_tag}",
                    minutes=args.resolution,
                )
            else:
                csv_path = files[-1]
                print(f"  Using existing: {csv_path}")
        else:
            print(f"  Collecting {args.days}-day {args.resolution}m data...")
            csv_path = collect_last_nd_with_tag(
                symbol=coin_cfg.symbol,
                upbit_market=coin_cfg.upbit_market,
                binance_symbol=coin_cfg.binance_symbol,
                n_days=args.days,
                out_dir="data/backtest",
                tag=f"{args.days}d_{args.resolution}m_{ts_tag}",
                minutes=args.resolution,
            )

        print(f"  CSV: {csv_path}")

        # Step 2: Run backtest
        result = run_backtest_v2(
            csv_path=csv_path,
            coin_cfg=coin_cfg,
            fx_fallback=cfg.fx_krw_per_usdt,
        )

        # Step 3: Save results
        report_path = save_v2_report(
            result,
            f"data/backtest/{coin_cfg.symbol.lower()}_{args.days}d_v2_report_{ts_tag}.json",
        )
        events_path = save_v2_events_csv(
            result,
            f"data/backtest/{coin_cfg.symbol.lower()}_{args.days}d_v2_trades_{ts_tag}.csv",
        )

        # Step 4: Print summary
        roi_pct = result.total_return_rate * 100
        net_profit_krw = result.total_pnl_krw
        trading_fee_krw = result.total_fee_krw
        # Requested display convention:
        # - cumulative_profit_krw: gross-like profit before fee deduction
        # - net_profit_krw: current PnL from engine (fees already reflected)
        cumulative_profit_krw = net_profit_krw + trading_fee_krw

        print(f"\n  === {coin_cfg.symbol} 결과 ===")
        print(f"  처리 행 수:       {result.rows_processed:,}")
        print(f"  거래 횟수:        {result.trade_count}")
        print(f"  리밸런싱 횟수:    {result.rebalance_count}")
        print(f"  벽필터 거절 횟수: {result.wall_reject_count}")
        print(f"  승률:             {result.win_rate:.1%}")
        print(f"  시작자본:         {result.start_equity_krw:,.0f} KRW")
        print(f"  ROI:              {roi_pct:.2f}%")
        print(f"  누적수익금:       {cumulative_profit_krw:,.0f} KRW")
        print(f"  거래수수료:       {trading_fee_krw:,.0f} KRW")
        print(f"  순수익:           {net_profit_krw:,.0f} KRW")
        print(f"  단순보유 수익:    {result.buy_hold_pnl_krw:,.0f} KRW ({result.buy_hold_return_rate*100:.2f}%)")
        print(f"  아비트리지 알파:  {result.arbitrage_alpha_krw:,.0f} KRW ({result.arbitrage_alpha_rate*100:.2f}%)")
        if result.arbitrage_alpha_krw > 0:
            print("  → 전략이 단순보유 대비 수익 기여")
        else:
            print("  → 전략이 단순보유 대비 손실 기여 (threshold 재검토 필요)")
        print(f"  최대낙폭(MDD):    {result.max_drawdown_rate:.2%}")
        print(f"  종료자본:         {result.end_equity_krw:,.0f}")
        print(f"  리포트: {report_path}")
        print(f"  거래 CSV: {events_path}")

        summary_rows.append(
            {
                "symbol": coin_cfg.symbol,
                "trade_count": result.trade_count,
                "rebalance_count": result.rebalance_count,
                "wall_reject_count": result.wall_reject_count,
                "start_capital": result.start_equity_krw,
                "roi_pct": roi_pct,
                "cumulative_profit": cumulative_profit_krw,
                "trading_fees": trading_fee_krw,
                "net_profit": net_profit_krw,
                "buy_hold_pnl": result.buy_hold_pnl_krw,
                "alpha_pnl": result.arbitrage_alpha_krw,
                "mdd_pct": result.max_drawdown_rate * 100,
            }
        )

    summary_dated, summary_latest = _save_markdown_summary(
        rows=summary_rows,
        days=args.days,
        resolution=args.resolution,
        ts_tag=ts_tag,
    )
    print(f"\n요약 Markdown(날짜별): {summary_dated}")
    print(f"요약 Markdown(최신):   {summary_latest}")


if __name__ == "__main__":
    main()
