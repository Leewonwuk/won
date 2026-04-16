from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.exchanges.binance_trading_client import BinanceTradingClient
from src.exchanges.upbit_trading_client import UpbitTradingClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tiny transfer smoke test (Upbit <-> Binance)."
    )
    parser.add_argument(
        "--direction",
        choices=["upbit_to_binance", "binance_to_upbit", "both"],
        default="both",
        help="Transfer direction to test.",
    )
    parser.add_argument("--amount", type=float, default=10.0, help="Transfer amount in TRX.")
    parser.add_argument("--network", default="TRX", help="Network code (default: TRX).")
    parser.add_argument("--upbit-to-binance-address", default="", help="Binance deposit address.")
    parser.add_argument(
        "--upbit-to-binance-secondary-address",
        default="",
        help="Secondary address/tag when required by destination.",
    )
    parser.add_argument("--binance-to-upbit-address", default="", help="Upbit deposit address.")
    parser.add_argument(
        "--binance-to-upbit-address-tag",
        default="",
        help="Address tag/memo when required by destination.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually submit withdrawal requests. Default is dry-run.",
    )
    return parser.parse_args()


def _required_env(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise RuntimeError(f"missing required env: {key}")
    return value


def _append_log(row: dict) -> None:
    out = Path("logs/transfer_smoke_test.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    row["ts"] = datetime.now(tz=timezone.utc).isoformat()
    with out.open("a", encoding="utf-8") as f:
        import json

        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    args = parse_args()
    load_dotenv()
    dry_run = not args.execute

    upbit = UpbitTradingClient(
        access_key=_required_env("UPBIT_ACCESS_KEY"),
        secret_key=_required_env("UPBIT_SECRET_KEY"),
        timeout_sec=5.0,
    )
    binance = BinanceTradingClient(
        api_key=_required_env("BINANCE_API_KEY"),
        api_secret=_required_env("BINANCE_API_SECRET"),
        timeout_sec=5.0,
    )

    directions: list[str]
    if args.direction == "both":
        directions = ["upbit_to_binance", "binance_to_upbit"]
    else:
        directions = [args.direction]

    for direction in directions:
        if direction == "upbit_to_binance":
            if not args.upbit_to_binance_address:
                raise RuntimeError("--upbit-to-binance-address is required")
            payload = {
                "direction": direction,
                "currency": "TRX",
                "amount": args.amount,
                "address": args.upbit_to_binance_address,
                "secondary_address": args.upbit_to_binance_secondary_address or None,
                "net_type": args.network,
                "dry_run": dry_run,
            }
            if dry_run:
                print(f"[DRY-RUN] {payload}")
                _append_log({"event_type": "transfer_dry_run", **payload})
            else:
                result = upbit.withdraw_coin(
                    currency="TRX",
                    amount=args.amount,
                    address=args.upbit_to_binance_address,
                    secondary_address=args.upbit_to_binance_secondary_address or None,
                    net_type=args.network,
                )
                print(f"[EXECUTED] upbit_to_binance withdrawal submitted")
                _append_log(
                    {
                        "event_type": "transfer_executed",
                        "direction": direction,
                        "currency": "TRX",
                        "amount": args.amount,
                        "result": result,
                    }
                )

        if direction == "binance_to_upbit":
            if not args.binance_to_upbit_address:
                raise RuntimeError("--binance-to-upbit-address is required")
            payload = {
                "direction": direction,
                "coin": "TRX",
                "amount": args.amount,
                "address": args.binance_to_upbit_address,
                "address_tag": args.binance_to_upbit_address_tag or None,
                "network": args.network,
                "dry_run": dry_run,
            }
            if dry_run:
                print(f"[DRY-RUN] {payload}")
                _append_log({"event_type": "transfer_dry_run", **payload})
            else:
                result = binance.withdraw_coin(
                    coin="TRX",
                    amount=args.amount,
                    address=args.binance_to_upbit_address,
                    network=args.network,
                    address_tag=args.binance_to_upbit_address_tag or None,
                )
                print(f"[EXECUTED] binance_to_upbit withdrawal submitted")
                _append_log(
                    {
                        "event_type": "transfer_executed",
                        "direction": direction,
                        "coin": "TRX",
                        "amount": args.amount,
                        "result": result,
                    }
                )


if __name__ == "__main__":
    main()
