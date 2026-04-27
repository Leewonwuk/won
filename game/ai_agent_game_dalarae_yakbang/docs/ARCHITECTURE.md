# ARCHITECTURE

## 기술 스택
- **런타임**: 브라우저 ES modules (빌드 도구 없음)
- **엔진**: Phaser 3.60 (CDN)
- **사운드**: Tone.js 14.8 (CDN)
- **서버**: `npx serve` (정적 파일 서빙)

## 디렉터리 구조
```
src/
├── index.html              ← CDN 로드 순서: Phaser → Tone.js → main.js(module)
└── game/
    ├── main.js             ← Phaser.Game 생성
    ├── config.js           ← gameConfig + BALANCE 상수
    ├── scenes/
    │   ├── BootScene.js    ← 모든 런타임 텍스처 생성
    │   ├── TitleScene.js   ← 타이틀 + START 버튼
    │   ├── GameScene.js    ← 메인 루프
    │   └── ResultScene.js  ← 날짜 결산 모달
    ├── objects/
    │   ├── Patient.js      ← 환자 스프라이트 + 인내심 + 상태머신
    │   ├── Room.js         ← 방 스프라이트 + 치료 게이지
    │   └── FloatingText.js ← +골드 플로팅 이펙트
    └── systems/
        ├── EconomySystem.js← 골드, 만족/불만 누적
        ├── RoomSystem.js   ← 방 4개 생성 + 해금 체크
        ├── PatientSystem.js← 스폰, 큐잉, 소개
        └── AudioSystem.js  ← Tone.js BGM/SFX 싱글톤
```

## 씬 흐름
```
BootScene ──(텍스처 생성 후)──▶ TitleScene
                                    │ START 클릭
                                    ▼
                               GameScene  ◀──────┐
                                    │ 60초 경과  │ 다음날
                                    ▼           │
                               ResultScene ─────┘
```

## 데이터 흐름 (한 사이클)
1. `PatientSystem.spawnPatient()` → `Patient` 인스턴스 생성
2. `PatientSystem._tryAssignOrQueue()` → `RoomSystem.findAvailableRoom()` 조회
3. 빈 방 있으면 → `Patient.walkTo(room)` → `Room.startTreatment(patient)`
4. 빈 방 없으면 → `_enqueue()` → 대기열 좌표로 `walkTo()`
5. `GameScene.update(delta)` 루프
   - `RoomSystem.update(delta)` → 각 `Room.update(delta)` → 게이지 진행
   - 방이 완료 → `Room.completeTreatment()` → `patient_satisfied` 이벤트 emit
   - 환자 인내심 소진 → `Patient.onAngry()` 훅 (`GameScene._wireAngryHandler()` 에서 주입) 호출
6. `GameScene._onPatientSatisfied()` → Economy 업데이트 → `RoomSystem.checkUnlocks()`

## 이벤트
- `scene.events.emit('patient_satisfied', { patient, room, stars, gold })`
- Act 2 해금은 1초 주기 타이머에서 `EconomySystem.canUnlockAct2()` 폴링

## 상태 저장 (세션 내)
`GameScene` → `ResultScene` 으로 `summary` 객체 전달:
```js
{ day, gold, todayIncome, todaySatisfied, todayAngry,
  totalSatisfied, royalSatisfied, actUnlocked, unlockedRooms }
```
`ResultScene._goNextDay()` 에서 `scene.start('GameScene', { savedState })` 로 복원.

## 텍스처 생성 전략
모든 스프라이트는 `BootScene.create()` 에서 `Phaser.Graphics.generateTexture()` 로 생성.
- 환자: 16×20 픽셀 배열을 `_rect()` 유틸로 채우고 scale=2로 렌더
- 방: 64×80 직접 그래픽스 드로잉 (삼각형/사각형/원 조합)
- UI: 동전/별/분노/기둥 팻말/1px 유틸

## 성능 고려
- 환자 동시 최대 ~12명 예상 (방 4 + 대기열 8)
- `update()` 당 작업: O(방) + O(환자) = O(N) < 20 — 문제 없음
- `pixelArt: true` + `roundPixels: true` 로 도트 번짐 방지
- 텍스처 한 번만 생성 → 씬 재시작해도 재생성 없음 (`anims.exists` 가드)

## 알려진 제약
- Tone.js는 사용자 첫 인터랙션 이후에만 초기화됨 (브라우저 자동재생 정책). TitleScene의 START 클릭에서 `audioSystem.init()` 수행.
- 창 크기 변경에 대응하는 `Phaser.Scale.FIT` 스케일 사용.
