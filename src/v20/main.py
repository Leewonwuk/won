"""v2.0 펀딩비 차익거래 메인 진입점.

사용법:
  python -m src.v20.main --configs configs/v20/v20_trx.yaml configs/v20/v20_xrp.yaml
  python -m src.v20.main --configs configs/v20/v20_trx.yaml --dry-run
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

from src.exchanges.binance_futures_client import BinanceFuturesClient
from src.exchanges.binance_trading_client import BinanceTradingClient

from .config_v20 import load_config
from .funding_engine import FundingEngine

load_dotenv()
log = logging.getLogger("v20.main")


def _setup_logging(log_dir: str):
    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = log_dir_path / f"v20_main_{date_str}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def _build_notifier():
    """텔레그램 알림 함수 생성."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        log.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정 — 알림 비활성")
        return lambda msg: None

    try:
        from src.notifications.telegram_notifier import send_telegram
        def notifier(msg: str):
            try:
                send_telegram(token, chat_id, msg)
            except Exception as e:
                log.warning(f"텔레그램 알림 실패: {e}")
        return notifier
    except ImportError:
        log.warning("telegram_notifier 모듈 없음 — 알림 비활성")
        return lambda msg: None


def _run_engine(engine: FundingEngine, stop_event: threading.Event):
    """단일 엔진 루프 (스레드에서 실행)."""
    cfg = engine.cfg
    log.info(f"[{cfg.symbol}] 엔진 시작 (dry_run={cfg.dry_run})")

    engine.setup_futures()

    while not stop_event.is_set():
        engine.tick()

        # 정산 5분 전이면 10초 간격으로 폴링
        if engine._is_pre_funding():
            sleep_sec = 10.0
        else:
            sleep_sec = cfg.poll_interval_sec

        stop_event.wait(sleep_sec)

    log.info(f"[{cfg.symbol}] 엔진 종료")


def main():
    parser = argparse.ArgumentParser(description="v2.0 펀딩비 차익거래 봇")
    parser.add_argument("--configs", nargs="+", required=True, help="YAML 설정 파일 경로")
    parser.add_argument("--dry-run", action="store_true", help="dry_run 강제 활성")
    args = parser.parse_args()

    # 환경변수
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    if not api_key or not api_secret:
        print("ERROR: BINANCE_API_KEY / BINANCE_API_SECRET 환경변수 필요")
        sys.exit(1)

    # 설정 로드
    configs = [load_config(p) for p in args.configs]
    if args.dry_run:
        for cfg in configs:
            cfg.dry_run = True

    # 로깅 (첫 번째 config의 log_dir 사용)
    _setup_logging(configs[0].log_dir)
    log.info(f"v2.0 시작 | 코인: {[c.symbol for c in configs]} | dry_run: {[c.dry_run for c in configs]}")

    # 클라이언트 (모든 엔진 공유)
    spot = BinanceTradingClient(api_key=api_key, api_secret=api_secret)
    futures = BinanceFuturesClient(api_key=api_key, api_secret=api_secret)
    notifier = _build_notifier()

    # 엔진 생성 + 스레드 시작
    stop_event = threading.Event()
    threads: list[threading.Thread] = []
    engines: list[FundingEngine] = []

    for cfg in configs:
        engine = FundingEngine(cfg=cfg, spot=spot, futures=futures, notifier=notifier)
        engines.append(engine)
        t = threading.Thread(
            target=_run_engine,
            args=(engine, stop_event),
            name=f"engine-{cfg.symbol}",
            daemon=True,
        )
        threads.append(t)
        t.start()

    log.info(f"{len(engines)}개 엔진 실행 중. Ctrl+C로 종료.")

    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        log.info("종료 신호 수신 → 엔진 중지 중...")
        stop_event.set()
        for t in threads:
            t.join(timeout=30)
        log.info("종료 완료")


if __name__ == "__main__":
    main()
