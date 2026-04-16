#!/usr/bin/env bash
# v1 단일코인 레거시(src.main) 프로세스만 중지. multi_main / systemd arb.service 는 건드리지 않음.
set -euo pipefail

echo "Stopping legacy v1 trading (src.main) if running..."
pkill -f '[p]ython.*-m src\.main' 2>/dev/null || true
pkill -f '[p]ython3.*-m src\.main' 2>/dev/null || true
pkill -f '[p]ython.*src/main\.py' 2>/dev/null || true
echo "Done. multi_main: sudo systemctl status arb"
