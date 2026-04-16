"""Collect and align Binance BTCUSDT + BTCUSDC candles for v1.2 backtest."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import csv

import requests

from src.backtest.historical_data import _dt_floor_utc


@dataclass(slots=True)
class OHLCVBar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    taker_buy_volume: float = 0.0


def fetch_binance_klines_ohlc(
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    minutes: int = 5,
    interval: str = "",
) -> list[OHLCVBar]:
    """interval 직접 지정 시 우선 사용 (예: '1s', '1m', '5m').
    interval 미지정 시 minutes 파라미터로 '{minutes}m' 생성.
    """
    url = "https://api.binance.com/api/v3/klines"
    resolved_interval = interval if interval else f"{minutes}m"
    # 봉 간격(ms) 계산 — 다음 startTime 계산에 사용
    if resolved_interval == "1s":
        bar_ms = 1_000
    elif resolved_interval.endswith("s"):
        bar_ms = int(resolved_interval[:-1]) * 1_000
    elif resolved_interval.endswith("m"):
        bar_ms = int(resolved_interval[:-1]) * 60_000
    else:
        bar_ms = minutes * 60_000

    out: list[OHLCVBar] = []
    current_ms = int(start_utc.timestamp() * 1000)
    end_ms = int(end_utc.timestamp() * 1000)
    while current_ms < end_ms:
        resp = requests.get(
            url,
            params={
                "symbol": symbol,
                "interval": resolved_interval,
                "startTime": current_ms,
                "endTime": end_ms,
                "limit": 1000,
            },
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            break
        for row in rows:
            ts = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc)
            out.append(
                OHLCVBar(
                    ts=ts,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                    taker_buy_volume=float(row[9]),
                )
            )
        current_ms = int(rows[-1][0]) + bar_ms
    return out


def align_binance_dual_btc_ohlc(
    usdt_bars: list[OHLCVBar],
    usdc_bars: list[OHLCVBar],
) -> list[dict]:
    u = {b.ts: b for b in usdt_bars}
    z = {b.ts: b for b in usdc_bars}
    common = sorted(set(u.keys()) & set(z.keys()))
    rows: list[dict] = []
    for ts in common:
        cu = u[ts]
        cc = z[ts]
        rows.append(
            {
                "ts": ts.isoformat(),
                "btc_usdt_open": cu.open,
                "btc_usdt_high": cu.high,
                "btc_usdt_low": cu.low,
                "btc_usdt_close": cu.close,
                "btc_usdc_open": cc.open,
                "btc_usdc_high": cc.high,
                "btc_usdc_low": cc.low,
                "btc_usdc_close": cc.close,
                "btc_usdt_volume": cu.volume,
                "btc_usdc_volume": cc.volume,
                "btc_usdt_taker_buy_volume": cu.taker_buy_volume,
                "btc_usdc_taker_buy_volume": cc.taker_buy_volume,
            }
        )
    return rows


V12_DUAL_FIELDNAMES = [
    "ts",
    "btc_usdt_open",
    "btc_usdt_high",
    "btc_usdt_low",
    "btc_usdt_close",
    "btc_usdc_open",
    "btc_usdc_high",
    "btc_usdc_low",
    "btc_usdc_close",
    "btc_usdt_volume",
    "btc_usdc_volume",
    "btc_usdt_taker_buy_volume",
    "btc_usdc_taker_buy_volume",
]


def save_v12_dual_csv(rows: list[dict], path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=V12_DUAL_FIELDNAMES)
        w.writeheader()
        w.writerows(rows)


def collect_v12_btc_dual(
    symbol_usdt: str,
    symbol_usdc: str,
    n_days: int,
    out_dir: str,
    tag: str,
    minutes: int = 1,
    interval: str = "",
    coin: str = "",
) -> str:
    """interval 직접 지정 가능 ('1s', '1m', '5m' 등).
    interval 미지정 시 minutes 파라미터 사용 (기존 동작 유지).
    coin: 파일명 접두어 (미지정 시 symbol_usdt에서 자동 추출, 예: SOLUSDT → sol)
    """
    if not interval and minutes not in {1, 5}:
        raise ValueError("minutes must be one of {1, 5}")
    resolved = interval if interval else f"{minutes}m"
    floor_min = 1
    end_utc = _dt_floor_utc(datetime.now(timezone.utc), floor_min)
    start_utc = end_utc - timedelta(days=n_days)
    ut = fetch_binance_klines_ohlc(symbol_usdt, start_utc, end_utc, interval=resolved)
    uc = fetch_binance_klines_ohlc(symbol_usdc, start_utc, end_utc, interval=resolved)
    aligned = align_binance_dual_btc_ohlc(ut, uc)
    coin_tag = coin.lower() if coin else symbol_usdt.replace("USDT", "").lower()
    out_csv = f"{out_dir}/v12_{coin_tag}_{n_days}d_{resolved}_{tag}.csv"
    save_v12_dual_csv(aligned, out_csv)
    return out_csv
