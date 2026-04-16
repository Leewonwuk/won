"""Append-only CSV logs for v2 multi_main: per-trade rows + hourly rollups with running totals."""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from src.config import CoinConfig
from src.state.multi_portfolio import RebalancePortfolio, TradeEvent


def _utc_kst_now() -> tuple[str, str]:
    utc = datetime.now(tz=timezone.utc)
    kst = utc.astimezone(timezone(timedelta(hours=9)))
    return utc.isoformat(), kst.isoformat()


def _hour_bucket_kst() -> str:
    """Wall-clock hour in KST, e.g. 2026-03-28T22."""
    _, kst_iso = _utc_kst_now()
    return kst_iso[:13]


def _portfolio_snapshot(portfolio: RebalancePortfolio, coins: list[CoinConfig]) -> str:
    parts: list[str] = []
    for c in coins:
        b = portfolio.get(c.symbol)
        parts.append(
            f"{c.symbol} Ukrw={b.upbit_krw:.0f} Ucoin={b.upbit_coin:.6f} "
            f"B_USDT={b.binance_usdt:.2f} Bcoin={b.binance_coin:.6f} "
            f"trades={b.total_trades} rebal={b.total_rebalances} fee={b.realized_fee_krw:.0f}"
        )
    return " | ".join(parts)


def _event_ko(event: str) -> str:
    mapping = {
        "TRADE_KIMCHI": "김프거래",
        "TRADE_REVERSE": "역프거래",
        "REBALANCE": "리밸",
    }
    return mapping.get(event, event)


def _migrate_trade_row_with_event_ko(row: list[str]) -> list[str]:
    # legacy row: [.., 이벤트, 코인, ...]
    if len(row) >= 4:
        event = row[2]
        return row[:3] + [_event_ko(event)] + row[3:]
    return row


def _migrate_trade_row_with_metrics(row: list[str]) -> list[str]:
    # Ensure extended trailing metrics columns exist:
    # [왕복손익, 왕복프리미엄, 보유시간, 슬리피지(업비트), 슬리피지(바이낸스)]
    if len(row) < 20:
        return row + [""] * (20 - len(row))
    return row


@dataclass
class _Period:
    loops: int = 0
    kimchi: int = 0
    reverse: int = 0
    rebalance: int = 0
    fee_krw: float = 0.0
    pnl_krw: float = 0.0
    trade_qty_sum: float = 0.0


@dataclass
class _Cumul:
    loops: int = 0
    kimchi: int = 0
    reverse: int = 0
    rebalance: int = 0
    fee_krw: float = 0.0
    pnl_krw: float = 0.0
    trade_qty_sum: float = 0.0


class MultiRunCsvRecorder:
    """Writes `logs/multi_trades.csv` (each fill) and `logs/multi_hourly.csv` (each KST hour)."""

    TRADES_HEADER_LEGACY = [
        "ts_kst",
        "ts_utc",
        "event",
        "symbol",
        "premium",
        "premium_pct",
        "pnl_krw",
        "fee_krw",
        "trade_qty",
        "upbit_price_krw",
        "binance_price_usdt",
        "fx",
        "detail",
        "terminal_line",
    ]
    TRADES_HEADER = [
        "시각_KST",
        "시각_UTC",
        "이벤트",
        "이벤트_한글",
        "코인",
        "프리미엄_비율",
        "프리미엄_퍼센트",
        "실현손익_KRW",
        "수수료_KRW",
        "거래수량",
        "업비트가격_KRW",
        "바이낸스가격_USDT",
        "환율_KRW_PER_USDT",
        "상세내역",
        "터미널요약",
        "왕복손익_KRW",
        "왕복프리미엄_비율",
        "보유시간_초",
        "실측슬리피지_업비트",
        "실측슬리피지_바이낸스",
    ]
    TRADES_HEADER_LEGACY_KR_V1 = [
        "시각_KST",
        "시각_UTC",
        "이벤트",
        "코인",
        "프리미엄_비율",
        "프리미엄_퍼센트",
        "실현손익_KRW",
        "수수료_KRW",
        "거래수량",
        "업비트가격_KRW",
        "바이낸스가격_USDT",
        "환율_KRW_PER_USDT",
        "상세내역",
        "터미널요약",
    ]
    TRADES_HEADER_LEGACY_KR_V2 = [
        "시각_KST",
        "시각_UTC",
        "이벤트",
        "이벤트_한글",
        "코인",
        "프리미엄_비율",
        "프리미엄_퍼센트",
        "실현손익_KRW",
        "수수료_KRW",
        "거래수량",
        "업비트가격_KRW",
        "바이낸스가격_USDT",
        "환율_KRW_PER_USDT",
        "상세내역",
        "터미널요약",
    ]
    HOURLY_HEADER_LEGACY = [
        "hour_bucket_kst",
        "written_ts_kst",
        "written_ts_utc",
        "loops_in_hour",
        "kimchi_cnt_hour",
        "reverse_cnt_hour",
        "rebalance_cnt_hour",
        "fee_krw_hour",
        "pnl_krw_hour",
        "trade_qty_sum_hour",
        "loops_total",
        "kimchi_cnt_total",
        "reverse_cnt_total",
        "rebalance_cnt_total",
        "fee_krw_total",
        "pnl_krw_total",
        "trade_qty_sum_total",
        "realized_pnl_portfolio",
        "fx",
        "terminal_summary",
        "portfolio_snapshot",
    ]
    HOURLY_HEADER = [
        "시간버킷_KST",
        "기록시각_KST",
        "기록시각_UTC",
        "구간루프수",
        "구간김프거래수",
        "구간역프거래수",
        "구간리밸런스수",
        "구간수수료합_KRW",
        "구간실현손익_KRW",
        "구간거래수량합",
        "누적루프수",
        "누적김프거래수",
        "누적역프거래수",
        "누적리밸런스수",
        "누적수수료합_KRW",
        "누적실현손익_KRW",
        "누적거래수량합",
        "포트폴리오누적실현손익_KRW",
        "환율_KRW_PER_USDT",
        "터미널요약",
        "포트폴리오스냅샷",
    ]

    def __init__(
        self,
        trades_path: str | Path | None = None,
        hourly_path: str | Path | None = None,
    ) -> None:
        root = Path(os.getenv("ARB_MULTI_CSV_DIR", "logs"))
        self.trades_path = Path(trades_path or os.getenv("ARB_MULTI_TRADES_CSV", str(root / "multi_trades.csv")))
        self.hourly_path = Path(hourly_path or os.getenv("ARB_MULTI_HOURLY_CSV", str(root / "multi_hourly.csv")))
        self.trades_path.parent.mkdir(parents=True, exist_ok=True)
        self.hourly_path.parent.mkdir(parents=True, exist_ok=True)
        self._period = _Period()
        self._cum = _Cumul()
        self._hour_bucket: str | None = None
        self._ensure_file(
            self.trades_path,
            self.TRADES_HEADER,
            [
                self.TRADES_HEADER_LEGACY,
                self.TRADES_HEADER_LEGACY_KR_V1,
                self.TRADES_HEADER_LEGACY_KR_V2,
            ],
            row_migrator=lambda row: _migrate_trade_row_with_metrics(
                _migrate_trade_row_with_event_ko(row)
            ),
        )
        self._ensure_file(self.hourly_path, self.HOURLY_HEADER, [self.HOURLY_HEADER_LEGACY])

    @staticmethod
    def _ensure_file(
        path: Path,
        header: list[str],
        legacy_headers: list[list[str]] | None = None,
        row_migrator: Callable[[list[str]], list[str]] | None = None,
    ) -> None:
        if not path.exists():
            with path.open("w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(header)
            return

        # 기존 헤더 파일은 데이터 유지한 채 헤더/행 구조만 교체.
        try:
            with path.open("r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                first_row = next(reader, [])
                if first_row and first_row[0].startswith("\ufeff"):
                    first_row[0] = first_row[0].lstrip("\ufeff")
                if not legacy_headers or first_row not in legacy_headers:
                    return
                rows = [row for row in reader]
            if row_migrator is not None:
                rows = [row_migrator(row) for row in rows]
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(rows)
        except Exception:
            # 헤더 정규화 실패는 치명적이지 않으므로 기존 파일을 그대로 사용.
            return

    def on_loop_tick(
        self,
        portfolio: RebalancePortfolio,
        coins: list[CoinConfig],
        fx: float,
    ) -> None:
        """Call once per main-loop iteration (after updating fx)."""
        bucket = _hour_bucket_kst()
        if self._hour_bucket is None:
            self._hour_bucket = bucket
        elif bucket != self._hour_bucket:
            self._flush_hourly(portfolio, coins, fx, self._hour_bucket)
            self._period = _Period()
            self._hour_bucket = bucket
        self._period.loops += 1
        self._cum.loops += 1

    def record_trade(self, event: TradeEvent, terminal_line: str) -> None:
        ts_utc, ts_kst = _utc_kst_now()
        prem_pct = f"{event.premium * 100:.4f}%"
        with self.trades_path.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                [
                    ts_kst,
                    ts_utc,
                    event.event,
                    _event_ko(event.event),
                    event.coin,
                    f"{event.premium:.8f}",
                    prem_pct,
                    f"{event.pnl_krw:.6f}",
                    f"{event.fee_krw:.6f}",
                    f"{event.trade_qty:.8f}",
                    f"{event.upbit_price_krw:.8f}",
                    f"{event.binance_price_usdt:.8f}",
                    f"{event.fx:.6f}",
                    event.detail.replace("\n", " ").strip(),
                    terminal_line.replace("\n", " ").strip(),
                    f"{event.round_trip_pnl_krw:.6f}" if event.round_trip_pnl_krw is not None else "",
                    f"{event.round_trip_premium:.8f}" if event.round_trip_premium is not None else "",
                    f"{event.hold_duration_sec:.3f}" if event.hold_duration_sec is not None else "",
                    f"{event.actual_slippage_upbit:.8f}" if event.actual_slippage_upbit is not None else "",
                    f"{event.actual_slippage_binance:.8f}" if event.actual_slippage_binance is not None else "",
                ]
            )

        self._period.fee_krw += event.fee_krw
        self._period.pnl_krw += event.pnl_krw
        self._cum.fee_krw += event.fee_krw
        self._cum.pnl_krw += event.pnl_krw
        if event.trade_qty > 0:
            self._period.trade_qty_sum += abs(event.trade_qty)
            self._cum.trade_qty_sum += abs(event.trade_qty)

        if event.event == "TRADE_KIMCHI":
            self._period.kimchi += 1
            self._cum.kimchi += 1
        elif event.event == "TRADE_REVERSE":
            self._period.reverse += 1
            self._cum.reverse += 1
        elif event.event == "REBALANCE":
            self._period.rebalance += 1
            self._cum.rebalance += 1

    def finalize(self, portfolio: RebalancePortfolio, coins: list[CoinConfig], fx: float) -> None:
        """Flush the current (possibly partial) hour when the process stops."""
        if self._hour_bucket is not None:
            self._flush_hourly(portfolio, coins, fx, self._hour_bucket, is_final=True)

    def _flush_hourly(
        self,
        portfolio: RebalancePortfolio,
        coins: list[CoinConfig],
        fx: float,
        hour_bucket: str,
        *,
        is_final: bool = False,
    ) -> None:
        ts_utc, ts_kst = _utc_kst_now()
        snap = _portfolio_snapshot(portfolio, coins)
        term = (
            f"[{hour_bucket}] "
            f"loops_h={self._period.loops} kimchi_h={self._period.kimchi} "
            f"rev_h={self._period.reverse} rebal_h={self._period.rebalance} "
            f"fee_h={self._period.fee_krw:.0f}KRW pnl_h={self._period.pnl_krw:.0f}KRW "
            f"| TOTAL loops={self._cum.loops} kimchi={self._cum.kimchi} "
            f"reverse={self._cum.reverse} rebal={self._cum.rebalance} "
            f"fee={self._cum.fee_krw:.0f}KRW pnl={self._cum.pnl_krw:.0f}KRW "
            f"qty_sum={self._cum.trade_qty_sum:.4f}"
        )
        if is_final:
            term += " (run_end)"

        with self.hourly_path.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                [
                    hour_bucket,
                    ts_kst,
                    ts_utc,
                    self._period.loops,
                    self._period.kimchi,
                    self._period.reverse,
                    self._period.rebalance,
                    f"{self._period.fee_krw:.6f}",
                    f"{self._period.pnl_krw:.6f}",
                    f"{self._period.trade_qty_sum:.8f}",
                    self._cum.loops,
                    self._cum.kimchi,
                    self._cum.reverse,
                    self._cum.rebalance,
                    f"{self._cum.fee_krw:.6f}",
                    f"{self._cum.pnl_krw:.6f}",
                    f"{self._cum.trade_qty_sum:.8f}",
                    f"{portfolio.realized_pnl_krw:.6f}",
                    f"{fx:.6f}",
                    term,
                    snap,
                ]
            )
