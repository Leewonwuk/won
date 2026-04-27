# ADR — Architecture Decision Records

## ADR-001: 빌드리스 ES 모듈
**Context**: 카이로소프트 스타일은 규모가 크지 않고, 핵심은 게임 디자인 이터레이션.
**Decision**: webpack/vite 없이 브라우저 네이티브 `<script type="module">`으로 import.
**Consequence**:
- (+) `npx serve` 만으로 바로 실행, 셋업 비용 0
- (+) 수정 → 새로고침 피드백 루프가 가장 짧음
- (−) 브라우저 지원 필요 (모던 브라우저만)
- (−) 번들 최적화/코드스플리팅 없음 — 이 규모에선 불필요

## ADR-002: 외부 이미지 에셋 0개
**Context**: 아트 파이프라인 없이 혼자 개발. 도트 아트 텍스처 수십 개를 에셋 파일로 관리하면 복잡.
**Decision**: 모든 텍스처를 `BootScene`에서 `Phaser.Graphics.generateTexture()`로 생성.
**Consequence**:
- (+) 색상/형상 튜닝이 코드 수정만으로 됨 (GIMP 왕복 불필요)
- (+) 빌드 산출물은 HTML/JS만 — 배포 단순
- (−) 픽셀아트의 섬세한 표현은 제한됨 (기하 도형 조합 수준)
- (−) 텍스처 수가 극적으로 늘면 BootScene 비대화 — 이 규모에선 OK

## ADR-003: Phaser physics 미사용
**Context**: 경영 시뮬은 물리 충돌이 필요 없다. 환자는 정해진 좌표 사이를 움직이기만 함.
**Decision**: `physics` 설정 생략. 모든 이동은 `this.tweens.add()` 로 구현.
**Consequence**:
- (+) 런타임 오버헤드 절감
- (+) 환자 이동 타이밍이 결정적 — 버그 재현/디버깅 쉬움
- (−) 환자 간 충돌/집단이동 같은 창발 움직임은 불가 — 의도된 제약

## ADR-004: Tone.js 지연 초기화
**Context**: 브라우저 자동재생 정책상 사용자 인터랙션 전에는 `AudioContext.start()` 실패.
**Decision**: `TitleScene` 의 START 버튼 클릭 시 `audioSystem.init()` 호출.
**Consequence**:
- (+) 콘솔 경고/에러 없이 깔끔하게 BGM 시작
- (+) Tone.js 로드 실패해도 게임은 계속 동작 (graceful degradation)
- (−) 사용자가 START를 누르기 전엔 음악 없음 — 타이틀 화면은 정적

## ADR-005: onAngry 훅 주입 (런타임 확장)
**Context**: `Patient` 클래스는 `onAngry()` 콜백을 가지고 있지만, 시스템 간 결합을 피하고 싶음.
**Decision**: `GameScene._wireAngryHandler()` 에서 `patientSys.spawnPatient`를 프록시로 덮어써 매 스폰 시 `patient.onAngry` 훅을 주입.
**Consequence**:
- (+) `Patient` 가 `EconomySystem`/`PatientSystem` 을 직접 알 필요 없음
- (+) 씬 레벨에서 한 곳에 배선 로직 집약
- (−) 프록시 패턴 — 익숙하지 않으면 흐름이 헷갈릴 수 있음. 주석으로 보완.

## ADR-006: 씬 간 상태 전달은 `scene.start(data)`
**Context**: 날짜 결산 후 다음 날로 넘어갈 때, 골드/누적만족을 유지해야 함. 글로벌 store 도입 vs 씬 인자.
**Decision**: Phaser 표준 `scene.start('GameScene', { savedState })` 패턴 사용.
**Consequence**:
- (+) 프레임워크가 제공하는 흐름 그대로 — 관례 일치
- (+) 상태가 씬 라이프사이클에 묶여 누수 없음
- (−) 씬을 재시작하므로 `EconomySystem` 등도 재생성 — 복원 로직이 약간 장황 (수용 가능)

## ADR-007: BALANCE 상수 단일 위치
**Context**: 치료 시간, 치료비, 인내심 등 수치 튜닝이 잦을 것으로 예상.
**Decision**: `config.js` 의 `BALANCE` 객체 한곳에만 숫자. 모든 모듈은 여기서 읽음.
**Consequence**:
- (+) 튜닝 1회 수정 → 게임 전체 반영
- (+) 밸런스 테이블이 한눈에 보임 (문서화 역할도)
- (−) 런타임 변경은 미지원 — 필요하면 별도 설정 레이어 추가
