"""TRX v1.2 임계값 × 슬리피지 스윕 테스트."""
from __future__ import annotations

import argparse
from dataclasses import replace

from src.v12.backtest_v2 import run_backtest_v2
from src.v12.config_v2 import load_v12_config_v2


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--csv", required=True)
    p.add_argument("--lag-bars", type=int, default=1)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    base_cfg = load_v12_config_v2(args.config)
    base_cfg.leg_b_lag_bars = args.lag_bars

    thresholds = [0.0003, 0.0004, 0.0005, 0.0006, 0.0007, 0.0008, 0.0010]
    slippages  = [0.0000, 0.0001, 0.0002, 0.0003]

    print(f"{'threshold':>10} {'slippage':>9} {'fee_stack':>10} {'trades':>7} {'emerg':>6} {'winrate':>8} {'pnl_usd':>10} {'ROI':>7}")
    print("-" * 75)

    for thr in thresholds:
        for slip in slippages:
            cfg = replace(base_cfg,
                          dt_entry_threshold_rate=thr,
                          dc_entry_threshold_rate=thr,
                          slippage_rate=slip)
            eff_fee = cfg.fee_maker_rate if cfg.use_maker_fees else cfg.fee_rate
            fee_stack = 2.0 * (eff_fee + slip)
            try:
                r = run_backtest_v2(csv_path=args.csv, cfg=cfg)
                print(
                    f"{thr*100:>9.4f}%"
                    f"{slip*100:>8.4f}%"
                    f"{fee_stack*100:>9.4f}%"
                    f"{r.trade_count:>8}"
                    f"{r.emergency_close_count:>7}"
                    f"{r.win_rate:>8.1%}"
                    f"{r.total_pnl_usd:>11.2f}"
                    f"{r.total_return_rate*100:>7.2f}%"
                )
            except Exception as e:
                print(f"{thr*100:>9.4f}% {slip*100:>8.4f}%  ERROR: {e}")


if __name__ == "__main__":
    main()
