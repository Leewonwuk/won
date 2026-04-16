#!/usr/bin/env bash
# 로컬(맥/리눅스)에서 EC2로 코드 동기화 후 서비스 재시작
# 사용 전: export ARB_DEPLOY_SERVER='ubuntu@x.x.x.x'
#   bash scripts/deploy.sh

set -euo pipefail

SERVER="${ARB_DEPLOY_SERVER:-ubuntu@YOUR_EC2_IP}"
PROJECT_DIR="/home/ubuntu/arb"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$SERVER" == *"YOUR_EC2_IP"* ]]; then
  echo "ARB_DEPLOY_SERVER 를 설정하세요. 예: export ARB_DEPLOY_SERVER='ubuntu@1.2.3.4'"
  exit 1
fi

echo "=== rsync → $SERVER:$PROJECT_DIR ==="
rsync -avz \
  --exclude='.env' \
  --exclude='logs/' \
  --exclude='data/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='venv/' \
  --exclude='.git/' \
  --exclude='.pytest_cache/' \
  "$ROOT/" "$SERVER:$PROJECT_DIR/"

echo "=== 레거시 v1 중지 + arb 재시작 (v1.1) ==="
ssh "$SERVER" "chmod +x $PROJECT_DIR/scripts/*.sh && bash $PROJECT_DIR/scripts/stop_legacy_trading.sh || true && sudo systemctl daemon-reload && sudo systemctl restart arb && sudo systemctl status arb --no-pager"

echo "=== 배포 완료 ==="
