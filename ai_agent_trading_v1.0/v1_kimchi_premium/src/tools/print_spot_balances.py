"""Print Upbit + Binance spot balances (read-only). Uses .env like the rest of the project.

Usage:
    python -m src.tools.print_spot_balances
    python -m src.tools.print_spot_balances --all-upbit
"""
from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv

from src.exchanges.binance_trading_client import BinanceTradingClient
from src.exchanges.upbit_trading_client import UpbitTradingClient


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Spot balances (Upbit + Binance), no orders")
    p.add_argument(
        "--all-upbit",
        action="store_true",
        help="List every Upbit currency with balance > 0 (default: --watch + any asset with balance > 0)",
    )
    p.add_argument(
        "--watch",
        default="TRX,SOL",
        help="Comma-separated symbols to always show on Binance + Upbit (default: TRX,SOL)",
    )
    return p.parse_args()


def _required_env(key: str) -> str:
    v = os.getenv(key, "").strip()
    if not v:
        raise SystemExit(f"missing env: {key} (load .env in project root or export it)")
    return v


def main() -> None:
    args = parse_args()
    load_dotenv()

    watch = {x.strip().upper() for x in args.watch.split(",") if x.strip()}
    watch.add("KRW")

    up = UpbitTradingClient(
        access_key=_required_env("UPBIT_ACCESS_KEY"),
        secret_key=_required_env("UPBIT_SECRET_KEY"),
        timeout_sec=10.0,
    )
    bn = BinanceTradingClient(
        api_key=_required_env("BINANCE_API_KEY"),
        api_secret=_required_env("BINANCE_API_SECRET"),
        timeout_sec=10.0,
    )

    by_cur = {str(a.get("currency", "")).upper(): float(a.get("balance", 0) or 0) for a in up.get_accounts()}
    print("\n=== Upbit (accounts) ===")
    if args.all_upbit:
        for cur in sorted(by_cur.keys()):
            bal = by_cur[cur]
            if bal > 0:
                print(f"  {cur:6s}  balance={bal}")
    else:
        show = set(watch)
        for cur, bal in by_cur.items():
            if bal > 0:
                show.add(cur)
        for cur in sorted(show):
            print(f"  {cur:6s}  balance={by_cur.get(cur, 0.0)}")

    acc = bn.get_account()
    bals = acc.get("balances", [])
    print("\n=== Binance (free / locked) ===")
    bn_by = {str(b.get("asset", "")).upper(): b for b in bals}
    show_bn = (set(watch) | {"USDT"}) - {"KRW"}
    for asset, bal in [(k, bn_by[k]) for k in bn_by]:
        free = float(bal.get("free", 0) or 0)
        locked = float(bal.get("locked", 0) or 0)
        if free > 1e-10 or locked > 1e-10:
            show_bn.add(asset)
    for asset in sorted(show_bn):
        bal = bn_by.get(asset, {})
        free = float(bal.get("free", 0) or 0)
        locked = float(bal.get("locked", 0) or 0)
        print(f"  {asset:6s}  free={free}  locked={locked}")

    print()


if __name__ == "__main__":
    main()
