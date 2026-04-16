from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import csv

import requests


@dataclass(slots=True)
class Candle:
    ts: datetime
    close: float
    volume: float = 0.0
    taker_buy_volume: float = 0.0


def _dt_floor_utc(dt: datetime, minutes: int) -> datetime:
    dt = dt.astimezone(timezone.utc).replace(second=0, microsecond=0)
    floored = dt - timedelta(minutes=dt.minute % minutes)
    return floored


def fetch_binance_klines(symbol: str, start_utc: datetime, end_utc: datetime, minutes: int = 5) -> list[Candle]:
    url = "https://api.binance.com/api/v3/klines"
    out: list[Candle] = []
    current_ms = int(start_utc.timestamp() * 1000)
    end_ms = int(end_utc.timestamp() * 1000)
    while current_ms < end_ms:
        resp = requests.get(
            url,
            params={
                "symbol": symbol,
                "interval": f"{minutes}m",
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
                Candle(
                    ts=ts,
                    close=float(row[4]),
                    volume=float(row[5]),
                    taker_buy_volume=float(row[9]),
                )
            )
        current_ms = int(rows[-1][0]) + (minutes * 60 * 1000)
    return out


def fetch_upbit_candles(market: str, start_utc: datetime, end_utc: datetime, minutes: int = 5) -> list[Candle]:
    url = f"https://api.upbit.com/v1/candles/minutes/{minutes}"
    out: list[Candle] = []
    cursor = end_utc
    while cursor > start_utc:
        resp = requests.get(
            url,
            params={"market": market, "to": cursor.strftime("%Y-%m-%dT%H:%M:%S"), "count": 200},
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            break
        for row in rows:
            ts = datetime.fromisoformat(row["candle_date_time_utc"]).replace(tzinfo=timezone.utc)
            if ts < start_utc or ts > end_utc:
                continue
            out.append(
                Candle(
                    ts=ts,
                    close=float(row["trade_price"]),
                    volume=float(row.get("candle_acc_trade_volume", 0.0)),
                )
            )
        min_ts = min(datetime.fromisoformat(r["candle_date_time_utc"]).replace(tzinfo=timezone.utc) for r in rows)
        cursor = min_ts - timedelta(minutes=minutes)
    # upbit returns newest-first; normalize ascending unique timestamps
    dedup = {c.ts: c for c in out}
    return [dedup[k] for k in sorted(dedup.keys())]


def align_candles(upbit: list[Candle], binance: list[Candle], usdtkrw: list[Candle]) -> list[dict]:
    up = {c.ts: c for c in upbit}
    bn = {c.ts: c for c in binance}
    fx = {c.ts: c.close for c in usdtkrw}
    common = sorted(set(up.keys()) & set(bn.keys()) & set(fx.keys()))
    return [
        {
            "ts": ts.isoformat(),
            "upbit_close_krw": up[ts].close,
            "binance_close_usdt": bn[ts].close,
            "usdtkrw_close": fx[ts],
            "upbit_volume": up[ts].volume,
            "binance_volume": bn[ts].volume,
            "binance_taker_buy_volume": bn[ts].taker_buy_volume,
        }
        for ts in common
    ]


def save_aligned_csv(rows: list[dict], path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "ts",
                "upbit_close_krw",
                "binance_close_usdt",
                "usdtkrw_close",
                "upbit_volume",
                "binance_volume",
                "binance_taker_buy_volume",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def collect_last_nd(upbit_market: str, binance_symbol: str, out_csv: str, days: int, minutes: int = 5) -> str:
    if minutes not in {1, 5}:
        raise ValueError("minutes must be one of {1, 5}")
    end_utc = _dt_floor_utc(datetime.now(timezone.utc), minutes)
    start_utc = end_utc - timedelta(days=days)
    upbit_rows = fetch_upbit_candles(upbit_market, start_utc, end_utc, minutes=minutes)
    binance_rows = fetch_binance_klines(binance_symbol, start_utc, end_utc, minutes=minutes)
    usdtkrw_rows = fetch_upbit_candles("KRW-USDT", start_utc, end_utc, minutes=minutes)
    aligned = align_candles(upbit_rows, binance_rows, usdtkrw_rows)
    save_aligned_csv(aligned, out_csv)
    return out_csv


def collect_last_nd_with_tag(
    symbol: str,
    upbit_market: str,
    binance_symbol: str,
    n_days: int,
    out_dir: str,
    tag: str,
    minutes: int = 5,
) -> str:
    out_csv = f"{out_dir}/{symbol.lower()}_{n_days}d_{minutes}m_{tag}.csv"
    return collect_last_nd(upbit_market, binance_symbol, out_csv, n_days, minutes=minutes)


def collect_last_nd_5m(upbit_market: str, binance_symbol: str, out_csv: str, days: int) -> str:
    return collect_last_nd(upbit_market, binance_symbol, out_csv, days, minutes=5)


def collect_last_30d_5m(upbit_market: str, binance_symbol: str, out_csv: str) -> str:
    return collect_last_nd_5m(upbit_market, binance_symbol, out_csv, days=30)

