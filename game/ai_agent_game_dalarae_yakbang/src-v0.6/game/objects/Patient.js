import { BALANCE, GATE_COL, GATE_ROW } from '../config.js';

// 계층별 소지금 범위 (BALANCE.wallet 은 평균 근사치) + 이동 속도 tint.
const TIER_GOLD_RANGE = {
  nobi:    { min: 2,  max: 8  },
  nongmin: { min: 5,  max: 15 },
  sangin:  { min: 8,  max: 25 },
  seonbi:  { min: 12, max: 35 },
  yangban: { min: 20, max: 50 }
};

// v0.5 이식: 계층 한글 라벨 — 환자 머리 위 표시용.
const TIER_LABEL = {
  nobi:    '노비',
  nongmin: '농민',
  sangin:  '상인',
  seonbi:  '선비',
  yangban: '양반'
};

// Phase 6: 계층 배지 색(텍스트 stroke 로 적용) — 신분 가시 구분.
const TIER_COLOR = {
  nobi:    '#9aa0a8',  // 회색 — 서민
  nongmin: '#c08040',  // 흙색
  sangin:  '#20a0a0',  // 청록 — 상인
  seonbi:  '#a068d0',  // 자주 — 학자
  yangban: '#f7d05b'   // 금색 — 귀족
};

// Phase 6: 병 상태(경증/중증/위중) — 계층별 가중치로 스폰 시 결정.
//   상위 계층일수록 위중 비율↑. 카이로풍 "치료 선호" 시각화.
//   실제 치료방 사용 강제 X — 현 Phase 는 UI 표시만. Phase 8 에서 행동 분기.
const ILLNESS_WEIGHT = {
  nobi:    { moxa: 0.6, acu: 0.3, herb: 0.1 },
  nongmin: { moxa: 0.4, acu: 0.45, herb: 0.15 },
  sangin:  { moxa: 0.2, acu: 0.45, herb: 0.35 },
  seonbi:  { moxa: 0.1, acu: 0.35, herb: 0.55 },
  yangban: { moxa: 0.05, acu: 0.25, herb: 0.70 }
};
const ILLNESS_COLOR = {
  moxa: 0xd06020,  // 주황 — 경증(뜸/열)
  acu:  0x3080d0,  // 청색 — 중증(침/금속)
  herb: 0x50a030   // 녹색 — 위중(약/식물)
};

function rollIllness(tier) {
  const w = ILLNESS_WEIGHT[tier] || ILLNESS_WEIGHT.nobi;
  const r = Math.random();
  let acc = 0;
  for (const [k, p] of Object.entries(w)) {
    acc += p;
    if (r < acc) return k;
  }
  return 'moxa';
}

// BootScene 에 미리 로드된 스프라이트시트 key 풀. 계층별로 성별 variant 중 1개 랜덤 선택.
// 시트가 로드 안 된 경우(자산 누락) 폴백: nobi_m.
const TIER_SPRITE_POOL = {
  nobi:    ['char_nobi_m', 'char_nobi_f'],
  nongmin: ['char_nongmin_m'],
  sangin:  ['char_sangin_m', 'char_sangin_f'],
  seonbi:  ['char_seonbi_m', 'char_seonbi_f'],
  yangban: ['char_yangban_m', 'char_yangban_f']
};

// 애니메이션 행 매핑 — BootScene CHAR_DIRS 와 동기.
// idle 시 가운데 프레임(col=1)으로 정지.
const DIR_ROW = { down: 0, left: 1, right: 2, up: 3 };

// 타일 하나 이동 시간(ms). 환자와 기존 테스트 walker 를 같게 유지.
// 220 → 420 → 1050 (2026-04-19): 유저 피드백 "현재 속도의 40% 로 줄여라".
//   42 0ms × (1 / 0.4) = 1050ms. 이 속도면 10타일 이동에 10.5초 소요 — 환자 체류
//   시간(patientStayMs 15s) 에 여유가 거의 없음. 추후 체류 시간 완화 필요.
export const PATIENT_STEP_MS = 1050;

// 환자 생명주기 상태.
// spawning : 그리드 진입 직후, 아직 목적지 미결정
// walking  : 경로 tween 진행 중 (목적지까지)
// using    : 시설 이용 중 (useRemaining 카운트다운)
// leaving  : 대문으로 복귀 중
// done     : 제거 대기. system.destroy 호출 대상.
export const PATIENT_STATE = Object.freeze({
  SPAWNING: 'spawning',
  WALKING:  'walking',
  USING:    'using',
  LEAVING:  'leaving',
  DONE:     'done'
});

export class Patient {
  constructor(scene, grid, tier = 'nobi') {
    this.scene = scene;
    this.grid = grid;
    this.tier = tier;

    const r = TIER_GOLD_RANGE[tier] || TIER_GOLD_RANGE.nobi;
    this.gold = Phaser.Math.Between(r.min, r.max);

    this.stayRemaining = BALANCE.patientStayMs;  // 전체 체류 타이머
    this.useRemaining = 0;                       // using 동안만 의미 있음
    this.useTotal = 0;                           // W3: 진행률 게이지 기준. _beginUsing 에서 갱신.
    // Phase 4-A0: 다녀온 건물 key 집합. "치료 1회 → 편의시설 순회 → 귀가" 동선을 위해
    // 단발 boolean 에서 Set 으로 승격. treat·amenity 통합 저장(옵션 ①A).
    // 재시도 방지용 — 직원 부재로 돌려보내진 경우·USING 중 철거된 경우도 여기 기록.
    this.usedBuildings = new Set();
    // Phase 4-A: 실제 _finishUsing 까지 도달한 건물만 집계(H3 보정).
    // usedBuildings 와 분리 — 돌려보냄/철거 노이즈가 만족도·명의에 섞이지 않도록.
    this.actuallyUsed = new Set();
    this.treatScoreSum = 0;
    this.amenityScoreSum = 0;
    // herb > acu > moxa 중 실제 이용 완료한 최고 등급 치료실 key. 명의 가산 기준.
    this.highestTreatUsed = null;
    // _fadeOutAndDone 재진입 시 판정 중복 방지(C1·C2 보정). 1회 판정 후 true.
    this.satisfactionEvaluated = false;
    // Phase 4-B ⑥A: 직원 부족으로 거절된 환자 — 편의 순회 skip + patient_rejected 분기.
    //   _beginUsing no_staff 분기에서 set, _planNextAction·_evaluateSatisfaction 이 읽음.
    this.rejectedByStaff = false;
    // Phase 4-B 자동-5 (C-4): 우물 보너스 스냅샷. _beginUsing herb 분기가 덮어쓰기 전 기본 0.
    //   생성 직후 _onTileChanged 의 방어 경로가 읽을 때 undefined 방지(타입 안정성).
    this.wellBonus = 0;
    // Phase 4-B 보정-1: 환영 스폰(⑤B)으로 결정적 생성된 환자 식별. abandoned 시
    //   _pendingWelcomeTier 복구 트리거. 일반 스폰은 false 유지 — 복구 대상 아님.
    this.isWelcomeSpawn = false;
    this.state = PATIENT_STATE.SPAWNING;

    // 대문 위치에서 스폰. 계층별 스프라이트 풀에서 랜덤 선택(성별 variant).
    //   시트 로드 실패 시(자산 누락) tex_walker 폴백.
    const pool = TIER_SPRITE_POOL[tier] || TIER_SPRITE_POOL.nobi;
    this.spriteKey = pool[Math.floor(Math.random() * pool.length)];
    this.facing = 'down';
    const p = grid.pixelFromTile(GATE_COL, GATE_ROW);
    if (scene.textures.exists(this.spriteKey)) {
      this.sprite = scene.add.sprite(p.x, p.y, this.spriteKey).setDepth(40);
      this.sprite.setFrame(DIR_ROW[this.facing] * 3 + 1);  // idle 가운데 프레임
    } else {
      this.sprite = scene.add.image(p.x, p.y, 'tex_walker').setDepth(40);
    }
    // Phase 6: 환자 클릭 → 정보 패널 오픈. scene 이 'patient_clicked' 리스너 구독.
    this.sprite.setInteractive({ useHandCursor: true });
    this.sprite.on('pointerdown', (pointer, lx, ly, evt) => {
      if (evt && evt.stopPropagation) evt.stopPropagation();
      scene.events.emit('patient_clicked', this);
    });

    this.moveTween = null;
    this.fadeTween = null;        // 퇴장 fade-out tween — destroy 시 정리
    this.targetBuilding = null;   // { col, row, key } — using 직전 기록

    // v0.5 이식 — 인내심 바 + 계층 라벨 (카이로 체감 복구 Tier A).
    //   patienceBg: 28×4 어두운 배경, patienceBar: 26×2 현재 잔량(녹→황→적).
    //   tierLabel : 10px 한글(노비/농민/…). 스프라이트와 함께 _syncUi 로 좌표 동기화.
    //   Depth 41 — 스프라이트(40)보다 위, FloatingText(50)보다 아래.
    this.patienceBg = scene.add.rectangle(p.x, p.y - 22, 28, 4, 0x000000, 0.55).setDepth(41);
    this.patienceBar = scene.add.rectangle(p.x - 13, p.y - 22, 26, 2, 0x4ac06a)
      .setOrigin(0, 0.5).setDepth(42);
    this.tierLabel = scene.add.text(p.x, p.y - 32, TIER_LABEL[tier] || '', {
      fontFamily: 'system-ui, sans-serif',
      fontSize: '10px',
      color: TIER_COLOR[tier] || '#ffe8b0',
      stroke: '#000000',
      strokeThickness: 2,
      fontStyle: 'bold'
    }).setOrigin(0.5, 0.5).setDepth(42);

    // Phase 6: 병 상태 도트 — 계층 라벨 우측. 실제 선호 치료 Phase 8 확장 진입점.
    this.illness = rollIllness(tier);
    this.illnessDot = scene.add.circle(p.x, p.y - 32, 3, ILLNESS_COLOR[this.illness] || 0xa0a0a0)
      .setStrokeStyle(1, 0x000000).setDepth(42);
    this._maxStayMs = BALANCE.patientStayMs;  // 잔량 비율 계산 기준(연장되면 갱신).
  }

  // 스프라이트 좌표에 UI(인내심 바·라벨) 동기화. 이동 중/정지 중 모두 호출 가능.
  // 잔량 비율: stayRemaining / _maxStayMs. amenity 로 stay 가 연장되면 _maxStayMs 도 확장.
  _syncUi() {
    if (!this.sprite) return;
    const sx = this.sprite.x;
    const sy = this.sprite.y;
    if (this.patienceBg)  { this.patienceBg.x  = sx;       this.patienceBg.y  = sy - 22; }
    if (this.tierLabel)   { this.tierLabel.x   = sx;       this.tierLabel.y   = sy - 32; }
    // 병 도트는 라벨 폭 기준으로 우측 오프셋. tierLabel.width 는 텍스트 렌더 직후 유효.
    if (this.illnessDot) {
      const off = (this.tierLabel ? this.tierLabel.width / 2 : 10) + 6;
      this.illnessDot.x = sx + off;
      this.illnessDot.y = sy - 32;
    }
    if (this.patienceBar) {
      this.patienceBar.x = sx - 13;
      this.patienceBar.y = sy - 22;
      // amenity 체류 연장 반영: 현재 잔량이 기준을 초과하면 기준을 올림(상한 없이 스케일 유지).
      if (this.stayRemaining > this._maxStayMs) this._maxStayMs = this.stayRemaining;
      const ratio = Math.max(0, Math.min(1, this.stayRemaining / this._maxStayMs));
      this.patienceBar.width = Math.max(0, 26 * ratio);
      // 녹(>0.5) → 황(>0.25) → 적. 카이로 체감 기준.
      let color = 0x4ac06a;
      if (ratio < 0.25) color = 0xc06060;
      else if (ratio < 0.5) color = 0xd0a020;
      this.patienceBar.fillColor = color;
    }
  }

  // 경로 tween 체인. 도중 상태가 done 이 되면 즉시 중단.
  // 2차 검증 C-1 보정: 경로가 비어 있으면 onArrive 를 다음 틱으로 미룸 — 동기 재귀
  // 호출 스택이 쌓여 _beginUsing → _planNextAction → walkPath 가 같은 프레임에서
  // 무한 재진입하는 이론 경로 차단(인접 시설 via 타일이 같을 때).
  walkPath(pathTiles, onArrive) {
    if (this.state === PATIENT_STATE.DONE) return;
    if (!pathTiles || pathTiles.length === 0) {
      if (onArrive) this.scene.time.delayedCall(0, onArrive);
      return;
    }
    // 첫 타일이 현 위치면 skip (대문 start 시 첫 요소가 gate 본인일 수 있음)
    const start = pathTiles[0];
    const startPix = this.grid.pixelFromTile(start.col, start.row);
    const dx = Math.abs(this.sprite.x - startPix.x);
    const dy = Math.abs(this.sprite.y - startPix.y);
    const rest = (dx < 1 && dy < 1) ? pathTiles.slice(1) : pathTiles.slice();
    if (rest.length === 0) {
      if (onArrive) this.scene.time.delayedCall(0, onArrive);
      return;
    }
    this._stepWalk(rest, onArrive);
  }

  _stepWalk(rest, onArrive) {
    if (this.state === PATIENT_STATE.DONE) return;
    if (rest.length === 0) {
      this._playIdle();
      onArrive && onArrive();
      return;
    }
    const next = rest.shift();
    const p = this.grid.pixelFromTile(next.col, next.row);
    // 방향 결정: dx/dy 중 절댓값 큰 축으로 매핑. 대각선은 grid 설계상 발생 안 함.
    const dx = p.x - this.sprite.x;
    const dy = p.y - this.sprite.y;
    if (Math.abs(dx) > Math.abs(dy)) {
      this.facing = dx > 0 ? 'right' : 'left';
    } else if (dy !== 0) {
      this.facing = dy > 0 ? 'down' : 'up';
    }
    this._playWalk();
    const tw = this.scene.tweens.add({
      targets: this.sprite,
      x: p.x, y: p.y,
      duration: PATIENT_STEP_MS,
      ease: 'Linear',
      onUpdate: () => this._syncUi(),
      onComplete: () => {
        if (this.moveTween !== tw) return;
        this.moveTween = null;
        this._syncUi();
        this._stepWalk(rest, onArrive);
      }
    });
    this.moveTween = tw;
  }

  // 방향 애니메이션 재생. 스프라이트가 Image(폴백) 면 no-op.
  _playWalk() {
    if (!this.sprite || typeof this.sprite.play !== 'function') return;
    const animKey = `${this.spriteKey}_${this.facing}`;
    if (this.scene.anims.exists(animKey)) this.sprite.play(animKey, true);
  }

  // 애니메이션 정지 + 현재 방향 idle 프레임(가운데 컬럼).
  _playIdle() {
    if (!this.sprite || typeof this.sprite.stop !== 'function') return;
    this.sprite.stop();
    const row = DIR_ROW[this.facing] || 0;
    if (this.sprite.setFrame) this.sprite.setFrame(row * 3 + 1);
  }

  cancelMovement() {
    if (this.moveTween) {
      const t = this.moveTween;
      this.moveTween = null;  // identity 체크 실패시키기 위해 먼저 null
      t.stop();               // remove() 는 onComplete 를 발화시키므로 stop() 사용
      t.remove();
    }
  }

  // 매 프레임 호출. 상태 전이는 PatientSystem 이 결정.
  update(delta) {
    if (this.state === PATIENT_STATE.DONE) return;
    this.stayRemaining -= delta;
    if (this.state === PATIENT_STATE.USING) {
      this.useRemaining -= delta;
    }
    this._syncUi();
  }

  destroy() {
    this.cancelMovement();
    if (this.fadeTween) {
      const ft = this.fadeTween;
      this.fadeTween = null;
      ft.stop();
      ft.remove();
    }
    if (this.patienceBg)  { this.patienceBg.destroy();  this.patienceBg  = null; }
    if (this.patienceBar) { this.patienceBar.destroy(); this.patienceBar = null; }
    if (this.tierLabel)   { this.tierLabel.destroy();   this.tierLabel   = null; }
    if (this.illnessDot)  { this.illnessDot.destroy();  this.illnessDot  = null; }
    if (this.sprite) { this.sprite.destroy(); this.sprite = null; }
    this.state = PATIENT_STATE.DONE;
  }
}
