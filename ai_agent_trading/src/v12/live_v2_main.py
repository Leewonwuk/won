"""v1.28 라이브 트레이딩 진입점.

단일 / 멀티코인 모두 지원. --configs 로 쉼표 구분 yaml 목록을 넘기면
코인당 별도 스레드에서 엔진이 실행되고 WS 피드는 공유된다.

사용법:
  # 단일 (기존과 동일)
  python -m src.v12.live_v2 --live --config configs/v12/v12_sol_v2.yaml

  # 멀티코인
  python -m src.v12.live_v2 --live \\
      --configs configs/v12/v12_sol_v2.yaml,configs/v12/v12_xrp_v2.yaml

환경변수:
  ARB_V12_CONFIGS   — 쉼표 구분 config 경로 목록 (--configs 우선)
  ARB_V12_CONFIG    — 단일 config 경로 (--config 우선)
  ARB_V12_LIVE      — "1" 또는 "true" 이면 실거래
  ARB_V12_POLL      — 폴링 간격(초), 기본 0.05 (WS 사용 시)
  ARB_V12_TIMEOUT   — 주문 타임아웃(초), 기본 15
  ARB_FX_KRW_PER_USDT      — KRW/USDT 환율
  TELEGRAM_HOUR_SUMMARY_SEC — 텔레그램 요약 주기(초)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

from src.exchanges.binance_trading_client import BinanceTradingClient
from src.v12.config_v2 import load_v12_config_v2
from src.v12.global_lock import GlobalTradeLock
from src.v12.live_engine_v2 import V12LiveEngineV2
from src.v12.price_feed import PriceFeed

_DEFAULT_CONFIG  = "configs/v12/v12_btc_v2.yaml"
_LOG_FORMAT      = "%(asctime)s %(levelname)s %(message)s"


def _setup_logging(log_dir: str = "logs/v12") -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    tag      = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = f"{log_dir}/live_v2_{tag}.log"
    logging.basicConfig(
        level=logging.INFO,
        format=_LOG_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    logging.info(f"로그 파일: {log_file}")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="v1.28 라이브 트레이딩")
    # 단일 config (하위 호환)
    p.add_argument("--config",  default="")
    # 멀티코인 config (쉼표 구분)
    p.add_argument("--configs", default="")
    p.add_argument("--live",    action="store_true", help="실거래 모드 (기본: dry-run)")
    p.add_argument("--timeout", type=float, default=None, help="Leg B 타임아웃(초). 미설정 시 각 config의 order_timeout_sec 사용")
    # WS 사용 시 0.05 로 줄임 — REST fallback 은 _REST_ORDER_CHECK_INTERVAL(0.5s) 로 별도 throttle
    p.add_argument("--poll",    type=float, default=0.05,  help="폴링 간격(초), 기본 0.05")
    p.add_argument("--global-lock", action="store_true",
                   help="통합 풀 모드: 한 코인이 거래 중이면 다른 코인 진입 차단 (env: ARB_GLOBAL_LOCK=1)")
    return p.parse_args()


def _resolve_config_paths(args: argparse.Namespace) -> list[str]:
    """--configs > --config > env 순으로 config 경로 목록 결정."""
    if args.configs:
        return [p.strip() for p in args.configs.split(",") if p.strip()]
    if args.config:
        return [args.config]
    # 환경변수
    env_configs = os.getenv("ARB_V12_CONFIGS", "")
    if env_configs:
        return [p.strip() for p in env_configs.split(",") if p.strip()]
    env_config = os.getenv("ARB_V12_CONFIG", _DEFAULT_CONFIG)
    return [env_config]


def _send_merged_csv(engines: list, total_pnl: float) -> None:
    """모든 엔진의 거래 CSV를 시각순으로 통합해 1개로 전송."""
    import csv as _csv
    from src.notifications.telegram_notifier import send_telegram_document
    from datetime import datetime, timezone

    try:
        all_rows: list[dict] = []
        fieldnames: list[str] = []
        log_dir = engines[0].log_dir if engines else "logs/v12"

        for e in engines:
            path = e._csv_path
            try:
                with open(path, encoding="utf-8-sig", newline="") as f:
                    reader = _csv.DictReader(f)
                    if not fieldnames and reader.fieldnames:
                        fieldnames = list(reader.fieldnames)
                    all_rows.extend(reader)
            except FileNotFoundError:
                pass

        if not all_rows or not fieldnames:
            return

        # 거래시각 기준 정렬
        all_rows.sort(key=lambda r: r.get("거래시각(KST)", ""))

        # 누적순수익 재계산: 코인별 누적 → 전체 포트폴리오 통합 누적
        # 개별 CSV의 누적순수익은 코인별 독립 누계이므로, 병합 후 시각 순으로 다시 계산
        fx_krw = engines[0].fx_krw if engines else 1450.0
        cum_pnl = 0.0
        for row in all_rows:
            try:
                pnl = float(row.get("순수익(USD)", "0") or "0")
            except (ValueError, TypeError):
                pnl = 0.0
            cum_pnl += pnl
            row["누적순수익(USD)"] = f"{cum_pnl:.4f}"
            row["누적순수익(원)"] = f"{cum_pnl * fx_krw:.0f}"

        tag = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = f"{log_dir}/trades_merged_{tag}.csv"
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = _csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)

        send_telegram_document(
            out_path,
            caption=(
                f"📎 거래기록 통합 (누적 {len(all_rows)}건)\n"
                f"누적 순수익: {total_pnl:+.4f} USDT (BNB 수수료 포함)"
            ),
        )
    except Exception as e:
        logging.warning(f"[MergedCSV] 생성 실패: {e}")


def _send_combined_excel(engines: list, span_min: int) -> None:
    """모든 엔진의 IOC miss / event rows를 통합 Excel 1개로 전송."""
    try:
        import openpyxl
        from src.notifications.telegram_notifier import send_telegram_document
        from datetime import datetime, timezone

        tag = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_dir = engines[0].log_dir if engines else "logs/v12"

        # IOC miss 통합
        ioc_rows = []
        for e in engines:
            ioc_rows.extend(e.pop_ioc_miss_rows())

        if ioc_rows:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "IOC_MISS"
            headers = list(ioc_rows[0].keys())
            ws.append(headers)
            for row in ioc_rows:
                ws.append([row.get(h, "") for h in headers])
            path = f"{log_dir}/ioc_miss_combined_{tag}.xlsx"
            wb.save(path)
            send_telegram_document(path, caption=f"📊 IOC miss 통합 ({span_min}분)  {len(ioc_rows)}건")

        # event 통합
        ev_rows = []
        for e in engines:
            ev_rows.extend(e.pop_event_rows())

        if ev_rows:
            wb2 = openpyxl.Workbook()
            ws2 = wb2.active
            ws2.title = "EVENTS"
            headers2 = list(ev_rows[0].keys())
            ws2.append(headers2)
            for row in ev_rows:
                ws2.append([row.get(h, "") for h in headers2])
            path2 = f"{log_dir}/event_combined_{tag}.xlsx"
            wb2.save(path2)
            send_telegram_document(path2, caption=f"📋 이벤트 통합 ({span_min}분)  {len(ev_rows)}건")

    except Exception as e:
        logging.warning(f"[CombinedExcel] 생성 실패: {e}")


def _combined_summary_loop(engines: list, summary_sec: float, fx_krw: float, integrated_pool: bool = False) -> None:
    """멀티코인 통합 텔레그램 요약을 주기적으로 전송."""
    from src.notifications.telegram_notifier import send_telegram
    span_min = max(1, int(round(summary_sec / 60.0)))
    last_ts = time.time()
    initial_stable: float | None = None  # USDT+USDC 구동 시작값 (누계 변화 추적용)

    while True:
        time.sleep(10)
        if time.time() - last_ts < summary_sec:
            continue
        last_ts = time.time()

        stats_list = [e.get_period_stats() for e in engines]

        # 전체 합산
        # 통합 풀 모드: 리밸런싱 후 엔진별 캐시가 달라지므로 engines[0] 신선 sync 후 그 값 사용
        # 분리 모드: 코인별 독립 자본이므로 sum 사용
        if integrated_pool:
            try:
                engines[0].sync_balances()
            except Exception as _e:
                logging.warning(f"[CombinedSummary] 잔고 동기화 실패: {_e}")
            total_usdt = engines[0].usdt
            total_usdc = engines[0].usdc
        else:
            total_usdt = sum(s["usdt"] for s in stats_list)
            total_usdc = sum(s["usdc"] for s in stats_list)
        total_bnb  = max(s["bnb"] for s in stats_list)  # BNB 공유 계좌
        total_equity = total_usdt + total_usdc
        total_krw = total_equity * fx_krw

        # USDT+USDC 누계 변화 추적
        if initial_stable is None:
            initial_stable = total_equity
        stable_delta = total_equity - initial_stable
        total_hour_trades = sum(s["hour_trades"] for s in stats_list)
        total_hour_pnl    = sum(s["hour_pnl"]    for s in stats_list)
        total_trades      = sum(s["total_trades"] for s in stats_list)
        total_pnl         = sum(s["total_pnl"]   for s in stats_list)
        total_emergency   = sum(s["emergency_count"]    for s in stats_list)
        total_timeout     = sum(s["timeout_count"]      for s in stats_list)
        total_ioc_miss    = sum(s["ioc_miss_count"]     for s in stats_list)
        total_abort       = sum(s["abort_count"]        for s in stats_list)
        period_abort      = sum(s["period_abort"]       for s in stats_list)
        period_emergency  = sum(s["period_emergency"]   for s in stats_list)
        period_ioc_miss   = sum(s["period_ioc_miss"]    for s in stats_list)

        # 구간 순수익 표시
        def pnl_str(usd: float) -> str:
            krw = int(usd * fx_krw)
            return f"{usd:+.4f} USDT (약 {krw:+,}원)"

        # 코인별 한 줄 요약
        coin_lines = ""
        for s in stats_list:
            sym = s["symbol"]
            best = max(s["hour_max_dc"], s["hour_max_dt"]) * 100
            thr = s["dc_threshold"] * 100
            miss = s["period_ioc_miss"]
            coin_lines += (
                f"  [{sym}]  거래 {s['hour_trades']}회  수익 {s['hour_pnl']:+.4f}  "
                f"최고 {best:+.3f}% / 기준 {thr:.3f}%  miss {miss}회\n"
            )

        msg = (
            f"⏰ <b>v1.28 운영 요약 ({span_min}분)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔄 이번 구간 거래: {total_hour_trades}회\n"
            f"💵 이번 구간 순수익: {pnl_str(total_hour_pnl)}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 코인별 현황\n"
            f"{coin_lines}"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 누적 거래: {total_trades}회\n"
            f"💰 누적 순수익: {pnl_str(total_pnl)}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💼 잔고\n"
            f"  USDT: {total_usdt:,.2f}  USDC: {total_usdc:,.2f}\n"
            f"  BNB: {total_bnb:.6f}\n"
            f"  총자산: {total_equity:,.2f} USDT (약 {int(total_krw):,}원)\n"
            f"  USDT+USDC 누계: {initial_stable:,.2f} → {total_equity:,.2f} ({stable_delta:+.4f} USDT)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ 이번구간: 조기청산 {period_abort}회  비상청산 {period_emergency}회  IOC miss {period_ioc_miss}회\n"
            f"   누  적: 조기청산 {total_abort}회  비상청산 {total_emergency}회  IOC miss {total_ioc_miss}회"
        )

        try:
            send_telegram(msg)
        except Exception as e:
            logging.warning(f"[CombinedSummary] 텔레그램 전송 실패: {e}")

        # 각 엔진 구간 카운터 리셋
        for e in engines:
            e.reset_period_stats()

        # 거래 CSV 통합 발송 (코인별 개별 CSV → 1개 병합 파일)
        _send_merged_csv(engines, total_pnl)

        # 통합 디버그 Excel 생성 및 전송
        _send_combined_excel(engines, span_min)


def main() -> None:
    load_dotenv()
    _setup_logging()
    args = _parse_args()

    api_key    = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    if not api_key or not api_secret:
        logging.error("BINANCE_API_KEY / BINANCE_API_SECRET 환경변수가 없습니다.")
        sys.exit(1)

    config_paths = _resolve_config_paths(args)
    for cp in config_paths:
        if not Path(cp).is_file():
            logging.error(f"Config 파일 없음: {cp}")
            sys.exit(1)

    configs  = [load_v12_config_v2(cp) for cp in config_paths]
    dry_run  = not (
        args.live
        or os.getenv("ARB_V12_LIVE", "0") in ("1", "true")
    )
    poll            = float(os.getenv("ARB_V12_POLL", str(args.poll)))
    # ARB_V12_TIMEOUT 또는 --timeout 이 명시된 경우 전역 값으로 덮어씀
    # 미설정 시 각 config의 order_timeout_sec 을 per-engine 으로 사용 (YAML 반영)
    _env_timeout    = os.getenv("ARB_V12_TIMEOUT")
    _global_timeout = (
        float(_env_timeout) if _env_timeout is not None
        else (float(args.timeout) if args.timeout is not None else None)
    )
    fx_krw   = float(os.getenv("ARB_FX_KRW_PER_USDT",      "1450"))
    tg_sec   = float(os.getenv("TELEGRAM_HOUR_SUMMARY_SEC", "1800"))
    use_global_lock = (
        getattr(args, "global_lock", False)
        or os.getenv("ARB_GLOBAL_LOCK", "0") in ("1", "true")
    )

    mode_str = "DRY RUN" if dry_run else "LIVE"
    symbols  = [s for cfg in configs for s in [cfg.binance_symbol_usdt, cfg.binance_symbol_usdc]]
    coins    = [cfg.symbol for cfg in configs]

    logging.info("=" * 60)
    logging.info(f"  v1.28  모드={mode_str}  코인={coins}  poll={poll}s")
    logging.info(f"  WS 심볼: {symbols}")
    logging.info("=" * 60)

    # ── WebSocket 피드 시작 ─────────────────────────────────────────
    feed = PriceFeed(api_key=api_key, api_secret=api_secret, symbols=symbols)
    feed.start()
    logging.info("[Main] PriceFeed WS 연결 대기 중...")
    ws_ok = feed.wait_ready(timeout=10.0)
    if ws_ok:
        logging.info("[Main] PriceFeed READY — WS 실시간 모드")
    else:
        logging.warning("[Main] PriceFeed 연결 실패 — REST fallback 모드로 시작")

    # ── WS Order API 클라이언트 시작 ────────────────────────────────────
    from src.v12.ws_order_client import BinanceTradingWsClient
    ws_order = BinanceTradingWsClient(api_key=api_key, api_secret=api_secret)
    ws_ok_order = ws_order.start(wait_timeout=8.0)
    if ws_ok_order:
        logging.info("[Main] WS Order API READY — 주문 발행 WS 모드")
    else:
        logging.warning("[Main] WS Order API 연결 실패 — REST fallback")

    # ── 엔진 생성 ───────────────────────────────────────────────────
    binance = BinanceTradingClient(api_key=api_key, api_secret=api_secret)

    # 통합 풀 모드: 하나의 락 인스턴스를 모든 엔진이 공유
    # expire_sec = 가장 긴 order_timeout_sec + 30s (크래시 방어)
    _max_timeout = max(
        (_global_timeout if _global_timeout is not None else float(cfg.order_timeout_sec))
        for cfg in configs
    )
    shared_lock: GlobalTradeLock | None = (
        GlobalTradeLock(expire_sec=_max_timeout + 30.0) if use_global_lock else None
    )
    if shared_lock is not None:
        logging.info(
            f"[Main] 통합 풀 모드 활성 — GlobalTradeLock(expire={shared_lock.expire_sec}s)"
        )

    engines = [
        V12LiveEngineV2(
            cfg                 = cfg,
            binance             = binance,
            dry_run             = dry_run,
            poll_interval_sec   = poll,
            # 전역 override > config의 order_timeout_sec 순으로 적용
            leg_timeout_sec     = _global_timeout if _global_timeout is not None else float(cfg.order_timeout_sec),
            fx_krw              = fx_krw,
            telegram_summary_sec= tg_sec,
            price_feed          = feed,
            ws_order_client     = ws_order,
            global_lock         = shared_lock,
        )
        for cfg in configs
    ]

    if len(engines) == 1:
        # 단일 코인: 현재 스레드에서 바로 실행
        engines[0].run()
        return

    # ── 멀티코인: 개별 텔레그램 억제 → 통합 요약 코디네이터 사용 ────
    for engine in engines:
        engine.suppress_hourly_telegram = True

    # ── 통합 시작 메시지 ────────────────────────────────────────────
    from src.notifications.telegram_notifier import send_telegram
    # 통합 풀: 잔고는 한 번만 표시 / 분리: 코인별 자본 표시
    if shared_lock:
        pool_usdt = configs[0].initial_usdt
        pool_usdc = configs[0].initial_usdc
        notional  = (pool_usdt + pool_usdc) * configs[0].entry_split_fraction
        pool_line = (
            f"💼 USDT={pool_usdt:.0f}  USDC={pool_usdc:.0f}  "
            f"(거래당 ~{notional:.0f} USDT)\n"
            f"🔒 통합 풀 모드 — {len(configs)}코인 / GlobalLock ON\n"
        )
    else:
        pool_line = "🔓 분리 운영 모드\n"

    coin_lines = "\n".join(
        f"  [{cfg.symbol}]  DT>{cfg.dt_entry_threshold_rate:.4%}  DC>{cfg.dc_entry_threshold_rate:.4%}"
        for cfg in configs
    )
    send_telegram(
        f"🚀 <b>v1.28 멀티코인 시작 ({mode_str})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{pool_line}"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{coin_lines}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"timeout={_global_timeout if _global_timeout is not None else 'per-cfg'}s  "
        f"poll={poll}s  요약주기={int(tg_sec//60)}분"
    )

    # ── 멀티코인: 코인당 스레드 ─────────────────────────────────────
    threads = [
        threading.Thread(
            target = engine.run,
            name   = f"Engine-{engine.cfg.symbol}",
            daemon = False,
        )
        for engine in engines
    ]
    for t in threads:
        t.start()
    logging.info(f"[Main] {len(threads)}개 엔진 스레드 시작: {coins}")

    # ── 통합 요약 코디네이터 스레드 ────────────────────────────────
    coordinator = threading.Thread(
        target=_combined_summary_loop,
        args=(engines, tg_sec, fx_krw, use_global_lock),
        name="CombinedSummary",
        daemon=True,
    )
    coordinator.start()

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        logging.info("[Main] KeyboardInterrupt — 엔진 종료 대기 중...")


if __name__ == "__main__":
    main()
