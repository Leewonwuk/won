"""v1.1 장기 백테스트: TRX / SOL / XRP / DOGE (1분봉 1년치)

실행:
  python -m scripts.backtest_v11_longterm
  python -m scripts.backtest_v11_longterm --days 365
  python -m scripts.backtest_v11_longterm --skip-collect   # 캐시 데이터 재사용
  python -m scripts.backtest_v11_longterm --days 365 --no-backtest  # 데이터만 수집
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# UTF-8 강제 (Windows cp949 터미널)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from src.backtest.backtest_runner import run_backtest_from_csv

# ------------------------------------------------------------------
# 설정
# ------------------------------------------------------------------
DAYS = 365
DATA_DIR = "data/v11_longterm"
MINUTES = 1

COINS = [
    {
        "symbol": "TRX", "upbit": "KRW-TRX", "binance": "TRXUSDT",
        # TRX: 483원, 1원 틱 = 0.21% bid-ask → 슬리피지 ~0.21%, 보수적 0.32%
        "slippage_upbit": 0.0032, "slippage_binance": 0.0002,
        "transfer_utob": 1.0,   # 업비트 TRX 출금
        "transfer_btou": 1.5,   # 바이낸스 TRX 출금 (실측)
    },
    {
        "symbol": "SOL", "upbit": "KRW-SOL", "binance": "SOLUSDT",
        # SOL: 50원 틱, bid-ask 0.08% → 슬리피지 ~0.04%
        "slippage_upbit": 0.0004, "slippage_binance": 0.0002,
        "transfer_utob": 0.01,  # 업비트 SOL 출금
        "transfer_btou": 0.001, # 바이낸스 SOL 출금 (실측)
    },
    {
        "symbol": "XRP", "upbit": "KRW-XRP", "binance": "XRPUSDT",
        # XRP: 2024원, 1원 틱 = 0.05% bid-ask → 슬리피지 ~0.025%
        "slippage_upbit": 0.0003, "slippage_binance": 0.0002,
        "transfer_utob": 0.25,  # 업비트 XRP 출금
        "transfer_btou": 0.20,  # 바이낸스 XRP 출금 (실측)
    },
    {
        "symbol": "DOGE", "upbit": "KRW-DOGE", "binance": "DOGEUSDT",
        # DOGE: 138원, 1원 틱 = 0.72% bid-ask → 슬리피지 ~0.36~0.40%
        "slippage_upbit": 0.0040, "slippage_binance": 0.0002,
        "transfer_utob": 5.0,   # 업비트 DOGE 출금
        "transfer_btou": 4.0,   # 바이낸스 DOGE 출금 (실측)
    },
]

INITIAL_KRW = 800_000     # 코인당 4슬롯 × 20만 원

FEE_SCENARIOS = {
    "구_설정(VIP4오적용)": {"fee_upbit": 0.0005, "fee_binance": 0.0004},
    "신_설정(VIP0+BNB25%)": {"fee_upbit": 0.0005, "fee_binance": 0.00075},
}

THRESHOLDS = [0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.010, 0.012, 0.015, 0.020]


# ------------------------------------------------------------------
# 데이터 수집
# ------------------------------------------------------------------

def _fetch_upbit_1m(market: str, start: datetime, end: datetime) -> list[dict]:
    url = "https://api.upbit.com/v1/candles/minutes/1"
    out: dict[str, float] = {}
    cursor = end
    req_count = 0
    while cursor > start:
        resp = requests.get(url,
            params={"market": market, "to": cursor.strftime("%Y-%m-%dT%H:%M:%S"), "count": 200},
            timeout=15)
        if resp.status_code == 429:
            time.sleep(1.0)
            continue
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            break
        for r in rows:
            ts = datetime.fromisoformat(r["candle_date_time_utc"]).replace(tzinfo=timezone.utc)
            if start <= ts <= end:
                out[ts.isoformat()] = float(r["trade_price"])
        min_ts = min(
            datetime.fromisoformat(r["candle_date_time_utc"]).replace(tzinfo=timezone.utc)
            for r in rows
        )
        cursor = min_ts - timedelta(minutes=1)
        req_count += 1
        # rate limit: 초당 ~8회 안전하게
        time.sleep(0.13)
    return [{"ts": ts, "price": p} for ts, p in sorted(out.items())]


def _fetch_binance_1m(symbol: str, start: datetime, end: datetime) -> list[dict]:
    url = "https://api.binance.com/api/v3/klines"
    out: dict[str, float] = {}
    current_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    while current_ms < end_ms:
        resp = requests.get(url,
            params={
                "symbol": symbol, "interval": "1m",
                "startTime": current_ms, "endTime": end_ms,
                "limit": 1000,
            }, timeout=15)
        if resp.status_code == 429:
            time.sleep(2.0)
            continue
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            break
        for r in rows:
            ts = datetime.fromtimestamp(int(r[0]) / 1000, tz=timezone.utc).isoformat()
            out[ts] = float(r[4])  # close
        current_ms = int(rows[-1][0]) + 60_000
    return [{"ts": ts, "price": p} for ts, p in sorted(out.items())]


def collect_coin(coin: dict, days: int, data_dir: str) -> str:
    sym = coin["symbol"]
    out_path = f"{data_dir}/{sym.lower()}_{days}d_1m.csv"
    if Path(out_path).exists():
        size = Path(out_path).stat().st_size
        if size > 10_000:
            print(f"  [{sym}] 캐시 재사용: {out_path} ({size//1024}KB)")
            return out_path

    print(f"  [{sym}] 다운로드 시작 (Upbit {coin['upbit']} + Binance {coin['binance']})...", flush=True)
    end = datetime.now(tz=timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(days=days)

    # Binance (빠름, 먼저)
    print(f"  [{sym}]   Binance {coin['binance']} ...", flush=True)
    bn_data = _fetch_binance_1m(coin["binance"], start, end)
    bn = {r["ts"]: r["price"] for r in bn_data}

    # Upbit FX (KRW-USDT)
    print(f"  [{sym}]   Upbit KRW-USDT (FX) ...", flush=True)
    fx_data = _fetch_upbit_1m("KRW-USDT", start, end)
    fx = {r["ts"]: r["price"] for r in fx_data}

    # Upbit 코인
    print(f"  [{sym}]   Upbit {coin['upbit']} ...", flush=True)
    up_data = _fetch_upbit_1m(coin["upbit"], start, end)
    up = {r["ts"]: r["price"] for r in up_data}

    # 3-way alignment
    common = sorted(set(up.keys()) & set(bn.keys()) & set(fx.keys()))
    print(f"  [{sym}]   정렬 완료: {len(common):,}개 봉 (전체의 {len(common)/max(len(up),1)*100:.1f}%)")

    Path(data_dir).mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["ts","upbit_close_krw","binance_close_usdt","usdtkrw_close"])
        writer.writeheader()
        for ts in common:
            writer.writerow({
                "ts": ts,
                "upbit_close_krw": up[ts],
                "binance_close_usdt": bn[ts],
                "usdtkrw_close": fx[ts],
            })
    print(f"  [{sym}] 저장 완료: {out_path}")
    return out_path


# ------------------------------------------------------------------
# 프리미엄 분포 분석
# ------------------------------------------------------------------

def analyze_premium(csv_path: str, symbol: str) -> dict:
    premiums = []
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            up = float(r["upbit_close_krw"])
            bn_u = float(r["binance_close_usdt"])
            fx = float(r["usdtkrw_close"])
            bn_krw = bn_u * fx
            if bn_krw > 0:
                premiums.append((up - bn_krw) / bn_krw)

    if not premiums:
        return {}

    premiums.sort(reverse=True)
    n = len(premiums)
    above = lambda thr: sum(1 for p in premiums if p >= thr)

    return {
        "symbol": symbol,
        "bars": n,
        "max_pct": round(max(premiums) * 100, 3),
        "min_pct": round(min(premiums) * 100, 3),
        "mean_pct": round(sum(premiums) / n * 100, 3),
        "above_0.3%": above(0.003),
        "above_0.5%": above(0.005),
        "above_1.0%": above(0.010),
        "above_2.0%": above(0.020),
        "above_3.0%": above(0.030),
        "top1_pct": round(premiums[0] * 100, 3),
        "top10_pct": round(premiums[9] * 100, 3) if n >= 10 else None,
        "p95_pct": round(premiums[int(n * 0.05)] * 100, 3),  # 상위 5%
        "p99_pct": round(premiums[int(n * 0.01)] * 100, 3),  # 상위 1%
    }


# ------------------------------------------------------------------
# 백테스트
# ------------------------------------------------------------------

def run_sweep(csv_path: str, coin: dict, fee_upbit: float, fee_binance: float) -> list[dict]:
    symbol = coin["symbol"]
    rows = []
    for thr in THRESHOLDS:
        r = run_backtest_from_csv(
            csv_path=csv_path,
            symbol=symbol,
            trade_size_base=3000.0,
            entry_threshold_rate=thr,
            exit_threshold_rate=round(thr * 0.3, 6),
            fee_upbit_rate=fee_upbit,
            fee_binance_rate=fee_binance,
            slippage_upbit_rate=coin["slippage_upbit"],
            slippage_binance_rate=coin["slippage_binance"],
            transfer_fee_upbit_to_binance_base=coin["transfer_utob"],
            transfer_fee_binance_to_upbit_base=coin["transfer_btou"],
            initial_upbit_krw=INITIAL_KRW,
            initial_binance_krw=INITIAL_KRW,
            use_full_capital_per_trade=True,
        )
        rows.append({
            "thr": thr,
            "trades": r.trade_count,
            "pnl": round(r.total_pnl_krw, 0),
            "ret_pct": round(r.total_return_rate * 100, 3),
            "win_pct": round(r.win_rate * 100, 1),
            "mdd_pct": round(r.max_drawdown_rate * 100, 3),
        })
    return rows


# ------------------------------------------------------------------
# 출력
# ------------------------------------------------------------------

def print_distribution(stats_list: list[dict]) -> None:
    print("\n" + "=" * 72)
    print("  김치프리미엄 분포 (1년, 1분봉)")
    print("=" * 72)
    print(f"  {'코인':>5}  {'봉수':>8}  {'최대':>7}  {'평균':>7}  {'상위1%':>7}  {'상위5%':>7}")
    print(f"  {'-'*62}")
    for s in stats_list:
        print(f"  {s['symbol']:>5}  {s['bars']:>8,}  "
              f"{s['max_pct']:>6.3f}%  {s['mean_pct']:>6.3f}%  "
              f"{s['p99_pct']:>6.3f}%  {s['p95_pct']:>6.3f}%")

    print()
    print(f"  {'코인':>5}  {'>=0.3%':>8}  {'>=0.5%':>8}  {'>=1.0%':>8}  {'>=2.0%':>8}  {'>=3.0%':>8}")
    print(f"  {'-'*56}")
    for s in stats_list:
        bars = s["bars"]
        def pct(n): return f"{n:,}({n/bars*100:.1f}%)" if bars else "-"
        print(f"  {s['symbol']:>5}  {pct(s['above_0.3%']):>15}  "
              f"{pct(s['above_0.5%']):>15}  {pct(s['above_1.0%']):>15}")


def print_sweep(coin: dict, rows_by_scenario: dict[str, list[dict]]) -> None:
    symbol = coin["symbol"]
    be_new = 0.0005 + 0.00075 + coin["slippage_upbit"] + coin["slippage_binance"]
    be_old = 0.0005 + 0.0004  + coin["slippage_upbit"] + coin["slippage_binance"]

    print(f"\n{'='*72}")
    print(f"  {symbol} 임계값 스윕")
    print(f"  손익분기: 구={be_old*100:.3f}%  신={be_new*100:.3f}%")
    print(f"{'='*72}")
    for scenario, rows in rows_by_scenario.items():
        print(f"\n  [{scenario}]")
        print(f"  {'임계값':>7}  {'거래':>5}  {'수익(원)':>10}  {'수익률':>7}  {'승률':>6}  {'MDD':>7}")
        print(f"  {'-'*56}")
        be = be_old if "구" in scenario else be_new
        for r in rows:
            flag = " *" if r["thr"] >= be and r["trades"] > 0 else ""
            print(f"  {r['thr']*100:>6.2f}%  {r['trades']:>5}  "
                  f"{r['pnl']:>+10,.0f}  {r['ret_pct']:>+6.3f}%  "
                  f"{r['win_pct']:>5.1f}%  {r['mdd_pct']:>6.3f}%{flag}")


# ------------------------------------------------------------------
# main
# ------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=DAYS)
    p.add_argument("--skip-collect", action="store_true")
    p.add_argument("--no-backtest", action="store_true", help="데이터 수집+분포만, 백테스트 생략")
    p.add_argument("--coins", default="TRX,SOL,XRP,DOGE", help="쉼표 구분 코인 목록")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    target_syms = {s.upper() for s in args.coins.split(",")}
    coins = [c for c in COINS if c["symbol"] in target_syms]

    print(f"\n[v1.1 장기 백테스트] {args.days}일 / 1분봉 / {[c['symbol'] for c in coins]}")
    print(f"  슬리피지: 코인별 개별 설정 (DOGE 0.40% / XRP 0.03% / TRX 0.32%)")
    print(f"  시드: {INITIAL_KRW*2:,}원/코인\n")

    # 데이터 수집 (순차 — Upbit rate limit)
    csv_paths: dict[str, str] = {}
    for coin in coins:
        sym = coin["symbol"]
        if args.skip_collect:
            p = f"{DATA_DIR}/{sym.lower()}_{args.days}d_1m.csv"
            if not Path(p).exists():
                candidates = sorted(Path(DATA_DIR).glob(f"{sym.lower()}_*_1m.csv"))
                p = str(candidates[-1]) if candidates else ""
            if p and Path(p).exists():
                print(f"  [{sym}] 캐시: {p}")
                csv_paths[sym] = p
            else:
                print(f"  [{sym}] 캐시 없음 -> 다운로드")
                csv_paths[sym] = collect_coin(coin, args.days, DATA_DIR)
        else:
            csv_paths[sym] = collect_coin(coin, args.days, DATA_DIR)

    # 프리미엄 분포 분석
    print("\n[프리미엄 분포 분석 중...]")
    stats_list = []
    for coin in coins:
        sym = coin["symbol"]
        if csv_paths.get(sym):
            s = analyze_premium(csv_paths[sym], sym)
            if s:
                stats_list.append(s)

    print_distribution(stats_list)

    if args.no_backtest:
        return

    # 백테스트 스윕
    print("\n[백테스트 스윕 실행 중...]")
    for coin in coins:
        sym = coin["symbol"]
        if not csv_paths.get(sym):
            continue
        print(f"  {sym} ...", flush=True)
        results_by_scenario: dict[str, list[dict]] = {}
        for scenario, fees in FEE_SCENARIOS.items():
            results_by_scenario[scenario] = run_sweep(
                csv_paths[sym], coin,
                fees["fee_upbit"], fees["fee_binance"],
            )
        print_sweep(coin, results_by_scenario)

    print("\n완료.\n")


if __name__ == "__main__":
    main()
