"""YAML loader for v1.2 dual-quote (BTCUSDT + BTCUSDC) backtest."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml


@dataclass
class V12Config:
    symbol: str = "BTC"
    binance_symbol_usdt: str = "BTCUSDT"
    binance_symbol_usdc: str = "BTCUSDC"
    initial_usdt: float = 2500.0
    initial_usdc: float = 2500.0
    initial_btc_usdt_leg_usd: float = 2500.0
    initial_btc_usdc_leg_usd: float = 2500.0
    entry_threshold_rate: float = 0.0005
    # 역방향(USDC>USDT) 전용 임계값. 0.0이면 entry_threshold_rate 와 동일하게 적용.
    reverse_entry_threshold_rate: float = 0.0
    entry_split_fraction: float = 1.0
    fee_usdt_leg_rate: float = 0.0004       # taker fee (기본)
    fee_usdc_leg_rate: float = 0.0004
    fee_usdt_leg_maker_rate: float = 0.0002  # maker fee (지정가 주문)
    fee_usdc_leg_maker_rate: float = 0.0002
    use_maker_fees: bool = False             # True 시 maker fee로 손익 계산·실행
    slippage_usdt_leg_rate: float = 0.0008
    slippage_usdc_leg_rate: float = 0.0008
    internal_transfer_btc_fee: float = 0.0
    internal_stable_move_fee_rate: float = 0.0
    max_daily_rebalances: int = 3
    rebalance_profit_multiplier: float = 2.0
    rebalance_imbalance_threshold: float = 0.15
    target_portfolio_ratio: float = 0.25
    emergency_cash_ratio: float = 0.08
    emergency_coin_ratio: float = 0.30
    wall_filter_enabled: bool = False
    wall_min_liquidity_ratio: float = 0.6
    wall_buy_usdc_leg_taker_buy_ratio_max: float = 0.7
    wall_sell_usdc_leg_taker_buy_ratio_min: float = 0.3
    # close: 1m 종가 | hl_mid: (high+low)/2 per leg (OHLC CSV 필요)
    price_mode: str = "close"


def slippage_pair_from_multi_yaml(
    multi_path: str | Path,
) -> tuple[float, float, str] | None:
    """Read v1.2 USDT/USDC leg slippage from ``configs/multi.yaml`` (or compatible file).

    Resolution order:

    1. **``v12_binance_dual_quote``** — 명시 블록 (바이낸스 BTCUSDT↔BTCUSDC 전용, v1.1 코인 슬리피지와 무관).
    2. **레거시** — ``coins[0]`` 의 ``slippage_binance_rate`` → USDT 레그, ``slippage_upbit_rate`` → USDC 레그
       (과거 호환용; TRX 등 업비트–바이낸스 코인 값이 v12에 빌려 쓰이던 방식).

    Returns ``(usdt_leg, usdc_leg, source_tag)`` or ``None`` if file missing / no usable data.
    """
    mp = Path(multi_path)
    if not mp.is_file():
        return None
    raw: dict[str, Any] = yaml.safe_load(mp.read_text(encoding="utf-8")) or {}

    v12 = raw.get("v12_binance_dual_quote")
    if isinstance(v12, dict):
        su = v12.get("slippage_usdt_leg_rate")
        sc = v12.get("slippage_usdc_leg_rate")
        if su is not None and sc is not None:
            return (float(su), float(sc), "v12_binance_dual_quote")

    coins = raw.get("coins")
    if not isinstance(coins, list) or not coins:
        return None
    c0 = coins[0]
    if not isinstance(c0, dict):
        return None
    slip_b = float(c0.get("slippage_binance_rate", 0.0008))
    slip_u = float(c0.get("slippage_upbit_rate", 0.0008))
    return (slip_b, slip_u, "coins_first_legacy")


def load_v12_config(
    path: str,
    *,
    multi_slippage_yaml: str | None = "configs/multi.yaml",
) -> V12Config:
    p = Path(path)
    data: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    cfg = V12Config(
        symbol=str(data.get("symbol", "BTC")),
        binance_symbol_usdt=str(data.get("binance_symbol_usdt", "BTCUSDT")),
        binance_symbol_usdc=str(data.get("binance_symbol_usdc", "BTCUSDC")),
        initial_usdt=float(data.get("initial_usdt", 2500)),
        initial_usdc=float(data.get("initial_usdc", 2500)),
        initial_btc_usdt_leg_usd=float(data.get("initial_btc_usdt_leg_usd", 2500)),
        initial_btc_usdc_leg_usd=float(data.get("initial_btc_usdc_leg_usd", 2500)),
        entry_threshold_rate=float(data.get("entry_threshold_rate", 0.0005)),
        reverse_entry_threshold_rate=float(data.get("reverse_entry_threshold_rate", 0.0)),
        entry_split_fraction=float(data.get("entry_split_fraction", 1.0)),
        fee_usdt_leg_rate=float(data.get("fee_usdt_leg_rate", 0.0004)),
        fee_usdc_leg_rate=float(data.get("fee_usdc_leg_rate", 0.0004)),
        fee_usdt_leg_maker_rate=float(data.get("fee_usdt_leg_maker_rate", 0.0002)),
        fee_usdc_leg_maker_rate=float(data.get("fee_usdc_leg_maker_rate", 0.0002)),
        use_maker_fees=bool(data.get("use_maker_fees", False)),
        slippage_usdt_leg_rate=float(data.get("slippage_usdt_leg_rate", 0.0008)),
        slippage_usdc_leg_rate=float(data.get("slippage_usdc_leg_rate", 0.0008)),
        internal_transfer_btc_fee=float(data.get("internal_transfer_btc_fee", 0.0)),
        internal_stable_move_fee_rate=float(data.get("internal_stable_move_fee_rate", 0.0)),
        max_daily_rebalances=int(data.get("max_daily_rebalances", 3)),
        rebalance_profit_multiplier=float(data.get("rebalance_profit_multiplier", 2.0)),
        rebalance_imbalance_threshold=float(data.get("rebalance_imbalance_threshold", 0.15)),
        target_portfolio_ratio=float(data.get("target_portfolio_ratio", 0.25)),
        emergency_cash_ratio=float(data.get("emergency_cash_ratio", 0.08)),
        emergency_coin_ratio=float(data.get("emergency_coin_ratio", 0.30)),
        wall_filter_enabled=bool(data.get("wall_filter_enabled", False)),
        wall_min_liquidity_ratio=float(data.get("wall_min_liquidity_ratio", 0.6)),
        wall_buy_usdc_leg_taker_buy_ratio_max=float(
            data.get("wall_buy_usdc_leg_taker_buy_ratio_max", 0.7)
        ),
        wall_sell_usdc_leg_taker_buy_ratio_min=float(
            data.get("wall_sell_usdc_leg_taker_buy_ratio_min", 0.3)
        ),
        price_mode=str(data.get("price_mode", "close")),
    )
    if multi_slippage_yaml:
        triple = slippage_pair_from_multi_yaml(multi_slippage_yaml)
        if triple is not None:
            su, sc, _src = triple
            cfg = replace(
                cfg,
                slippage_usdt_leg_rate=su,
                slippage_usdc_leg_rate=sc,
            )
    return cfg
