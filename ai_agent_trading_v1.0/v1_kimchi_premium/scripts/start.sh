#!/usr/bin/env bash
# systemd 진입점: ARB_SERVICE_LINE 으로 v1.1 / v1.2 선택.
#   v1.1 (기본): multi_main TRX+SOL — configs/multi.yaml
#   v1.2: 바이낸스 BTCUSDT/USDC만 — python -m src.v12.live_v2 (cloud.env.v1.2.example)
# 레거시 v1 단일코인(src.main)은 실행하지 말 것 — scripts/stop_legacy_trading.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

if [[ -f "${PROJECT_ROOT}/venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "${PROJECT_ROOT}/venv/bin/activate"
fi

mkdir -p logs

LINE="${ARB_SERVICE_LINE:-v1.1}"

if [[ "$LINE" == "v1.2" ]] || [[ "$LINE" == "v12" ]]; then
  export ARB_APP_VERSION="${ARB_APP_VERSION:-v1.2}"
  POLL="${ARB_V12_POLL:-0.05}"
  TIMEOUT="${ARB_V12_TIMEOUT:-15}"
  CMD=(python -m src.v12.live_v2 --poll "$POLL" --timeout "$TIMEOUT")
  # 멀티코인: ARB_V12_CONFIGS 우선, 없으면 ARB_V12_CONFIG (단일)
  if [[ -n "${ARB_V12_CONFIGS:-}" ]]; then
    CMD+=(--configs "$ARB_V12_CONFIGS")
  else
    CONFIG="${ARB_V12_CONFIG:-configs/v12/v12_btc_v2.yaml}"
    CMD+=(--config "$CONFIG")
  fi
  if [[ "${ARB_V12_LIVE:-0}" == "1" ]] || [[ "${ARB_V12_LIVE:-}" == "true" ]]; then
    CMD+=(--live)
  fi
  exec "${CMD[@]}"
fi

export ARB_APP_VERSION="${ARB_APP_VERSION:-v1.1}"
CONFIG="${ARB_MULTI_CONFIG:-configs/multi.yaml}"
exec python -m src.multi_main --config "$CONFIG"
