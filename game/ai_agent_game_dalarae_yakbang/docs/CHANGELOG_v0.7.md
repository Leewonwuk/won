# v0.7 — Phase 7-A · 7-B (인접성 경제학 + 살아있는 환자)

릴리스 일자: 2026-04-20
기준 코드: `src-v0.7/` (= 작업 종료 시점의 `src-v0.6/` 스냅샷)

이번 버전은 단일 거대 기능 추가가 아니라 "환자 의사결정 + 공간 퍼즐" 두 축의 밀도 보강이다.
기존 v0.6 의 랜덤·평면적 의사결정을 줄이고, 사용자가 "어디에 어떤 방을 놓을지" 매번 고민하게 만드는 게 목적.

---

## 묶음 A — Phase 7-A "살아있는 환자"

### A1. 병세별 치료방 선호 가중치
- **파일**: `game/systems/PatientSystem.js:_findReachableTreatRoom`, `game/config.js`
- **로직**: 환자 `illness` (moxa/acu/herb) 와 다른 치료방은 거리 점수에 `BALANCE.illnessMismatchPenalty` (=5) 가산.
  - 매칭 치료방이 5칸 더 멀어도 매칭 우선. 더 멀면 어쩔 수 없이 다른 방.
- **체감 변화**: 머리 위 도트색이 실제 들어가는 방과 시각적으로 일치.

### A2. 방별 수입 집계 + ResultScene 스택바
- **파일**: `game/scenes/GameScene.js (_monthIncomeByBuilding, _onPatientPaid, _openMonthResult)`, `game/scenes/ResultScene.js`
- **로직**: 월간 누적기 `_monthIncomeByBuilding{ moxa, acu, herb, haewoso, gukbap }` + 결산에 가로 스택바 + 색상 범례.
- **체감 변화**: "어느 방이 벌었나" 즉시 보임. 다음 달 어디 늘릴지 데이터 기반 결정 가능.

### A3. 철거 시 50% 환급
- **파일**: `game/scenes/GameScene.js:_tryDemolish` (이미 v0.6 에 구현돼 있어 검증만)
- **로직**: 마루·건물 모두 `cost/2` 환급 + `+N전` floating text.
- **체감 변화**: 잘못 지은 방 부수기 부담 감소 → 실험 빈도 ↑.

---

## 묶음 B — Phase 7-B "공간 퍼즐의 밀도"

### B1. 우물 보너스를 모든 치료방으로 확장
- **파일**: `game/systems/PatientSystem.js:_beginUsing`, `_finishUsing`, `game/config.js`
- **로직**: `BALANCE.wellBonus` 에 `acuScore: 1`, `moxaScore: 1` 추가.
  - 약방: +2 전 (기존)
  - 침방·뜸방: 만족도 점수 +1 (신규)
- **체감 변화**: 우물이 "약방 전용 부속품"에서 "치료실 종합 보조"로 격상.

### B2. 같은 치료방 4방 인접 시 혼잡 페널티
- **파일**: `game/systems/PatientSystem.js:_clusterPenalty`, `_finishUsing`, `game/config.js`
- **로직**: `BALANCE.clusterPenaltyPerRoom` (=1) × 같은 종류 인접 방 개수 → fee 차감 (최소 1전 보장).
  - moxa(fee 2): 인접 1개 → 1전 (-50%, 강한 압력)
  - acu(fee 3): 인접 1개 → 2전 (-33%)
  - herb(fee 6): 인접 1개 → 5전 (-16%)
- **체감 변화**: 한 모퉁이 몰빵이 손해. "흩어 배치" 동기 부여.

### B3. 배치 모드 인접 보너스/페널티 미리보기
- **파일**: `game/scenes/GameScene.js:_renderAdjPreview`, `_clearAdjPreview`, `_onTileHover`, `_selectTool`, `_onShutdown`, `game/systems/GridSystem.js:tile_hover` (v0.6에 이미 emit 중)
- **로직**: 빈 마루 호버 시 선택 도구별 영향 영역 후광 + 머리 위 라벨.
  - 치료방: 인접 소나무(녹) / 우물(파랑) / 같은 종류(빨강) + "+1점수 / +2전 / -1전 (혼잡)"
  - 우물: 영향 받을 치료방에 청색 후광
  - 소나무: 영향 받을 4방 건물에 녹색 후광
- **체감 변화**: 보너스가 더는 invisible 이 아님. "여기 놓으면 +N" 학습 가능.

---

## 호환성 노트

- v0.6 세이브 데이터 호환 (현재 세이브 시스템 자체가 없음 — 세션 단위 플레이)
- `BALANCE` 추가 키: `illnessMismatchPenalty`, `wellBonus.acuScore`, `wellBonus.moxaScore`, `clusterPenaltyPerRoom`
- 기존 `BALANCE` 키 변경 없음 (추가만)
- `_onPatientPaid` 시그니처에 `building` 추가 — PatientSystem 이 이미 emit 중이라 destructure 만 추가

## 다음 단계 (묶음 C 후보 — Phase 7-C)

- "달이 뜨면 도깨비가" — Act II 요괴 환자 + 이벤트 루프
- 또는 사용자 검증 결과 보고 우선순위 재조정
