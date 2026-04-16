# Upbit-Binance Arbitrage MVP

동기식 루프 기반 업비트-바이낸스 아비트리지 MVP입니다.  
초기 기본 모드는 `paper`이며, `live`는 안전 플래그 없이는 실행되지 않습니다.
또한 `live`에서도 기본은 `dry-run`으로 실제 주문 없이 주문 페이로드만 검증합니다.

## 1) 설치

```powershell
Set-Location "G:\내 드라이브\trading\arb"
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2) 실행 (기본: v2 멀티코인)

```powershell
python -m src.multi_main --config configs/multi.yaml --iterations 20
```

실행 로그는 `logs/multi_events.jsonl`에 저장됩니다.
레거시(v1) 단일코인 실행은 하위 섹션 참고.

## 3) 구조

- `src/multi_main.py`: v2 멀티코인 메인 루프 (기본)
- `src/backtest_v2_main.py`: v2 백테스트 엔트리
- `src/backtest/backtest_v2.py`: v2 백테스트 엔진
- `src/strategy/capital_allocator.py`: v2 거래/리밸런싱 의사결정
- `src/state/multi_portfolio.py`: v2 4-잔고 포트폴리오
- `configs/multi.yaml`: v2 기본 설정
- `src/main.py`: v1 단일코인 메인 루프 (레거시)
- `src/marketdata.py`: 업비트/바이낸스 시세 스냅샷
- `src/strategy/spread_calc.py`: 순스프레드 계산
- `src/strategy/signal.py`: 진입/청산 결정
- `src/execution/paper_engine.py`: 페이퍼 주문 실행
- `src/execution/live_engine.py`: 실거래 주문 라우팅(dry-run 지원)
- `src/execution/router.py`: paper/live 라우팅
- `src/execution/risk_guard.py`: 리스크 가드
- `src/state/portfolio.py`: 포지션/PnL 상태
- `src/logging/event_logger.py`: JSONL 이벤트 로깅

## 4) 안전 원칙

- 기본 `mode: paper`
- `mode: live`는 `enable_live_orders: true` 없으면 실패
- `live_dry_run: true`를 기본으로 유지 후 충분히 검증된 뒤 `false` 전환
- 실거래 키는 `.env`에만 보관 (`.env.example` 참조)

## 5) 라이브 확장 사용법

`.env`에 키를 넣고 아래와 같이 활성화합니다.

```powershell
$env:ARB_MODE="live"
$env:ARB_ENABLE_LIVE_ORDERS="true"
$env:ARB_LIVE_DRY_RUN="true"
python -m src.main --config configs/default.yaml --iterations 5
```

`ARB_LIVE_DRY_RUN=false`로 바꾸면 실제 주문 API를 호출합니다.
`live` 모드에서도 내부 `paper_result`를 함께 기록해 포지션/PnL 상태를 동기화합니다.

## 6) 송금수수료 반영 방식 (SOL/TRX 권장)

송금 수수료는 체인 특성상 보통 "고정 코인 수량"이므로, 엔진에서 아래처럼 거래금액 대비 비율(%)로 환산합니다.

- `upbit -> binance` 환산율  
  `transfer_fee_upbit_to_binance_base * binance_ask(USDT) * fx / trade_notional_krw`
- `binance -> upbit` 환산율  
  `transfer_fee_binance_to_upbit_base * upbit_ask(KRW) / trade_notional_krw`

그 다음 최종 순엣지는:
- `raw_spread - (거래수수료 + 슬리피지) - 환산된 송금수수료율`

### SOL/TRX 프리셋 실행

```powershell
python -m src.main --config configs/sol.yaml --iterations 30
python -m src.main --config configs/trx.yaml --iterations 30
```

`configs/sol.yaml`, `configs/trx.yaml`의 `transfer_fee_*_base`를 실제 출금 수수료 코인 수량으로 맞춰주면 됩니다.

## 7) v2 백테스트 (기본)

멀티코인(SOL/TRX) 기준:

```powershell
python -m src.backtest_v2_main --config configs/multi.yaml --days 30 --resolution 1
```

기존 CSV 재사용:

```powershell
python -m src.backtest_v2_main --config configs/multi.yaml --days 180 --resolution 1 --skip-collect
```

생성 결과:
- `data/backtest/*_v2_report_*.json`
- `data/backtest/*_v2_trades_*.csv`

## 8) 레거시(v1) 30일 백테스트 (5분봉)

네가 원한 조건(업비트 100만 + 바이낸스 100만, 30일, 5분봉)으로 바로 실행:

```powershell
python -m src.backtest_main --config configs/sol.yaml
python -m src.backtest_main --config configs/trx.yaml
```

백테스트 러너는 위 명령에서 각 사이드 자본 100만원을 기준으로 매 진입 시점에
`use_full_capital_per_trade=True`를 적용해 100% 노셔널 가정으로 포지션 크기를 계산합니다.

생성 결과:
- `data/backtest/*_30d_5m_*.csv` : 정렬된 5분봉 입력 데이터
- `data/backtest/*_30d_report_*.json` : 수익률/손익/승률/MDD 리포트

백테스트 데이터는 아래 API 기반:
- 업비트 5분봉: 대상 코인 KRW 마켓 + `KRW-USDT`(환율 시계열)
- 바이낸스 5분봉: 대상 코인 USDT 심볼

## 9) 테스트

```powershell
pytest -q
```

## 10) 6개월 백테스트 + 거래수>0 스윕 (v1)

```powershell
python -m src.backtest_main --config configs/sol.yaml --days 180 --sweep
python -m src.backtest_main --config configs/trx.yaml --days 180 --sweep
```

- `--days 180`: 최근 6개월(5분봉) 데이터 수집/백테스트
- `--sweep`: 임계치 조합 중 `trade_count > 0` 결과만 CSV로 저장
- 출력 파일 예시:
  - `data/backtest/sol_180d_sweep_gt0_*.csv`
  - `data/backtest/trx_180d_sweep_gt0_*.csv`

## 11) 거래 발생 로직 설명 (v1)

백테스트 기준은 아래와 같습니다.

- 타임프레임: `5분봉`
- 기간: `--days` 값 (예: 180일)
- 초기자본: 업비트 100만 + 바이낸스 100만
- 주문크기: `use_full_capital_per_trade=True` (진입 시점 100% 노셔널)
- 비용: 거래수수료 + 슬리피지 + 송금수수료(코인 고정 수수료 -> 거래금액 대비 % 환산)

거래 발생 조건:
- 포지션 없음:
  - `upbit_to_binance_edge_rate >= entry_threshold_rate` 이면 `OPEN_UPBIT_SHORT_BINANCE_LONG`
  - `binance_to_upbit_edge_rate >= entry_threshold_rate` 이면 `OPEN_UPBIT_LONG_BINANCE_SHORT`
- 포지션 보유 중:
  - `max(open_edge_rates) <= exit_threshold_rate` 이면 `CLOSE`

생성 파일:
- `*_report_*.json`: 총 거래수/수익률/누적수익금/승률/MDD
- `*_trades_*.csv`: 각 OPEN/CLOSE 시점의 조건과 가격, 엣지, 손익

## 12) Next Steps 참고사항 (고도화 후보)

아래는 유튜브 리서치 + 현재 구조를 기준으로, 실제 적용 가치가 높은 순서의 개선 후보입니다.

### A. 순엣지 임계값의 동적화 (최우선)

현재 임계값 로직이 있더라도, 다음 항목을 반영해 동적으로 보정하면 과진입/미체결 리스크를 줄일 수 있습니다.

- 고정 임계값 대신 `dynamic_threshold` 도입:
  - 변동성 확대 구간: 임계값 상향
  - 호가 얕은 구간/야간 유동성 약한 구간: 임계값 상향
- 비용 추정 실시간화:
  - 슬리피지, 펀딩/헤지비, 환헤지비를 가능한 최신 상태로 반영
- 불확실성 버퍼 분리:
  - `net_edge >= dynamic_threshold + uncertainty_buffer` 구조로 보수적 진입

권장 구현 포인트:
- `src/strategy/spread_calc.py`: 순엣지 계산 확장
- `src/strategy/signal.py` 또는 `src/strategy/capital_allocator.py`: 동적 임계값 반영

### B. 전송 구간 델타헤지 상태머신화 (우선)

전송 지연/급변 구간에서 손익 분산을 줄이기 위해 상태 기반 실행을 명시적으로 관리합니다.

권장 상태:
- `hedge_open -> transfer_pending -> transfer_confirmed -> hedge_close -> rebalance_done`

가드레일:
- 최대 전송 대기시간 초과 시:
  - 포지션 축소 또는 강제 unwind
- 부분체결 발생 시:
  - 잔량 기준 재헤지(델타 중립 유지) 우선

권장 구현 포인트:
- `src/execution/router.py`, `src/execution/risk_guard.py`
- `src/state/portfolio.py`, `src/state/multi_portfolio.py`

### C. 김프/역프 밴드 리밸런싱 (우선)

단발 진입보다 밴드 기반 왕복 운용이 과매매를 줄이고 복리 효율을 높이는 데 유리합니다.

권장 규칙 예시:
- 진입 밴드: `entry_band_low ~ entry_band_high`
- 청산 밴드: `exit_band_low ~ exit_band_high`
- 재진입 쿨다운: `n` 캔들

운영 팁:
- SOL/TRX를 동일 임계값으로 묶지 말고 종목별 밴드 분리
- 멀티코인 총 리스크 버짓(cap) 설정

### D. 체결확률 기반 기대값 필터 (중요)

시그널 발생 자체보다 "실제 체결 성공 가능성"을 반영한 기대값이 더 중요합니다.

- `expected_value = net_edge * fill_probability - tail_risk_penalty`
- 임계값 비교 대상을 raw edge가 아닌 expected value로 전환

권장 구현 포인트:
- 최근 체결 로그(`logs/*.jsonl`) 기반으로 시간대/호가깊이별 fill model 추정

### E. 운영 체크리스트 (라이브 전 필수)

- `ARB_LIVE_DRY_RUN=true`로 최소 N회 연속 정상 시퀀스 확인
- 실패 케이스 별 리커버리 정책 문서화:
  - API 지연
  - 전송 지연
  - 부분체결
  - 환율 급변
- 백테스트/리플레이에서 아래를 반드시 함께 보고:
  - `trade_count`, `total_return_rate`, `max_drawdown_rate`
  - 실패 복구 후 손익 회복 시간

### F. 우선순위 요약

1. 동적 순엣지 임계값
2. 전송 구간 델타헤지 상태머신
3. 김프/역프 밴드 리밸런싱
4. 체결확률 기반 expected value 필터
5. 라이브 장애복구 플레이북 고정

## 13) Claude Code / 에이전트 운영 (토큰·컨텍스트)

Claude Code나 Cursor 에이전트로 이 저장소를 다룰 때, 불필요한 읽기·탐색 토큰을 줄이기 위한 규약은 아래에 둡니다.

- **SOP 스킬**: [`.cursor/skills/claude-code-token-efficiency/SKILL.md`](.cursor/skills/claude-code-token-efficiency/SKILL.md) — `.claudeignore`, 슬림 `CLAUDE.md`, 세션 정리, 선택적 qmd 인덱싱, 3-에이전트(Architect→Builder→Reviewer) 체크리스트
- **프로젝트 힌트**: 루트 [`CLAUDE.md`](CLAUDE.md) (짧게 유지; 상세는 스킬 `reference/`로 분리)
- **Claude가 읽지 않을 경로**: 루트 [`.claudeignore`](.claudeignore) — `venv`, 캐시, `logs/`, 대용량 `data/backtest/` 등 (`src/`, `configs/`는 제외하지 않음)
- **QMD MCP**: Cursor는 [`.cursor/mcp.json`](.cursor/mcp.json)에서 [`scripts/qmd-mcp-launch.cjs`](scripts/qmd-mcp-launch.cjs)로 `qmd mcp`를 띄웁니다(`.qmd/` 생성 + `INDEX_PATH` 설정으로 DB 디렉터리 누락 오류 방지). 루트에서 **`npm install`** 후 MCP를 다시 로드하세요. 인덱싱은 [`scripts/qmd-index.ps1`](scripts/qmd-index.ps1). 상세는 [`.cursor/skills/claude-code-token-efficiency/reference/qmd-cursor-mcp.md`](.cursor/skills/claude-code-token-efficiency/reference/qmd-cursor-mcp.md).

출처 요약 영상: [Claude Code 토큰 절감 3가지 기법 (YouTube)](https://www.youtube.com/watch?v=t55_Ys4q7Uo)

