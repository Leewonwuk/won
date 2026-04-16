# 아키텍처: Go-Running

## 디렉토리 구조
```
src/
├── index.html                  # CDN 로드 + main.js import
├── assets/
│   ├── ref-bichon.jpg          # 비숑 참고 이미지 (런타임 미사용)
│   └── ref-pomeranian.jpg      # 포메 참고 이미지 (런타임 미사용)
└── game/
    ├── main.js                 # new Phaser.Game(config) 진입점
    ├── config.js               # Phaser.Game 설정
    ├── scenes/
    │   ├── BootScene.js        # 픽셀 텍스처/애니메이션 생성
    │   ├── IntroScene.js       # 스토리 인트로 + 시작 버튼
    │   ├── GameScene.js        # 메인 게임 루프
    │   └── GameOverScene.js    # 게임 오버 화면
    ├── objects/
    │   ├── Gorani.js           # 고라니 상태머신(픽셀 스프라이트)
    │   ├── Obstacle.js         # 장애물(hit 상태 포함)
    │   └── Item.js             # 아이템(collect 상태 포함)
    └── systems/
        ├── AudioSystem.js      # Tone.js BGM/SFX 관리
        ├── DayNightSystem.js   # 낮/밤 전환
        └── HelperSystem.js     # 참새/쥐 도우미 + 보스 타격
```

## Phaser Scene 흐름
```
BootScene
  → IntroScene
  → GameScene
  → GameOverScene
  → GameScene
```

## 게임 루프 데이터 흐름
```
GameScene.update()
  ├── Gorani.update()               → run/jump/hurt 상태 전환
  ├── Parallax layers               → 구름/빌딩 스크롤
  ├── Obstacle/Item update          → 이동 + 수명 관리
  ├── DayNightSystem.update(delta)  → 낮/밤 + BGM 테마
  ├── HelperSystem.update(delta)    → 도우미 스폰
  ├── HelperSystem.tryHitBoss()     → 도우미-보스 상호작용
  └── Boss loop                     → 450m 주기 소환 + 경고 + 다트 패턴
```

## 주인공 애니메이션 처리 (픽셀 스프라이트)
- `BootScene`이 런타임 픽셀 텍스처를 생성한다.
- 텍스처 키:
  - `gorani-run-1`, `gorani-run-2`
  - `gorani-jump-up`, `gorani-jump-down`
  - `gorani-hurt-1`, `gorani-hurt-2`
- 애니메이션 키:
  - `gorani-run` (지상)
  - `gorani-hurt` (피격)
- 공중 상태는 `setTexture`로 상승/하강 프레임을 직접 전환한다.

## 충돌/수집 처리
- `Obstacle`는 `hit` 상태를 갖고 `markHit()`으로 재충돌을 방지한다.
- `Item`은 `collected` 상태를 갖고 `collect()`에서 바디 비활성화 후 페이드아웃 제거한다.
- overlap process에서 `item.active && !item.collected` 조건을 사용한다.

## 오디오 아키텍처 (Tone.js)
- `AudioSystem` 싱글톤으로 BGM/SFX를 관리한다.
- BGM은 `Tone.Sequence` 루프(낮/밤/보스/인트로/게임오버)로 구성한다.
- SFX는 점프/수집/피격/보스등장 이벤트에 연결한다.

## 상태 관리
- 씬 간 데이터 전달은 `scene.start(key, data)`를 사용한다.
- 게임 상태(HP, 점수, 거리, 속도, 낮밤, 보스)는 `GameScene` 인스턴스 변수로 관리한다.
- 게임오버 시 `{ score, distance }`를 전달한다.

## 좌표계 & 물리
- Phaser Arcade Physics 사용
- 캔버스 크기: 800 x 400
- 중력: 600 (y축)
- 지면 y: 340
- 스크롤 속도: 초기 290px/s, 매 120m마다 +14px/s, 최대 640px/s
