"""v2.0 펀딩비 차익거래 설정."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class FundingArbConfig:
    # ── 코인 식별 ──────────────────────────────────────────────────────────
    symbol: str = "TRX"
    spot_symbol: str = "TRXUSDT"       # 현물 페어
    futures_symbol: str = "TRXUSDT"   # 선물 페어 (USDT-M)

    # ── 자본 설정 ──────────────────────────────────────────────────────────
    capital_usdt: float = 500.0        # 이 코인에 배분된 총 자본 (현물+선물 증거금 합산)
    position_fraction: float = 0.8    # capital_usdt 중 실제 사용 비율
    leverage: int = 2                  # 선물 레버리지 (ISOLATED)

    # ── 진입 조건 ──────────────────────────────────────────────────────────
    entry_funding_rate: float = 0.0003   # 0.03%/8h — 이 이상일 때 진입
    max_basis_rate: float = 0.001        # 0.1% — 선물-현물 괴리 최대 허용치

    # ── 청산 조건 ──────────────────────────────────────────────────────────
    exit_funding_rate: float = 0.00005  # 0.005%/8h — 이 미만이면 청산
    stop_loss_usdt: float = -30.0       # net PnL 이 값 이하 시 비상 청산
    danger_margin_ratio: float = 0.20   # 선물 증거금 비율 이 값 미만 시 경고
    max_hold_hours: float = 168.0       # 최대 보유 시간 (7일)

    # ── 쿨다운 ─────────────────────────────────────────────────────────────
    reentry_cooldown_sec: float = 300.0       # 일반 청산 후 재진입 대기
    emergency_cooldown_sec: float = 3600.0   # stop_loss 청산 후 재진입 대기

    # ── 수수료 ─────────────────────────────────────────────────────────────
    spot_fee_rate: float = 0.00075      # 현물 시장가 수수료 (BNB 할인 적용)
    futures_fee_rate: float = 0.0002    # 선물 시장가 수수료

    # ── 운영 ───────────────────────────────────────────────────────────────
    dry_run: bool = True
    poll_interval_sec: float = 60.0         # 펀딩비 폴링 주기 (초)
    pre_funding_check_sec: float = 300.0    # 정산 N초 전 조기 체크 (5분)
    telegram_summary_sec: float = 1800.0    # 텔레그램 요약 주기 (30분)
    log_dir: str = "logs/v20"


def load_config(path: str) -> FundingArbConfig:
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return FundingArbConfig(
        symbol=str(data.get("symbol", "TRX")),
        spot_symbol=str(data.get("spot_symbol", "TRXUSDT")),
        futures_symbol=str(data.get("futures_symbol", "TRXUSDT")),
        capital_usdt=float(data.get("capital_usdt", 500.0)),
        position_fraction=float(data.get("position_fraction", 0.8)),
        leverage=int(data.get("leverage", 2)),
        entry_funding_rate=float(data.get("entry_funding_rate", 0.0003)),
        max_basis_rate=float(data.get("max_basis_rate", 0.001)),
        exit_funding_rate=float(data.get("exit_funding_rate", 0.00005)),
        stop_loss_usdt=float(data.get("stop_loss_usdt", -30.0)),
        danger_margin_ratio=float(data.get("danger_margin_ratio", 0.20)),
        max_hold_hours=float(data.get("max_hold_hours", 168.0)),
        reentry_cooldown_sec=float(data.get("reentry_cooldown_sec", 300.0)),
        emergency_cooldown_sec=float(data.get("emergency_cooldown_sec", 3600.0)),
        spot_fee_rate=float(data.get("spot_fee_rate", 0.00075)),
        futures_fee_rate=float(data.get("futures_fee_rate", 0.0002)),
        dry_run=bool(data.get("dry_run", True)),
        poll_interval_sec=float(data.get("poll_interval_sec", 60.0)),
        pre_funding_check_sec=float(data.get("pre_funding_check_sec", 300.0)),
        telegram_summary_sec=float(data.get("telegram_summary_sec", 1800.0)),
        log_dir=str(data.get("log_dir", "logs/v20")),
    )
