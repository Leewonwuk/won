"""Rebalance one coin's spot legs toward its multi.yaml block (TRX, SOL, ...).

코인 **각각** `initial_*` 슬롯당 목표 원화(예: 10만×4)를 쓴다. TRX+SOL 동시 운용 시
업비트 KRW 한 통장은 `initial_upbit_krw` 가중치로만 나뉜다 (예: 둘 다 10만이면 1:1).

Usage:
    python -m src.tools.rebalance_coin_slots_to_yaml --symbol TRX --dry-run
    python -m src.tools.rebalance_coin_slots_to_yaml --symbol SOL --execute
    python -m src.tools.rebalance_coin_slots_to_yaml --all --dry-run
"""
from __future__ import annotations

import argparse
import os
from typing import Any

import requests
import yaml
from dotenv import load_dotenv

from src.exchanges.binance_trading_client import BinanceTradingClient
from src.exchanges.upbit_trading_client import UpbitTradingClient


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Rebalance one coin toward yaml 4-slot targets")
    p.add_argument("--config", default="configs/multi.yaml")
    p.add_argument("--symbol", default="", help="TRX, SOL, ... (omit with --all)")
    p.add_argument("--all", action="store_true", help="Run each coin in config in order")
    p.add_argument("--dry-run", action="store_true", help="Plan only")
    p.add_argument("--execute", action="store_true", help="Submit market orders")
    return p.parse_args()


def _required_env(key: str) -> str:
    v = os.getenv(key, "").strip()
    if not v:
        raise SystemExit(f"missing env: {key}")
    return v


def _bn_lot_step(bn_sym: str) -> float:
    r = requests.get(
        "https://api.binance.com/api/v3/exchangeInfo",
        params={"symbol": bn_sym},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    for s in data.get("symbols", []):
        if s.get("symbol") != bn_sym:
            continue
        for f in s.get("filters", []):
            if f.get("filterType") == "LOT_SIZE":
                return float(f["stepSize"])
    return 0.1


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


def _coin_cfg(data: dict[str, Any], symbol: str) -> dict[str, Any]:
    for c in data.get("coins", []):
        if str(c.get("symbol", "")).upper() == symbol.upper():
            return c
    raise SystemExit(f"symbol {symbol} not found in config")


def _floor_step(qty: float, step: float) -> float:
    if step <= 0:
        return qty
    return (int(qty / step + 1e-12)) * step


def _upbit_sell_volume(qty: float, symbol: str) -> float:
    if symbol.upper() == "TRX":
        return round(qty, 2)
    if symbol.upper() == "SOL":
        return round(qty, 4)
    return round(qty, 6)


def rebalance_one_coin(
    *,
    coin: dict[str, Any],
    dry_run: bool,
    up_cli: UpbitTradingClient,
    bn_cli: BinanceTradingClient,
) -> None:
    sym = str(coin["symbol"]).upper()
    tgt_krw_coin = float(coin["initial_upbit_coin_krw"])
    tgt_bn_usdt_krw = float(coin["initial_binance_usdt_krw"])
    tgt_bn_coin_krw = float(coin["initial_binance_coin_krw"])
    up_market = str(coin["upbit_market"])
    bn_sym = str(coin["binance_symbol"])

    p_up, fx, p_bn = _fetch_prices(up_market, bn_sym)
    u_tgt_ideal = tgt_bn_usdt_krw / fx
    q_tgt_ideal = tgt_bn_coin_krw / (fx * p_bn)
    q_tgt_up_ideal = tgt_krw_coin / p_up
    lot_step = _bn_lot_step(bn_sym)

    up_bal = {str(a["currency"]).upper(): float(a["balance"]) for a in up_cli.get_accounts()}
    krw = up_bal.get("KRW", 0.0)
    coin_up = up_bal.get(sym, 0.0)

    bn_acc = bn_cli.get_account()
    bn_map = {str(b["asset"]).upper(): b for b in bn_acc.get("balances", [])}
    usdt = float(bn_map.get("USDT", {}).get("free", 0) or 0)
    coin_bn = float(bn_map.get(sym, {}).get("free", 0) or 0)

    print(f"\n======== {sym} ========")
    print(f"[prices] Upbit {sym}={p_up:.6f} KRW  FX={fx:.4f}  Binance {sym}={p_bn:.8f} USDT")
    print(
        f"[yaml targets KRW] upbit_coin={tgt_krw_coin:,.0f}  bn_usdt={tgt_bn_usdt_krw:,.0f}  bn_coin={tgt_bn_coin_krw:,.0f}"
    )
    print(f"[before] Upbit KRW={krw:,.2f} {sym}={coin_up:.8f}  |  Binance USDT={usdt:.6f} {sym}={coin_bn:.8f}")

    up_notional = coin_up * p_up
    dq_up = q_tgt_up_ideal - coin_up
    print(f"\n[Upbit] coin notional ~{up_notional:,.0f} KRW  target_qty~{q_tgt_up_ideal:.6f}  delta={dq_up:+.6f}")
    min_krw_move = 12000.0  # 그보다 작은 조정은 수수료만 낭비
    if abs(dq_up) * p_up < min_krw_move:
        print(f"  [ok] within tolerance (<{min_krw_move:,.0f} KRW notional delta)")
    elif dq_up > 1e-8:
        spend = min(dq_up * p_up * 1.003, krw - 5000.0)
        spend = max(0.0, spend)
        if spend < max(5000.0, min_krw_move):
            print("  [skip] KRW too low or below min notional move")
        else:
            spend_i = int(spend)
            print(f"  market BUY {up_market} spend ~{spend_i:,} KRW")
            if not dry_run:
                r = up_cli.place_market_buy(up_market, float(spend_i))
                print(f"  [ok] {r}")
    elif dq_up < -1e-8:
        sell_v = min(-dq_up, coin_up * 0.999)
        sell_v = _upbit_sell_volume(sell_v, sym)
        if sell_v > 1e-6 and (-dq_up) * p_up >= min_krw_move:
            print(f"  market SELL {up_market} volume={sell_v}")
            if not dry_run:
                r = up_cli.place_market_sell(up_market, sell_v)
                print(f"  [ok] {r}")
        else:
            print("  [ok] sell skipped (within tolerance)")

    total_usdt_equiv = usdt + coin_bn * p_bn
    need_total = u_tgt_ideal + q_tgt_ideal * p_bn
    print(f"\n[Binance] USDT-equiv total={total_usdt_equiv:.6f}  ideal~{need_total:.6f}")
    if total_usdt_equiv + 1e-12 < need_total * 0.95:
        half = total_usdt_equiv / 2.0
        q_goal = half / p_bn
        u_goal = half
        print(f"  [mode] under-funded -> 50/50 split  qty~{q_goal:.6f}  USDT~{u_goal:.6f}")
    else:
        q_goal = q_tgt_ideal
        u_goal = u_tgt_ideal
        print(f"  [mode] yaml  qty~{q_goal:.6f}  USDT~{u_goal:.6f}")

    dq_bn = q_goal - coin_bn
    min_step = max(lot_step, 1e-8)
    min_usd_move = 3.0  # 그보다 작은 USDT 노치는 스킵
    if abs(dq_bn) * p_bn < min_usd_move:
        print(f"  [ok] Binance qty delta within tolerance (<{min_usd_move} USDT notional)")
    elif abs(dq_bn) >= min_step * 1.01:
        if dq_bn > 0:
            q_buy = _floor_step(dq_bn, lot_step)
            if q_buy >= min_step:
                print(f"  market BUY {bn_sym} qty={q_buy}")
                if not dry_run:
                    r = bn_cli.place_market_order(bn_sym, "BUY", q_buy)
                    print(f"  [ok] {r}")
        else:
            q_sell = _floor_step(-dq_bn, lot_step)
            q_sell = min(q_sell, coin_bn * 0.999)
            q_sell = _floor_step(q_sell, lot_step)
            if q_sell >= min_step:
                print(f"  market SELL {bn_sym} qty={q_sell}")
                if not dry_run:
                    r = bn_cli.place_market_order(bn_sym, "SELL", q_sell)
                    print(f"  [ok] {r}")


def main() -> None:
    args = parse_args()
    load_dotenv()
    dry_run = not args.execute
    if not args.execute and not args.dry_run:
        dry_run = True

    path = args.config
    data = yaml.safe_load(open(path, encoding="utf-8"))
    coins_cfg = data.get("coins", [])

    if args.all:
        symbols = [str(c["symbol"]).upper() for c in coins_cfg]
    else:
        if not args.symbol:
            raise SystemExit("pass --symbol TRX or --all")
        symbols = [args.symbol.upper()]

    up_cli = UpbitTradingClient(
        access_key=_required_env("UPBIT_ACCESS_KEY"),
        secret_key=_required_env("UPBIT_SECRET_KEY"),
        timeout_sec=15.0,
    )
    bn_cli = BinanceTradingClient(
        api_key=_required_env("BINANCE_API_KEY"),
        api_secret=_required_env("BINANCE_API_SECRET"),
        timeout_sec=15.0,
    )

    for s in symbols:
        coin = _coin_cfg(data, s)
        rebalance_one_coin(coin=coin, dry_run=dry_run, up_cli=up_cli, bn_cli=bn_cli)

    if dry_run:
        print("\n[dry-run] no orders sent. Use --execute to trade.")
    else:
        print("\n[done] python -m src.tools.print_spot_balances")


if __name__ == "__main__":
    main()
