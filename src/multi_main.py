"""Multi-coin asyncio main loop for rebalancing arbitrage.

Connects to Upbit + Binance WebSocket feeds, evaluates premium for
each coin every tick, and executes trades / rebalancing.

Paper: in-memory `RebalancePortfolio` only.
Live (`mode: live`, `enable_live_orders: true`): Kimchi/Reverse also send
Upbit+Binance market orders via `MultiLiveExecutionEngine`. On-chain
rebalance (REBALANCE_*) is not auto-executed in live — do transfers manually.

Run:
    python -m src.multi_main --config configs/multi.yaml
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import platform
import time
from datetime import datetime, timedelta, timezone

from src.config import CoinConfig, MultiCoinConfig, load_multi_config
from src.execution.multi_live_engine import MultiLiveExecutionEngine
from src.exchanges.binance_trading_client import BinanceTradingClient
from src.exchanges.upbit_trading_client import UpbitTradingClient
from src.exchanges.upbit_ws import upbit_ws_loop
from src.exchanges.binance_ws import binance_ws_loop
from src.logging.event_logger import EventLogger
from src.logging.multi_run_csv import MultiRunCsvRecorder
from src.notifications.telegram_notifier import TelegramNotifier
from src.state.multi_portfolio import RebalancePortfolio
from src.strategy.capital_allocator import Action, decide

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class HedgeHaltError(RuntimeError):
    """Raised when hedge restore failed and live loop must stop."""


def _bn_mid_usdt(bn_data: dict) -> float:
    bid = float(bn_data.get("bid_price", 0) or 0)
    ask = float(bn_data.get("ask_price", 0) or 0)
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    return bid or ask


def _equity_total_krw(
    portfolio: RebalancePortfolio,
    coins: list[CoinConfig],
    upbit_prices: dict,
    binance_prices: dict,
    fx: float,
) -> float:
    total = 0.0
    for c in coins:
        up_p = float(upbit_prices.get(c.upbit_market, {}).get("trade_price", 0) or 0)
        bn_m = _bn_mid_usdt(binance_prices.get(c.binance_symbol, {}))
        if up_p <= 0 or bn_m <= 0:
            continue
        b = portfolio.get(c.symbol)
        total += b.total_value_krw(up_p, bn_m, fx)
    return total


def _yaml_seed_totals_krw(coins: list[CoinConfig]) -> dict[str, float]:
    upbit_total = 0.0
    binance_total = 0.0
    for c in coins:
        upbit_total += float(c.initial_upbit_krw) + float(c.initial_upbit_coin_krw)
        binance_total += float(c.initial_binance_usdt_krw) + float(c.initial_binance_coin_krw)
    return {
        "upbit_total_krw": upbit_total,
        "binance_total_krw": binance_total,
        "combined_total_krw": upbit_total + binance_total,
    }


def _initial_asset_plan_text(coins: list[CoinConfig]) -> str:
    lines: list[str] = []
    for c in coins:
        lines.append(
            (
                f"- {c.symbol}: 업비트 KRW {c.initial_upbit_krw:,.0f} / "
                f"업비트 코인 {c.initial_upbit_coin_krw:,.0f} / "
                f"바이낸스 USDT {c.initial_binance_usdt_krw:,.0f} / "
                f"바이낸스 코인 {c.initial_binance_coin_krw:,.0f} KRW"
            )
        )
    totals = _yaml_seed_totals_krw(coins)
    lines.append(
        (
            f"- 합계: 업비트 {totals['upbit_total_krw']:,.0f} / "
            f"바이낸스 {totals['binance_total_krw']:,.0f} / "
            f"전체 {totals['combined_total_krw']:,.0f} KRW"
        )
    )
    return "\n".join(lines)


def _exchange_asset_totals_krw(
    portfolio: RebalancePortfolio,
    coins: list[CoinConfig],
    upbit_prices: dict,
    binance_prices: dict,
    fx: float,
) -> dict[str, float]:
    upbit_cash_krw = 0.0
    upbit_coin_krw = 0.0
    binance_usdt_krw = 0.0
    binance_coin_krw = 0.0
    for c in coins:
        b = portfolio.get(c.symbol)
        up_p = float(upbit_prices.get(c.upbit_market, {}).get("trade_price", 0) or 0)
        bn_m = _bn_mid_usdt(binance_prices.get(c.binance_symbol, {}))
        upbit_cash_krw += float(b.upbit_krw)
        upbit_coin_krw += float(b.upbit_coin) * up_p if up_p > 0 else 0.0
        binance_usdt_krw += float(b.binance_usdt) * float(fx)
        binance_coin_krw += float(b.binance_coin) * bn_m * float(fx) if bn_m > 0 else 0.0
    return {
        "upbit_total_krw": upbit_cash_krw + upbit_coin_krw,
        "binance_total_krw": binance_usdt_krw + binance_coin_krw,
        "combined_total_krw": upbit_cash_krw + upbit_coin_krw + binance_usdt_krw + binance_coin_krw,
        "upbit_cash_krw": upbit_cash_krw,
        "upbit_coin_krw": upbit_coin_krw,
        "binance_usdt_krw": binance_usdt_krw,
        "binance_coin_krw": binance_coin_krw,
    }


def _position_state_summary(portfolio: RebalancePortfolio, coins: list[CoinConfig]) -> str:
    states: list[str] = []
    for c in coins:
        pos = portfolio.get(c.symbol).open_position
        if not isinstance(pos, dict):
            states.append(f"{c.symbol}:중립")
            continue
        ptype = str(pos.get("type", "")).upper()
        if ptype == "TRADE_KIMCHI":
            states.append(f"{c.symbol}:김프 상태")
        elif ptype == "TRADE_REVERSE":
            states.append(f"{c.symbol}:역프 상태")
        else:
            states.append(f"{c.symbol}:중립")
    return ", ".join(states)


def _fees_total_krw(portfolio: RebalancePortfolio, coins: list[CoinConfig]) -> float:
    return sum(portfolio.get(c.symbol).realized_fee_krw for c in coins)


def _tg_hour_bucket_kst() -> str:
    utc = datetime.now(tz=timezone.utc)
    kst = utc.astimezone(timezone(timedelta(hours=9)))
    return kst.strftime("%Y-%m-%dT%H")


def _markets_data_ok(
    coins: list[CoinConfig],
    upbit_prices: dict,
    binance_prices: dict,
) -> tuple[bool, list[str]]:
    """업비트 체결가·바이낸스 호가·KRW-USDT FX가 모두 있으면 True."""
    issues: list[str] = []
    fx_px = float(upbit_prices.get("KRW-USDT", {}).get("trade_price") or 0)
    if fx_px <= 0:
        issues.append("KRW-USDT(FX) 없음")
    for c in coins:
        up = float(upbit_prices.get(c.upbit_market, {}).get("trade_price") or 0)
        bn = binance_prices.get(c.binance_symbol, {})
        bp = float(bn.get("bid_price") or 0) or float(bn.get("ask_price") or 0)
        if up <= 0:
            issues.append(f"{c.symbol} 업빗 시세 없음")
        if bp <= 0:
            issues.append(f"{c.symbol} 바낸 호가 없음")
    return len(issues) == 0, issues


def _compute_hourly_health(
    coins: list[CoinConfig],
    upbit_prices: dict,
    binance_prices: dict,
    ui_state: dict,
    tg_period: dict[str, float | int],
    stale_threshold_sec: float,
) -> dict[str, object]:
    """시세 즉시성·단절·구간 에러로 구동 상태 문자열과 로그용 필드를 만든다."""
    data_ok, issues = _markets_data_ok(coins, upbit_prices, binance_prices)
    last_m = ui_state.get("last_all_markets_ok_mono")
    now_m = time.monotonic()
    err_n = int(tg_period.get("errors", 0))
    if last_m is None:
        stale_age: float | None = None
        recent_ok = False
    else:
        stale_age = now_m - float(last_m)
        recent_ok = stale_age <= stale_threshold_sec

    if not data_ok:
        title = "⚠️ 구동 불가 (시세 누락)"
        detail = " · ".join(issues) if issues else "원인 미상"
        ok = False
    elif not recent_ok:
        title = "⚠️ 구동 불가 (시세 단절 의심)"
        if stale_age is None:
            detail = "전체 시세 정상 시각 미기록"
        else:
            detail = (
                f"마지막 정상 시세 후 {int(stale_age)}초 (허용 {int(stale_threshold_sec)}초)"
            )
        ok = False
    elif err_n > 0:
        title = "⚠️ 구동 불가 (에러 구간)"
        detail = f"구간 내 처리/라이브 에러 {err_n}건"
        ok = False
    else:
        title = "✅ 정상 구동"
        detail = "시세·루프 정상"
        ok = True

    return {
        "ok": ok,
        "title": title,
        "detail": detail,
        "data_ok_now": data_ok,
        "issues": issues,
        "stale_sec_since_ok": stale_age,
        "errors_in_period": err_n,
    }


def _kst_now_str() -> str:
    utc = datetime.now(tz=timezone.utc)
    kst = utc.astimezone(timezone(timedelta(hours=9)))
    return kst.strftime("%Y-%m-%d %H:%M KST")


def _csv_data_rows(path: str) -> int:
    """CSV 데이터 행 수(헤더 제외). 실패 시 0."""
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            total = sum(1 for _ in f)
        return max(total - 1, 0)
    except Exception:
        return 0


def _check_portfolio_imbalance(
    portfolio: RebalancePortfolio,
    coins: list[CoinConfig],
    now_mono: float,
    state: dict,
    *,
    threshold_hours: float,
    repeat_alert_hours: float = 1.0,
) -> list[dict]:
    alerts: list[dict] = []
    started = state.setdefault("started", {})
    last_alert = state.setdefault("last_alert", {})
    threshold_sec = max(threshold_hours, 0.0) * 3600.0
    repeat_sec = max(repeat_alert_hours, 0.0) * 3600.0

    for coin in coins:
        b = portfolio.get(coin.symbol)
        # one-sided inventory after repeated one-direction trades.
        side_a = b.upbit_coin < 1e-6 and b.binance_usdt < 0.01
        side_b = b.upbit_krw < 1.0 and b.binance_coin < 1e-6
        imbalanced = side_a or side_b
        key = coin.symbol

        if not imbalanced:
            started.pop(key, None)
            last_alert.pop(key, None)
            continue

        begin = started.get(key)
        if begin is None:
            started[key] = now_mono
            continue

        elapsed = now_mono - float(begin)
        if elapsed < threshold_sec:
            continue

        last = last_alert.get(key)
        if last is not None and (now_mono - float(last)) < repeat_sec:
            continue

        last_alert[key] = now_mono
        alerts.append(
            {
                "symbol": coin.symbol,
                "elapsed_hours": elapsed / 3600.0,
                "upbit_krw": b.upbit_krw,
                "upbit_coin": b.upbit_coin,
                "binance_usdt": b.binance_usdt,
                "binance_coin": b.binance_coin,
            }
        )
    return alerts


def _log_multi_status_kr(
    *,
    title: str,
    loop_count: int,
    equity: float,
    baseline: float | None,
    portfolio: RebalancePortfolio,
    coins: list[CoinConfig],
) -> None:
    """한글 요약: 총평가, 누적실현(비용반영), 수수료, 수수료 제외 참고이익(원), 수익률."""
    fees = _fees_total_krw(portfolio, coins)
    realized = portfolio.realized_pnl_krw
    gross_ref = realized + fees
    ts = _kst_now_str()
    parts = [
        f"[{title}] {ts}",
        f"메인루프 {loop_count:,}회 돌았음",
        f"지금 총평가(원화환산) 약 {equity:,.0f}원",
    ]
    if baseline is not None and baseline > 0:
        mtm_pct = (equity - baseline) / baseline * 100
        parts.append(f"시작 총자산 {baseline:,.0f}원 대비 평가수익률 {mtm_pct:+.2f}%")
        net_roi = realized / baseline * 100
        parts.append(f"누적 실현손익만 기준 순수익률(수수료·슬리피지 반영) {net_roi:+.2f}%")
    else:
        parts.append("시작 총자산 기준 아직 없음(가격 수신 후 자동 설정)")
    parts.append(f"누적 실현손익(모델상, 비용 반영) {realized:+,.0f}원")
    parts.append(f"누적 수수료·슬리피지(기록 합) {fees:,.0f}원")
    parts.append(f"수수료 제외 참고이익(실현손익+위 비용합) {gross_ref:+,.0f}원")
    logger.info(" | ".join(parts))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-coin rebalancing arb runner")
    parser.add_argument("--config", default="configs/multi.yaml", help="YAML config path")
    parser.add_argument("--iterations", type=int, default=0, help="0 = infinite loop")
    return parser.parse_args()


def _init_portfolio_from_exchange(
    cfg: MultiCoinConfig,
    upbit_accounts_raw: list[dict],
    binance_account_raw: dict,
    *,
    fx: float,
    upbit_prices: dict[str, dict],
    binance_prices: dict[str, dict],
) -> RebalancePortfolio:
    """Seed 4-balance state from real spot balances (live only).

    Splits shared Upbit KRW / Binance USDT by each coin's ``initial_*_krw`` weights,
    then **caps** every leg at that coin's YAML ``initial_*`` so a large KRW wallet
    (e.g. 690k) does not size TRX/SOL legs beyond 10만+10만 each.

    Prefer ``ARB_LIVE_SEED_FROM_CONFIG=true`` if you want strictly synthetic qty from
    YAML (ignores on-chain rounding); capped exchange mode uses min(actual, cap).
    """
    up = {str(a["currency"]).upper(): float(a["balance"]) for a in upbit_accounts_raw}
    bn: dict[str, float] = {}
    for b in binance_account_raw.get("balances", []):
        asset = str(b.get("asset", "")).upper()
        amt = float(b.get("free", 0) or 0) + float(b.get("locked", 0) or 0)
        bn[asset] = amt

    w_krw_sum = sum(c.initial_upbit_krw for c in cfg.coins) or 1.0
    w_usdt_sum = sum(c.initial_binance_usdt_krw for c in cfg.coins) or 1.0
    krw_total = up.get("KRW", 0.0)
    usdt_total = bn.get("USDT", 0.0)
    fx_use = float(fx) if float(fx) > 0 else float(cfg.fx_krw_per_usdt)

    portfolio = RebalancePortfolio()
    for coin in cfg.coins:
        sym = coin.symbol.upper()
        fk = coin.initial_upbit_krw / w_krw_sum
        fu = coin.initial_binance_usdt_krw / w_usdt_sum
        raw_krw = krw_total * fk
        upbit_krw = min(raw_krw, coin.initial_upbit_krw)

        raw_usdt = usdt_total * fu
        cap_usdt = coin.initial_binance_usdt_krw / fx_use
        binance_usdt = min(raw_usdt, cap_usdt)

        up_data = upbit_prices.get(coin.upbit_market, {})
        up_p = float(up_data.get("trade_price", 0) or 0)
        act_u = up.get(sym, 0.0)
        if up_p > 0:
            max_u = coin.initial_upbit_coin_krw / up_p
            upbit_coin = min(act_u, max_u)
        else:
            upbit_coin = act_u

        bn_d = binance_prices.get(coin.binance_symbol, {})
        bp = float(bn_d.get("bid_price", 0) or 0)
        ba = float(bn_d.get("ask_price", 0) or 0)
        bn_p = (bp + ba) / 2.0 if bp > 0 and ba > 0 else max(bp, ba)
        act_b = bn.get(sym, 0.0)
        if bn_p > 0 and fx_use > 0:
            max_b = coin.initial_binance_coin_krw / (bn_p * fx_use)
            binance_coin = min(act_b, max_b)
        else:
            binance_coin = act_b

        portfolio.init_coin(
            symbol=coin.symbol,
            upbit_krw=upbit_krw,
            upbit_coin=upbit_coin,
            binance_usdt=binance_usdt,
            binance_coin=binance_coin,
        )
    return portfolio


def _init_portfolio(cfg: MultiCoinConfig, upbit_prices: dict, binance_prices: dict) -> RebalancePortfolio:
    """Initialize portfolio from config + current prices."""
    portfolio = RebalancePortfolio()
    for coin in cfg.coins:
        # Try to get current prices to convert KRW → coin qty
        # If WS not ready yet, use 0 (will be set on first tick)
        up_data = upbit_prices.get(coin.upbit_market, {})
        bn_data = binance_prices.get(coin.binance_symbol, {})

        upbit_price = up_data.get("trade_price", 0.0)
        binance_price = float(bn_data.get("ask_price", 0.0) or bn_data.get("bid_price", 0.0))

        if upbit_price > 0 and binance_price > 0:
            upbit_coin_qty = coin.initial_upbit_coin_krw / upbit_price
            binance_coin_qty = coin.initial_binance_coin_krw / (binance_price * cfg.fx_krw_per_usdt)
            binance_usdt = coin.initial_binance_usdt_krw / cfg.fx_krw_per_usdt
        else:
            # 가격 데이터 미수신 → 코인 수량 0으로 초기화 (첫 틱 이후 갱신 필요)
            logger.warning(
                "[%s] 초기화 시 가격 데이터 없음 (upbit=%.2f, binance=%.2f). "
                "upbit_coin/binance_coin=0으로 초기화됨. 봇 기동 후 첫 틱에서 정정 필요.",
                coin.symbol, upbit_price, binance_price,
            )
            upbit_coin_qty = 0.0
            binance_coin_qty = 0.0
            binance_usdt = coin.initial_binance_usdt_krw / cfg.fx_krw_per_usdt

        portfolio.init_coin(
            symbol=coin.symbol,
            upbit_krw=coin.initial_upbit_krw,
            upbit_coin=upbit_coin_qty,
            binance_usdt=binance_usdt,
            binance_coin=binance_coin_qty,
        )
    return portfolio


async def main_loop(cfg: MultiCoinConfig, max_iterations: int = 0) -> None:
    """Main async loop: WS feeds + decision engine."""
    if cfg.mode == "live" and not cfg.enable_live_orders:
        raise RuntimeError("multi v2 live mode requires enable_live_orders=true in config")

    live_engine: MultiLiveExecutionEngine | None = None
    if cfg.mode == "live" and cfg.enable_live_orders:
        upbit_access = os.getenv("UPBIT_ACCESS_KEY", "")
        upbit_secret = os.getenv("UPBIT_SECRET_KEY", "")
        binance_key = os.getenv("BINANCE_API_KEY", "")
        binance_secret = os.getenv("BINANCE_API_SECRET", "")
        if not all([upbit_access, upbit_secret, binance_key, binance_secret]):
            raise RuntimeError("multi v2 live: missing API credentials in environment")
        live_engine = MultiLiveExecutionEngine(
            upbit=UpbitTradingClient(
                access_key=upbit_access,
                secret_key=upbit_secret,
                timeout_sec=cfg.order_timeout_sec,
            ),
            binance=BinanceTradingClient(
                api_key=binance_key,
                api_secret=binance_secret,
                timeout_sec=cfg.order_timeout_sec,
            ),
            dry_run=cfg.live_dry_run,
        )

    # Shared price dicts (updated by WS tasks)
    upbit_prices: dict[str, dict] = {}
    binance_prices: dict[str, dict] = {}

    # Build subscription lists
    upbit_markets = [c.upbit_market for c in cfg.coins] + ["KRW-USDT"]
    binance_symbols = [c.binance_symbol for c in cfg.coins]

    # Start WebSocket tasks
    ws_tasks = [
        asyncio.create_task(upbit_ws_loop(upbit_markets, upbit_prices)),
        asyncio.create_task(binance_ws_loop(binance_symbols, binance_prices)),
    ]

    # Wait for initial prices (max 10 seconds)
    logger.info("Waiting for initial WebSocket data...")
    for _ in range(100):
        await asyncio.sleep(0.1)
        if upbit_prices and binance_prices:
            break
    else:
        logger.warning("WS data not fully received, proceeding with available data")

    # Per-symbol prices (avoid init with 0 coin qty before first bookTicker tick)
    logger.info("Waiting for per-coin tickers + KRW-USDT FX...")
    for _ in range(150):
        await asyncio.sleep(0.1)
        fx_ok = upbit_prices.get("KRW-USDT", {}).get("trade_price", 0) > 0
        coins_ok = True
        for c in cfg.coins:
            up_p = upbit_prices.get(c.upbit_market, {}).get("trade_price", 0)
            bn = binance_prices.get(c.binance_symbol, {})
            bn_p = float(bn.get("ask_price", 0) or bn.get("bid_price", 0))
            if up_p <= 0 or bn_p <= 0:
                coins_ok = False
                break
        if fx_ok and coins_ok:
            break
    else:
        logger.warning("Some WS prices still missing; portfolio coin qty may be 0 until next run")

    # Get FX rate from Upbit KRW-USDT
    fx_data = upbit_prices.get("KRW-USDT", {})
    fx = fx_data.get("trade_price", cfg.fx_krw_per_usdt)

    event_logger = EventLogger(path="logs/multi_events.jsonl")

    live_seed_from_config = os.getenv("ARB_LIVE_SEED_FROM_CONFIG", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }

    if live_engine is not None:
        preflight = live_engine.preflight_check()
        event_logger.log("live_preflight", preflight)
        logger.info("Live order path enabled: preflight=%s", preflight.get("status"))
        if live_seed_from_config:
            portfolio = _init_portfolio(cfg, upbit_prices, binance_prices)
            event_logger.log(
                "portfolio_seed",
                {
                    "source": "config_limited_live",
                    "guard": "ARB_LIVE_SEED_FROM_CONFIG=true",
                },
            )
            logger.warning(
                "LIVE 제한모드: 거래소 전체잔고 대신 config 초기금액으로만 주문 사이징합니다 "
                "(ARB_LIVE_SEED_FROM_CONFIG=true)"
            )
        else:
            up_acc = live_engine.upbit.get_accounts()
            bn_acc = live_engine.binance.get_account()
            portfolio = _init_portfolio_from_exchange(
                cfg,
                up_acc,
                bn_acc,
                fx=float(fx),
                upbit_prices=upbit_prices,
                binance_prices=binance_prices,
            )
            event_logger.log(
                "portfolio_seed",
                {
                    "source": "exchange_api_capped_yaml",
                    "upbit_currencies": list({a.get("currency") for a in up_acc}),
                    "note": "Each leg min(weight-split, initial_*) from multi.yaml",
                },
            )
            logger.info(
                "Live portfolio: exchange balances capped per coin to YAML initial_* "
                "(Upbit KRW split + cap; same for USDT / coin qty)"
            )
    else:
        portfolio = _init_portfolio(cfg, upbit_prices, binance_prices)
        event_logger.log("portfolio_seed", {"source": "config_and_ws_prices"})

    app_version = (os.getenv("ARB_APP_VERSION", "v1.1") or "v1.1").strip() or "v1.1"
    logger.info(
        "Started multi-coin arb: %s, mode=%s, ARB_APP_VERSION=%s",
        [c.symbol for c in cfg.coins],
        cfg.mode,
        app_version,
    )
    event_logger.log(
        "app_start",
        {"version": app_version, "coins": [c.symbol for c in cfg.coins], "mode": cfg.mode},
    )
    for coin in cfg.coins:
        b = portfolio.get(coin.symbol)
        logger.info(f"  {coin.symbol}: upbit_krw={b.upbit_krw:.0f}, upbit_coin={b.upbit_coin:.6f}, "
                     f"binance_usdt={b.binance_usdt:.2f}, binance_coin={b.binance_coin:.6f}")

    csv_recorder = MultiRunCsvRecorder()
    last_fx = fx
    notifier = TelegramNotifier()
    notifier.on_start(cfg.mode, [c.symbol for c in cfg.coins], float(fx), app_version=app_version)

    feeds_ok, _feed_issues = _markets_data_ok(cfg.coins, upbit_prices, binance_prices)
    cloud_flag = os.getenv("ARB_CLOUD_DEPLOY", "").strip().lower()
    if cloud_flag in ("1", "true", "yes", "cloud"):
        host_hint = (os.getenv("ARB_CLOUD_HOST_LABEL", "") or "").strip() or platform.node()
        notifier.on_cloud_deploy_ready(
            mode=cfg.mode,
            coins=[c.symbol for c in cfg.coins],
            fx=float(fx),
            feeds_ok=feeds_ok,
            host_hint=host_hint,
            app_version=app_version,
        )

    heartbeat_sec = float(os.getenv("ARB_MULTI_HEARTBEAT_SEC", "300"))
    tg_hourly_sec = float(os.getenv("TELEGRAM_HOUR_SUMMARY_SEC", "1800"))
    tg_export_sec = float(os.getenv("TELEGRAM_EXPORT_SEC", "1800"))
    health_stale_sec = float(os.getenv("TELEGRAM_HEALTH_STALE_SEC", "180"))
    imbalance_alert_hours = float(os.getenv("TELEGRAM_IMBALANCE_ALERT_HOURS", "4"))
    ui_state: dict = {
        "baseline_equity": None,
        "baseline_upbit_total_krw": None,
        "baseline_binance_total_krw": None,
        "last_hb_mono": time.monotonic(),
        "last_all_markets_ok_mono": None,
        "last_trade_exec_mono": {},
        "imbalance_alert": {"started": {}, "last_alert": {}},
        "fx_last_update_mono": 0.0,   # FX 스탈 감지용: KRW-USDT 마지막 수신 시각
    }
    last_tg_summary_mono = time.monotonic()
    last_tg_export_mono = time.monotonic()
    tg_loops_at_period_start = 0
    tg_period: dict[str, float | int] = {
        "kimchi": 0,
        "reverse": 0,
        "rebalance": 0,
        "pnl": 0.0,
        "fee": 0.0,
        "errors": 0,
    }
    first_loop_mode_sent = False
    logger.info(
        "터미널 구동확인 로그: 매 %.0f초마다 출력 (기본 300초=약5분, ARB_MULTI_HEARTBEAT_SEC 로 변경)",
        heartbeat_sec,
    )
    if notifier.enabled and tg_hourly_sec > 0:
        logger.info(
            "텔레그램 운영 요약: 매 %.0f초 (TELEGRAM_HOUR_SUMMARY_SEC, 기본 1800=30분)",
            tg_hourly_sec,
        )
        logger.info(
            "텔레그램 구동 상태: 시세 단절 판정 %.0f초 (TELEGRAM_HEALTH_STALE_SEC, 기본 180)",
            health_stale_sec,
        )
    if notifier.enabled and tg_export_sec > 0:
        logger.info(
            "텔레그램 누적 거래 CSV 전송: 매 %.0f초 (TELEGRAM_EXPORT_SEC, 기본 1800=30분, 끄려면 0)",
            tg_export_sec,
        )

    loop_count = 0
    try:
        while True:
            loop_count += 1

            # Update FX + 스탈 감지
            fx_data = upbit_prices.get("KRW-USDT", {})
            if fx_data.get("trade_price", 0) > 0:
                fx = fx_data["trade_price"]
                ui_state["fx_last_update_mono"] = time.monotonic()
            last_fx = fx
            # FX 환율이 오래 갱신 안 됐으면 경고
            fx_stale_limit = float(cfg.coins[0].fx_stale_sec) if cfg.coins else 60.0
            fx_last_upd = float(ui_state.get("fx_last_update_mono") or 0.0)
            if fx_last_upd > 0 and (time.monotonic() - fx_last_upd) > fx_stale_limit:
                logger.warning(
                    "FX 환율(KRW-USDT) %.1f초 이상 미갱신 — 현재값 %.2f 사용 중 (WS 점검 필요)",
                    time.monotonic() - fx_last_upd, fx,
                )

            csv_recorder.on_loop_tick(portfolio, cfg.coins, fx)

            equity_now = _equity_total_krw(portfolio, cfg.coins, upbit_prices, binance_prices, fx)
            if ui_state["baseline_equity"] is None and equity_now > 0:
                if live_seed_from_config:
                    seed_totals = _yaml_seed_totals_krw(cfg.coins)
                    ui_state["baseline_equity"] = float(seed_totals["combined_total_krw"])
                    ui_state["baseline_upbit_total_krw"] = float(seed_totals["upbit_total_krw"])
                    ui_state["baseline_binance_total_krw"] = float(seed_totals["binance_total_krw"])
                    logger.info(
                        "시작 기준을 YAML 시드로 고정했습니다: 총 %,.0f원 (업비트 %,.0f / 바이낸스 %,.0f)",
                        float(seed_totals["combined_total_krw"]),
                        float(seed_totals["upbit_total_krw"]),
                        float(seed_totals["binance_total_krw"]),
                    )
                else:
                    ui_state["baseline_equity"] = equity_now
                    ex_totals = _exchange_asset_totals_krw(
                        portfolio, cfg.coins, upbit_prices, binance_prices, fx
                    )
                    ui_state["baseline_upbit_total_krw"] = float(ex_totals["upbit_total_krw"])
                    ui_state["baseline_binance_total_krw"] = float(ex_totals["binance_total_krw"])
                logger.info(
                    f"시작 총자산(원화평가) 기준을 잡았습니다: {ui_state['baseline_equity']:,.0f}원 "
                    "(이후 수익률은 이 금액 대비)"
                )

            if notifier.enabled and (not first_loop_mode_sent) and loop_count == 1:
                notifier.on_first_loop_mode(
                    mode=cfg.mode,
                    enable_live_orders=cfg.enable_live_orders,
                    live_dry_run=cfg.live_dry_run,
                    config_path=os.getenv("ARB_MULTI_CONFIG", "configs/multi.yaml"),
                    app_version=app_version,
                    yaml_seed_total_krw=_yaml_seed_totals_krw(cfg.coins)["combined_total_krw"],
                    initial_asset_plan_text=_initial_asset_plan_text(cfg.coins),
                )
                first_loop_mode_sent = True

            for coin in cfg.coins:
                try:
                    _process_coin(
                        coin,
                        portfolio,
                        upbit_prices,
                        binance_prices,
                        fx,
                        event_logger,
                        live_engine,
                        csv_recorder,
                        notifier=notifier,
                        run_mode=cfg.mode,
                        tg_period=tg_period,
                        loop_count=loop_count,
                        ui_state=ui_state,
                        all_coins=cfg.coins,
                        equity_now=equity_now,
                    )
                except HedgeHaltError as exc:
                    event_logger.log("live_halt", {"coin": coin.symbol, "message": str(exc)})
                    logger.error("%s HALT: %s", coin.symbol, exc)
                    tg_period["errors"] = int(tg_period["errors"]) + 1
                    notifier.on_live_halt(coin.symbol, str(exc))
                    raise
                except Exception as exc:
                    event_logger.log("error", {"coin": coin.symbol, "message": str(exc)})
                    logger.error(f"{coin.symbol} error: {exc}")
                    tg_period["errors"] = int(tg_period["errors"]) + 1
                    notifier.on_error(coin.symbol, str(exc))

            mk_ok, _mk_issues = _markets_data_ok(cfg.coins, upbit_prices, binance_prices)
            if mk_ok:
                ui_state["last_all_markets_ok_mono"] = time.monotonic()

            now_mono = time.monotonic()
            if now_mono - float(ui_state["last_hb_mono"]) >= heartbeat_sec:
                _log_multi_status_kr(
                    title="구동확인",
                    loop_count=loop_count,
                    equity=equity_now,
                    baseline=ui_state["baseline_equity"],
                    portfolio=portfolio,
                    coins=cfg.coins,
                )
                ui_state["last_hb_mono"] = now_mono

            if notifier.enabled and tg_hourly_sec > 0:
                if time.monotonic() - last_tg_summary_mono >= tg_hourly_sec:
                    hb = _tg_hour_bucket_kst()
                    health = _compute_hourly_health(
                        cfg.coins,
                        upbit_prices,
                        binance_prices,
                        ui_state,
                        tg_period,
                        health_stale_sec,
                    )
                    loops_period = loop_count - tg_loops_at_period_start
                    event_logger.log(
                        "tg_hourly_health",
                        {
                            "hour_bucket_kst": hb,
                            "health_ok": health["ok"],
                            "health_title": health["title"],
                            "health_detail": health["detail"],
                            "data_ok_now": health["data_ok_now"],
                            "issues": health["issues"],
                            "stale_sec_since_ok": health["stale_sec_since_ok"],
                            "errors_in_period": health["errors_in_period"],
                            "loops_in_period": loops_period,
                        },
                    )
                    ex_now = _exchange_asset_totals_krw(
                        portfolio, cfg.coins, upbit_prices, binance_prices, fx
                    )
                    notifier.on_hourly_summary(
                        hour_bucket=hb,
                        loops=loops_period,
                        kimchi_cnt=int(tg_period["kimchi"]),
                        reverse_cnt=int(tg_period["reverse"]),
                        rebalance_cnt=int(tg_period["rebalance"]),
                        pnl_krw=float(tg_period["pnl"]),
                        fee_krw=float(tg_period["fee"]),
                        fx=fx,
                        equity=equity_now,
                        health_status=str(health["title"]),
                        health_detail=str(health["detail"]),
                        upbit_total_krw=float(ex_now["upbit_total_krw"]),
                        binance_total_krw=float(ex_now["binance_total_krw"]),
                        baseline_upbit_total_krw=(
                            float(ui_state["baseline_upbit_total_krw"])
                            if ui_state.get("baseline_upbit_total_krw") is not None
                            else None
                        ),
                        baseline_binance_total_krw=(
                            float(ui_state["baseline_binance_total_krw"])
                            if ui_state.get("baseline_binance_total_krw") is not None
                            else None
                        ),
                        position_state=_position_state_summary(portfolio, cfg.coins),
                    )
                    alerts = _check_portfolio_imbalance(
                        portfolio,
                        cfg.coins,
                        now_mono=time.monotonic(),
                        state=ui_state["imbalance_alert"],
                        threshold_hours=imbalance_alert_hours,
                    )
                    for alert in alerts:
                        notifier.on_portfolio_imbalance(
                            alert["symbol"],
                            upbit_krw=float(alert["upbit_krw"]),
                            upbit_coin=float(alert["upbit_coin"]),
                            binance_usdt=float(alert["binance_usdt"]),
                            binance_coin=float(alert["binance_coin"]),
                            elapsed_hours=float(alert["elapsed_hours"]),
                        )
                        event_logger.log(
                            "portfolio_imbalance_alert",
                            {
                                "symbol": alert["symbol"],
                                "elapsed_hours": float(alert["elapsed_hours"]),
                                "threshold_hours": imbalance_alert_hours,
                                "upbit_krw": float(alert["upbit_krw"]),
                                "upbit_coin": float(alert["upbit_coin"]),
                                "binance_usdt": float(alert["binance_usdt"]),
                                "binance_coin": float(alert["binance_coin"]),
                            },
                        )
                    tg_period["kimchi"] = 0
                    tg_period["reverse"] = 0
                    tg_period["rebalance"] = 0
                    tg_period["pnl"] = 0.0
                    tg_period["fee"] = 0.0
                    tg_period["errors"] = 0
                    tg_loops_at_period_start = loop_count
                    last_tg_summary_mono = time.monotonic()

            if notifier.enabled and tg_export_sec > 0:
                if time.monotonic() - last_tg_export_mono >= tg_export_sec:
                    trades_csv_path = str(csv_recorder.trades_path)
                    trade_rows = _csv_data_rows(trades_csv_path)
                    if trade_rows > 0:
                        sent = notifier.on_trade_export_csv(
                            file_path=trades_csv_path,
                            rows=trade_rows,
                            interval_sec=tg_export_sec,
                        )
                        event_logger.log(
                            "tg_trade_export",
                            {
                                "path": trades_csv_path,
                                "rows": trade_rows,
                                "interval_sec": tg_export_sec,
                                "sent": sent,
                            },
                        )
                    else:
                        notifier.on_trade_export_empty()
                    last_tg_export_mono = time.monotonic()

            if max_iterations > 0 and loop_count >= max_iterations:
                break

            await asyncio.sleep(cfg.loop_interval_sec)
    finally:
        csv_recorder.finalize(portfolio, cfg.coins, last_fx)
        notifier.on_stop(loop_count, portfolio.realized_pnl_krw)

    # Cleanup
    for t in ws_tasks:
        t.cancel()

    # Final summary
    logger.info("=== Final Portfolio ===")
    for coin in cfg.coins:
        b = portfolio.get(coin.symbol)
        logger.info(f"  {coin.symbol}: upbit_krw={b.upbit_krw:.0f}, upbit_coin={b.upbit_coin:.6f}, "
                     f"binance_usdt={b.binance_usdt:.2f}, binance_coin={b.binance_coin:.6f}, "
                     f"trades={b.total_trades}, rebalances={b.total_rebalances}, "
                     f"fees={b.realized_fee_krw:.0f}")
    logger.info(f"Total realized PnL: {portfolio.realized_pnl_krw:.0f} KRW")
    logger.info(
        "CSV: trades=%s hourly=%s (append; hourly row each KST hour + final flush on exit)",
        csv_recorder.trades_path,
        csv_recorder.hourly_path,
    )


def _process_coin(
    coin: CoinConfig,
    portfolio: RebalancePortfolio,
    upbit_prices: dict,
    binance_prices: dict,
    fx: float,
    event_logger: EventLogger,
    live_engine: MultiLiveExecutionEngine | None,
    csv_recorder: MultiRunCsvRecorder,
    notifier: TelegramNotifier,
    run_mode: str,
    tg_period: dict[str, float | int],
    *,
    loop_count: int,
    ui_state: dict,
    all_coins: list[CoinConfig],
    equity_now: float,
) -> None:
    """Evaluate and execute decision for one coin."""
    up_data = upbit_prices.get(coin.upbit_market, {})
    bn_data = binance_prices.get(coin.binance_symbol, {})

    upbit_price = up_data.get("trade_price", 0.0)
    binance_price = bn_data.get("bid_price", 0.0)
    binance_ask = bn_data.get("ask_price", 0.0)

    if upbit_price <= 0 or binance_price <= 0:
        return  # no data yet

    b = portfolio.get(coin.symbol)

    decision = decide(
        symbol=coin.symbol,
        upbit_price_krw=upbit_price,
        binance_bid_price_usdt=binance_price,   # bid: 역프 수익성 + 임계값 기준
        binance_ask_price_usdt=binance_ask,     # ask: 김프 수익성 기준 (실제 매수 체결가)
        fx=fx,
        upbit_krw=b.upbit_krw,
        upbit_coin=b.upbit_coin,
        binance_usdt=b.binance_usdt,
        binance_coin=b.binance_coin,
        entry_threshold_rate=coin.entry_threshold_rate,
        fee_upbit_rate=coin.fee_upbit_rate,
        fee_binance_rate=coin.fee_binance_rate,
        slippage_upbit_rate=coin.slippage_upbit_rate,
        slippage_binance_rate=coin.slippage_binance_rate,
        transfer_fee_coin_base_utob=coin.transfer_fee_upbit_to_binance_base,
        transfer_fee_coin_base_btou=coin.transfer_fee_binance_to_upbit_base,
        fx_conversion_fee_rate=coin.fx_conversion_fee_rate,
        rebalance_profit_multiplier=coin.rebalance_profit_multiplier,
        rebalance_imbalance_threshold=coin.rebalance_imbalance_threshold,
        daily_rebalances=b.daily_rebalances,
        max_daily_rebalances=coin.max_daily_rebalances,
        emergency_cash_ratio=coin.emergency_cash_ratio,
        emergency_coin_ratio=coin.emergency_coin_ratio,
        target_portfolio_ratio=coin.target_portfolio_ratio,
    )

    if decision.action == Action.TRADE_KIMCHI:
        now_mono = time.monotonic()
        last_exec_mono = float(ui_state["last_trade_exec_mono"].get(coin.symbol, 0.0))
        if last_exec_mono > 0 and (now_mono - last_exec_mono) < float(coin.cooldown_sec):
            remain = max(float(coin.cooldown_sec) - (now_mono - last_exec_mono), 0.0)
            event_logger.log(
                "trade_cooldown_skip",
                {
                    "symbol": coin.symbol,
                    "action": "TRADE_KIMCHI",
                    "cooldown_sec": float(coin.cooldown_sec),
                    "remaining_sec": remain,
                },
            )
            return
        if live_engine is not None:
            live_res = live_engine.execute_kimchi(
                coin,
                b,
                expected_upbit_price_krw=float(upbit_price),
                expected_binance_price_usdt=float(binance_ask or binance_price),
            )
            event_logger.log(
                "multi_live_exec",
                {"symbol": coin.symbol, "leg": "TRADE_KIMCHI", **live_res},
            )
            st = live_res.get("status")
            if st in ("LIVE_ERROR", "LIVE_ERROR_UPBIT"):
                tg_period["errors"] = int(tg_period["errors"]) + 1
                notifier.on_error(coin.symbol, str(live_res.get("error", "")))
                return
            if st in ("LIVE_ERROR_HEDGE_RECOVERED", "LIVE_ERROR_HEDGE_FAIL"):
                tg_period["errors"] = int(tg_period["errors"]) + 1
                notifier.on_hedge_incomplete(
                    coin.symbol,
                    str(live_res.get("error", "")),
                    recovered=bool(live_res.get("recovered", False)),
                )
                return
            if st == "LIVE_HALT":
                tg_period["errors"] = int(tg_period["errors"]) + 1
                notifier.on_hedge_incomplete(
                    coin.symbol,
                    str(live_res.get("error", "")),
                    recovered=False,
                )
                raise HedgeHaltError(
                    f"헤지 복구 실패: {coin.symbol} / {live_res.get('error', '')}"
                )
            if st not in ("LIVE_EXECUTED", "LIVE_DRY_RUN"):
                logger.warning("[%s] KIMCHI live not applied: %s", coin.symbol, live_res)
                return
        event = portfolio.execute_kimchi_trade(
            symbol=coin.symbol,
            upbit_price_krw=upbit_price,
            binance_price_usdt=binance_ask,  # buy at ask
            fx=fx,
            fee_upbit_rate=coin.fee_upbit_rate,
            fee_binance_rate=coin.fee_binance_rate,
            slippage_upbit_rate=coin.slippage_upbit_rate,
            slippage_binance_rate=coin.slippage_binance_rate,
        )
        if live_engine is not None:
            slip = live_res.get("slippage", {})
            if isinstance(slip, dict):
                event.actual_slippage_upbit = slip.get("upbit")
                event.actual_slippage_binance = slip.get("binance")
                if event.actual_slippage_upbit is not None or event.actual_slippage_binance is not None:
                    logger.info(
                        "[SLIPPAGE] %s kimchi upbit=%s binance=%s",
                        coin.symbol,
                        f"{float(event.actual_slippage_upbit):.4%}" if event.actual_slippage_upbit is not None else "n/a",
                        f"{float(event.actual_slippage_binance):.4%}" if event.actual_slippage_binance is not None else "n/a",
                    )
        event_logger.log("trade", event.__dict__)
        line = (
            f"[{coin.symbol}] KIMCHI TRADE: premium={decision.premium:.4%}, "
            f"pnl={event.pnl_krw:.0f}, fee={event.fee_krw:.0f}"
        )
        logger.info(line)
        csv_recorder.record_trade(event, line)
        _log_multi_status_kr(
            title=f"거래완료·{coin.symbol}·김치",
            loop_count=loop_count,
            equity=equity_now,
            baseline=ui_state.get("baseline_equity"),
            portfolio=portfolio,
            coins=all_coins,
        )
        notifier.on_trade(
            action="TRADE_KIMCHI",
            symbol=coin.symbol,
            premium=event.premium,
            pnl_krw=event.pnl_krw,
            fee_krw=event.fee_krw,
            trade_qty=event.trade_qty,
            upbit_price=upbit_price,
            binance_price=float(binance_ask or binance_price),
            fx=fx,
            mode=run_mode,
        )
        tg_period["kimchi"] = int(tg_period["kimchi"]) + 1
        tg_period["pnl"] = float(tg_period["pnl"]) + event.pnl_krw
        tg_period["fee"] = float(tg_period["fee"]) + event.fee_krw
        ui_state["last_trade_exec_mono"][coin.symbol] = time.monotonic()

    elif decision.action == Action.TRADE_REVERSE:
        now_mono = time.monotonic()
        last_exec_mono = float(ui_state["last_trade_exec_mono"].get(coin.symbol, 0.0))
        if last_exec_mono > 0 and (now_mono - last_exec_mono) < float(coin.cooldown_sec):
            remain = max(float(coin.cooldown_sec) - (now_mono - last_exec_mono), 0.0)
            event_logger.log(
                "trade_cooldown_skip",
                {
                    "symbol": coin.symbol,
                    "action": "TRADE_REVERSE",
                    "cooldown_sec": float(coin.cooldown_sec),
                    "remaining_sec": remain,
                },
            )
            return
        if live_engine is not None:
            live_res = live_engine.execute_reverse(
                coin,
                b,
                expected_upbit_price_krw=float(upbit_price),
                expected_binance_price_usdt=float(binance_price),
            )
            event_logger.log(
                "multi_live_exec",
                {"symbol": coin.symbol, "leg": "TRADE_REVERSE", **live_res},
            )
            st = live_res.get("status")
            if st in ("LIVE_ERROR", "LIVE_ERROR_UPBIT"):
                tg_period["errors"] = int(tg_period["errors"]) + 1
                notifier.on_error(coin.symbol, str(live_res.get("error", "")))
                return
            if st in ("LIVE_ERROR_HEDGE_RECOVERED", "LIVE_ERROR_HEDGE_FAIL"):
                tg_period["errors"] = int(tg_period["errors"]) + 1
                notifier.on_hedge_incomplete(
                    coin.symbol,
                    str(live_res.get("error", "")),
                    recovered=bool(live_res.get("recovered", False)),
                )
                return
            if st == "LIVE_HALT":
                tg_period["errors"] = int(tg_period["errors"]) + 1
                notifier.on_hedge_incomplete(
                    coin.symbol,
                    str(live_res.get("error", "")),
                    recovered=False,
                )
                raise HedgeHaltError(
                    f"헤지 복구 실패: {coin.symbol} / {live_res.get('error', '')}"
                )
            if st not in ("LIVE_EXECUTED", "LIVE_DRY_RUN"):
                logger.warning("[%s] REVERSE live not applied: %s", coin.symbol, live_res)
                return
        event = portfolio.execute_reverse_trade(
            symbol=coin.symbol,
            upbit_price_krw=upbit_price,
            binance_price_usdt=binance_price,  # sell at bid
            fx=fx,
            fee_upbit_rate=coin.fee_upbit_rate,
            fee_binance_rate=coin.fee_binance_rate,
            slippage_upbit_rate=coin.slippage_upbit_rate,
            slippage_binance_rate=coin.slippage_binance_rate,
        )
        if live_engine is not None:
            slip = live_res.get("slippage", {})
            if isinstance(slip, dict):
                event.actual_slippage_upbit = slip.get("upbit")
                event.actual_slippage_binance = slip.get("binance")
                if event.actual_slippage_upbit is not None or event.actual_slippage_binance is not None:
                    logger.info(
                        "[SLIPPAGE] %s reverse upbit=%s binance=%s",
                        coin.symbol,
                        f"{float(event.actual_slippage_upbit):.4%}" if event.actual_slippage_upbit is not None else "n/a",
                        f"{float(event.actual_slippage_binance):.4%}" if event.actual_slippage_binance is not None else "n/a",
                    )
        event_logger.log("trade", event.__dict__)
        line = (
            f"[{coin.symbol}] REVERSE TRADE: premium={decision.premium:.4%}, "
            f"pnl={event.pnl_krw:.0f}, fee={event.fee_krw:.0f}"
        )
        logger.info(line)
        csv_recorder.record_trade(event, line)
        _log_multi_status_kr(
            title=f"거래완료·{coin.symbol}·역프",
            loop_count=loop_count,
            equity=equity_now,
            baseline=ui_state.get("baseline_equity"),
            portfolio=portfolio,
            coins=all_coins,
        )
        notifier.on_trade(
            action="TRADE_REVERSE",
            symbol=coin.symbol,
            premium=event.premium,
            pnl_krw=event.pnl_krw,
            fee_krw=event.fee_krw,
            trade_qty=event.trade_qty,
            upbit_price=upbit_price,
            binance_price=float(binance_price),
            fx=fx,
            mode=run_mode,
        )
        tg_period["reverse"] = int(tg_period["reverse"]) + 1
        tg_period["pnl"] = float(tg_period["pnl"]) + event.pnl_krw
        tg_period["fee"] = float(tg_period["fee"]) + event.fee_krw
        ui_state["last_trade_exec_mono"][coin.symbol] = time.monotonic()

    elif decision.action == Action.REBALANCE_B_TO_U:
        if live_engine is not None:
            notifier.on_rebalance_signal(
                coin.symbol,
                "REBALANCE B→U (바이낸스 코인→업비트, 업비트 현금→바이낸스 USDT)",
                decision.premium,
                note="라이브: 온체인 수동 이체 후 재가동",
            )
            event_logger.log(
                "rebalance_skipped_live",
                {
                    "symbol": coin.symbol,
                    "action": "REBALANCE_B_TO_U",
                    "reason": "on_chain_transfer_not_automated",
                },
            )
            logger.warning(
                "[%s] REBALANCE_B_TO_U skipped in live (manual transfer required)",
                coin.symbol,
            )
            # 수동 이체 모드에서도 내부 포트폴리오 상태를 즉시 업데이트.
            # 업데이트 하지 않으면 0.5초마다 동일한 imbalance가 재감지되어 알럿이 무한 반복된다.
            # 사용자가 실제 이체를 완료하면 봇 재시작으로 실잔고와 동기화할 수 있다.
            portfolio.execute_rebalance(
                symbol=coin.symbol,
                upbit_price_krw=upbit_price,
                binance_price_usdt=binance_price,
                fx=fx,
                transfer_fee_coin_base=coin.transfer_fee_binance_to_upbit_base,
                fx_conversion_fee_rate=coin.fx_conversion_fee_rate,
                direction="binance_to_upbit",
            )
            return
        notifier.on_rebalance_signal(
            coin.symbol,
            "REBALANCE B→U",
            decision.premium,
            note="페이퍼: 시뮬 잔고 즉시 반영",
        )
        event = portfolio.execute_rebalance(
            symbol=coin.symbol,
            upbit_price_krw=upbit_price,
            binance_price_usdt=binance_price,
            fx=fx,
            transfer_fee_coin_base=coin.transfer_fee_binance_to_upbit_base,
            fx_conversion_fee_rate=coin.fx_conversion_fee_rate,
            direction="binance_to_upbit",
        )
        event_logger.log("rebalance", event.__dict__)
        line = f"[{coin.symbol}] REBALANCE B→U: cost={event.fee_krw:.0f}"
        logger.info(line)
        csv_recorder.record_trade(event, line)
        _log_multi_status_kr(
            title=f"거래완료·{coin.symbol}·리밸런스B→U",
            loop_count=loop_count,
            equity=equity_now,
            baseline=ui_state.get("baseline_equity"),
            portfolio=portfolio,
            coins=all_coins,
        )
        tg_period["rebalance"] = int(tg_period["rebalance"]) + 1
        tg_period["pnl"] = float(tg_period["pnl"]) + event.pnl_krw
        tg_period["fee"] = float(tg_period["fee"]) + event.fee_krw

    elif decision.action == Action.REBALANCE_U_TO_B:
        if live_engine is not None:
            notifier.on_rebalance_signal(
                coin.symbol,
                "REBALANCE U→B (업비트 코인→바이낸스, 바이낸스 USDT→업비트 원화)",
                decision.premium,
                note="라이브: 온체인 수동 이체 후 재가동",
            )
            event_logger.log(
                "rebalance_skipped_live",
                {
                    "symbol": coin.symbol,
                    "action": "REBALANCE_U_TO_B",
                    "reason": "on_chain_transfer_not_automated",
                },
            )
            logger.warning(
                "[%s] REBALANCE_U_TO_B skipped in live (manual transfer required)",
                coin.symbol,
            )
            # 수동 이체 모드에서도 내부 포트폴리오 상태를 즉시 업데이트.
            # 업데이트 하지 않으면 0.5초마다 동일한 imbalance가 재감지되어 알럿이 무한 반복된다.
            # 사용자가 실제 이체를 완료하면 봇 재시작으로 실잔고와 동기화할 수 있다.
            portfolio.execute_rebalance(
                symbol=coin.symbol,
                upbit_price_krw=upbit_price,
                binance_price_usdt=binance_price,
                fx=fx,
                transfer_fee_coin_base=coin.transfer_fee_upbit_to_binance_base,
                fx_conversion_fee_rate=coin.fx_conversion_fee_rate,
                direction="upbit_to_binance",
            )
            return
        notifier.on_rebalance_signal(
            coin.symbol,
            "REBALANCE U→B",
            decision.premium,
            note="페이퍼: 시뮬 잔고 즉시 반영",
        )
        event = portfolio.execute_rebalance(
            symbol=coin.symbol,
            upbit_price_krw=upbit_price,
            binance_price_usdt=binance_price,
            fx=fx,
            transfer_fee_coin_base=coin.transfer_fee_upbit_to_binance_base,
            fx_conversion_fee_rate=coin.fx_conversion_fee_rate,
            direction="upbit_to_binance",
        )
        event_logger.log("rebalance", event.__dict__)
        line = f"[{coin.symbol}] REBALANCE U→B: cost={event.fee_krw:.0f}"
        logger.info(line)
        csv_recorder.record_trade(event, line)
        _log_multi_status_kr(
            title=f"거래완료·{coin.symbol}·리밸런스U→B",
            loop_count=loop_count,
            equity=equity_now,
            baseline=ui_state.get("baseline_equity"),
            portfolio=portfolio,
            coins=all_coins,
        )
        tg_period["rebalance"] = int(tg_period["rebalance"]) + 1
        tg_period["pnl"] = float(tg_period["pnl"]) + event.pnl_krw
        tg_period["fee"] = float(tg_period["fee"]) + event.fee_krw


def main() -> None:
    args = parse_args()
    cfg = load_multi_config(args.config)
    asyncio.run(main_loop(cfg, max_iterations=args.iterations))


if __name__ == "__main__":
    main()
