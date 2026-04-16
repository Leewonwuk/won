# SOL + XRP 듀얼 라이브 배포 가이드

> **대상**: Cursor AI (자동 배포 실행)
> **목표**: EC2에서 SOL/XRP 동시 라이브 트레이딩 실행
> **이전 상태**: 단일 `arb.service` (BTC 운용 중 또는 중단됨)
> **이후 상태**: `arb-sol.service` + `arb-xrp.service` 2개 독립 서비스

---

## 사전 확인사항 (배포 전 반드시 체크)

### 1. 로컬 코드 상태 확인

```powershell
cd C:\Users\user\trading\arb
git status   # 커밋되지 않은 변경사항 없는지 확인
```

반드시 커밋되어야 할 파일:
- `src/v12/live_engine_v2.py` — `sync_balances()` cap 로직 추가됨
- `configs/v12/v12_sol_v2.yaml` — `initial_usdt/usdc: 300`
- `configs/v12/v12_xrp_v2.yaml` — `initial_usdt/usdc: 300`
- `scripts/arb-sol.service` — 신규
- `scripts/arb-xrp.service` — 신규

### 2. 바이낸스 계좌 잔고 준비

서버 실행 전 바이낸스 계좌에 다음이 있어야 합니다:
- **USDT: 600 이상** (SOL 300 + XRP 300)
- **USDC: 600 이상** (SOL 300 + XRP 300)
- **BNB: 소량** (수수료 할인용, 0.01 BNB 이상 권장)

### 3. 서버 .env 필수값 확인

서버 `.env`에 아래 값이 있어야 합니다 (SSH로 직접 확인):

```bash
# SSH 접속 후
cat ~/arb/.env | grep -E "BINANCE|TELEGRAM|ARB_"
```

필수 항목:
```
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
ARB_SERVICE_LINE=v1.2   ← 이 값은 .service 파일이 override하므로 없어도 됨
```

> ⚠️ **주의**: `-UploadLocalEnv` 옵션 사용 금지. 로컬 .env는 v1.1 설정이라 서버 .env를 덮어쓰면 장애 발생.

---

## Step 1: 코드 배포

```powershell
cd C:\Users\user\trading\arb
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy_ec2_windows.ps1
```

`-UploadLocalEnv` **없이** 실행합니다. 코드만 업로드됩니다.

완료 메시지 확인:
```
=== done ===
Logs: ssh ... tail -f ~/arb/logs/system.log
```

---

## Step 2: 기존 arb.service 중지

> ✅ **완료됨** — 사용자가 수동으로 중지 및 비활성화 완료. 이 단계 스킵.

---

## Step 3: 새 서비스 파일 등록

```bash
# EC2 SSH 접속 후
sudo cp ~/arb/scripts/arb-sol.service /etc/systemd/system/
sudo cp ~/arb/scripts/arb-xrp.service /etc/systemd/system/
sudo systemctl daemon-reload
```

---

## Step 4: 로그 디렉토리 생성

```bash
mkdir -p ~/arb/logs
```

---

## Step 5: DRY-RUN 검증 (실거래 전 필수)

서비스 파일에서 `ARB_V12_LIVE=1` 라인을 임시로 제거하거나,
SSH에서 직접 dry-run 실행:

```bash
cd ~/arb
source venv/bin/activate

# SOL dry-run (약 30초 관찰)
python -m src.v12.live_v2 --config configs/v12/v12_sol_v2.yaml &
sleep 30
kill %1

# XRP dry-run (약 30초 관찰)
python -m src.v12.live_v2 --config configs/v12/v12_xrp_v2.yaml &
sleep 30
kill %1
```

확인할 것:
- `잔고 동기화: USDT=300(실제=6xx)` — cap 로직 정상 작동
- `DRY-RUN 모드` 메시지 출력
- 에러 없이 신호 대기 루프 진입

---

## Step 6: 라이브 서비스 시작

```bash
# SOL 먼저 시작, 텔레그램 알림 확인 후 XRP 시작
sudo systemctl enable arb-sol
sudo systemctl start arb-sol
```

텔레그램에서 SOL 시작 알림 수신 확인 후:

```bash
sudo systemctl enable arb-xrp
sudo systemctl start arb-xrp
```

---

## Step 7: 정상 동작 확인

```bash
# 서비스 상태
sudo systemctl status arb-sol --no-pager
sudo systemctl status arb-xrp --no-pager

# 실시간 로그 (각각 다른 터미널)
tail -f ~/arb/logs/sol.log
tail -f ~/arb/logs/xrp.log

# 잔고 cap 확인 (log에서 검색)
grep "잔고 동기화" ~/arb/logs/sol.log | tail -5
grep "잔고 동기화" ~/arb/logs/xrp.log | tail -5
```

정상 로그 예시:
```
잔고 동기화: USDT=300.00(실제=612.34)  USDC=298.50(실제=611.20)  BNB=0.012500
```

---

## 운영 중 명령어 참조

```bash
# 개별 재시작
sudo systemctl restart arb-sol
sudo systemctl restart arb-xrp

# 개별 중지
sudo systemctl stop arb-sol
sudo systemctl stop arb-xrp

# 전체 중지
sudo systemctl stop arb-sol arb-xrp

# 에러 확인
sudo journalctl -u arb-sol -n 50 --no-pager
sudo journalctl -u arb-xrp -n 50 --no-pager

# 에러 로그
tail -50 ~/arb/logs/sol_error.log
tail -50 ~/arb/logs/xrp_error.log
```

---

## 설정 요약

| 항목 | SOL | XRP |
|------|-----|-----|
| config | `configs/v12/v12_sol_v2.yaml` | `configs/v12/v12_xrp_v2.yaml` |
| 할당 자본 | USDT 300 + USDC 300 | USDT 300 + USDC 300 |
| 진입 임계값 | 0.04% | 0.04% |
| 수수료 (레그당) | maker 0.015% | maker 0.015% |
| fee_stack | 0.03% | 0.03% |
| 타임아웃 | 15초 | 15초 |
| 서비스명 | `arb-sol` | `arb-xrp` |
| 로그 | `logs/sol.log` | `logs/xrp.log` |

---

## 롤백 (긴급 전체 중지)

```bash
sudo systemctl stop arb-sol arb-xrp
```

미체결 주문이 있을 수 있으므로 바이낸스 앱에서 미체결 주문 수동 확인 후 취소.
