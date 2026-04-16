"""v1.1 TRX 수수료 비교 백테스트 (구: VIP4 오적용 vs 신: VIP0+BNB할인)

실행:
  python -m scripts.backtest_v11_fee_compare
  python -m scripts.backtest_v11_fee_compare --days 14
  python -m scripts.backtest_v11_fee_compare --skip-collect  # 기존 데이터 재사용
"""
from __future__ import annotations

import argparse
import io
import sys
from datetime import datetime
from pathlib import Path

# UTF-8 강제 (Windows cp949 터미널 대응)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from src.backtest.historical_data import collect_last_nd
from src.backtest.backtest_runner import run_backtest_from_csv

# ------------------------------------------------------------------
# 설정
# ------------------------------------------------------------------
DAYS = 14
COIN = "TRX"
UPBIT_MARKET = "KRW-TRX"
BINANCE_SYMBOL = "TRXUSDT"
DATA_DIR = "data/v11_backtest"

# 실제 운용 슬리피지 (multi.yaml 기준)
SLIPPAGE_UPBIT = 0.0032
SLIPPAGE_BINANCE = 0.0002
TRANSFER_FEE_BASE = 1.0  # TRX 단위

INITIAL_KRW = 800_000  # 4슬롯 × 20만 원 (multi.yaml 기준 단일 코인 총자본)

# 수수료 시나리오
FEE_SCENARIOS = {
    "구_설정 (VIP4 오적용)": {
        "fee_upbit_rate":   0.0005,
        "fee_binance_rate": 0.0004,   # VIP4 taker — 잘못된 값
    },
    "신_설정 (VIP0+BNB25%)": {
        "fee_upbit_rate":   0.0005,
        "fee_binance_rate": 0.00075,  # VIP0 taker BNB 25% 할인
    },
}

# 임계값 범위: 손익분기(구 0.0043 / 신 0.00465) 기준으로 0.2%~0.7% 범위 스윕
THRESHOLDS = [0.0020, 0.0025, 0.0030, 0.0035, 0.0040, 0.0045, 0.0050, 0.0060, 0.0070]


def _collect(days: int, tag: str) -> str:
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    out = f"{DATA_DIR}/{COIN.lower()}_{days}d_5m_{tag}.csv"
    if Path(out).exists():
        print(f"  [재사용] {out}")
        return out
    print(f"  [다운로드] Upbit {UPBIT_MARKET} + Binance {BINANCE_SYMBOL} {days}일...")
    return collect_last_nd(UPBIT_MARKET, BINANCE_SYMBOL, out, days, minutes=5)


def _run_sweep(csv_path: str, fee_upbit: float, fee_binance: float) -> list[dict]:
    rows = []
    for thr in THRESHOLDS:
        exit_thr = round(thr * 0.3, 6)
        r = run_backtest_from_csv(
            csv_path=csv_path,
            symbol=COIN,
            trade_size_base=3000.0,
            entry_threshold_rate=thr,
            exit_threshold_rate=exit_thr,
            fee_upbit_rate=fee_upbit,
            fee_binance_rate=fee_binance,
            slippage_upbit_rate=SLIPPAGE_UPBIT,
            slippage_binance_rate=SLIPPAGE_BINANCE,
            transfer_fee_upbit_to_binance_base=TRANSFER_FEE_BASE,
            transfer_fee_binance_to_upbit_base=TRANSFER_FEE_BASE,
            initial_upbit_krw=INITIAL_KRW,
            initial_binance_krw=INITIAL_KRW,
            use_full_capital_per_trade=True,
        )
        rows.append({
            "threshold": thr,
            "exit_thr": exit_thr,
            "trades": r.trade_count,
            "pnl_krw": round(r.total_pnl_krw, 0),
            "return_pct": round(r.total_return_rate * 100, 3),
            "win_rate": round(r.win_rate * 100, 1),
            "max_dd_pct": round(r.max_drawdown_rate * 100, 3),
        })
    return rows


def _print_table(scenario_name: str, rows: list[dict], breakeven: float) -> None:
    print(f"\n{'='*70}")
    print(f"  {scenario_name}   (손익분기: {breakeven*100:.3f}%)")
    print(f"{'='*70}")
    print(f"  {'임계값':>7}  {'거래':>5}  {'수익(원)':>10}  {'수익률':>7}  {'승률':>6}  {'MDD':>7}  {'비고'}")
    print(f"  {'-'*65}")
    for r in rows:
        be_flag = " <-- 손익분기 미만" if r["threshold"] < breakeven else ""
        print(
            f"  {r['threshold']*100:>6.3f}%  {r['trades']:>5}  "
            f"{r['pnl_krw']:>+10,.0f}  {r['return_pct']:>+6.3f}%  "
            f"{r['win_rate']:>5.1f}%  {r['max_dd_pct']:>6.3f}%{be_flag}"
        )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=DAYS)
    p.add_argument("--skip-collect", action="store_true", help="기존 CSV 재사용")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    stamp = datetime.now().strftime("%Y%m%d")

    print(f"\n[v1.1 TRX 수수료 비교 백테스트] {args.days}일 / 5분봉")
    print(f"  슬리피지: 업비트 {SLIPPAGE_UPBIT*100:.2f}% / 바이낸스 {SLIPPAGE_BINANCE*100:.2f}%")
    print(f"  시드: 업비트 {INITIAL_KRW:,}원 + 바이낸스 {INITIAL_KRW:,}원 = {INITIAL_KRW*2:,}원\n")

    tag = f"{stamp}_{args.days}d"
    if args.skip_collect:
        csv_path = f"{DATA_DIR}/{COIN.lower()}_{args.days}d_5m_{tag}.csv"
        # 같은 날짜 파일이 없으면 최신 파일 찾기
        if not Path(csv_path).exists():
            candidates = sorted(Path(DATA_DIR).glob(f"{COIN.lower()}_{args.days}d_5m_*.csv"))
            if candidates:
                csv_path = str(candidates[-1])
                print(f"  [재사용] {csv_path}")
            else:
                print("  기존 CSV 없음 — 다운로드 시작")
                csv_path = _collect(args.days, tag)
    else:
        csv_path = _collect(args.days, tag)

    print(f"\n  데이터: {csv_path}")

    results = {}
    for name, fees in FEE_SCENARIOS.items():
        print(f"\n  [{name}] 스윕 실행 중...")
        breakeven = fees["fee_upbit_rate"] + fees["fee_binance_rate"] + SLIPPAGE_UPBIT + SLIPPAGE_BINANCE
        rows = _run_sweep(csv_path, fees["fee_upbit_rate"], fees["fee_binance_rate"])
        results[name] = (rows, breakeven)

    # 결과 출력
    for name, (rows, breakeven) in results.items():
        _print_table(name, rows, breakeven)

    # 요약: 신설정 vs 구설정 수익 차이
    print(f"\n{'='*70}")
    print("  [수익 차이 요약] 신_설정 - 구_설정 (양수 = 신설정이 손실 더 크게 인식)")
    print(f"  {'-'*50}")
    old_rows = results["구_설정 (VIP4 오적용)"][0]
    new_rows = results["신_설정 (VIP0+BNB25%)"][0]
    for o, n in zip(old_rows, new_rows):
        diff_pnl = n["pnl_krw"] - o["pnl_krw"]
        diff_trades = n["trades"] - o["trades"]
        print(
            f"  {o['threshold']*100:.3f}%  "
            f"거래수: {o['trades']} -> {n['trades']} ({diff_trades:+d})  "
            f"수익: {o['pnl_krw']:+,.0f} -> {n['pnl_krw']:+,.0f} ({diff_pnl:+,.0f}원)"
        )
    print()


if __name__ == "__main__":
    main()
