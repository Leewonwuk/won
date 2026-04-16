# 암호화폐 차익거래 자동매매 시스템

> **Crypto Arbitrage Trading Bot** — v1.1 (Upbit ↔ Binance) / v1.28 (Binance USDT/USDC)

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![AWS EC2](https://img.shields.io/badge/AWS-EC2_t3.micro-orange)](https://aws.amazon.com/ec2/)
[![Binance API](https://img.shields.io/badge/Binance-REST%20%2F%20WebSocket-yellow)](https://binance-docs.github.io/apidocs/)

---

## 📄 포트폴리오 상세 문서

전략 원리, 구현 상세, 백테스트 결과, 버그 해결 이력을 아래 Notion 페이지에 정리했습니다.

**[→ Notion 포트폴리오 보기](https://www.notion.so/3449fc6966538181bcb7ce45a254af3b)**

---

## 프로젝트 개요

| 항목 | 내용 |
|---|---|
| 기간 | 2025년 3월 ~ 2026년 4월 (약 13개월) |
| 역할 | 기획 · 설계 · 개발 · 운영 (1인) |
| 스택 | Python 3.11, asyncio, WebSocket, Binance/Upbit API |
| 인프라 | AWS EC2 t3.micro, systemd, Telegram Bot |
| AI 도구 | **Claude Code + Cursor** (설계·구현·디버깅 전 주기 활용) |

---

## 전략 구성

### v1.1 — Upbit ↔ Binance 김치프리미엄 재정거래

한국 거래소(Upbit)와 글로벌 거래소(Binance)의 **동일 코인 가격 괴리(김치프리미엄)**를 이용한 차익거래.

- 코인별 **4-잔고 모델** (upbit_krw / upbit_coin / binance_usdt / binance_coin)
- `asyncio` 기반 멀티코인 동시 운영 (DOGE, XRP, TRX, SOL)
- WebSocket 실시간 틱 + FX 피드로 매 틱 프리미엄 계산
- 잔고 소진 시 거래소 간 온체인 전송(리밸런싱) 자동 판단

**백테스트 결과 (1년 1분봉)**

| 코인 | 최적 임계값 | 연간 거래수 | 1년 수익률 |
|---|---|---|---|
| DOGE | 0.60% | 76회 | **+29.3%** |
| XRP | 0.70% | 23회 | +13.5% |
| TRX | 0.60% | 10회 | +6.1% |

---

### v1.28 — Binance USDT/USDC 스프레드 차익거래 (현재 운영 중)

동일 거래소(Binance) 내 **COINUSDT ↔ COINUSDC 마켓 간 일시적 스프레드**를 이용한 차익거래.

- 상태 머신: `IDLE → LEG_A_PENDING → LEG_B_PENDING → IDLE`
- 진입 임계값 **0.17%**, taker+maker 수수료 합산 ~0.15%
- **후기 Reprice 알고리즘**: T=30초 이후 maker 체결 유도 → 비상청산 taker fee 절감
- **GlobalTradeLock**: 6개 코인 병렬 엔진의 동시진입 방지
- 운영 코인: TRX, DOGE, XRP, SOL, BNB, ADA (6개)
- 운용 규모: ~1,975 USDT, 1회 거래 ~494 USDT

---

## 아키텍처

```
src/
├── multi_main.py              # v1.1 멀티코인 asyncio 메인 루프
├── strategy/
│   ├── spread_calc.py         # 프리미엄·순수익 계산
│   ├── signal.py              # 매매 신호 판단
│   └── capital_allocator.py  # 리밸런싱 판단
├── state/
│   └── multi_portfolio.py    # 4-잔고 포트폴리오 모델
├── exchanges/
│   ├── upbit_ws.py            # Upbit WebSocket
│   └── binance_ws.py          # Binance WebSocket
├── execution/
│   ├── live_engine.py         # 실주문 실행
│   └── paper_engine.py        # 페이퍼트레이딩
├── v12/
│   ├── live_engine_v2.py      # v1.28 상태 머신 엔진
│   ├── live_v2_main.py        # v1.28 멀티코인 메인
│   └── allocator_v2.py        # DT/DC 신호 판단
└── v20/
    └── funding_engine.py      # v2.0 펀딩비 차익 (개발 완료, 대기 중)
```

---

## 핵심 기술 구현

### 1. 실시간 WebSocket 아키텍처
- Upbit · Binance · FX(KRW/USDT) 3개 WebSocket을 단일 `asyncio` 이벤트 루프에서 동시 구독
- 연결 끊김 시 자동 재연결, WS 유실 시 REST 폴백

### 2. 상태 머신 기반 주문 관리 (v1.28)
- Leg A(진입) 미체결 → 타임아웃 취소 후 IDLE 복귀
- Leg B(청산) 지연 → 30초까지 수익권 GTC reprice → 30~120초 시장가 추종 maker 유도 → 120초 비상청산
- `stop_loss` + 타임아웃 이중 백스톱

### 3. 백테스팅 엔진
- Binance `/api/v3/klines` + Upbit `/v1/candles/minutes/1` 1분봉 수집
- 4-잔고 시뮬레이션으로 슬리피지·수수료·전송비 반영

### 4. 운영 자동화
- systemd 서비스 자동 재시작
- Telegram Bot: 거래 체결 즉시 알림 + 1시간마다 요약 + CSV 자동 전송

---

## AI Agent 활용

이 프로젝트는 **Claude Code (Anthropic)** 와 **Cursor** AI Agent를 전 개발 주기에 활용했습니다.

- **설계 단계**: 전략 로직, 상태 머신 구조, 수수료 모델 설계
- **구현 단계**: 핵심 알고리즘 코드 작성 및 리뷰
- **디버깅 단계**: Race condition, 누적 수치 오류 등 프로덕션 버그 분석 및 수정
- **운영 단계**: EC2 배포 자동화, 파라미터 튜닝 의사결정

> 커밋 히스토리에서 `Co-Authored-By: Claude` 태그로 AI 협업 구간을 확인할 수 있습니다.

---

## 설치 및 실행

```bash
pip install -r requirements.txt
cp .env.example .env
# .env에 API 키 입력
```

**v1.28 로컬 백테스트**
```bash
python -m src.v12.cli_backtest_v2 --config configs/v12/v12_doge_v2.yaml --days 30
```

**v1.1 멀티코인 페이퍼트레이딩**
```bash
python -m src.multi_main --config configs/multi.yaml
```

**테스트**
```bash
pytest -q
```

---

## 안전 원칙

- 기본 모드: `paper` (실주문 없음)
- 실주문 활성화: `ARB_ENABLE_LIVE_ORDERS=true` + `ARB_LIVE_DRY_RUN=false` 명시적 설정 필요
- API 키는 `.env`에만 보관 (`.env.example` 참조, 절대 커밋 금지)

---

## 라이선스

개인 포트폴리오 프로젝트입니다. 실전 투자 사용에 대한 책임은 사용자 본인에게 있습니다.
