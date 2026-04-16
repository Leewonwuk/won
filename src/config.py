from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import os

import yaml
from dotenv import load_dotenv


@dataclass(slots=True)
class RiskConfig:
    max_notional_krw: float = 1_000_000
    max_daily_loss_krw: float = 100_000
    max_open_positions: int = 1


# ---------------------------------------------------------------------------
# Multi-coin config
# ---------------------------------------------------------------------------

@dataclass
class CoinConfig:
    """Per-coin trading parameters for 4-balance rebalancing arb."""
    symbol: str
    upbit_market: str                           # e.g. "KRW-SOL"
    binance_symbol: str                         # e.g. "SOLUSDT"
    # -- initial allocation (KRW equivalent) --
    initial_upbit_krw: float = 150_000          # 업비트 초기 현금
    initial_upbit_coin_krw: float = 150_000     # 업비트 초기 코인 (KRW 환산)
    initial_binance_usdt_krw: float = 150_000   # 바이낸스 초기 USDT (KRW 환산)
    initial_binance_coin_krw: float = 150_000   # 바이낸스 초기 코인 (KRW 환산)
    # -- signal --
    entry_threshold_rate: float = 0.003         # 김프/역프 진입 임계값
    cooldown_sec: int = 5                       # 연속 거래 간 쿨다운
    entry_split_fraction: float = 0.35          # 1회 진입 시 가용 잔고 사용 비율
    reentry_min_premium_gap_rate: float = 0.0004  # 동일방향 재진입 최소 프리미엄 개선폭
    max_upbit_coin_ratio: float = 0.40          # 총자산 대비 업비트 코인 비중 상한
    max_binance_coin_ratio: float = 0.40        # 총자산 대비 바이낸스 코인 비중 상한
    min_upbit_coin_ratio_for_kimchi: float = 0.03  # 김프 매도 최소 업비트 코인 비중
    min_binance_coin_ratio_for_reverse: float = 0.03  # 역프 매도 최소 바이낸스 코인 비중
    rebalance_streak_enabled: bool = True
    rebalance_streak_count: int = 3
    rebalance_streak_min_interval_sec: int = 300
    rebalance_streak_window_sec: int = 1800
    # -- fees --
    fee_upbit_rate: float = 0.0005              # 업비트 거래 수수료
    fee_binance_rate: float = 0.0004            # 바이낸스 거래 수수료
    slippage_upbit_rate: float = 0.0008
    slippage_binance_rate: float = 0.0008
    transfer_fee_upbit_to_binance_base: float = 0.01   # 코인 단위 (e.g. 0.01 SOL)
    transfer_fee_binance_to_upbit_base: float = 0.01   # 코인 단위
    fx_conversion_fee_rate: float = 0.001       # KRW↔USDT 전환 수수료율
    # -- rebalancing --
    max_daily_rebalances: int = 3               # 일일 최대 리밸런싱 횟수
    rebalance_profit_multiplier: float = 2.0    # 예상수익 > 비용 × N 일때만 리밸런싱
    rebalance_imbalance_threshold: float = 0.15  # 목표 25% 대비 허용 편차 비율
    # -- wall/orderflow proxy filter (for backtest) --
    wall_filter_enabled: bool = True
    wall_min_liquidity_ratio: float = 0.6
    # TRADE_KIMCHI(바이낸스 매수) 시, taker buy 비율이 너무 높으면(매수 과열) 진입 회피
    wall_buy_binance_taker_buy_ratio_max: float = 0.7
    # TRADE_REVERSE(바이낸스 매도) 시, taker buy 비율이 너무 낮으면(매도 과열) 진입 회피
    wall_sell_binance_taker_buy_ratio_min: float = 0.3
    # -- 긴급 리밸런싱 / 포트폴리오 목표 비율 --
    # 현금 비율이 이 값 미만이고 코인 비율이 emergency_coin_ratio 초과 시 긴급 리밸런싱
    emergency_cash_ratio: float = 0.08       # 기본 8%
    emergency_coin_ratio: float = 0.30       # 기본 30%
    # 4-잔고 포트폴리오 각 슬롯 목표 비율 (25% = 1/4 균등배분)
    target_portfolio_ratio: float = 0.25     # 기본 25%
    # FX 환율 데이터가 이 시간(초) 이상 갱신되지 않으면 스탈 경고
    fx_stale_sec: float = 60.0               # 기본 60초


@dataclass
class MultiCoinConfig:
    """Global multi-coin runner configuration."""
    coins: list[CoinConfig] = field(default_factory=list)
    mode: str = "paper"                  # paper | live
    enable_live_orders: bool = False
    live_dry_run: bool = True
    loop_interval_sec: float = 1.0
    order_timeout_sec: float = 3.0
    max_daily_loss_krw: float = 500_000
    fx_krw_per_usdt: float = 1350.0     # fallback; override via env ARB_FX_KRW_PER_USDT


def load_multi_config(config_path: str) -> MultiCoinConfig:
    """Load multi-coin config from YAML."""
    load_dotenv()
    path = Path(config_path)
    data: dict[str, Any] = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    fx = float(os.getenv("ARB_FX_KRW_PER_USDT", data.get("fx_krw_per_usdt", 1350.0)))
    mode = os.getenv("ARB_MODE", data.get("mode", "paper"))
    enable_live = os.getenv("ARB_ENABLE_LIVE_ORDERS", str(data.get("enable_live_orders", False))).lower() in {"1", "true", "yes"}
    live_dry = os.getenv("ARB_LIVE_DRY_RUN", str(data.get("live_dry_run", True))).lower() in {"1", "true", "yes"}

    raw_coins: list[dict] = data.get("coins", [])
    coins: list[CoinConfig] = []
    for c in raw_coins:
        coins.append(CoinConfig(
            symbol=c["symbol"],
            upbit_market=c["upbit_market"],
            binance_symbol=c["binance_symbol"],
            initial_upbit_krw=float(c.get("initial_upbit_krw", 150_000)),
            initial_upbit_coin_krw=float(c.get("initial_upbit_coin_krw", 150_000)),
            initial_binance_usdt_krw=float(c.get("initial_binance_usdt_krw", 150_000)),
            initial_binance_coin_krw=float(c.get("initial_binance_coin_krw", 150_000)),
            entry_threshold_rate=float(c.get("entry_threshold_rate", 0.003)),
            cooldown_sec=int(c.get("cooldown_sec", 5)),
            entry_split_fraction=float(c.get("entry_split_fraction", 0.35)),
            reentry_min_premium_gap_rate=float(c.get("reentry_min_premium_gap_rate", 0.0004)),
            max_upbit_coin_ratio=float(c.get("max_upbit_coin_ratio", 0.40)),
            max_binance_coin_ratio=float(c.get("max_binance_coin_ratio", 0.40)),
            min_upbit_coin_ratio_for_kimchi=float(c.get("min_upbit_coin_ratio_for_kimchi", 0.03)),
            min_binance_coin_ratio_for_reverse=float(c.get("min_binance_coin_ratio_for_reverse", 0.03)),
            rebalance_streak_enabled=bool(c.get("rebalance_streak_enabled", True)),
            rebalance_streak_count=int(c.get("rebalance_streak_count", 3)),
            rebalance_streak_min_interval_sec=int(c.get("rebalance_streak_min_interval_sec", 300)),
            rebalance_streak_window_sec=int(c.get("rebalance_streak_window_sec", 1800)),
            fee_upbit_rate=float(c.get("fee_upbit_rate", 0.0005)),
            fee_binance_rate=float(c.get("fee_binance_rate", 0.0004)),
            slippage_upbit_rate=float(c.get("slippage_upbit_rate", 0.0008)),
            slippage_binance_rate=float(c.get("slippage_binance_rate", 0.0008)),
            transfer_fee_upbit_to_binance_base=float(c.get("transfer_fee_upbit_to_binance_base", 0.01)),
            transfer_fee_binance_to_upbit_base=float(c.get("transfer_fee_binance_to_upbit_base", 0.01)),
            fx_conversion_fee_rate=float(c.get("fx_conversion_fee_rate", 0.001)),
            max_daily_rebalances=int(c.get("max_daily_rebalances", 3)),
            rebalance_profit_multiplier=float(c.get("rebalance_profit_multiplier", 2.0)),
            rebalance_imbalance_threshold=float(c.get("rebalance_imbalance_threshold", 0.15)),
            wall_filter_enabled=bool(c.get("wall_filter_enabled", True)),
            wall_min_liquidity_ratio=float(c.get("wall_min_liquidity_ratio", 0.6)),
            wall_buy_binance_taker_buy_ratio_max=float(
                c.get("wall_buy_binance_taker_buy_ratio_max", 0.7)
            ),
            wall_sell_binance_taker_buy_ratio_min=float(
                c.get("wall_sell_binance_taker_buy_ratio_min", 0.3)
            ),
            emergency_cash_ratio=float(c.get("emergency_cash_ratio", 0.08)),
            emergency_coin_ratio=float(c.get("emergency_coin_ratio", 0.30)),
            target_portfolio_ratio=float(c.get("target_portfolio_ratio", 0.25)),
            fx_stale_sec=float(c.get("fx_stale_sec", 60.0)),
        ))

    return MultiCoinConfig(
        coins=coins,
        mode=mode,
        enable_live_orders=enable_live,
        live_dry_run=live_dry,
        loop_interval_sec=float(data.get("loop_interval_sec", 1.0)),
        order_timeout_sec=float(data.get("order_timeout_sec", 3.0)),
        max_daily_loss_krw=float(data.get("max_daily_loss_krw", 500_000)),
        fx_krw_per_usdt=fx,
    )


@dataclass(slots=True)
class TradingConfig:
    symbol: str = "BTC"
    upbit_market: str = "KRW-BTC"
    binance_symbol: str = "BTCUSDT"
    fx_krw_per_usdt: float = 1350.0
    fx_refresh_sec: float = 60.0
    max_position_hold_sec: float = 0.0
    entry_threshold_rate: float = 0.003
    exit_threshold_rate: float = 0.0005
    loop_interval_sec: float = 1.5
    marketdata_mode: str = "poll"  # poll | tick
    cooldown_sec: int = 10
    trade_size_base: float = 0.001
    fee_upbit_rate: float = 0.0005
    fee_binance_rate: float = 0.0004
    slippage_upbit_rate: float = 0.0007
    slippage_binance_rate: float = 0.0007
    transfer_fee_upbit_to_binance_base: float = 0.0
    transfer_fee_binance_to_upbit_base: float = 0.0
    mode: str = "paper"  # paper | live
    enable_live_orders: bool = False
    live_dry_run: bool = True
    order_timeout_sec: float = 3.0
    risk: RiskConfig = field(default_factory=RiskConfig)


def _deep_update(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_update(out[k], v)
        else:
            out[k] = v
    return out


def load_config(config_path: str) -> TradingConfig:
    load_dotenv()
    path = Path(config_path)
    data: dict[str, Any] = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    default = TradingConfig()
    cfg_dict = {
        "symbol": default.symbol,
        "upbit_market": default.upbit_market,
        "binance_symbol": default.binance_symbol,
        "fx_krw_per_usdt": default.fx_krw_per_usdt,
        "fx_refresh_sec": default.fx_refresh_sec,
        "max_position_hold_sec": default.max_position_hold_sec,
        "entry_threshold_rate": default.entry_threshold_rate,
        "exit_threshold_rate": default.exit_threshold_rate,
        "loop_interval_sec": default.loop_interval_sec,
        "marketdata_mode": default.marketdata_mode,
        "cooldown_sec": default.cooldown_sec,
        "trade_size_base": default.trade_size_base,
        "fee_upbit_rate": default.fee_upbit_rate,
        "fee_binance_rate": default.fee_binance_rate,
        "slippage_upbit_rate": default.slippage_upbit_rate,
        "slippage_binance_rate": default.slippage_binance_rate,
        "transfer_fee_upbit_to_binance_base": default.transfer_fee_upbit_to_binance_base,
        "transfer_fee_binance_to_upbit_base": default.transfer_fee_binance_to_upbit_base,
        "mode": default.mode,
        "enable_live_orders": default.enable_live_orders,
        "live_dry_run": default.live_dry_run,
        "order_timeout_sec": default.order_timeout_sec,
        "risk": {
            "max_notional_krw": default.risk.max_notional_krw,
            "max_daily_loss_krw": default.risk.max_daily_loss_krw,
            "max_open_positions": default.risk.max_open_positions,
        },
    }
    merged = _deep_update(cfg_dict, data)

    # Environment variable override for quick dry-runs.
    merged["mode"] = os.getenv("ARB_MODE", merged["mode"])
    merged["enable_live_orders"] = os.getenv(
        "ARB_ENABLE_LIVE_ORDERS", str(merged["enable_live_orders"])
    ).lower() in {"1", "true", "yes"}
    merged["live_dry_run"] = os.getenv("ARB_LIVE_DRY_RUN", str(merged["live_dry_run"])).lower() in {
        "1",
        "true",
        "yes",
    }
    if os.getenv("ARB_FX_KRW_PER_USDT"):
        merged["fx_krw_per_usdt"] = float(os.getenv("ARB_FX_KRW_PER_USDT", "0"))
    if os.getenv("ARB_FX_REFRESH_SEC"):
        merged["fx_refresh_sec"] = float(os.getenv("ARB_FX_REFRESH_SEC", "0"))
    if os.getenv("ARB_MAX_POSITION_HOLD_SEC"):
        merged["max_position_hold_sec"] = float(os.getenv("ARB_MAX_POSITION_HOLD_SEC", "0"))

    risk = RiskConfig(**merged["risk"])
    cfg = TradingConfig(**{**merged, "risk": risk})
    _validate(cfg)
    return cfg


def _validate(cfg: TradingConfig) -> None:
    if cfg.mode not in {"paper", "live"}:
        raise ValueError("mode must be one of {'paper','live'}")
    if cfg.marketdata_mode not in {"poll", "tick"}:
        raise ValueError("marketdata_mode must be one of {'poll','tick'}")
    if cfg.mode == "live" and not cfg.enable_live_orders:
        raise ValueError("live mode requires enable_live_orders=true")
    if cfg.entry_threshold_rate <= cfg.exit_threshold_rate:
        raise ValueError("entry_threshold_rate must be greater than exit_threshold_rate")
    if cfg.trade_size_base <= 0:
        raise ValueError("trade_size_base must be > 0")
    if cfg.order_timeout_sec <= 0:
        raise ValueError("order_timeout_sec must be > 0")
    if cfg.fx_refresh_sec < 0:
        raise ValueError("fx_refresh_sec must be >= 0")
    if cfg.max_position_hold_sec < 0:
        raise ValueError("max_position_hold_sec must be >= 0")

