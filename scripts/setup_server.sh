#!/usr/bin/env bash
# EC2 Ubuntu 초기 설정 (저장소 클론 후 프로젝트 루트에서 한 번 실행)
#   bash scripts/setup_server.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== 1. 패키지 업데이트 ==="
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git

echo "=== 2. 가상환경 및 의존성 ==="
cd "$PROJECT_DIR"
python3 -m venv venv
# shellcheck source=/dev/null
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=== 3. 로그 디렉터리 ==="
mkdir -p logs

echo "=== 4. start.sh / stop_legacy_trading.sh 실행 권한 ==="
chmod +x scripts/start.sh scripts/stop_legacy_trading.sh

echo "=== 5. systemd 등록 ==="
sudo cp scripts/arb.service /etc/systemd/system/arb.service
sudo systemctl daemon-reload
sudo systemctl enable arb.service

echo "=== 완료 ==="
echo "1) 서버 .env:"
echo "   v1.1: scripts/cloud.env.v1.1.example (ARB_SERVICE_LINE 생략 또는 v1.1)"
echo "   v1.2: scripts/cloud.env.v1.2.example (ARB_SERVICE_LINE=v1.2, BINANCE 키, ARB_V12_LIVE)"
echo "2) 레거시 v1(src.main) 끄기: bash scripts/stop_legacy_trading.sh"
echo "3) 필요 시: sudo nano /etc/systemd/system/arb.service 경로/User 조정"
echo "4) 기동/재기동: sudo systemctl daemon-reload && sudo systemctl restart arb"
echo "5) 상태: sudo systemctl status arb --no-pager"
echo "6) 로그: tail -f logs/system.log"
