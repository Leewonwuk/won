"""Compare Upbit/Binance spot balances to multi.yaml initial_* targets (e.g. TRX+SOL 80만 시드).

Uses public tickers for KRW notionals. Exit 0 if all checks pass within tolerance; 1 otherwise.

- Upbit KRW: one check vs sum(initial_upbit_krw). If total KRW is much larger (other holdings), per-coin
  KRW attribution is skipped (WARN only).
- Binance USDT: one check vs sum(initial_binance_usdt_krw) (single wallet shared by coins).

Usage:
    python -m src.tools.verify_arb_allocation
    python -m src.tools.verify_arb_allocation --config configs/multi.yaml --tolerance-pct 0.15
"""
from __future__ import annotations

import argparse
import os
import sys

import requests
from dotenv import load_dotenv

from src.config import load_multi_config
from src.exchanges.binance_trading_client import BinanceTradingClient
from src.exchanges.upbit_trading_client import UpbitTradingClient


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Verify spot vs multi.yaml 4-slot targets")
    p.add_argument("--config", default=os.getenv("ARB_MULTI_CONFIG", "configs/multi.yaml"))
    p.add_argument(
        "--tolerance-pct",
        type=float,
        default=0.18,
        help="Relative tolerance per leg (default 0.18 = 18%%)",
    )
    return p.parse_args()


def _required_env(key: str) -> str:
    v = os.getenv(key, "").strip()
    if not v:
        raise SystemExit(f"missing env: {key}")
    return v


def _fetch_prices(up_market: str, bn_sym: str) -> tuple[float, float, float]:
    up = requests.get(
        "https://api.upbit.com/v1/ticker",
        params={"markets": f"{up_market},KRW-USDT"},
        timeout=15,
    )
    up.raise_for_status()
    rows = {x["market"]: x for x in up.json()}
    p_coin_krw = float(rows[up_market]["trade_price"])
    fx = float(rows["KRW-USDT"]["trade_price"])
    bn = requests.get(
        "https://api.binance.com/api/v3/ticker/price",
        params={"symbol": bn_sym},
        timeout=15,
    )
    bn.raise_for_status()
    p_coin_usdt = float(bn.json()["price"])
    return p_coin_krw, fx, p_coin_usdt


def _within(actual: float, target: float, tol: float) -> bool:
    if target <= 0:
        return abs(actual) <= max(5000.0, abs(actual) * tol)
    return abs(actual - target) / target <= tol


def main() -> None:
    args = parse_args()
    load_dotenv()
    tol = float(args.tolerance_pct)
    if tol <= 0 or tol >= 1:
        raise SystemExit("--tolerance-pct must be in (0, 1)")

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    cfg = load_multi_config(args.config)
    if not cfg.coins:
        raise SystemExit("no coins in config")

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
    krw_bal = by_cur.get("KRW", 0.0)
    target_krw_sum = sum(c.initial_upbit_krw for c in cfg.coins)
    target_usdt_krw_sum = sum(c.initial_binance_usdt_krw for c in cfg.coins)

    bn_acc = bn.get_account()
    bn_by = {str(b.get("asset", "")).upper(): b for b in bn_acc.get("balances", [])}
    usdt_b = bn_by.get("USDT", {})
    usdt = float(usdt_b.get("free", 0) or 0) + float(usdt_b.get("locked", 0) or 0)

    _, fx0, _ = _fetch_prices(cfg.coins[0].upbit_market, cfg.coins[0].binance_symbol)
    notional_bn_usdt_total = usdt * fx0

    print(f"\n=== verify_arb_allocation  config={args.config}  tolerance={tol:.0%} ===\n")

    ok = True
    warns: list[str] = []

    if target_krw_sum > 0:
        if krw_bal < target_krw_sum * (1.0 - tol):
            print(
                f"FAIL  Upbit KRW total  actual={krw_bal:,.0f}  "
                f"target_sum(initial_upbit_krw)={target_krw_sum:,.0f}  (too low)"
            )
            ok = False
        elif _within(krw_bal, target_krw_sum, tol):
            print(f"OK    Upbit KRW total  {krw_bal:,.0f}  (yaml sum {target_krw_sum:,.0f})")
        else:
            warns.append(
                f"Upbit KRW total {krw_bal:,.0f} exceeds yaml sum {target_krw_sum:,.0f} "
                "(non-arb KRW mixed; per-coin KRW share check skipped)"
            )

    upbit_krw_share_check = target_krw_sum > 0 and _within(krw_bal, target_krw_sum, tol)
    w_sum = sum(c.initial_upbit_krw for c in cfg.coins)

    if target_usdt_krw_sum > 0:
        if _within(notional_bn_usdt_total, target_usdt_krw_sum, tol):
            print(
                f"OK    Binance USDT (KRW)  {notional_bn_usdt_total:,.0f}  "
                f"(yaml sum {target_usdt_krw_sum:,.0f}, one wallet)"
            )
        else:
            print(
                f"FAIL  Binance USDT (KRW)  {notional_bn_usdt_total:,.0f}  "
                f"target sum={target_usdt_krw_sum:,.0f}"
            )
            ok = False

    print()
    for c in cfg.coins:
        sym = c.symbol.upper()
        p_krw, fx, p_usdt = _fetch_prices(c.upbit_market, c.binance_symbol)
        coin_up = by_cur.get(sym, 0.0)
        notional_up_coin = coin_up * p_krw

        bal_bn = bn_by.get(sym, {})
        coin_bn = float(bal_bn.get("free", 0) or 0) + float(bal_bn.get("locked", 0) or 0)
        notional_bn_coin = coin_bn * p_usdt * fx

        share = (c.initial_upbit_krw / w_sum) if w_sum > 0 else 0.0
        attrib_krw = krw_bal * share

        print(f"--- {sym} ---")
        if upbit_krw_share_check:
            label = "Upbit KRW share (model)"
            if _within(attrib_krw, c.initial_upbit_krw, tol):
                print(f"OK    {label}  actual={attrib_krw:,.0f}  target={c.initial_upbit_krw:,.0f}")
            else:
                print(f"FAIL  {label}  actual={attrib_krw:,.0f}  target={c.initial_upbit_krw:,.0f}")
                ok = False
        else:
            print(
                f"SKIP  Upbit KRW share  (~{attrib_krw:,.0f} vs target {c.initial_upbit_krw:,.0f})  "
                "(total KRW != yaml sum)"
            )

        for label, actual, target in (
            ("Upbit coin (KRW)", notional_up_coin, c.initial_upbit_coin_krw),
            ("Binance coin (KRW)", notional_bn_coin, c.initial_binance_coin_krw),
        ):
            if _within(actual, target, tol):
                print(f"OK    {label}  actual={actual:,.0f}  target={target:,.0f}")
            else:
                print(f"FAIL  {label}  actual={actual:,.0f}  target={target:,.0f}")
                ok = False
        print()

    for w in warns:
        print(f"WARN  {w}")

    print()
    if ok:
        print("Overall: PASS (within tolerance)")
    else:
        print("Overall: FAIL - adjust or: python -m src.tools.rebalance_coin_slots_to_yaml --all --dry-run")
    print()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
