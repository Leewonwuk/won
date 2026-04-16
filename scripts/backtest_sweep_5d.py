#!/usr/bin/env python3
"""
1초봉 5일치 멀티코인 임계값 스윕 백테스트.

사용법:
  python scripts/backtest_sweep_5d.py
  python scripts/backtest_sweep_5d.py --skip-collect        # 기존 CSV 재사용
  python scripts/backtest_sweep_5d.py --coins trx xrp doge  # 특정 코인만
  python scripts/backtest_sweep_5d.py --scenario A          # 수수료 시나리오 A만

수수료 시나리오:
  A = 현재설정 (fee=0.03%, maker=0.015%)
  B = BNB할인 표준 (fee=0.075%, maker=0.075%)
  C = 추정 실제 (fee=0.04%, maker=0.02%)  ← check_fee_rate.py 분석 기반

임계값 스윕:
  0.04%, 0.05%, 0.06%, 0.07%, 0.08%, 0.10%, 0.12%, 0.15%, 0.18%, 0.20%

주의:
  - 1초봉 5일 데이터 = 코인당 ~86400행 × 2페어 × 432 API 요청
  - 첫 실행 시 수집에 코인당 3~5분 소요 (6코인 = 약 20~30분)
  - 이후 --skip-collect 로 재사용 가능
"""
from __future__ import annotations

import argparse
import copy
import glob
import concurrent.futures
import io
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Windows cp949 터미널에서 유니코드 출력 강제 UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.v12.backtest_v2 import run_backtest_v2
from src.v12.config_v2 import load_v12_config_v2, V12ConfigV2
from src.v12.historical_data import collect_v12_btc_dual

# ─── 설정 ────────────────────────────────────────────────────────────────────

DAYS = 5
INTERVAL = "1s"
LAG_BARS = 1   # 1초봉 sequential 모드 (거래 중 새 진입 차단)

ALL_COINS = ["trx", "doge", "xrp", "sol", "bnb", "ada"]

CONFIG_MAP = {
    "trx":  "configs/v12/v12_trx_v2.yaml",
    "doge": "configs/v12/v12_doge_v2.yaml",
    "xrp":  "configs/v12/v12_xrp_v2.yaml",
    "sol":  "configs/v12/v12_sol_v2.yaml",
    "bnb":  "configs/v12/v12_bnb_v2.yaml",
    "ada":  "configs/v12/v12_ada_v2.yaml",
}

# 임계값 스윕 (DT = DC 동일 적용)
THRESHOLDS = [0.0004, 0.0005, 0.0006, 0.0007, 0.0008, 0.0010, 0.0012, 0.0015, 0.0018, 0.0020]

# 수수료 시나리오
#   fee_rate: Leg A IOC taker 수수료
#   fee_maker_rate: Leg B GTC maker 수수료
#   emergency_taker_fee_rate: 비상청산 시장가 수수료
# NOTE: 백테스트 내부 fee_stack = 2 × fee_maker_rate (allocator_v2.py)
#        라이브 fee_stack = fee_rate + fee_maker_rate
#        → 두 값을 동일하게 설정하면 일관됨
FEE_SCENARIOS: dict[str, dict] = {
    "A_현재설정": {
        "label": "A 현재설정 (taker=0.030% maker=0.015%)",
        "fee_rate": 0.0003,
        "fee_maker_rate": 0.00015,
        "emergency_taker_fee_rate": 0.0003,
        "emergency_slippage_rate": 0.0002,
    },
    "B_BNB할인": {
        "label": "B BNB할인 표준 (taker=0.075% maker=0.075%)",
        "fee_rate": 0.00075,
        "fee_maker_rate": 0.00075,
        "emergency_taker_fee_rate": 0.00075,
        "emergency_slippage_rate": 0.0002,
    },
    "C_추정실제": {
        "label": "C 추정실제 (taker=0.040% maker=0.020%) ← check_fee_rate 분석값",
        "fee_rate": 0.0004,
        "fee_maker_rate": 0.0002,
        "emergency_taker_fee_rate": 0.0004,
        "emergency_slippage_rate": 0.0002,
    },
}

# ─── 데이터 수집 ─────────────────────────────────────────────────────────────

def get_or_collect_csv(coin: str, cfg: V12ConfigV2, skip_collect: bool) -> str:
    """기존 1s CSV 재사용 또는 신규 수집."""
    pattern = f"data/backtest/v12_{coin}_{DAYS}d_{INTERVAL}_*.csv"
    existing = sorted(glob.glob(pattern))
    if skip_collect and existing:
        path = existing[-1]
        print(f"  [{coin.upper()}] 기존 CSV 재사용: {path}")
        return path
    if existing:
        # 24시간 이내 파일이면 재사용
        mtime = Path(existing[-1]).stat().st_mtime
        age_hours = (time.time() - mtime) / 3600
        if age_hours < 24:
            path = existing[-1]
            print(f"  [{coin.upper()}] 최근 CSV 재사용 ({age_hours:.1f}h 전): {path}")
            return path

    tag = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    print(f"  [{coin.upper()}] 1초봉 {DAYS}일치 수집 중 (약 3~5분)...", flush=True)
    t0 = time.time()
    path = collect_v12_btc_dual(
        symbol_usdt=cfg.binance_symbol_usdt,
        symbol_usdc=cfg.binance_symbol_usdc,
        n_days=DAYS,
        out_dir="data/backtest",
        tag=tag,
        interval=INTERVAL,
        coin=coin,
    )
    elapsed = time.time() - t0
    rows = sum(1 for _ in open(path)) - 1
    print(f"  [{coin.upper()}] 수집 완료: {rows:,}행, {elapsed:.0f}초 → {path}")
    return path


# ─── 백테스트 실행 ────────────────────────────────────────────────────────────

def run_sweep(coin: str, csv_path: str, base_cfg: V12ConfigV2, scenario_key: str) -> list[dict]:
    """단일 코인 × 단일 수수료 시나리오 → 임계값별 결과 리스트."""
    fee = FEE_SCENARIOS[scenario_key]
    results = []
    for thr in THRESHOLDS:
        cfg = copy.copy(base_cfg)
        # 수수료 덮어쓰기
        cfg.fee_rate = fee["fee_rate"]
        cfg.fee_maker_rate = fee["fee_maker_rate"]
        cfg.emergency_taker_fee_rate = fee["emergency_taker_fee_rate"]
        cfg.emergency_slippage_rate = fee["emergency_slippage_rate"]
        # 임계값 덮어쓰기
        cfg.dt_entry_threshold_rate = thr
        cfg.dc_entry_threshold_rate = thr
        # 1초봉 sequential 모드
        cfg.leg_b_lag_bars = LAG_BARS

        r = run_backtest_v2(csv_path=csv_path, cfg=cfg)

        # 수수료 스택 (백테스트 내부 기준: 2 × maker)
        bt_fee_stack = 2.0 * cfg.fee_maker_rate
        # 라이브 기준: taker + maker
        live_fee_stack = cfg.fee_rate + cfg.fee_maker_rate

        total_trades = r.trade_count
        em_rate = r.emergency_close_count / total_trades if total_trades > 0 else 0.0

        results.append({
            "threshold": thr,
            "trades": total_trades,
            "pnl": r.total_pnl_usd,
            "fee_total": r.total_fee_usd,
            "win_rate": r.win_rate,
            "emergency": r.emergency_close_count,
            "em_rate": em_rate,
            "unfilled": r.unfilled_timeout_count,
            "mdd": r.max_drawdown_rate,
            "bt_fee_stack": bt_fee_stack,
            "live_fee_stack": live_fee_stack,
            "rows": r.rows_processed,
        })
    return results


# ─── 출력 ────────────────────────────────────────────────────────────────────

def print_coin_table(coin: str, scenario_label: str, results: list[dict]) -> None:
    equity_label = f"초기자본"
    print(f"\n{'─'*80}")
    print(f"  {coin.upper()}  |  {scenario_label}")
    print(f"{'─'*80}")
    print(f"  {'임계값':>8}  {'거래수':>6}  {'순수익':>9}  {'수수료':>8}  "
          f"{'승률':>6}  {'비상청산':>8}  {'EM율':>5}  {'미체결':>6}  {'MDD':>6}")
    print(f"  {'':─>8}  {'':─>6}  {'':─>9}  {'':─>8}  "
          f"{'':─>6}  {'':─>8}  {'':─>5}  {'':─>6}  {'':─>6}")
    for r in results:
        marker = ""
        # 수익성 마커
        if r["pnl"] > 0 and r["trades"] >= 5:
            marker = " ✓"
        elif r["pnl"] < 0:
            marker = " ✗"
        print(
            f"  {r['threshold']*100:>7.3f}%"
            f"  {r['trades']:>6,}"
            f"  {r['pnl']:>+9.3f}$"
            f"  {r['fee_total']:>8.3f}$"
            f"  {r['win_rate']:>6.1%}"
            f"  {r['emergency']:>8,}"
            f"  {r['em_rate']:>5.1%}"
            f"  {r['unfilled']:>6,}"
            f"  {r['mdd']:>6.2%}"
            f"{marker}"
        )
    # 백테스트 vs 라이브 fee_stack 경고
    if results:
        r0 = results[0]
        if abs(r0["bt_fee_stack"] - r0["live_fee_stack"]) > 1e-6:
            print(f"\n  ⚠ fee_stack 불일치:"
                  f" 백테스트={r0['bt_fee_stack']*100:.4f}%"
                  f" / 라이브={r0['live_fee_stack']*100:.4f}%"
                  f" (백테스트가 더 낙관적)")


def print_summary_table(all_results: dict) -> None:
    """시나리오 × 코인 × 임계값 최적값 요약."""
    print(f"\n{'═'*80}")
    print("  ★ 코인별 최적 임계값 요약 (순수익 최대 기준, 거래 5회 이상)")
    print(f"{'═'*80}")
    print(f"  {'시나리오':<20}  {'코인':>5}  {'최적임계값':>10}  "
          f"{'순수익':>9}  {'거래수':>6}  {'EM율':>5}")
    print(f"  {'':─<20}  {'':─>5}  {'':─>10}  {'':─>9}  {'':─>6}  {'':─>5}")

    for scenario_key, coin_data in all_results.items():
        label = FEE_SCENARIOS[scenario_key]["label"]
        for coin, results in coin_data.items():
            profitable = [r for r in results if r["trades"] >= 5]
            if not profitable:
                print(f"  {label[:20]:<20}  {coin.upper():>5}  {'거래 없음':>10}")
                continue
            best = max(profitable, key=lambda r: r["pnl"])
            print(
                f"  {label[:20]:<20}"
                f"  {coin.upper():>5}"
                f"  {best['threshold']*100:>9.3f}%"
                f"  {best['pnl']:>+9.3f}$"
                f"  {best['trades']:>6,}"
                f"  {best['em_rate']:>5.1%}"
            )


# ─── 메인 ────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="1초봉 5일치 멀티코인 임계값 스윕 백테스트")
    p.add_argument("--coins", nargs="+", default=ALL_COINS, choices=ALL_COINS,
                   metavar="COIN", help=f"대상 코인 (기본: {' '.join(ALL_COINS)})")
    p.add_argument("--scenario", nargs="+", default=list(FEE_SCENARIOS.keys()),
                   choices=list(FEE_SCENARIOS.keys()),
                   help="수수료 시나리오 (기본: 전체)")
    p.add_argument("--skip-collect", action="store_true",
                   help="기존 CSV 재사용 (수집 생략)")
    p.add_argument("--thresholds", nargs="+", type=float, default=None,
                   metavar="RATE",
                   help="임계값 직접 지정 (예: 0.0006 0.0010 0.0015)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    coins: list[str] = args.coins
    scenarios: list[str] = args.scenario
    if args.thresholds:
        global THRESHOLDS
        THRESHOLDS = sorted(args.thresholds)

    print(f"{'═'*80}")
    print(f"  v1.28 임계값 스윕 백테스트  |  {DAYS}일  {INTERVAL}봉  lag={LAG_BARS}s")
    print(f"  코인: {', '.join(c.upper() for c in coins)}")
    print(f"  시나리오: {', '.join(scenarios)}")
    print(f"  임계값: {[f'{t*100:.2f}%' for t in THRESHOLDS]}")
    print(f"{'═'*80}\n")

    # ── Step 1: 데이터 수집 (병렬) ──────────────────────────────────────────
    print("[ Step 1 ] 데이터 수집 (최대 3코인 병렬)")
    cfg_map: dict[str, V12ConfigV2] = {
        coin: load_v12_config_v2(CONFIG_MAP[coin]) for coin in coins
    }

    def _collect(coin: str) -> tuple[str, str]:
        return coin, get_or_collect_csv(coin, cfg_map[coin], args.skip_collect)

    csv_map: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_collect, coin): coin for coin in coins}
        for fut in concurrent.futures.as_completed(futures):
            coin, path = fut.result()
            csv_map[coin] = path

    # ── Step 2: 백테스트 스윕 ───────────────────────────────────────────────
    print(f"\n[ Step 2 ] 백테스트 스윕 ({len(coins)} 코인 × {len(scenarios)} 시나리오 × {len(THRESHOLDS)} 임계값)")
    all_results: dict[str, dict[str, list[dict]]] = {}

    for scenario_key in scenarios:
        all_results[scenario_key] = {}
        label = FEE_SCENARIOS[scenario_key]["label"]
        print(f"\n  ▶ 시나리오 {label}")
        for coin in coins:
            t0 = time.time()
            results = run_sweep(coin, csv_map[coin], cfg_map[coin], scenario_key)
            elapsed = time.time() - t0
            all_results[scenario_key][coin] = results
            print(f"    [{coin.upper()}] {len(THRESHOLDS)}개 임계값 완료 ({elapsed:.1f}초)")
            print_coin_table(coin, label, results)

    # ── Step 3: 요약 ────────────────────────────────────────────────────────
    print_summary_table(all_results)
    print(f"\n{'═'*80}")
    print("  완료. 임계값 선택 기준:")
    print("  1. 순수익(+) 유지 구간에서 가장 낮은 임계값 = 기회 최대 포착")
    print("  2. EM율 < 5% 유지 필요 (비상청산 과다 시 threshold 높여야)")
    print("  3. 시나리오 A(현재설정)가 수익이어도 B(BNB실제)도 확인 필수")
    print(f"{'═'*80}\n")


if __name__ == "__main__":
    main()
