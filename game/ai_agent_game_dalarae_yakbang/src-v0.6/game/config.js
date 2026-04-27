// ─── 캔버스 ──────────────────────────────────────────────
// Scene 은 main.js 에서 주입. 여기서 import 하면 config→scene→system→config
// 순환(BuildingRegistry 가 최상위에서 BALANCE.costs 접근) → TDZ 에러.
export const GAME_WIDTH = 800;
// Phase 7-C: 카이로풍 하단 탭 메뉴 공간 확보 (720 → 860, +140).
// 탭바 32 + 콘텐츠 108 = 140. 그리드·HUD 치수·밸런스는 불변.
export const GAME_HEIGHT = 860;

// ─── 그리드 ──────────────────────────────────────────────
export const TILE_SIZE = 64;
export const GRID_COLS = 10;
export const GRID_ROWS = 10;
export const GRID_PIXEL_W = TILE_SIZE * GRID_COLS;        // 640
export const GRID_PIXEL_H = TILE_SIZE * GRID_ROWS;        // 640

export const HUD_TOP_H = 40;
export const HUD_BOT_H = 40;
export const GRID_ORIGIN_X = (GAME_WIDTH - GRID_PIXEL_W) / 2; // 80
export const GRID_ORIGIN_Y = HUD_TOP_H;                       // 40

// ─── 하단 카이로풍 탭 메뉴 (Phase 7-C) ──────────────────
// 그리드(40~680) 아래, 하단 HUD(820~860) 위에 위치.
// 상단 32px 탭바 + 하단 108px 콘텐츠(아이콘 그리드 + 상세 패널).
export const MENU_STRIP_Y = GRID_ORIGIN_Y + GRID_PIXEL_H;     // 680
export const MENU_STRIP_H = 140;
export const MENU_TAB_H = 32;

// 대문: 하단 중앙 1칸 고정
export const GATE_COL = 4;
export const GATE_ROW = GRID_ROWS - 1;      // 9
// 환자 스폰/퇴장 포인트: 대문 바로 위 타일
export const SPAWN_COL = GATE_COL;
export const SPAWN_ROW = GATE_ROW - 1;      // 8

export const gameConfig = {
  type: window.Phaser.AUTO,
  parent: 'game-root',
  width: GAME_WIDTH,
  height: GAME_HEIGHT,
  backgroundColor: '#1a1428',
  pixelArt: true,
  roundPixels: true,
  scale: {
    mode: window.Phaser.Scale.FIT,
    autoCenter: window.Phaser.Scale.CENTER_BOTH,
    width: GAME_WIDTH,
    height: GAME_HEIGHT
  },
  scene: []  // main.js 에서 주입
};

// ─── v0.6 게임 밸런스 ───────────────────────────────────
// Phase 1은 그리드·대문·마루 pathfinding 뼈대만 사용.
// 나머지 숫자는 이후 Phase에서 점진 활성화.
export const BALANCE = {
  startGold: 100,
  startMyeongui: 0,

  // 시간축
  weekMs: 15_000,
  monthMs: 60_000,
  yearMs: 720_000,

  // 스폰
  autoSpawnIntervalMs: 10_000,
  spawnMinGapMs: 3_000,
  patientStayMs: 15_000,
  stayBonusHaewosoMs: 5_000,
  stayBonusWellMs: 5_000,
  stayBonusGukbapMs: 5_000,
  maxPatients: 8,
  patientFadeOutMs: 400,

  // 시설 이용시간. 국밥집은 식사 연출을 위해 편의시설 기본값(2초)보다 길게.
  treatUseMs: 4_000,
  amenityUseMs: 2_000,
  gukbapUseMs: 4_000,

  // 구매가
  costs: {
    maru: 2,
    moxa: 30,
    haewoso: 20,
    acu: 50,
    herb: 100,
    gukbap: 30,
    well: 10,  // 약방 근접 1개 배치 결정점 — 설치비 10전, 이용료 없음(amenity)
    pine: 0    // 기본 3개 무료, 추가 가격 미정
  },

  // 환자 지불
  fees: {
    moxa: 2,
    haewoso: 1,
    acu: 3,
    herb: 6,
    herbWithPulse: 8,
    gukbap: 3
  },

  // 계층 소지금
  wallet: { nobi: 5, nongmin: 10, sangin: 15, seonbi: 20, yangban: 30 },

  // 만족도 점수
  treatScore:   { moxa: 1, acu: 2, herb: 3 },
  amenityScore: { gukbap: 2, well: 1, haewoso: 1 },
  // Phase 4-A0: 기존 `pineBoost: 1.2` (×1.2 곱셈 floor) 폐기 → +1 가산, 스태킹 금지.
  // Phase 6: PatientSystem._pineAdjacentBonus 가 4방 인접 PINE 검출 시 점수 +1 가산.
  pineBonusPerRoom: 1,
  pineStack: false,
  // Phase 6: 소나무 무료 한도. 추가 구매 가격 미정 → 4번째 배치 자체 차단(토스트).
  pineFreeMax: 3,

  satisfyNeedTreat:   { nobi: 1, nongmin: 2, sangin: 3, seonbi: 4, yangban: 5 },
  satisfyNeedAmenity: { nobi: 3, nongmin: 4, sangin: 5, seonbi: 7, yangban: 10 },

  // Phase 4-A: 만족도 3단 판정 비율.
  // 치료·편의 각 축을 need 대비 달성률로 계산 후 두 축의 MIN 값으로 tier 결정.
  //   ok (≥1.0)  → 만족    (myeonguiOnSatisfy 100%)
  //   mid (≥0.5) → 보통    (myeonguiOnSatisfy 50%)
  //   < mid      → 불만족  (가산 0)
  satisfyTier: { ok: 1.0, mid: 0.5 },

  // 선비·양반은 현재 편의 빌딩 합(국밥2+우물1+해우소1=4) 이 need(7·10) 에 수학적으로 못 닿음.
  // Phase 6 소나무 편의 보너스 도입 전까지 만족·불만족 카운터에서 제외("판정 보류").
  // 디버그 스폰(F4·F5)으로 띄워도 이 두 계층은 patient_pending 이벤트로만 기록.
  satisfyPendingTiers: ['seonbi', 'yangban'],

  // 명의 가산
  myeonguiOnUse:     { moxa: 0.1, acu: 0.3, herb: 0.6 },
  myeonguiOnSatisfy: { moxa: 0.1, acu: 0.3, herb: 0.6 },

  // ─── 티켓 시스템 (Phase 4-C) ─────────────────────────
  // 풀 = 평판 누적. 15장 차면 1명 결정적 스폰 + 차감.
  // 치료티켓: 가중치 스폰 (Q3 권장 B → tierSpawnWeight 사용, 미해금 계층 자연 차단).
  // 편의티켓: 풀 안에서 1장 추첨 → 그 계층 스폰. 수요는 33/33/33 균등.
  // ⚠️ weightedProb 는 더 이상 PatientSystem 이 참조하지 않음 — 티켓 redeem 도 tierSpawnWeight 통일.
  //   (체크리스트 line 157 의 "노30/농20/상20/선20/양10" 분포는 tierSpawnWeight 6/3/2/0/0 에 비례 매핑)
  ticketLifeMs: 120_000,
  ticketsToSpawn: 15,
  // 치료티켓 발행 확률 (Phase 4-C, 체크리스트 line 146-148).
  //   key = 환자가 사용한 최고등급 치료방, value = [{ kind, prob }, ...] 합 1.0
  //   Q5 권장 B: 약탕 시설 미정 → 약 만족 100% 약 흡수(약탕 발행 자체 차단).
  treatTicketIssuance: {
    moxa: [{ kind: 'moxa', prob: 0.40 }, { kind: 'acu', prob: 0.60 }],
    acu:  [{ kind: 'acu',  prob: 0.70 }, { kind: 'herb', prob: 0.30 }],
    herb: [{ kind: 'herb', prob: 1.00 }]
  },
  // 편의티켓 redeem 시 새 환자의 수요 종류(읽기 전용 메타, Phase 8 환자 행동 분기 진입점).
  amenityRedeemDemand: { moxa: 0.33, acu: 0.34, herb: 0.33 },

  // 해금
  unlockChain: {
    haewoso: { room: 'moxa',    count: 5  },
    acu:     { room: 'moxa',    count: 10 },
    herb:    { room: 'acu',     count: 20 },
    well:    { room: 'haewoso', count: 10 },
    gukbap:  { room: 'any',     count: 30 }
  },
  // @deprecated v0.5 "만족 환자 N명" 기반 해금 계획. v0.6 은 명의 누적 기반
  // tierThresholdByMyeongui 로 이전. 이 필드는 현재 참조 0건 — Phase 4-C 청소 티켓.
  tierUnlock: { nongmin: 10, sangin: 10, seonbi: 10, yangban: 10 },

  // Phase 4-B ①A + ③A: 계층 해금 기준 — 누적 명의(myeonguiOnUse + myeonguiOnSatisfy).
  //   nongmin 10(침방 해금 ≈ moxa 10회 이용 시점과 align — FM-A2 회피),
  //   sangin 15, seonbi 40, yangban 100.
  //   선비·양반은 satisfyPendingTiers 라 해금돼도 tierSpawnWeight 0 으로 풀 제외(④A),
  //   양반만 해금 순간 1회 결정적 환영 스폰(⑤B, PatientSystem._pendingWelcomeTier).
  tierThresholdByMyeongui: { nongmin: 10, sangin: 15, seonbi: 40, yangban: 100 },

  // Phase 4-B: 해금된 계층 풀에서 가중치 sample. ④A 로 선비·양반 0 유지.
  //   환영 스폰은 가중치 무시하고 _pendingWelcomeTier 로 결정적 처리.
  tierSpawnWeight: { nobi: 6, nongmin: 3, sangin: 2, seonbi: 0, yangban: 0 },

  // Phase 7-A1: 병세-치료방 매칭 패널티. _findReachableTreatRoom 이 거리에 가산.
  //   값=5 의 의미: 일치 치료방이 거리 5칸 더 멀어도 선호 (도보 ≈ 5 × PATIENT_STEP_MS = 5.25초).
  //   너무 크면 동선 비현실적, 너무 작으면 매칭 안 됨 — 5 가 카이로풍 약한 편향.
  illnessMismatchPenalty: 5,

  // 직원
  staff: {
    musuri: { hire: 10, wage: 1, covers: 'moxa', maxRooms: 2, radius: 1 },
    chimgu: { hire: 20, wage: 2, covers: 'moxa', maxRooms: 3, radius: 1 },
    uinyeo: { hire: 30, wage: 3, covers: 'acu',  maxRooms: 3, radius: 1 },
    uigwan: { hire: 40, wage: 4, covers: 'herb', maxRooms: 2, radius: 1 }
  },

  upkeepMonthly: { treat: 2, amenity: 1 },

  // 우물 보너스 — 치료방 3×3 (Chebyshev r=1) 범위 내 우물 1개 이상이면 효과 발동.
  // 단일 적용: 우물 여러 개 배치해도 효과 1회만(stacking 금지). staff.radius(Manhattan)과
  // 의도적으로 `shape` 필드로 구분.
  // Phase 7-B1 확장: 약방=fee 가산, 침방·뜸방=만족도 점수 +1 (효과 안정성 의미).
  wellBonus: { herbFee: 2, acuScore: 1, moxaScore: 1, shape: 'chebyshev', radius: 1 },

  // Phase 7-B2: 같은 종류 치료방 4방 직접 인접 시 혼잡 페널티 — fee 감소(최소 1전 보장).
  //   값=1 의 의미: 옆에 같은 방 1개 → fee -1. 카이로풍 "흩어 배치" 동기.
  //   herb fee=8 기준 -12.5%, moxa fee=2 기준 -50% — moxa 는 클러스터 압력이 강하게 걸림(의도).
  clusterPenaltyPerRoom: 1
};
