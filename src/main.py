from __future__ import annotations

import argparse
import atexit
import csv
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.config import load_config
from src.execution.live_engine import LiveExecutionEngine
from src.execution.paper_engine import PaperExecutionEngine
from src.execution.risk_guard import RiskGuard
from src.execution.router import ExecutionRouter
from src.exchanges.binance_client import BinanceClient
from src.exchanges.binance_trading_client import BinanceTradingClient
from src.exchanges.fx_upbit import fetch_fx_krw_per_usdt
from src.exchanges.upbit_client import UpbitClient
from src.exchanges.upbit_trading_client import UpbitTradingClient
from src.logging.event_logger import EventLogger
from src.marketdata import MarketDataService
from src.state.portfolio import PortfolioState
from src.strategy.signal import SignalEngine
from src.strategy.spread_calc import calc_edge


@dataclass(slots=True)
class RuntimeStats:
    start_capital_krw: float
    total_fees_krw: float = 0.0
    buy_count: int = 0
    sell_count: int = 0
    close_count: int = 0
    loop_count: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upbit-Binance arbitrage runner")
    parser.add_argument(
        "--config",
        default="configs/default.yaml",
        help="Path to YAML config file",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="Loop iterations. 0 means infinite loop.",
    )
    parser.add_argument(
        "--allow-duplicate",
        action="store_true",
        help="Allow duplicate process with same config lock.",
    )
    return parser.parse_args()


def _lock_path_for_config(config_path: str) -> Path:
    cfg_name = Path(config_path).stem
    lock_dir = Path("logs")
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / f"run_{cfg_name}.lock"


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _acquire_instance_lock(lock_path: Path, allow_duplicate: bool) -> None:
    if allow_duplicate:
        return
    if lock_path.exists():
        raw = lock_path.read_text(encoding="utf-8").strip()
        try:
            existing_pid = int(raw)
        except ValueError:
            existing_pid = -1
        if _is_pid_running(existing_pid):
            raise RuntimeError(
                f"duplicate execution detected for this config (pid={existing_pid}). "
                "Use --allow-duplicate to bypass."
            )
    lock_path.write_text(str(os.getpid()), encoding="utf-8")

    def _cleanup() -> None:
        try:
            if lock_path.exists() and lock_path.read_text(encoding="utf-8").strip() == str(os.getpid()):
                lock_path.unlink()
        except Exception:
            pass

    atexit.register(_cleanup)


def _estimate_order_fee_krw(edge_upbit_mid: float, edge_binance_mid_krw: float, size_base: float, fee_upbit: float, fee_binance: float) -> float:
    return (edge_upbit_mid * size_base * fee_upbit) + (edge_binance_mid_krw * size_base * fee_binance)


def _print_runtime_summary(stats: RuntimeStats, realized_pnl_krw: float) -> None:
    cumulative_profit = realized_pnl_krw + stats.total_fees_krw
    roi = (realized_pnl_krw / stats.start_capital_krw) if stats.start_capital_krw > 0 else 0.0
    print(f"시작자본: {stats.start_capital_krw:,.0f} KRW")
    print(f"ROI: {roi*100:.2f}%")
    print(f"누적수익금: {cumulative_profit:,.0f} KRW")
    print(f"거래수수료(추정): {stats.total_fees_krw:,.0f} KRW")
    print(f"순수익: {realized_pnl_krw:,.0f} KRW")
    print(f"매수횟수: {stats.buy_count} | 매도횟수: {stats.sell_count} | 청산횟수: {stats.close_count}")


def _append_trade_csv(
    csv_path: Path,
    *,
    ts_kst: str,
    ts_utc: str,
    action: str,
    edge_rate: float,
    upbit_mid_krw: float,
    binance_mid_krw: float,
    live_status: str,
    realized_pnl_krw: float,
    fees_est_krw: float,
    buy_count: int,
    sell_count: int,
    close_count: int,
    upbit_order_id: str,
    binance_order_id: str,
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(
                [
                    "ts_kst",
                    "ts_utc",
                    "action",
                    "edge_rate",
                    "upbit_mid_krw",
                    "binance_mid_krw",
                    "live_status",
                    "realized_pnl_krw",
                    "fees_est_krw",
                    "buy_count",
                    "sell_count",
                    "close_count",
                    "upbit_order_id",
                    "binance_order_id",
                ]
            )
        writer.writerow(
            [
                ts_kst,
                ts_utc,
                action,
                f"{edge_rate:.8f}",
                f"{upbit_mid_krw:.8f}",
                f"{binance_mid_krw:.8f}",
                live_status,
                f"{realized_pnl_krw:.8f}",
                f"{fees_est_krw:.8f}",
                buy_count,
                sell_count,
                close_count,
                upbit_order_id,
                binance_order_id,
            ]
        )


def _now_utc_kst() -> tuple[str, str]:
    now_utc = datetime.now(tz=timezone.utc)
    kst = now_utc.astimezone(timezone(timedelta(hours=9)))
    return now_utc.isoformat(), kst.isoformat()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    _acquire_instance_lock(_lock_path_for_config(args.config), allow_duplicate=args.allow_duplicate)

    portfolio = PortfolioState()
    marketdata = MarketDataService(upbit=UpbitClient(), binance=BinanceClient())
    signal = SignalEngine(
        entry_threshold_rate=cfg.entry_threshold_rate,
        exit_threshold_rate=cfg.exit_threshold_rate,
        cooldown_sec=cfg.cooldown_sec,
        max_position_hold_sec=cfg.max_position_hold_sec,
    )
    risk_guard = RiskGuard(config=cfg.risk)
    live_engine = None
    if cfg.mode == "live":
        upbit_access = os.getenv("UPBIT_ACCESS_KEY", "")
        upbit_secret = os.getenv("UPBIT_SECRET_KEY", "")
        binance_key = os.getenv("BINANCE_API_KEY", "")
        binance_secret = os.getenv("BINANCE_API_SECRET", "")
        if not all([upbit_access, upbit_secret, binance_key, binance_secret]):
            raise RuntimeError("missing live API credentials in environment")
        live_engine = LiveExecutionEngine(
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
            upbit_market=cfg.upbit_market,
            binance_symbol=cfg.binance_symbol,
            dry_run=cfg.live_dry_run,
        )

    router = ExecutionRouter(
        mode=cfg.mode,
        enable_live_orders=cfg.enable_live_orders,
        paper_engine=PaperExecutionEngine(portfolio=portfolio),
        live_engine=live_engine,
    )
    logger = EventLogger(path="logs/events.jsonl")
    trades_csv_path = Path("logs/trades_live.csv")
    stats = RuntimeStats(start_capital_krw=cfg.risk.max_notional_krw * 4.0)
    ts_utc, ts_kst = _now_utc_kst()
    current_fx = fetch_fx_krw_per_usdt(cfg.fx_krw_per_usdt, timeout_sec=min(cfg.order_timeout_sec, 5.0))
    startup_payload = {
        "config": args.config,
        "mode": cfg.mode,
        "marketdata_mode": cfg.marketdata_mode,
        "symbol": cfg.symbol,
        "entry_threshold_rate": cfg.entry_threshold_rate,
        "exit_threshold_rate": cfg.exit_threshold_rate,
        "trade_size_base": cfg.trade_size_base,
        "max_notional_krw": cfg.risk.max_notional_krw,
        "max_daily_loss_krw": cfg.risk.max_daily_loss_krw,
        "fx_krw_per_usdt": current_fx,
        "fx_krw_per_usdt_config_fallback": cfg.fx_krw_per_usdt,
        "fx_refresh_sec": cfg.fx_refresh_sec,
        "max_position_hold_sec": cfg.max_position_hold_sec,
    }
    logger.log("startup", startup_payload)
    print(
        f"[{ts_kst} | {ts_utc}] [시작] config={args.config} mode={cfg.mode} mdata={cfg.marketdata_mode} "
        f"symbol={cfg.symbol} entry={cfg.entry_threshold_rate:.4f} exit={cfg.exit_threshold_rate:.4f} "
        f"size={cfg.trade_size_base} max_notional={cfg.risk.max_notional_krw:,.0f}KRW "
        f"max_daily_loss={cfg.risk.max_daily_loss_krw:,.0f}KRW "
        f"fx_krw_per_usdt={current_fx:.2f} (yaml_fallback={cfg.fx_krw_per_usdt:.2f}) "
        f"fx_refresh_sec={cfg.fx_refresh_sec}"
    )
    if live_engine is not None:
        preflight = live_engine.preflight_check()
        logger.log("live_preflight", preflight)
    if cfg.marketdata_mode == "tick":
        marketdata.start_tick_streams(cfg.upbit_market, cfg.binance_symbol)
        logger.log(
            "marketdata_mode",
            {"mode": "tick", "upbit_market": cfg.upbit_market, "binance_symbol": cfg.binance_symbol},
        )
    else:
        logger.log("marketdata_mode", {"mode": "poll"})

    loop_count = 0
    last_heartbeat_ts = time.monotonic()
    last_fx_refresh_mono = time.monotonic()
    heartbeat_sec = float(os.getenv("ARB_HEARTBEAT_SEC", "300"))  # default 5 minutes
    try:
        while True:
            loop_count += 1
            stats.loop_count = loop_count
            latest_edge_rate = 0.0
            try:
                if cfg.marketdata_mode == "tick":
                    marketdata.wait_tick(timeout_sec=max(cfg.loop_interval_sec, 0.2))
                now_mono = time.monotonic()
                if now_mono - last_fx_refresh_mono >= cfg.fx_refresh_sec:
                    current_fx = fetch_fx_krw_per_usdt(current_fx, timeout_sec=min(cfg.order_timeout_sec, 5.0))
                    last_fx_refresh_mono = now_mono
                snapshot = marketdata.snapshot(
                    upbit_market=cfg.upbit_market,
                    binance_symbol=cfg.binance_symbol,
                    fx_krw_per_usdt=current_fx,
                    fee_upbit_rate=cfg.fee_upbit_rate,
                    fee_binance_rate=cfg.fee_binance_rate,
                    slippage_upbit_rate=cfg.slippage_upbit_rate,
                    slippage_binance_rate=cfg.slippage_binance_rate,
                )
                edge = calc_edge(
                    snapshot,
                    cfg.symbol,
                    cfg.trade_size_base,
                    cfg.transfer_fee_upbit_to_binance_base,
                    cfg.transfer_fee_binance_to_upbit_base,
                )
                decision = signal.decide(
                    edge=edge,
                    has_open_position=portfolio.is_open,
                    position_open_at=portfolio.open_timestamp if portfolio.is_open else None,
                )
                latest_edge_rate = decision.edge_rate
                allowed, reason = risk_guard.check(
                    decision=decision,
                    edge=edge,
                    portfolio=portfolio,
                    size_base=cfg.trade_size_base,
                )

                if not allowed:
                    logger.log(
                        "risk_reject",
                        {
                            "reason": reason,
                            "action": decision.action,
                            "edge_rate": decision.edge_rate,
                            "realized_pnl_krw": portfolio.realized_pnl_krw,
                        },
                    )
                else:
                    result = router.execute(decision=decision, edge=edge, size_base=cfg.trade_size_base)
                    live_status = (
                        result.get("live_result", {}).get("status")
                        if isinstance(result, dict)
                        else None
                    )
                    if decision.action.startswith("OPEN") and live_status == "LIVE_EXECUTED":
                        est_fee = _estimate_order_fee_krw(
                            edge.upbit_mid_krw,
                            edge.binance_mid_krw,
                            cfg.trade_size_base,
                            cfg.fee_upbit_rate,
                            cfg.fee_binance_rate,
                        )
                        stats.total_fees_krw += est_fee
                        # One OPEN executes one buy leg and one sell leg.
                        stats.buy_count += 1
                        stats.sell_count += 1
                        ts_utc, ts_kst = _now_utc_kst()
                        upbit_order_id = ""
                        binance_order_id = ""
                        live_details = result.get("live_result", {}).get("details", []) if isinstance(result, dict) else []
                        if isinstance(live_details, list):
                            if len(live_details) >= 1 and isinstance(live_details[0], dict):
                                upbit_order_id = str(live_details[0].get("uuid", ""))
                            if len(live_details) >= 2 and isinstance(live_details[1], dict):
                                binance_order_id = str(live_details[1].get("orderId", ""))
                        _append_trade_csv(
                            trades_csv_path,
                            ts_kst=ts_kst,
                            ts_utc=ts_utc,
                            action=decision.action,
                            edge_rate=decision.edge_rate,
                            upbit_mid_krw=edge.upbit_mid_krw,
                            binance_mid_krw=edge.binance_mid_krw,
                            live_status=live_status,
                            realized_pnl_krw=portfolio.realized_pnl_krw,
                            fees_est_krw=stats.total_fees_krw,
                            buy_count=stats.buy_count,
                            sell_count=stats.sell_count,
                            close_count=stats.close_count,
                            upbit_order_id=upbit_order_id,
                            binance_order_id=binance_order_id,
                        )
                        print(
                            f"[{ts_kst} | {ts_utc}] [체결] {decision.action} | edge={decision.edge_rate:.4%} | "
                            f"upbit_mid={edge.upbit_mid_krw:,.1f} | binance_mid_krw={edge.binance_mid_krw:,.1f}"
                        )
                        _print_runtime_summary(stats, portfolio.realized_pnl_krw)
                    elif decision.action == "CLOSE" and live_status == "LIVE_EXECUTED":
                        est_fee = _estimate_order_fee_krw(
                            edge.upbit_mid_krw,
                            edge.binance_mid_krw,
                            cfg.trade_size_base,
                            cfg.fee_upbit_rate,
                            cfg.fee_binance_rate,
                        )
                        stats.total_fees_krw += est_fee
                        stats.close_count += 1
                        # Close also executes one buy leg and one sell leg.
                        stats.buy_count += 1
                        stats.sell_count += 1
                        ts_utc, ts_kst = _now_utc_kst()
                        upbit_order_id = ""
                        binance_order_id = ""
                        live_details = result.get("live_result", {}).get("details", []) if isinstance(result, dict) else []
                        if isinstance(live_details, list):
                            if len(live_details) >= 1 and isinstance(live_details[0], dict):
                                upbit_order_id = str(live_details[0].get("uuid", ""))
                            if len(live_details) >= 2 and isinstance(live_details[1], dict):
                                binance_order_id = str(live_details[1].get("orderId", ""))
                        _append_trade_csv(
                            trades_csv_path,
                            ts_kst=ts_kst,
                            ts_utc=ts_utc,
                            action=decision.action,
                            edge_rate=decision.edge_rate,
                            upbit_mid_krw=edge.upbit_mid_krw,
                            binance_mid_krw=edge.binance_mid_krw,
                            live_status=live_status,
                            realized_pnl_krw=portfolio.realized_pnl_krw,
                            fees_est_krw=stats.total_fees_krw,
                            buy_count=stats.buy_count,
                            sell_count=stats.sell_count,
                            close_count=stats.close_count,
                            upbit_order_id=upbit_order_id,
                            binance_order_id=binance_order_id,
                        )
                        print(
                            f"[{ts_kst} | {ts_utc}] [청산체결] edge={decision.edge_rate:.4%} | "
                            f"upbit_mid={edge.upbit_mid_krw:,.1f} | binance_mid_krw={edge.binance_mid_krw:,.1f}"
                        )
                        _print_runtime_summary(stats, portfolio.realized_pnl_krw)
                    logger.log(
                        "decision",
                        {
                            "action": decision.action,
                            "reason": decision.reason,
                            "edge_rate": decision.edge_rate,
                            "fx_krw_per_usdt": current_fx,
                            "result": result,
                            "transfer_fee_rates": {
                                "upbit_to_binance": edge.upbit_to_binance_transfer_fee_rate,
                                "binance_to_upbit": edge.binance_to_upbit_transfer_fee_rate,
                            },
                            "portfolio_open": portfolio.is_open,
                            "realized_pnl_krw": portfolio.realized_pnl_krw,
                        },
                    )
            except Exception as exc:
                logger.log("error", {"message": str(exc)})
            finally:
                now_mono = time.monotonic()
                if now_mono - last_heartbeat_ts >= heartbeat_sec:
                    ts_utc, ts_kst = _now_utc_kst()
                    heartbeat_payload = {
                        "event_type": "heartbeat",
                        "loops": stats.loop_count,
                        "portfolio_open": portfolio.is_open,
                        "direction": portfolio.direction,
                        "realized_pnl_krw": portfolio.realized_pnl_krw,
                        "edge_rate": latest_edge_rate,
                        "fx_krw_per_usdt": current_fx,
                        "fees_est_krw": stats.total_fees_krw,
                        "buy_count": stats.buy_count,
                        "sell_count": stats.sell_count,
                        "close_count": stats.close_count,
                    }
                    logger.log("heartbeat", {k: v for k, v in heartbeat_payload.items() if k != "event_type"})
                    print(
                        f"[{ts_kst} | {ts_utc}] [구동중] loops={stats.loop_count} "
                        f"open={portfolio.is_open} dir={portfolio.direction} "
                        f"edge={latest_edge_rate:.4%} fx={current_fx:.2f} "
                        f"pnl={portfolio.realized_pnl_krw:,.0f}KRW fee_est={stats.total_fees_krw:,.0f}KRW"
                    )
                    last_heartbeat_ts = now_mono

            if args.iterations > 0 and loop_count >= args.iterations:
                break
            if cfg.marketdata_mode != "tick":
                time.sleep(cfg.loop_interval_sec)
    finally:
        marketdata.stop_tick_streams()


if __name__ == "__main__":
    main()

