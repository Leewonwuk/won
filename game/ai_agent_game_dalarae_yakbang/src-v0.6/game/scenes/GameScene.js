import {
  BALANCE, GAME_WIDTH, GAME_HEIGHT,
  TILE_SIZE, GRID_COLS, GRID_ROWS,
  GRID_ORIGIN_X, GRID_ORIGIN_Y, GRID_PIXEL_W, GRID_PIXEL_H,
  HUD_TOP_H, HUD_BOT_H,
  MENU_STRIP_Y, MENU_STRIP_H, MENU_TAB_H,
  GATE_COL, GATE_ROW, SPAWN_COL, SPAWN_ROW
} from '../config.js';
import {
  GridSystem,
  TILE_EMPTY, TILE_MARU, TILE_GATE, TILE_MOXA,
  TILE_ACU, TILE_HERB, TILE_WELL, TILE_PINE
} from '../systems/GridSystem.js';
import { PathSystem } from '../systems/PathSystem.js';
import { audioSystem } from '../systems/AudioSystem.js';
import { getBuildingByKey, getBuildingByTileType } from '../systems/BuildingRegistry.js';
import { FloatingText } from '../objects/FloatingText.js';
import { PatientSystem } from '../systems/PatientSystem.js';
import { PATIENT_STATE } from '../objects/Patient.js';
import { UnlockSystem } from '../systems/UnlockSystem.js';
import { StaffSystem } from '../systems/StaffSystem.js';
import { TicketSystem } from '../systems/TicketSystem.js';
import { StaffPanel } from '../ui/StaffPanel.js';
import { PatientInfoPanel } from '../ui/PatientInfoPanel.js';

// Phase 1-A/B/C: 그리드, 대문, 마루 pathfinding 뼈대.
// 환자 스폰·경제·해금은 이후 Phase에서 본격 구현.
export class GameScene extends Phaser.Scene {
  constructor() { super({ key: 'GameScene' }); }

  create() {
    this.audioSys = audioSystem;

    this._drawBackground();

    this.grid = new GridSystem(this);
    this.path = new PathSystem(this.grid);
    // StaffSystem 은 PatientSystem 보다 먼저 — tile_changed 이벤트가 staff 정리를 먼저 수행한
    // 뒤 patients 가 USING 환자의 귀가를 결정하도록 순서 계약을 고정.
    this.staff = new StaffSystem(this, this.grid);
    this.patients = new PatientSystem(this, this.grid, this.path, this.staff);
    // named handler 로 등록해 shutdown 시 명시적 off 가능. PatientSystem.destroy 가
    // removeAllListeners 를 호출해 대체로 커버하지만, 향후 reset/재생성 시 안전.
    this._onPatientPaid = this._onPatientPaid.bind(this);
    this._onPatientUsing = this._onPatientUsing.bind(this);
    this._onPatientServed = this._onPatientServed.bind(this);
    this._onPatientTurnedAway = this._onPatientTurnedAway.bind(this);
    this._onPatientSatisfied = this._onPatientSatisfied.bind(this);
    this._onPatientPending = this._onPatientPending.bind(this);
    this._onPatientAbandoned = this._onPatientAbandoned.bind(this);
    this._onPatientRejected = this._onPatientRejected.bind(this);
    this.patients.events.on('patient_paid', this._onPatientPaid);
    this.patients.events.on('patient_using', this._onPatientUsing);
    this.patients.events.on('patient_served', this._onPatientServed);
    this.patients.events.on('patient_turned_away', this._onPatientTurnedAway);
    this.patients.events.on('patient_satisfied', this._onPatientSatisfied);
    this.patients.events.on('patient_pending', this._onPatientPending);
    this.patients.events.on('patient_abandoned', this._onPatientAbandoned);
    this.patients.events.on('patient_rejected', this._onPatientRejected);

    // v0.5 이식 — 치료 진행 게이지. 건물 타일 상단에 잔여 useMs 비율로 채워지는 막대.
    //   Map<Patient, { bg, bar, useMs }>. USING 상태 종료(served/abandoned/rejected) 시 정리.
    //   update() 에서 patient.state !== USING 인 엔트리도 방어적으로 정리.
    this._useGauges = new Map();

    // Phase 3 해금 체인 — 이용 누적에 따라 툴바 확장.
    this.unlocks = new UnlockSystem(this, this.patients);
    this._onUnlocked = this._onUnlocked.bind(this);
    this._onTierUnlocked = this._onTierUnlocked.bind(this);
    this.unlocks.events.on('unlocked', this._onUnlocked);
    this.unlocks.events.on('tier_unlocked', this._onTierUnlocked);

    // Phase 4-C 티켓 시스템 — 평판 풀 + 가중치/추첨 스폰. UnlockSystem 보다 뒤에 두어
    //   생성 시점에 unlockedTiers 동기화 가능. patient_satisfied 는 직접 위임.
    this.tickets = new TicketSystem(this);
    this.tickets.setUnlockedTiers(this.unlocks.unlockedTiers || ['nobi']);
    this._onTicketIssued = this._onTicketIssued.bind(this);
    this._onTicketRedeemTreat = this._onTicketRedeemTreat.bind(this);
    this._onTicketRedeemAmenity = this._onTicketRedeemAmenity.bind(this);
    this.tickets.events.on('ticket_issued', this._onTicketIssued);
    this.tickets.events.on('ticket_redeem_treat', this._onTicketRedeemTreat);
    this.tickets.events.on('ticket_redeem_amenity', this._onTicketRedeemAmenity);

    // Phase 3-C 치료방 UI. staff 상태 변경 시 뱃지 갱신.
    this.staffPanel = new StaffPanel(this, this.staff, this.grid);
    // Phase 6: 환자 클릭 → 두루마기 상태창.
    this.patientInfoPanel = new PatientInfoPanel(this);
    this._onPatientClicked = (patient) => {
      if (this.staffPanel.isOpened()) return;
      this.patientInfoPanel.open(patient);
    };
    this.events.on('patient_clicked', this._onPatientClicked);
    this._onStaffChanged = this._refreshBadges.bind(this);
    this.staff.events.on('staff_hired', this._onStaffChanged);
    this.staff.events.on('staff_assigned', this._onStaffChanged);
    this.staff.events.on('staff_fired', this._onStaffChanged);
    this.grid.events.on('tile_changed', this._onStaffChanged);
    this.unlocks.events.on('unlocked', this._onStaffChanged);
    // Phase 6: 직원 고용 시 인접 배정 가능 방 0 감지 → 경고 토스트.
    this._onStaffHiredWarn = this._warnIfNoAssignable.bind(this);
    this.staff.events.on('staff_hired', this._onStaffHiredWarn);
    // Phase 6 S1/W2: tile_changed / staff_fired 발생 시 기존 직원 고립 여부 재검사.
    this._isolatedStaff = new Set();
    this._onRecheckIsolation = this._recheckStaffIsolation.bind(this);
    this.grid.events.on('tile_changed', this._onRecheckIsolation);
    this.staff.events.on('staff_fired', this._onRecheckIsolation);
    this.staff.events.on('staff_assigned', this._onRecheckIsolation);
    this._badgeSprites = [];

    // 스폰 포인트 마커 (대문 바로 위)
    const sp = this.grid.pixelFromTile(SPAWN_COL, SPAWN_ROW);
    this.spawnMark = this.add.image(sp.x, sp.y, 'tex_spawn_mark').setDepth(15);
    this.add.text(sp.x, sp.y + 30, '스폰', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '10px', color: '#ff8a3c'
    }).setOrigin(0.5, 0).setDepth(16);

    // hover 커서
    this.hoverCursor = this.add.image(-999, -999, 'tex_tile_hover').setDepth(50).setVisible(false);

    // 타일 클릭 → 빈 ↔ 마루 토글 (Phase 1-A/1-C 테스트용)
    // hover 도 GridSystem 이 격리된 Zone 에서 발행
    this.grid.events.on('tile_clicked', (t, button) => this._onTileClicked(t, button));
    this.grid.events.on('tile_hover', (t) => this._onTileHover(t));
    // UX: 우클릭 = 철거. 캔버스 컨텍스트 메뉴는 차단해야 우클릭이 게임 입력으로만 사용됨.
    if (this.game && this.game.canvas) {
      this._onCanvasContextMenu = (e) => e.preventDefault();
      this.game.canvas.addEventListener('contextmenu', this._onCanvasContextMenu);
    }

    // HUD
    this._createHud();

    // 선택 도구 (우하단 툴바) — 기본은 마루. 'select' 는 배치가 아닌 치료방 패널 진입용.
    this._selectedTool = 'maru';
    this._createToolbar();
    // 첫 프레임 뱃지 렌더
    this._refreshBadges();

    // 테스트 키: T — 테스트 환자 / R — 마루 전부 철거 / Y — 주 점프(QA) / P — 환자 강제 스폰(Phase 2)
    // H — 무수리 고용(Phase 3-B 레거시 QA 키). 정식 UI 는 StaffPanel(선택 도구).
    this.input.keyboard.on('keydown-T', () => this._spawnTestWalker());
    this.input.keyboard.on('keydown-R', () => this._clearAllMaru());
    this.input.keyboard.on('keydown-Y', () => this._debugFastForwardWeek());
    this.input.keyboard.on('keydown-P', () => this._debugSpawnPatient());
    this.input.keyboard.on('keydown-H', () => this._debugHireMusuri());
    // M — 마스터 쇼룸: 전 건물/계층 해금 + 7종 쇼케이스 자동 배치(애니 자산 시각 점검용).
    this.input.keyboard.on('keydown-M', () => this._debugMasterMode());
    // Phase 4-A ⑥A: 계층별 강제 스폰(개발 전용, 배포 시 제거 대상). Phase 4-D 해금 전
    //   계층 분기 배관을 미리 검증하기 위한 창구.
    // 2차 H2 보정: F5(새로고침)·F2(Edge 피드백)·F3(Chrome 검색)·F4(일부 브라우저)는
    //   브라우저 기본 동작과 충돌 → addKey 로 등록 후 preventDefault 로 차단.
    // TODO(Phase 4-D 릴리스): 배포 빌드에서 이 블록 전체 제거.
    const addDebugTierKey = (keyName, tier) => {
      const key = this.input.keyboard.addKey(keyName, true, false);
      key.on('down', (ev) => {
        if (ev && ev.event && ev.event.preventDefault) ev.event.preventDefault();
        this._debugSpawnTier(tier);
      });
    };
    addDebugTierKey('F2', 'nongmin');
    addDebugTierKey('F3', 'sangin');
    addDebugTierKey('F4', 'seonbi');
    addDebugTierKey('F5', 'yangban');

    // BGM (audioSystem은 유저 제스처 이후 init 된 상태를 기대)
    // switchTheme 은 구현에 따라 Promise 를 반환하지 않을 수 있어 Promise.resolve 로 래핑.
    if (this.audioSys && typeof this.audioSys.switchTheme === 'function') {
      Promise.resolve(this.audioSys.switchTheme('day')).catch(() => {});
    }

    // 상태
    this.gold = BALANCE.startGold;
    this.myeongui = BALANCE.startMyeongui;
    this.elapsedMs = 0;
    this.testWalkerCount = 0;
    this._toastTimer = null;

    // 결산 리듬 — 주간은 HUD 배너(pause 없음), 월간만 ResultScene 팝업(pause).
    // 40분 세션 기준 주간 160회 pause 가 카이로 리듬을 훼손한다는 검증 피드백 반영.
    this._lastWeek = 0;
    this._lastMonth = 0;
    this._weekNetIncome = 0;
    this._monthNetIncome = 0;

    // Phase 4-A: 만족도 카운터. 주간·월간 경계에서 리셋.
    // pending(선비·양반 Phase 6 대기) / abandoned(입장 못 한 환자) 는 totalJudged 에서 제외.
    // 2차 FM-N1 보정: pending 은 월간 결산에만 "보류 N명" 으로 별도 표시 — 주간 배너는 공간 부족.
    this._weekSatisfied = 0;
    this._weekNeutral = 0;
    this._weekDissatisfied = 0;
    this._monthSatisfied = 0;
    this._monthNeutral = 0;
    this._monthDissatisfied = 0;
    this._monthPending = 0;
    // Phase 4-B ⑥A + ⑨B: 월간 거절 카운터. 계층별 breakdown 은 ResultScene 에 "거절 N명 (양반 M…)".
    //   주간 배너는 이미 세 줄이라 rejected 는 월간 전용 — UI 밀도 관리(자동 판단).
    this._monthRejected = 0;
    this._monthRejectedByTier = {};
    // Phase 7-A2: 방별 수입 누적기. building.key → 누적 fee. 월간 결산 ResultScene 스택바 입력.
    //   wellBonus 포함(총 환자가 낸 돈) — herb 방의 우물 인접 가치를 같은 막대에 시각화.
    this._monthIncomeByBuilding = {};

    // Phase 5: 6개월 누적 — 매 6달마다 ResultScene 에 halfYear 요약 첨부.
    //   체크리스트 line 184: "총수입 - 유지비 - 급료 - 약재비 = 순이익. 그래프 형태로(상/하반기)".
    //   현 단계는 텍스트 요약만 — 그래프 시각화는 Phase 6 폴리시 트랙.
    this._halfYearIncome = 0;
    this._halfYearWage = 0;
    this._halfYearUpkeep = 0;
    this._halfYearMonths = 0;
    // Phase 6: 월별 시계열 히스토리 — 최대 6개월, 6개월 결산 그래프 입력.
    this._monthlyHistory = [];

    // ResultScene 에서 돌아올 때 배경 오디오 재개 신호
    this.events.on(Phaser.Scenes.Events.RESUME, this._onResumed, this);

    // 씬 종료 시 자원 정리 — Phaser 생명주기상 shutdown 이 항상 먼저 오고
    // restart/stop 시엔 destroy 가 안 불리므로 shutdown 하나로 충분.
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, this._onShutdown, this);

    // Phase 1-F: 첫 세션 튜토리얼 (4-step action-gated). flag 존재 시 skip.
    this._initTutorial();
  }

  update(time, delta) {
    // ResultScene pause 중 프레임 레이스 가드 (Phaser 3 pause 직후 1프레임 실행 가능성)
    if (!this.scene.isActive()) return;

    // 탭 비활성 후 복귀 시 큰 delta 스파이크 클램프
    const clampedDelta = Math.min(delta, 100);
    this.elapsedMs += clampedDelta;
    this._updateHud();

    if (this.patients) this.patients.update(clampedDelta);
    // Phase 4-C: 티켓 만료 청소 — time(=Phaser.now) 기준.
    if (this.tickets) this.tickets.update(time);
    // Phase 7-D: 직원 순찰 — 홈↔배정 치료방 왕복.
    if (this.staff) this.staff.update(clampedDelta);

    // 치료 진행 게이지 — 매 프레임 잔여 useRemaining 비율로 막대 채우기.
    //   USING 외 상태로 전이한 엔트리는 방어적으로 정리(patient_served 가 이미 커버하지만
    //   abandoned/rejected 등 엣지 경로에서 누수 방지).
    if (this._useGauges && this._useGauges.size > 0) {
      for (const [patient, g] of this._useGauges) {
        if (!patient || patient.state !== PATIENT_STATE.USING || !patient.sprite) {
          this._destroyUseGauge(patient);
          continue;
        }
        const ratio = Math.max(0, Math.min(1, (patient.useRemaining || 0) / g.useMs));
        if (g.bar) g.bar.width = Math.max(0, 40 * (1 - ratio));
      }
    }

    // 주간 경계 — HUD 배너만(pause 없음). 매 15초.
    // Phase 4-B 자동-4: 카운터 리셋을 호출자(여기)에 모음 — _emitWeekBanner 는 순수 표시 함수.
    //   배너 함수가 내부에서 상태를 갈아치우면 "재생 중 배너 재계산" 류 확장 시 레이스가 생김.
    const weeksElapsed = Math.floor(this.elapsedMs / BALANCE.weekMs);
    if (weeksElapsed > this._lastWeek) {
      this._lastWeek = weeksElapsed;
      this._emitWeekBanner(weeksElapsed, this._weekNetIncome);
      this._weekNetIncome = 0;
      this._weekSatisfied = 0;
      this._weekNeutral = 0;
      this._weekDissatisfied = 0;
    }

    // 월간 경계 — ResultScene 팝업 + pause. 4주마다 (≈1분).
    // 동일 프레임에 주간·월간 둘 다 발화 가능(주 4 경계 = 월 1 경계).
    const monthsElapsed = Math.floor(weeksElapsed / 4);
    if (monthsElapsed > this._lastMonth) {
      this._lastMonth = monthsElapsed;
      this._openMonthResult(monthsElapsed);
    }
  }

  _onShutdown() {
    if (this._toastTimer) { this._toastTimer.remove(false); this._toastTimer = null; }
    this._toastQueue = null;
    if (this._onCanvasContextMenu && this.game && this.game.canvas) {
      this.game.canvas.removeEventListener('contextmenu', this._onCanvasContextMenu);
      this._onCanvasContextMenu = null;
    }
    if (this._activeBanner) this._destroyActiveBanner();
    this._destroyTutorialNodes();
    this._destroyBadges();
    if (this.staffPanel) { this.staffPanel.destroy(); this.staffPanel = null; }
    if (this.patientInfoPanel) { this.patientInfoPanel.destroy(); this.patientInfoPanel = null; }
    this._forceCloseScrollPopup();
    // Phase 7-B3: 인접 미리보기 자원 정리.
    this._clearAdjPreview();
    if (this._adjPreviewGfx) { this._adjPreviewGfx.destroy(); this._adjPreviewGfx = null; }
    this._adjPreviewLabels = null;
    if (this._onPatientClicked) {
      this.events.off('patient_clicked', this._onPatientClicked);
      this._onPatientClicked = null;
    }
    if (this.unlocks) {
      this.unlocks.events?.off('unlocked', this._onUnlocked);
      this.unlocks.events?.off('unlocked', this._onStaffChanged);
      this.unlocks.events?.off('tier_unlocked', this._onTierUnlocked);
      this.unlocks.destroy();
      this.unlocks = null;
    }
    // Phase 4-C: 티켓은 patients.destroy() 보다 앞에 정리 — destroy 안에서 미판정 환자가
    //   patient_satisfied 를 마지막으로 emit 할 때 ticket 핸들러가 살아있도록 순서 유지하려면
    //   여기서 off 만 먼저, destroy 는 patients 다음에. 이벤트 emitter 살아있게 destroy 보류.
    if (this.tickets) {
      this.tickets.events?.off('ticket_issued', this._onTicketIssued);
      this.tickets.events?.off('ticket_redeem_treat', this._onTicketRedeemTreat);
      this.tickets.events?.off('ticket_redeem_amenity', this._onTicketRedeemAmenity);
    }
    if (this.patients) {
      // Phase 4-B 자동-2: destroy() 먼저 → off 뒤. destroy 내부에서 미판정 환자
      //   _evaluateSatisfaction 을 돌려 patient_satisfied/rejected/abandoned 를 발화하는데,
      //   이때 GameScene 핸들러가 살아 있어야 마지막 배치가 월간 카운터에 잡힘.
      this.patients.destroy();
      this.patients.events?.off('patient_paid', this._onPatientPaid);
      this.patients.events?.off('patient_using', this._onPatientUsing);
      this.patients.events?.off('patient_served', this._onPatientServed);
      this.patients.events?.off('patient_turned_away', this._onPatientTurnedAway);
      this.patients.events?.off('patient_satisfied', this._onPatientSatisfied);
      this.patients.events?.off('patient_pending', this._onPatientPending);
      this.patients.events?.off('patient_abandoned', this._onPatientAbandoned);
      this.patients.events?.off('patient_rejected', this._onPatientRejected);
      this.patients = null;
    }
    if (this.tickets) { this.tickets.destroy(); this.tickets = null; }
    if (this.staff) {
      this.staff.events?.off('staff_hired', this._onStaffChanged);
      this.staff.events?.off('staff_assigned', this._onStaffChanged);
      this.staff.events?.off('staff_fired', this._onStaffChanged);
      this.staff.events?.off('staff_hired', this._onStaffHiredWarn);
      this.staff.events?.off('staff_fired', this._onRecheckIsolation);
      this.staff.events?.off('staff_assigned', this._onRecheckIsolation);
      this.staff.destroy();
      this.staff = null;
    }
    if (this.grid) this.grid.events?.off('tile_changed', this._onStaffChanged);
    if (this.grid) this.grid.events?.off('tile_changed', this._onRecheckIsolation);
    if (this.path) { this.path.destroy(); this.path = null; }
    if (this.grid) { this.grid.destroy(); this.grid = null; }
    if (this.events) this.events.off(Phaser.Scenes.Events.RESUME, this._onResumed, this);
    this.hudHint = null;
    this.hudTime = null;
    this.hudGold = null;
    this.hudMyeongui = null;
    this.hudTickets = null;
    if (this._bgmHit) { this._bgmHit.removeAllListeners(); this._bgmHit.destroy(); this._bgmHit = null; }
    if (this._bgmBg) { this._bgmBg.destroy(); this._bgmBg = null; }
    if (this._bgmLabel) { this._bgmLabel.destroy(); this._bgmLabel = null; }
    this.hoverCursor = null;
    this._toolButtons = null;
    this._tutorial = null;
    this._onStaffChanged = null;
    this._badgeSprites = null;
    if (this._useGauges) {
      for (const g of this._useGauges.values()) {
        if (g.bg)  g.bg.destroy();
        if (g.bar) g.bar.destroy();
      }
      this._useGauges.clear();
      this._useGauges = null;
    }
  }

  // ─── 주간 HUD 배너 (pause 없음, 2초 페이드) ───────
  // Phase 4-A ③A: 주간 배너에 만족 카운터 1줄 추가 — 카이로 리듬 단기 피드백.
  //   totalJudged = satisfied+neutral+dissatisfied (pending·abandoned 제외).
  //   0/0 은 "집계 중" 가드 — S10 P0 대응.
  _emitWeekBanner(weekNum, income) {
    const x = GAME_WIDTH / 2;
    const y = HUD_TOP_H + 28;
    const totalJudged = this._weekSatisfied + this._weekNeutral + this._weekDissatisfied;
    const satLabel = totalJudged === 0
      ? '만족 — 집계 중'
      : `만족 ${this._weekSatisfied}/${totalJudged}`;
    const msg = income >= 0
      ? `第 ${weekNum} 週 — 수입 +${income}전 · ${satLabel}`
      : `第 ${weekNum} 週 — 적자 ${income}전 · ${satLabel}`;
    const color = income >= 0 ? '#c06000' : '#c02020';

    const w = 380, h = 36;
    const bg = this.add.graphics().setDepth(489);
    bg.fillStyle(0xfdf0d0, 0.95);
    bg.fillRoundedRect(x - w / 2, y - h / 2, w, h, 8);
    bg.lineStyle(2, 0xd08020, 1);
    bg.strokeRoundedRect(x - w / 2, y - h / 2, w, h, 8);

    const label = this.add.text(x, y, msg, {
      fontFamily: 'Noto Serif KR, serif', fontSize: '15px',
      color, fontStyle: 'bold', stroke: '#ffffff', strokeThickness: 1
    }).setOrigin(0.5).setDepth(490);

    // 500ms hold → 1500ms fade → destroy
    // 월간 팝업 직전에 강제 정리할 수 있도록 현재 배너 참조 저장.
    if (this._activeBanner) this._destroyActiveBanner();
    const tween = this.tweens.add({
      targets: [bg, label],
      alpha: 0, duration: 1500, delay: 500, ease: 'Cubic.easeIn',
      onComplete: () => {
        bg.destroy(); label.destroy();
        if (this._activeBanner && this._activeBanner.bg === bg) this._activeBanner = null;
      }
    });
    this._activeBanner = { bg, label, tween };
  }

  _destroyActiveBanner() {
    const b = this._activeBanner;
    if (!b) return;
    if (b.tween && b.tween.isPlaying && b.tween.isPlaying()) b.tween.stop();
    if (b.bg) b.bg.destroy();
    if (b.label) b.label.destroy();
    this._activeBanner = null;
  }

  // ─── 월간 결산 (pause + launch) ─────────────────
  // Phase 3-B: 직원 wage 합계를 월 경계에서 차감 (S2 경제 투명성 — FAIL→PASS 레버).
  // 차감은 `_applyGold(-wage)` 로 summary.income 에 반영. 별도 wage 필드로 내역도 노출.
  _openMonthResult(monthNum) {
    // A 보정: 패널 오픈 중 월간 결산 트리거 시 좀비 handler 방지 — 강제 close.
    if (this.staffPanel && this.staffPanel.isOpened()) this.staffPanel.close();
    if (this.patientInfoPanel && this.patientInfoPanel.isOpened()) this.patientInfoPanel.close();
    // BUG-3: Scene pause 중 두루마기 tween 중간상태 잔존 방지.
    this._forceCloseScrollPopup();
    // H-3 보정: wage 차감 전 income 스냅샷 — ResultScene 에서 수입/급료가 이중으로
    // 보이는 UX 혼동 제거. summary.income 은 순수 수입, summary.wage 는 분리 표시.
    const incomeBeforeWage = this._monthNetIncome;
    const wage = this.staff ? this.staff.getMonthlyWage() : 0;
    // Phase 5: 월별 유지비 차감 — 배치된 치료방·편의시설 카테고리별 합산.
    //   체크리스트: treat 2전/월, amenity 1전/월. (해우소·우물 제외 라인은 향후 분리 — 일단 amenity 균등 적용)
    const upkeep = this._computeMonthlyUpkeep();
    if (wage > 0) this._applyGold(-wage);
    if (upkeep > 0) this._applyGold(-upkeep);
    if ((wage + upkeep) > 0 && this.gold < 0) {
      this._toast('자금 부족 — 다음달 운영에 경고');
    }
    const totalJudged = this._monthSatisfied + this._monthNeutral + this._monthDissatisfied;
    // Phase 4-B ⑧C: 다음 미해금 계층 진행률 — 장기 목표(K1) 라인.
    const nextTier = this.unlocks ? this.unlocks.getNextTierTarget() : null;
    const summary = {
      kind: 'month',
      month: monthNum,
      gold: this.gold,
      income: incomeBeforeWage,
      wage,
      upkeep,
      myeongui: this.myeongui,
      // Phase 4-A ③A + S10: 만족도 3단 카운터. totalJudged === 0 은 ResultScene 에서 "—" 가드.
      satisfied: this._monthSatisfied,
      neutral: this._monthNeutral,
      dissatisfied: this._monthDissatisfied,
      totalJudged,
      // 2차 FM-N1: 선비·양반 보류 카운터 — "Phase 6 기능 해금 전" 설명 라인용.
      pending: this._monthPending,
      // Phase 4-B ⑨B: 거절 환자 총계 + 계층별 breakdown (ResultScene 이 "양반 M · 상인 L" 조립).
      rejected: this._monthRejected,
      rejectedByTier: { ...this._monthRejectedByTier },
      // Phase 7-A2: 방별 수입 — building.key → 누적 fee. ResultScene 스택바.
      incomeByBuilding: { ...this._monthIncomeByBuilding },
      // Phase 4-B ⑧C: 다음 계층 해금까지 — { tier, threshold } 또는 null(모두 해금).
      nextTier
    };
    // Phase 5: 6개월 누적 (월 결산 직전 가산, 6의 배수 도달 시 summary 에 attach + 리셋).
    this._halfYearIncome += incomeBeforeWage;
    this._halfYearWage += wage;
    this._halfYearUpkeep += upkeep;
    this._halfYearMonths += 1;
    // Phase 6: 월별 스냅샷 누적 (링 버퍼, 최대 6).
    this._monthlyHistory.push({
      month: monthNum,
      income: incomeBeforeWage,
      wage, upkeep,
      net: incomeBeforeWage - wage - upkeep
    });
    if (this._monthlyHistory.length > 6) this._monthlyHistory.shift();
    if (this._halfYearMonths >= 6) {
      const net = this._halfYearIncome - this._halfYearWage - this._halfYearUpkeep;
      summary.halfYear = {
        income: this._halfYearIncome,
        wage: this._halfYearWage,
        upkeep: this._halfYearUpkeep,
        net,
        history: this._monthlyHistory.slice()
      };
      this._halfYearIncome = 0;
      this._halfYearWage = 0;
      this._halfYearUpkeep = 0;
      this._halfYearMonths = 0;
    }
    this._monthNetIncome = 0;
    this._monthSatisfied = 0;
    this._monthNeutral = 0;
    this._monthDissatisfied = 0;
    this._monthPending = 0;
    this._monthRejected = 0;
    this._monthRejectedByTier = {};
    this._monthIncomeByBuilding = {};
    this.scene.launch('ResultScene', { summary });
    this.scene.pause();
  }

  _onResumed() {
    // ResultScene 이 resume('GameScene') 호출 후 돌아왔을 때 BGM 복귀
    if (this.audioSys && typeof this.audioSys.switchTheme === 'function') {
      Promise.resolve(this.audioSys.switchTheme('day')).catch(() => {});
    }
  }

  // Phase 5: 월별 유지비 — BUILDINGS.category 별로 grid 배치 개수 × upkeepMonthly 단가 합.
  //   장식(decor) 은 유지비 0. 향후 amenity 내 해우소·우물 면제 분기 가능 (현 설계는 단순화).
  _computeMonthlyUpkeep() {
    if (!this.grid) return 0;
    const fees = BALANCE.upkeepMonthly || {};
    let total = 0;
    // BuildingRegistry import 가 이미 상단에 있어 BUILDINGS 직접 enum 안 함 → 카테고리만 카운트.
    //   getBuildingByTileType 은 이미 import 됨.
    for (let r = 0; r < GRID_ROWS; r++) {
      for (let c = 0; c < GRID_COLS; c++) {
        const tile = this.grid.get(c, r);
        if (!tile) continue;
        const b = getBuildingByTileType(tile.type);
        if (!b) continue;
        const fee = fees[b.category] || 0;
        if (fee > 0) total += fee;
      }
    }
    return total;
  }

  // PatientSystem 이벤트 → gold/명의 갱신 + FloatingText 렌더. 시스템↔씬 경계 분리.
  // G 보정: wellBonus 는 기본 fee 와 시각적으로 분리 표시(y 오프셋 + 파란색).
  _onPatientPaid({ building, fee, myeongui, wellBonus, col, row }) {
    if (fee) this._applyGold(+fee);
    if (myeongui) this._applyMyeongui(myeongui);
    // Phase 7-A2: 방별 수입 누적 — wellBonus 포함된 총 fee. 월간 결산 스택바 입력.
    if (building && building.key && fee > 0) {
      this._monthIncomeByBuilding[building.key] =
        (this._monthIncomeByBuilding[building.key] || 0) + fee;
    }
    if (col == null || row == null) return;
    const pix = this.grid.pixelFromTile(col, row);
    const baseFee = (fee || 0) - (wellBonus || 0);
    if (baseFee > 0) {
      FloatingText.spawn(this, pix.x, pix.y - 24, `+${baseFee}전`, { color: '#4ac06a', size: 14 });
    }
    if (wellBonus && wellBonus > 0) {
      FloatingText.spawn(this, pix.x - 8, pix.y - 40, `+${wellBonus}전 우물`, { color: '#3ca0e0', size: 13 });
      audioSystem.playSFX?.('well_bonus');
    }
    if (myeongui > 0) {
      FloatingText.spawn(this, pix.x + 24, pix.y - 24, `+${myeongui.toFixed(1)}명`, { color: '#208030', size: 12 });
    }
  }

  // Phase 4-A0 ④A: 편의시설 이용 중에도 머리 위 라벨로 직관 표시.
  // 체크박스만 켜지는 느낌 방지 — "지금 뭐 하는지" 즉시 보이게.
  // 2차 검증 M1 보정: 라벨 지속시간을 이용시간에 맞춤(최소 900ms) — 이용 끝나기 전에
  // 라벨이 사라져 "뭐 하는지 모름" 구간이 생기는 문제 해소.
  _onPatientUsing({ patient, building, col, row }) {
    if (col == null || row == null) return;
    const pix = this.grid.pixelFromTile(col, row);
    const key = building ? building.key : null;
    let text = '진료중…';
    let color = '#d08020';
    if (key === 'haewoso') { text = '볼일중…'; color = '#8aa08a'; }
    else if (key === 'well')    { text = '목축임…'; color = '#3ca0e0'; }
    else if (key === 'gukbap')  { text = '식사중…'; color = '#c87040'; }
    const useMs = building ? (building.useMs || 0) : 0;
    const duration = Math.max(900, Math.round(useMs * 0.9));
    FloatingText.spawn(this, pix.x, pix.y - 18, text, { color, size: 12, duration });

    // v0.5 이식 — 진행 게이지(건물 상단). 기존 FloatingText 는 "무엇을 하는지" 라벨,
    //   게이지는 "얼마나 남았는지" 정량 피드백. 카이로 체감 핵심 — 둘 다 유지.
    if (patient && useMs > 0) {
      this._destroyUseGauge(patient);
      const gy = pix.y - 30;
      const bg = this.add.rectangle(pix.x, gy, 42, 5, 0x000000, 0.6).setDepth(46);
      const bar = this.add.rectangle(pix.x - 20, gy, 40, 3, 0xf0c050)
        .setOrigin(0, 0.5).setDepth(47);
      this._useGauges.set(patient, { bg, bar, useMs });
    }
  }

  // USING 정상 종료 — patient_served 구독. 건물→다른건물 순회 시 즉시 정리 후
  //   다음 _beginUsing 이 새 게이지 생성(중복 위험 없음).
  _onPatientServed({ patient }) {
    if (patient) this._destroyUseGauge(patient);
  }

  _destroyUseGauge(patient) {
    const g = this._useGauges.get(patient);
    if (!g) return;
    if (g.bg)  g.bg.destroy();
    if (g.bar) g.bar.destroy();
    this._useGauges.delete(patient);
  }

  // Phase 4-A: 만족도 판정 결과 처리.
  // - satisfied/neutral/dissatisfied 3단 카운터를 주간·월간에 누적.
  // - FloatingText 는 환자 스프라이트 위치(대문 근처)에서 색·문구 구분.
  // - M4 대비: duration 1100ms — 페이드 400ms 이후에도 잔상 유지.
  _onPatientSatisfied(payload) {
    const { patient, result, myeongui } = payload;
    if (myeongui && myeongui > 0) this._applyMyeongui(myeongui);
    if (result === 'satisfied') {
      this._weekSatisfied++; this._monthSatisfied++;
    } else if (result === 'neutral') {
      this._weekNeutral++; this._monthNeutral++;
    } else {
      this._weekDissatisfied++; this._monthDissatisfied++;
    }
    // Phase 4-C: 만족 페이로드 통째로 TicketSystem 위임 (내부에서 result/score 가드).
    if (this.tickets) this.tickets.onPatientSatisfied(payload);
    if (!patient || !patient.sprite) return;
    const sx = patient.sprite.x;
    const sy = patient.sprite.y - 22;
    let text, color;
    if (result === 'satisfied') {
      text = myeongui > 0 ? `만족 +${myeongui.toFixed(1)}명` : '만족';
      color = '#4ac06a';
    } else if (result === 'neutral') {
      text = myeongui > 0 ? `보통 +${myeongui.toFixed(1)}명` : '보통';
      color = '#d0a020';
    } else {
      text = '불만족'; color = '#c06060';
    }
    FloatingText.spawn(this, sx, sy, text, { color, size: 13, duration: 1100 });
  }

  // Phase 4-C 티켓 핸들러 — issue 시 floating text(가시화), redeem 시 PatientSystem.spawnOne 라우팅.
  _onTicketIssued({ type, kind, tier }) {
    // Sawyer/Molyneux: 즉각 피드백. 대문 근처에 작은 로그.
    const sp = this.grid ? this.grid.pixelFromTile(SPAWN_COL, SPAWN_ROW) : { x: GAME_WIDTH/2, y: HUD_TOP_H+40 };
    const label = type === 'treat' ? `+치료티켓(${kind || ''})` : '+편의티켓';
    FloatingText.spawn(this, sp.x + 28, sp.y - 18, label, {
      color: '#f7d05b', size: 11, duration: 900
    });
  }

  _onTicketRedeemTreat({ tier }) {
    if (!this.patients) return;
    const p = this.patients.spawnOne(tier, { isTicketSpawn: true, ticketType: 'treat' });
    if (p) this._toast(`치료평판 누적 — ${this._tierLabel(tier)} 손님 입장`);
  }

  _onTicketRedeemAmenity({ tier, demand }) {
    if (!this.patients) return;
    const p = this.patients.spawnOne(tier, { isTicketSpawn: true, ticketType: 'amenity', demand });
    if (p) this._toast(`편의평판 누적 — ${this._tierLabel(tier)} 손님 입장`);
  }

  _tierLabel(tier) {
    const map = { nobi: '노비', nongmin: '농민', sangin: '상인', seonbi: '선비', yangban: '양반' };
    return map[tier] || tier;
  }

  // 선비·양반은 현 빌딩으로 수학적 만족 불가 — Phase 6 소나무 편의 보너스 후 활성.
  // 만족/불만족 카운터에 넣지 않고 별도 시각만 제공. 명의 가산 없음.
  // 2차 FM-N1 보정: 월간 결산에 "보류 N명" 표시용 카운터 누적.
  _onPatientPending({ patient }) {
    this._monthPending++;
    if (!patient || !patient.sprite) return;
    FloatingText.spawn(
      this, patient.sprite.x, patient.sprite.y - 22,
      '…평가 보류', { color: '#8090b0', size: 12, duration: 1100 }
    );
  }

  // 입장도 못 한 환자(스폰 후 경로 없어 즉시 fade) — 통계 왜곡 방지용 분리 이벤트.
  _onPatientAbandoned(/* { patient } */) {
    // 시각 피드백 없음(환자가 이미 fade 중). 추후 필요 시 추가.
  }

  // Phase 4-A ⑥A: 개발용 계층 스폰. 배포 빌드에선 제거 예정.
  _debugSpawnTier(tier) {
    if (!this.patients) return;
    const p = this.patients.spawnOne(tier);
    if (!p) this._toast('환자 정원 초과');
  }

  // 치료방에 staff 미커버 상태에서 환자가 돌아가는 순간 — C1 학습 스파이럴 방지용 시각 단서.
  // H-5 보정: 건물(key)별 1회 토스트 — acu/herb 해금 후에도 재교육 보장.
  // Phase 4-B ⑦C: 가드 키를 `${건물key}_${tier}` 튜플로 — 새 계층 첫 거절마다 재안내.
  //   계층별 관리 비용 각인 목적. building 없어도 `_any_${tier}` 로 유효 키 생성.
  _onPatientTurnedAway({ building, col, row, reason, tier }) {
    if (col == null || row == null) return;
    const pix = this.grid.pixelFromTile(col, row);
    FloatingText.spawn(this, pix.x, pix.y - 22, '직원!', { color: '#e8c040', size: 14 });
    if (reason !== 'no_staff') return;
    if (!this._noStaffToastShownByBuildingTier) this._noStaffToastShownByBuildingTier = new Set();
    const bk = building ? building.key : '_any';
    const tk = tier || 'nobi';
    const guardKey = `${bk}_${tk}`;
    if (this._noStaffToastShownByBuildingTier.has(guardKey)) return;
    this._noStaffToastShownByBuildingTier.add(guardKey);
    const label = building ? building.label : '치료방';
    this._toast(`${label} 운영엔 직원이 필요합니다 — 인접 마루에 직원을 배치하세요`);
  }

  // 첫 치료방 배치 + 직원 0명 → 인접 maru 에 무수리 자동 스폰 + 자동 배정.
  // 결정적 순서(좌→우→상→하)로 첫 번째 가용 maru 선택 → K1 회귀 방지.
  // H-1 보정: 세션당 1회만 보장 — 재지급 익스플로잇 차단 (해고/타일 파괴 후 재스폰 금지).
  _autoSpawnTutorialMusuri(roomCol, roomRow) {
    if (this._tutorialStaffGranted) return;
    const deltas = [[-1, 0], [1, 0], [0, -1], [0, 1]];
    for (const [dc, dr] of deltas) {
      const nc = roomCol + dc, nr = roomRow + dr;
      if (!this.grid.inBounds(nc, nr)) continue;
      const tile = this.grid.get(nc, nr);
      if (!tile || tile.type !== TILE_MARU) continue;
      const s = this.staff.hire('musuri', nc, nr);
      if (!s) continue;
      const res = this.staff.assign(s, roomCol, roomRow);
      if (res.ok) {
        this._tutorialStaffGranted = true;
        this._toast('무수리 합류 — 뜸방 운영을 시작합니다');
        return;
      }
    }
    // 인접 maru 없음 — 유저가 마루를 뜸방 옆에 깔 때까지 힌트. grant 플래그는 아직 미설정 → 재시도 가능.
    this._toast('뜸방 옆에 마루를 깔면 무수리가 자동 합류합니다');
  }

  // C-4 보정: 뜸방 먼저 → 마루 나중에 배치 시 자동 스폰 재트리거.
  // 조건: 튜토리얼 미지급 + staff 0 + 인접 4방향에 category==treat 건물 존재.
  _retryTutorialSpawnNearMaru(maruCol, maruRow) {
    if (this._tutorialStaffGranted) return;
    if (!this.staff || this.staff.count() > 0) return;
    const deltas = [[-1, 0], [1, 0], [0, -1], [0, 1]];
    for (const [dc, dr] of deltas) {
      const nc = maruCol + dc, nr = maruRow + dr;
      if (!this.grid.inBounds(nc, nr)) continue;
      const tile = this.grid.get(nc, nr);
      if (!tile) continue;
      const b = getBuildingByTileType(tile.type);
      if (!b || b.category !== 'treat') continue;
      this._autoSpawnTutorialMusuri(nc, nr);
      return;
    }
  }

  // M 키 — 마스터 쇼룸 모드. 자산 애니(국밥집·소나무) 시각 점검용.
  //   · 전 건물 해금 (acu/herb/haewoso/gukbap/well/pine)
  //   · 전 계층 해금 (농민·상인·선비·양반) — P 키 스폰 다양성 확보
  //   · 그리드에 7종 자동 배치 + 대문→건물 마루 경로 구축
  //   · 1회 실행 guard (중복 호출 시 무해). 기존 환자 영향 최소화를 위해 초기 세션에서 사용 권장.
  _debugMasterMode() {
    if (this._masterModeDone) { this._toast('마스터 모드 이미 적용됨'); return; }
    this._masterModeDone = true;

    // 1) 건물·계층 전부 해금
    for (const k of ['acu', 'herb', 'haewoso', 'gukbap', 'well', 'pine']) {
      this.unlocks.forceUnlock(k);
    }
    for (const t of ['nongmin', 'sangin', 'seonbi', 'yangban']) {
      this.unlocks.forceUnlockTier?.(t);
    }

    // 2) 대문(4,9) → spawn(4,8) 세로 통로 (col=4, row=8..3)
    for (let r = 8; r >= 3; r--) this.grid.setType(4, r, TILE_MARU);
    // 3) row=3 가로 통로 전체
    for (let c = 0; c < 10; c++) this.grid.setType(c, 3, TILE_MARU);
    // 4) row=2 에 7종 건물 쇼케이스 (col 4 는 통로 연결 지점이라 skip)
    const layout = [
      { col: 0, key: 'moxa' },
      { col: 1, key: 'acu' },
      { col: 2, key: 'herb' },
      { col: 3, key: 'haewoso' },
      { col: 5, key: 'gukbap' },
      { col: 6, key: 'well' },
      { col: 7, key: 'pine' }
    ];
    for (const { col, key } of layout) {
      const b = getBuildingByKey(key);
      if (b) this.grid.setType(col, 2, b.tileType);
    }
    this._toast('마스터: 7종 쇼룸 배치 + 전 계층 해금');
  }

  // H 키: musuri 추가 고용. Phase 3-C UI 전까지 자동 배정까지 함께 처리.
  // 우선순위: (1) 미커버 moxa 옆 maru → 즉시 assign, (2) 아무 maru → 고용만.
  _debugHireMusuri() {
    const spec = BALANCE.staff.musuri;
    if (this.gold < spec.hire) {
      this._toast(`무수리 고용 실패: 돈 부족 (${spec.hire}전 필요)`);
      return;
    }
    const marus = this.grid.listByType(TILE_MARU);
    // (1) 미커버 moxa 인접 maru 탐색
    const moxas = this.grid.listByType(TILE_MOXA);
    for (const m of moxas) {
      if (this.staff.isRoomCovered(m.col, m.row)) continue;
      const deltas = [[-1, 0], [1, 0], [0, -1], [0, 1]];
      for (const [dc, dr] of deltas) {
        const nc = m.col + dc, nr = m.row + dr;
        const tile = this.grid.get(nc, nr);
        if (!tile || tile.type !== TILE_MARU) continue;
        const s = this.staff.hire('musuri', nc, nr);
        if (!s) continue;
        const res = this.staff.assign(s, m.col, m.row);
        this._applyGold(-spec.hire);
        this._toast(res.ok
          ? `무수리 고용 (-${spec.hire}전) — 뜸방 커버 시작`
          : `무수리 고용 (-${spec.hire}전)`);
        return;
      }
    }
    // (2) fallback — 아무 maru 고용
    for (const t of marus) {
      const s = this.staff.hire('musuri', t.col, t.row);
      if (s) {
        this._applyGold(-spec.hire);
        this._toast(`무수리 고용 (-${spec.hire}전)`);
        return;
      }
    }
    this._toast('무수리를 배치할 빈 마루가 없습니다');
  }

  // gold 변동을 주간·월간 수입 누적과 함께 처리. 모든 mutation 은 이 헬퍼를 경유.
  _applyGold(delta) {
    this.gold += delta;
    this._weekNetIncome += delta;
    this._monthNetIncome += delta;
  }

  // Phase 4-B ①A + 자동-1: 명의 변경 통로. patient_paid / patient_satisfied 모두 여기로 일원화.
  //   변경 직후 UnlockSystem.checkTierUnlocks 로 계층 해금 평가 — tier_unlocked 이벤트는
  //   _onTierUnlocked 가 받아 PatientSystem 풀 동기화·환영 스폰·토스트 처리.
  //   delta 음수 허용(현재 사용처 없음, 미래 패널티 확장 여지) — 해금은 상한 도달 시점에만 발화.
  _applyMyeongui(delta) {
    if (!delta) return;
    this.myeongui += delta;
    if (this.unlocks && delta > 0) this.unlocks.checkTierUnlocks(this.myeongui);
  }

  // Phase 4-B ⑤B: 계층 해금 → PatientSystem 풀 동기화 + (양반 한정) 환영 스폰 예약 + 토스트.
  //   nongmin/sangin 은 tierSpawnWeight 양수라 풀 동기화만으로 자연 출현.
  //   seonbi 는 Phase 6 소나무 편의 해금 전까지 weight 0 유지 — 토스트만.
  //   yangban 은 weight 0 이지만 해금 순간 1회 환영 스폰으로 "누가 해금됐는지" 서사 보존.
  _onTierUnlocked({ tier }) {
    if (this.patients) this.patients.setUnlockedTiers(this.unlocks.unlockedTiers);
    // Phase 4-C: 티켓 풀의 가중치 샘플도 같은 unlock 풀 공유 — 동시 동기화.
    if (this.tickets) this.tickets.setUnlockedTiers(this.unlocks.unlockedTiers);
    if (tier === 'yangban' && this.patients) this.patients.requestWelcomeSpawn(tier);
    const labels = { nongmin: '농민', sangin: '상인', seonbi: '선비', yangban: '양반' };
    const label = labels[tier] || tier;
    this._toast(`계층 해금: ${label} 환자 등장`);
  }

  // Phase 4-B ⑥A + ⑨B: 직원 부족 귀가 환자 — 월간·계층별 카운터 누적. 시각은 turned_away 가
  //   이미 "직원!" 라벨을 띄워 중복 방지. 월간 결산 UI 에서 "거절 N명 (양반 M · …)" 로 표시.
  _onPatientRejected({ tier }) {
    this._monthRejected++;
    const t = tier || 'nobi';
    this._monthRejectedByTier[t] = (this._monthRejectedByTier[t] || 0) + 1;
  }

  // QA 훅: Y 키로 다음 주 경계를 즉시 트리거 (월간 경계 도달 시 팝업까지).
  _debugFastForwardWeek() {
    // elapsedMs 를 다음 주 경계 직후로 점프. update() 에서 자연스레 트리거.
    const nextWeekMs = (this._lastWeek + 1) * BALANCE.weekMs + 1;
    if (this.elapsedMs < nextWeekMs) this.elapsedMs = nextWeekMs;
  }

  // QA 훅: P 키로 환자 1명 강제 스폰. 스폰 조건(스폰 포인트 마루) 미충족 시 토스트.
  _debugSpawnPatient() {
    if (!this.patients) return;
    const spawn = this.grid.get(SPAWN_COL, SPAWN_ROW);
    if (!spawn || spawn.type !== TILE_MARU) {
      this._toast('스폰 포인트에 마루를 먼저 놓으세요.');
      return;
    }
    const p = this.patients.spawnOne('nobi');
    if (!p) { this._toast(`정원 만석 (${BALANCE.maxPatients}명 한도)`); return; }
    this._toast('환자 스폰 (P키)');
  }

  // ─── 배경 ───────────────────────────────────────────
  _drawBackground() {
    const g = this.add.graphics();
    // 전체 배경 — 어두운 깊이감
    g.fillStyle(0x1a1428, 1);
    g.fillRect(0, 0, GAME_WIDTH, GAME_HEIGHT);

    // 그리드 둘레 (바깥 영역) — 살짝 어두운 나무 바닥
    g.fillStyle(0x2e1f14, 1);
    g.fillRect(0, HUD_TOP_H, GAME_WIDTH, GAME_HEIGHT - HUD_TOP_H - HUD_BOT_H);

    // 그리드 테두리 (금색 외곽)
    g.lineStyle(3, 0xf7d05b, 0.9);
    g.strokeRect(GRID_ORIGIN_X - 1, GRID_ORIGIN_Y - 1, GRID_PIXEL_W + 2, GRID_PIXEL_H + 2);

    // 그리드 선
    g.lineStyle(1, 0x000000, 0.25);
    for (let i = 1; i < GRID_COLS; i++) {
      const x = GRID_ORIGIN_X + i * TILE_SIZE;
      g.lineBetween(x, GRID_ORIGIN_Y, x, GRID_ORIGIN_Y + GRID_PIXEL_H);
    }
    for (let i = 1; i < GRID_ROWS; i++) {
      const y = GRID_ORIGIN_Y + i * TILE_SIZE;
      g.lineBetween(GRID_ORIGIN_X, y, GRID_ORIGIN_X + GRID_PIXEL_W, y);
    }
  }

  // ─── HUD ────────────────────────────────────────────
  _createHud() {
    const DEPTH = 500;
    // 상단 바
    this.add.rectangle(0, 0, GAME_WIDTH, HUD_TOP_H, 0x8b4a10).setOrigin(0, 0).setDepth(DEPTH);
    this.add.rectangle(0, HUD_TOP_H - 3, GAME_WIDTH, 3, 0x6a3208).setOrigin(0, 0).setDepth(DEPTH);
    // 하단 바
    this.add.rectangle(0, GAME_HEIGHT - HUD_BOT_H, GAME_WIDTH, HUD_BOT_H, 0x8b4a10).setOrigin(0, 0).setDepth(DEPTH);
    this.add.rectangle(0, GAME_HEIGHT - HUD_BOT_H, GAME_WIDTH, 3, 0x6a3208).setOrigin(0, 0).setDepth(DEPTH);

    // 좌상단: 시간
    this.hudTime = this.add.text(12, 10, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '18px', color: '#f7d05b', fontStyle: 'bold'
    }).setDepth(DEPTH + 1);

    // BGM 토글 버튼 — 시간 우측에 작은 박스. 클릭 시 audioSystem.toggleMute + 라벨 갱신.
    this._createBgmToggle(DEPTH);

    // 우상단: 돈·명의
    this.hudGold = this.add.text(GAME_WIDTH - 12, 10, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '18px', color: '#f7d05b', fontStyle: 'bold'
    }).setOrigin(1, 0).setDepth(DEPTH + 1);

    this.hudMyeongui = this.add.text(GAME_WIDTH - 12, 10 + 20, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '12px', color: '#e8dcc4'
    }).setOrigin(1, 0).setDepth(DEPTH + 1);

    // Phase 4-C: 티켓 카운터 — 시간 우측 inline. Sawyer 가시화 + 카이로 평판 풀 노출.
    //   "치료 7/15  편의 3/15" 형태. 풀 한도(15) 도달 임박이면 강조색.
    this.hudTickets = this.add.text(240, 12, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '12px', color: '#e8dcc4'
    }).setOrigin(0, 0).setDepth(DEPTH + 1);

    // 하단 안내 (Phase 1 임시)
    this.hudHint = this.add.text(GAME_WIDTH / 2, GAME_HEIGHT - HUD_BOT_H + 10, '', {
      fontFamily: 'monospace', fontSize: '12px', color: '#e8dcc4'
    }).setOrigin(0.5, 0).setDepth(DEPTH + 1);
    this.hudHint.setText(this._defaultHintText());
  }

  // 시간 라벨 우측, 상단 바 내부에 작은 토글 박스. 아이콘 없이 텍스트("♪ 켬"/"♪ 꺼짐").
  //   hitZone 을 배경 rect 보다 살짝 크게 잡아 터치 타겟 확보. zone.setInteractive 로
  //   HUD Depth(500+) 아래 그리드 Zone 과 분리 — 별 충돌 없음.
  _createBgmToggle(depth) {
    const x = 150, y = 20;
    this._bgmBg = this.add.rectangle(x, y, 76, 22, 0x3a1f08, 0.9)
      .setOrigin(0, 0.5).setStrokeStyle(1, 0xb07f1e).setDepth(depth + 1);
    this._bgmLabel = this.add.text(x + 38, y, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '12px', color: '#f7d05b'
    }).setOrigin(0.5, 0.5).setDepth(depth + 2);
    this._bgmHit = this.add.zone(x, y - 11, 76, 22).setOrigin(0, 0).setInteractive({ useHandCursor: true });
    this._bgmHit.setDepth(depth + 2);
    this._bgmHit.on('pointerdown', () => {
      const muted = audioSystem.toggleMute();
      this._refreshBgmLabel();
      this._toast(muted ? 'BGM 꺼짐' : 'BGM 켜짐');
    });
    this._refreshBgmLabel();
  }

  _refreshBgmLabel() {
    if (!this._bgmLabel) return;
    const muted = audioSystem.isMuted && audioSystem.isMuted();
    this._bgmLabel.setText(muted ? '♪ 꺼짐' : '♪ 켬');
    this._bgmLabel.setColor(muted ? '#a08060' : '#f7d05b');
  }

  _defaultHintText() {
    return '[선택] 치료방 클릭=직원투입   [클릭] 배치/철거   [P] 환자 스폰   [Y] 주 점프';
  }

  // 카이로풍 카테고리 그룹 — 기초/치료/편의/식재 4섹션. 해금 안 된 그룹은 자동 숨김.
  // select 는 'special' (배치 아닌 StaffPanel 진입), maru 는 항상 노출.
  _buildToolGroups() {
    const groups = [
      { label: '기초', tools: [
        { key: 'select', label: '선택', icon: 'tex_tool_select', cost: 0, special: true },
        { key: 'maru',   label: '마루', icon: 'tex_tile_maru',   cost: BALANCE.costs.maru }
      ]},
      { label: '치료', tools: [] },
      { label: '편의', tools: [] },
      { label: '식재', tools: [] }
    ];
    const catToIdx = { treat: 1, amenity: 2, decor: 3 };
    const order = ['moxa', 'acu', 'herb', 'haewoso', 'well', 'gukbap', 'pine'];
    for (const key of order) {
      if (!this.unlocks || !this.unlocks.isUnlocked(key)) continue;
      const b = getBuildingByKey(key);
      if (!b) continue;
      const idx = catToIdx[b.category];
      if (idx == null) continue;
      groups[idx].tools.push({ key: b.key, label: b.label, icon: b.texture, cost: b.cost });
    }
    return groups.filter((g) => g.tools.length > 0);
  }

  // ─── 하단 카이로풍 탭 메뉴 (Phase 7-C) ──────────────────────
  // 기존 우측 세로 툴바(②)를 하단 고정 탭 메뉴로 대체.
  //   - 프레임: y=MENU_STRIP_Y ~ +MENU_STRIP_H (680~820), full-width.
  //   - 상단 32px: 4 탭(기초/치료/편의/식재) — 전환 시 콘텐츠만 재그림.
  //   - 하단 108px: 좌 3×2 아이콘 그리드 + 우 상세 패널(이름/비용/설명).
  // 메서드 이름(`_createToolbar` 등)은 유지 — 호출부(shutdown·`_onUnlocked`·`_updateHud`) 불변.
  _createToolbar() {
    this._toolGroups = this._buildToolGroups();
    if (this._selectedTab == null) this._selectedTab = 0;
    if (this._selectedTab >= this._toolGroups.length) this._selectedTab = 0;
    this._menuElements = { bgPanel: null, tabs: [], itemSlots: [], detail: null };
    // 구 _toolButtons API 호환 — _redrawToolbar·shutdown 이 참조.
    this._toolButtons = this._menuElements.itemSlots;

    this._drawMenuFrame();
    this._drawTabs();
    this._drawTabContent();
  }

  _drawMenuFrame() {
    const DEPTH = 400;
    const g = this.add.graphics().setDepth(DEPTH);
    g.fillStyle(0x2e1f14, 1);
    g.fillRect(0, MENU_STRIP_Y, GAME_WIDTH, MENU_STRIP_H);
    g.lineStyle(2, 0x6a3208, 1);
    g.strokeRect(0, MENU_STRIP_Y, GAME_WIDTH, MENU_STRIP_H);
    // 탭/콘텐츠 경계선
    g.lineStyle(1, 0x1a0f06, 1);
    g.lineBetween(0, MENU_STRIP_Y + MENU_TAB_H, GAME_WIDTH, MENU_STRIP_Y + MENU_TAB_H);
    this._menuElements.bgPanel = g;
  }

  _drawTabs() {
    const DEPTH = 400;
    const groups = this._toolGroups;
    const tabW = Math.floor(GAME_WIDTH / groups.length);
    for (let i = 0; i < groups.length; i++) {
      const x = i * tabW;
      const y = MENU_STRIP_Y;
      const active = i === this._selectedTab;
      const bg = this.add.graphics().setDepth(DEPTH + 1);
      bg.fillStyle(active ? 0x8b5a2a : 0x3a2414, 1);
      bg.fillRect(x, y, tabW, MENU_TAB_H);
      if (active) {
        bg.fillStyle(0xf7d05b, 1);
        bg.fillRect(x, y, tabW, 3);
      }
      if (i < groups.length - 1) {
        bg.lineStyle(1, 0x6a3208, 1);
        bg.lineBetween(x + tabW, y, x + tabW, y + MENU_TAB_H);
      }
      const label = this.add.text(x + tabW / 2, y + MENU_TAB_H / 2, groups[i].label, {
        fontFamily: 'Noto Serif KR, serif', fontSize: '15px',
        color: active ? '#f7d05b' : '#e8dcc4', fontStyle: 'bold'
      }).setOrigin(0.5).setDepth(DEPTH + 2);
      const hit = this.add.zone(x, y, tabW, MENU_TAB_H)
        .setOrigin(0, 0).setInteractive({ useHandCursor: true });
      hit.on('pointerdown', () => this._selectTab(i));
      this._menuElements.tabs.push({ bg, label, hit });
    }
  }

  _selectTab(idx) {
    if (this._selectedTab === idx) return;
    this._selectedTab = idx;
    this._destroyTabs();
    this._destroyTabContent();
    this._drawTabs();
    this._drawTabContent();
  }

  _drawTabContent() {
    const DEPTH = 400;
    const m = this._menuElements;
    const group = this._toolGroups[this._selectedTab];
    if (!group) return;
    const contentY = MENU_STRIP_Y + MENU_TAB_H;

    // 좌측 3×2 아이콘 그리드
    const gridX0 = 8, gridY0 = contentY + 6;
    const slotW = 62, slotH = 50, colGap = 4, rowGap = 4;
    const cols = 3;
    group.tools.forEach((tool, i) => {
      const c = i % cols, r = Math.floor(i / cols);
      const x = gridX0 + c * (slotW + colGap);
      const y = gridY0 + r * (slotH + rowGap);
      const bg = this.add.graphics().setDepth(DEPTH + 1);
      const iconImg = this.add.image(x + slotW / 2, y + 20, tool.icon)
        .setDisplaySize(32, 32).setDepth(DEPTH + 2);
      const nameLabel = this.add.text(x + slotW / 2, y + slotH - 10, tool.label, {
        fontFamily: 'Noto Serif KR, serif', fontSize: '10px', color: '#e8dcc4',
        stroke: '#141414', strokeThickness: 2, fontStyle: 'bold'
      }).setOrigin(0.5, 0.5).setDepth(DEPTH + 3);
      let costLabel = null;
      if (!tool.special && tool.cost > 0) {
        costLabel = this.add.text(x + slotW - 3, y + 3, `${tool.cost}`, {
          fontFamily: 'Noto Serif KR, serif', fontSize: '10px',
          color: '#f7d05b', fontStyle: 'bold',
          stroke: '#1a0f06', strokeThickness: 2
        }).setOrigin(1, 0).setDepth(DEPTH + 3);
      }
      const hit = this.add.zone(x + slotW / 2, y + slotH / 2, slotW, slotH)
        .setInteractive({ useHandCursor: true });
      hit.on('pointerdown', () => this._selectTool(tool.key));
      m.itemSlots.push({
        tool, bg, iconImg, nameLabel, costBg: null, costLabel, hit,
        x, y, w: slotW, h: slotH
      });
    });

    // 우측 상세 패널
    const detailX0 = 214, detailY0 = contentY + 6;
    const detailW = GAME_WIDTH - detailX0 - 8;
    const detailH = MENU_STRIP_H - MENU_TAB_H - 12;
    const dbg = this.add.graphics().setDepth(DEPTH + 1);
    dbg.fillStyle(0x1a0f06, 0.55).fillRoundedRect(detailX0, detailY0, detailW, detailH, 6);
    dbg.lineStyle(1, 0x6a3208, 1).strokeRoundedRect(detailX0, detailY0, detailW, detailH, 6);

    const d = this._buildDetail();
    const iconImg = this.add.image(detailX0 + 34, detailY0 + 38, d.icon || 'tex_tool_select')
      .setDisplaySize(48, 48).setDepth(DEPTH + 2)
      .setVisible(!!d.icon);
    const titleLabel = this.add.text(detailX0 + 66, detailY0 + 8, d.title, {
      fontFamily: 'Noto Serif KR, serif', fontSize: '15px', color: '#f7d05b', fontStyle: 'bold'
    }).setOrigin(0, 0).setDepth(DEPTH + 2);
    const costLabel = this.add.text(detailX0 + 66, detailY0 + 28, d.costText, {
      fontFamily: 'Noto Serif KR, serif', fontSize: '12px', color: d.costColor
    }).setOrigin(0, 0).setDepth(DEPTH + 2);
    // 아이콘(좌측 상단 48×48, x=10~58 / y=14~62)과 겹치지 않도록 설명은 아이콘 우측으로 래핑.
    const descLabel = this.add.text(detailX0 + 66, detailY0 + 48, d.desc, {
      fontFamily: 'Noto Serif KR, serif', fontSize: '11px', color: '#e8dcc4',
      wordWrap: { width: detailW - 78 }
    }).setOrigin(0, 0).setDepth(DEPTH + 2);
    m.detail = { bg: dbg, iconImg, titleLabel, costLabel, descLabel };

    this._redrawToolbar();
  }

  // 현재 선택 도구 기준 상세 패널 데이터. 선택 없으면 힌트.
  _buildDetail() {
    const key = this._selectedTool;
    if (!key) {
      return {
        title: '선택된 도구 없음', costText: '카테고리에서 도구를 고르세요.',
        costColor: '#a08060',
        desc: '아이콘 클릭 → 도구 선택 후 그리드 타일을 클릭해 배치합니다.',
        icon: null
      };
    }
    if (key === 'select') {
      return {
        title: '선택', costText: '-', costColor: '#a08060',
        desc: '치료방 클릭 시 직원을 투입하거나 건물 정보를 볼 수 있습니다.',
        icon: 'tex_tool_select'
      };
    }
    if (key === 'maru') {
      return {
        title: '마루', costText: `설치비 ${BALANCE.costs.maru} 전`,
        costColor: (this.gold || 0) >= BALANCE.costs.maru ? '#f7d05b' : '#c06060',
        desc: '환자가 걸어다닐 길. 건물은 마루로 대문과 연결돼야 합니다.',
        icon: 'tex_tile_maru'
      };
    }
    const b = getBuildingByKey(key);
    if (!b) return { title: key, costText: '-', costColor: '#a08060', desc: '', icon: null };
    const aff = (this.gold || 0) >= b.cost;
    const feeText = b.fee > 0 ? `   이용료 ${b.fee} 전` : '';
    const costText = b.cost > 0 ? `설치비 ${b.cost} 전${feeText}` : (b.fee > 0 ? `이용료 ${b.fee} 전` : '무료');
    const descs = {
      moxa: '기본 치료방. 뜸 치료, 만족도 +1.',
      acu:  '침 치료방. 만족도 +2, 상위 계층 선호.',
      herb: '약 치료방. 만족도 +3. 우물 근접 시 약값 보너스.',
      haewoso: '편의시설. 머무는 시간 +5초.',
      gukbap:  '편의시설. 식사 만족도 +2, 체류 +5초.',
      well:    '편의시설. 만족도 +1, 약방 근접 보너스.',
      pine:    `장식. 4방 인접 건물에 만족도 +${BALANCE.pineBonusPerRoom} (중첩 X). 무료 ${BALANCE.pineFreeMax}개까지.`
    };
    return {
      title: b.label, costText, costColor: aff ? '#f7d05b' : '#c06060',
      desc: descs[b.key] || '', icon: b.texture
    };
  }

  _refreshDetail() {
    const m = this._menuElements;
    if (!m || !m.detail) return;
    const d = this._buildDetail();
    m.detail.titleLabel.setText(d.title);
    m.detail.costLabel.setText(d.costText);
    m.detail.costLabel.setColor(d.costColor);
    m.detail.descLabel.setText(d.desc);
    if (m.detail.iconImg) {
      if (d.icon) m.detail.iconImg.setTexture(d.icon).setVisible(true);
      else m.detail.iconImg.setVisible(false);
    }
  }

  _redrawToolbar() {
    const m = this._menuElements;
    if (!m) return;
    for (const b of m.itemSlots) {
      b.bg.clear();
      const selected = this._selectedTool === b.tool.key;
      b.bg.fillStyle(selected ? 0x8b5a2a : 0x3a2414, 1);
      b.bg.fillRoundedRect(b.x, b.y, b.w, b.h, 5);
      b.bg.lineStyle(selected ? 3 : 2, selected ? 0xf7d05b : 0x6a3208, 1);
      b.bg.strokeRoundedRect(b.x, b.y, b.w, b.h, 5);
      if (b.costLabel && b.tool.cost > 0) {
        const affordable = (this.gold || 0) >= b.tool.cost;
        b.costLabel.setColor(affordable ? '#f7d05b' : '#8a7a5e');
      }
    }
    this._refreshDetail();
  }

  _destroyTabs() {
    const m = this._menuElements;
    if (!m) return;
    for (const t of m.tabs) {
      if (t.bg) t.bg.destroy();
      if (t.label) t.label.destroy();
      if (t.hit) t.hit.destroy();
    }
    m.tabs.length = 0;
  }

  _destroyTabContent() {
    const m = this._menuElements;
    if (!m) return;
    for (const s of m.itemSlots) {
      if (s.bg) s.bg.destroy();
      if (s.iconImg) s.iconImg.destroy();
      if (s.nameLabel) s.nameLabel.destroy();
      if (s.costLabel) s.costLabel.destroy();
      if (s.hit) s.hit.destroy();
    }
    m.itemSlots.length = 0;
    if (m.detail) {
      if (m.detail.bg) m.detail.bg.destroy();
      if (m.detail.iconImg) m.detail.iconImg.destroy();
      if (m.detail.titleLabel) m.detail.titleLabel.destroy();
      if (m.detail.costLabel) m.detail.costLabel.destroy();
      if (m.detail.descLabel) m.detail.descLabel.destroy();
      m.detail = null;
    }
  }

  _destroyToolbar() {
    this._destroyTabs();
    this._destroyTabContent();
    if (this._menuElements) {
      if (this._menuElements.bgPanel) this._menuElements.bgPanel.destroy();
      this._menuElements = null;
    }
    this._toolButtons = null;
    this._toolGroups = null;
  }

  // 해금 이벤트 → 툴바 재구성 + 두루마기 팝업(Phase 6).
  // 두루마기: 중앙 반투명 패널 + 양옆 나무 롤러 + 해금 문구.
  // BUG-4 대응: 동시 해금 시 큐로 순차 표시.
  _onUnlocked({ key, building }) {
    this._destroyToolbar();
    this._createToolbar();
    const label = building ? building.label : key;
    this._enqueueScrollPopup(label, building);
  }

  _enqueueScrollPopup(label, building) {
    if (!this._scrollQueue) this._scrollQueue = [];
    this._scrollQueue.push({ label, building });
    if (!this._scrollActive) this._showScrollPopup();
  }

  // BUG-3 대응: 월간 결산 등 강제 정리 진입점.
  _forceCloseScrollPopup() {
    if (this._scrollActive) {
      if (this._scrollActive.timer) this._scrollActive.timer.remove(false);
      if (this._scrollActive.tween) this._scrollActive.tween.stop();
      for (const p of this._scrollActive.parts) if (p && p.destroy) p.destroy();
      this._scrollActive = null;
    }
    if (this._scrollQueue) this._scrollQueue.length = 0;
  }

  _showScrollPopup() {
    if (!this._scrollQueue || this._scrollQueue.length === 0) {
      this._scrollActive = null;
      return;
    }
    const { label, building } = this._scrollQueue.shift();
    // K3 대응: 해금 SFX — 카이로 "뿅" 리듬.
    audioSystem.playSFX?.('unlock');

    const cx = GAME_WIDTH / 2;
    const cy = HUD_TOP_H + (GRID_PIXEL_H / 2) - 40;
    const w = 360, h = 120;
    const x0 = cx - w / 2, y0 = cy - h / 2;
    const depth = 80;
    const g = this.add.graphics().setDepth(depth);
    g.fillStyle(0xf3e3b6, 0.96);
    g.fillRoundedRect(x0, y0, w, h, 6);
    g.lineStyle(2, 0x6b3d1a, 1);
    g.strokeRoundedRect(x0, y0, w, h, 6);
    g.fillStyle(0x5a3314, 1);
    g.fillRoundedRect(x0 - 12, y0 - 6, 14, h + 12, 4);
    g.fillRoundedRect(x0 + w - 2, y0 - 6, 14, h + 12, 4);
    g.fillStyle(0xd9a84a, 1);
    g.fillCircle(x0 - 5, y0, 3);
    g.fillCircle(x0 - 5, y0 + h, 3);
    g.fillCircle(x0 + w + 5, y0, 3);
    g.fillCircle(x0 + w + 5, y0 + h, 3);

    const title = this.add.text(cx, y0 + 22, '✦ 해금 ✦', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '16px', color: '#6b3d1a',
      fontStyle: 'bold'
    }).setOrigin(0.5).setDepth(depth + 1);
    const body = this.add.text(cx, y0 + 58, `${label} 사용 가능!`, {
      fontFamily: 'Noto Serif KR, serif', fontSize: '22px', color: '#2a1808',
      fontStyle: 'bold'
    }).setOrigin(0.5).setDepth(depth + 1);
    const hint = this.add.text(cx, y0 + 92, building?.desc ? building.desc : '하단 메뉴에서 선택하세요.', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '12px', color: '#5a3314',
      wordWrap: { width: w - 32 }
    }).setOrigin(0.5).setDepth(depth + 1);

    const parts = [g, title, body, hint];
    for (const p of parts) { p.setAlpha(0); p.y -= 10; }
    const inTween = this.tweens.add({
      targets: parts, alpha: 1, y: '+=10', duration: 260, ease: 'Back.out'
    });
    // active 핸들 저장 — 결산 진입 시 _forceCloseScrollPopup 에서 참조.
    this._scrollActive = { parts, timer: null, tween: inTween };
    this._scrollActive.timer = this.time.delayedCall(2400, () => {
      if (!this._scrollActive) return;
      const outTween = this.tweens.add({
        targets: parts, alpha: 0, y: '-=8', duration: 260, ease: 'Sine.in',
        onComplete: () => {
          for (const p of parts) if (p && p.destroy) p.destroy();
          this._scrollActive = null;
          // 큐에 대기 중이면 다음 해금 팝업 연쇄.
          this._showScrollPopup();
        }
      });
      this._scrollActive.tween = outTween;
      this._scrollActive.timer = null;
    });
  }

  _selectTool(key) {
    if (this._selectedTool === key) return;
    // 패널 오픈 중 도구 전환 시 auto-close — H-5 race 방지.
    if (this.staffPanel && this.staffPanel.isOpened()) this.staffPanel.close();
    this._selectedTool = key;
    // Phase 7-B3: 도구 전환 시 이전 도구 기준으로 그려진 인접 미리보기 즉시 정리.
    this._clearAdjPreview();
    this._redrawToolbar();
    let label;
    if (key === 'select') label = '선택';
    else if (key === 'maru') label = '마루';
    else { const b = getBuildingByKey(key); label = b ? b.label : key; }
    this._toast(`도구: ${label} 선택`);
    // K 보정: select 는 배치/건설 행동이 아니므로 튜토리얼 tool step 트리거 금지.
    if (key !== 'select') this._advanceTutorial('tool');
  }

  _updateHud() {
    // 15초=1주, 1분=1달, 12분=1년 → 연/월/주 계산
    const weeks = Math.floor(this.elapsedMs / BALANCE.weekMs);
    const month = Math.floor(weeks / 4) + 1;              // 대략: 1달 = 4주
    const weekOfMonth = (weeks % 4) + 1;
    const year = Math.floor((month - 1) / 12) + 1;
    const monthInYear = ((month - 1) % 12) + 1;
    this.hudTime.setText(`${year}년 ${monthInYear}월 ${weekOfMonth}주`);
    this.hudGold.setText(`${this.gold} 전`);
    this.hudMyeongui.setText(`명의 ${this.myeongui.toFixed(1)}`);
    // Phase 4-C 티켓 카운터 — 한도 임박(>=cap-3) 노란 강조.
    if (this.hudTickets && this.tickets) {
      const c = this.tickets.counts();
      const cap = BALANCE.ticketsToSpawn;
      const nearCap = c.treat >= cap - 3 || c.amenity >= cap - 3;
      this.hudTickets.setText(`치료 ${c.treat}/${cap}  편의 ${c.amenity}/${cap}`);
      this.hudTickets.setColor(nearCap ? '#f7d05b' : '#e8dcc4');
    }
    // 가격 badge 색(살 수 있음/부족) 갱신 — 골드 변동 시에만.
    if (this._lastRenderedGold !== this.gold) {
      this._lastRenderedGold = this.gold;
      this._redrawToolbar();
    }
  }

  // ─── 상호작용 ────────────────────────────────────
  _onTileClicked(tile, button) {
    // 패널 오픈 중엔 그리드 입력 무시 (staffPanel 의 overlay zone 이 선제 차단하지만 방어용).
    if (this.staffPanel && this.staffPanel.isOpened()) return;

    // UX 규칙: 우클릭 = 철거 전용. 좌클릭 = 설치/선택 전용. 토글 오삭제 방지.
    if (button === 'right') {
      this._tryDemolish(tile);
      return;
    }

    if (tile.type === TILE_GATE) {
      // B 보정: select 도구로 대문 클릭 시 "철거 불가" 오염 방지 — 조용히 무시.
      if (this._selectedTool === 'select') return;
      this._toast('대문은 철거할 수 없습니다.');
      return;
    }
    // B 보정: select 분기는 GATE 다음, maru/건물 이전. 치료방 타일이면 패널 오픈.
    if (this._selectedTool === 'select') {
      const b = getBuildingByTileType(tile.type);
      if (b && b.category === 'treat') {
        this.staffPanel.open(b, tile.col, tile.row);
        this._advanceTutorial('panel');
      } else {
        this._toast('치료방을 클릭하세요');
      }
      return;
    }
    if (this._selectedTool === 'maru') {
      this._tryPlaceMaru(tile);
      return;
    }
    const b = getBuildingByKey(this._selectedTool);
    if (!b) return;
    this._tryPlaceBuilding(tile, b);
  }

  // 우클릭 전용 철거 — 선택 도구와 무관하게 현재 타일에 있는 것을 철거.
  _tryDemolish(tile) {
    if (tile.type === TILE_GATE) {
      this._toast('대문은 철거할 수 없습니다.');
      return;
    }
    if (tile.type === TILE_EMPTY) {
      // 빈 타일 우클릭은 조용히 무시 — 토스트 스팸 방지.
      return;
    }
    if (tile.type === TILE_MARU) {
      this.grid.setType(tile.col, tile.row, TILE_EMPTY);
      const refund = Math.floor(BALANCE.costs.maru / 2);
      this._applyGold(+refund);
      this._floatGold(tile, `+${refund}전`, '#f7d05b');
      return;
    }
    const b = getBuildingByTileType(tile.type);
    if (!b) return;
    this.grid.setType(tile.col, tile.row, TILE_EMPTY);
    const refund = Math.floor((b.cost || 0) / 2);
    if (refund > 0) {
      this._applyGold(+refund);
      this._floatGold(tile, `+${refund}전`, '#f7d05b');
    } else {
      this._floatGold(tile, '철거', '#a08060');
    }
  }

  _tryPlaceMaru(tile) {
    if (tile.type === TILE_MARU) {
      this._toast('이미 마루입니다 — 철거는 우클릭');
      return;
    }
    if (tile.type !== TILE_EMPTY) {
      this._toast('마루는 빈 타일 위에만 놓을 수 있습니다.');
      return;
    }
    if (this.gold < BALANCE.costs.maru) {
      this._toast(`마루 구매 실패: 돈 부족 (${BALANCE.costs.maru}전 필요)`);
      return;
    }
    this.grid.setType(tile.col, tile.row, TILE_MARU);
    this._applyGold(-BALANCE.costs.maru);
    this._floatGold(tile, `-${BALANCE.costs.maru}전`, '#e84a4a');
    this._advanceTutorial('maru');
    // C-4 보정: 치료방 먼저 → 마루 나중 배치 시 dead-lock 복구.
    this._retryTutorialSpawnNearMaru(tile.col, tile.row);
  }

  _tryPlaceBuilding(tile, building) {
    if (tile.type === building.tileType) {
      this._toast(`이미 ${building.label}입니다 — 철거는 우클릭`);
      return;
    }
    if (tile.type !== TILE_EMPTY) {
      this._toast(`${building.label}은(는) 빈 타일 위에만 지을 수 있습니다.`);
      return;
    }
    if (this.gold < building.cost) {
      this._toast(`${building.label} 구매 실패: 돈 부족 (${building.cost}전 필요)`);
      return;
    }
    // Phase 6: 소나무 무료 3개 한도. cost=0 무한 배치 차단 — 추가 가격 미정이라 일단 cap.
    if (building.key === 'pine') {
      const placed = this.grid.listByType(building.tileType).length;
      if (placed >= (BALANCE.pineFreeMax || 3)) {
        this._toast(`소나무는 무료 ${BALANCE.pineFreeMax || 3}개 까지 — 추가 구매 미정`);
        return;
      }
    }
    this.grid.setType(tile.col, tile.row, building.tileType);
    this._applyGold(-building.cost);
    this._floatGold(tile, `-${building.cost}전`, '#e84a4a');
    // Phase 6: 소나무 배치 시 4방 인접 치료방에 하트 이펙트(0.5s) — 보너스 ±1 가시화.
    if (building.key === 'pine') this._spawnPineHearts(tile.col, tile.row);
    // 건물 키가 moxa 면 튜토리얼 3단계 매칭. 향후 다른 건물도 'moxa' 스텝을 충족하도록 유지.
    if (building.key === 'moxa') this._advanceTutorial('moxa');
    // Phase 3-B 첫경험 보호: 치료방 최초 배치 + 직원 0명이면 튜토리얼 무수리 자동 합류.
    // 해금 체인 dead-lock(환자 복귀 → patient_served 미emit) 방지.
    if (building.category === 'treat' && this.staff && this.staff.count() === 0) {
      this._autoSpawnTutorialMusuri(tile.col, tile.row);
    }
    // C 보정: 첫 치료방 배치 시 "선택 도구" 사용법 1회 플로팅 가이드.
    if (building.category === 'treat' && !this._staffPanelHintShown) {
      this._staffPanelHintShown = true;
      this.time.delayedCall(500, () => {
        FloatingText.spawn(this, GAME_WIDTH / 2, HUD_TOP_H + 160,
          '우측 [선택] 도구 → 치료방 클릭으로 직원 투입',
          { color: '#d08020', size: 15, duration: 3200, rise: 0 });
      });
    }
  }

  _floatGold(tile, text, color) {
    const { x, y } = this.grid.pixelFromTile(tile.col, tile.row);
    FloatingText.spawn(this, x, y - 8, text, { color, size: 16 });
  }

  // Phase 6: 소나무 배치 시 4방 인접 치료방에 +1 보너스 가시화.
  // K1 수정: 도트 하트 텍스처(tex_pine_heart, 24×24 4색)로 교체.
  //   Medeiros P1/P2: 실루엣 가독성 + 한정 팔레트. 폰트 의존 제거.
  _spawnPineHearts(col, row) {
    const dirs = [[0, -1], [0, 1], [-1, 0], [1, 0]];
    const hasTex = this.textures.exists('tex_pine_heart');
    const candidates = [];
    for (const [dc, dr] of dirs) {
      const t = this.grid.get(col + dc, row + dr);
      if (!t) continue;
      const b = getBuildingByTileType(t.type);
      if (!b || b.category !== 'treat') continue;
      candidates.push(t);
    }
    if (candidates.length === 0) {
      // 인접 치료방 0 — 하트 없음. 사용자 혼란 방지용 안내 토스트.
      this._toast('소나무 옆에 치료방이 있으면 보너스 하트가 나타납니다.');
      return 0;
    }
    for (const t of candidates) {
      const { x, y } = this.grid.pixelFromTile(t.col, t.row);
      // pop-in, rise, fade-out 을 sequential tween 으로 — chain 보다 호환성 우수.
      const heart = hasTex
        ? this.add.image(x, y, 'tex_pine_heart')
        : this.add.text(x, y, '♥', {
            fontFamily: 'sans-serif', fontSize: '28px', color: '#ff4060',
            stroke: '#ffffff', strokeThickness: 3
          });
      heart.setOrigin(0.5).setDepth(46).setAlpha(0).setScale(0.4);
      // 1단계: pop-in.
      this.tweens.add({
        targets: heart, alpha: 1, scale: 2.2,
        duration: 180, ease: 'Back.out',
        onComplete: () => {
          // 2단계: rise.
          this.tweens.add({
            targets: heart, y: y - 48, scale: 1.8,
            duration: 700, ease: 'Sine.out',
            onComplete: () => {
              // 3단계: fade-out.
              this.tweens.add({
                targets: heart, alpha: 0,
                duration: 350, ease: 'Sine.in',
                onComplete: () => heart.destroy()
              });
            }
          });
        }
      });
    }
    return candidates.length;
  }

  // Phase 6: 직원 고용 직후 인접 배정 가능 방 0개 감지.
  // 시나리오 — chimgu 가 모든 moxa 방을 덮어버린 뒤 musuri 를 고용하면
  // 새 musuri 의 radius 1 내 unsurface 방이 없어 놀게 됨. 토스트로 즉시 알림.
  _computeStaffAdjacency(staff) {
    const covers = staff.spec && staff.spec.covers;
    if (!covers) return { adjacent: 0, taken: 0, covers: null };
    const dirs = [[0, -1], [0, 1], [-1, 0], [1, 0]];
    let adjacent = 0, taken = 0;
    for (const [dc, dr] of dirs) {
      const t = this.grid.get(staff.col + dc, staff.row + dr);
      if (!t) continue;
      const b = getBuildingByTileType(t.type);
      if (!b || b.key !== covers) continue;
      adjacent += 1;
      if (this.staff.isRoomCovered(t.col, t.row)) taken += 1;
    }
    return { adjacent, taken, covers };
  }

  _warnIfNoAssignable({ staff }) {
    if (!staff || !staff.spec) return;
    const { adjacent, taken, covers } = this._computeStaffAdjacency(staff);
    if (adjacent === 0) {
      this._toast(`⚠ 인접 ${covers} 방이 없습니다 — 치료방 옆 마루에 배치하세요.`);
      this._isolatedStaff?.add(staff);
    } else if (taken >= adjacent) {
      this._toast(`⚠ 인접 ${covers} 방이 이미 다른 직원에게 배정됨.`);
      this._isolatedStaff?.add(staff);
    }
  }

  // S1/W2 대응: tile_changed 시 전체 staff 재검사. 이전에 배정 가능했던 직원이
  // 방 철거로 고립되면 1회 토스트. _isolatedStaff Set 로 중복 경고 방지
  // — 방이 돌아와 assignable 복구되면 Set 에서 제거 → 다시 고립 시 재경고.
  _recheckStaffIsolation() {
    if (!this.staff || !this.staff.staff) return;
    if (!this._isolatedStaff) this._isolatedStaff = new Set();
    const STAFF_LABEL = { musuri: '무수리', chimgu: '침구', uinyeo: '의녀', uigwan: '의관' };
    for (const s of this.staff.staff) {
      const { adjacent, taken } = this._computeStaffAdjacency(s);
      const isolated = adjacent === 0 || taken >= adjacent;
      const was = this._isolatedStaff.has(s);
      if (isolated && !was) {
        const label = STAFF_LABEL[s.type] || s.type;
        this._toast(`⚠ ${label} 배정 가능 방이 사라졌습니다.`);
        this._isolatedStaff.add(s);
      } else if (!isolated && was) {
        this._isolatedStaff.delete(s);
      }
    }
  }

  // 치료방 상태 뱃지 — 미배정(0/1 점멸·클릭 진입)·약방+우물(🌊) 표시.
  // tile_changed / staff 변경 시마다 전부 다시 그린다 (타일 10×10 이므로 비용 무시 가능).
  _refreshBadges() {
    if (!this._badgeSprites) this._badgeSprites = [];
    // C 보정: destroy 전에 tween.stop() — 고아 tween 누수 방지.
    for (const s of this._badgeSprites) {
      if (s && s._tween) s._tween.stop();
      if (s && s.destroy) s.destroy();
    }
    this._badgeSprites.length = 0;
    if (!this.grid || !this.staff || !this.patients) return;

    for (let r = 0; r < this.grid.rows; r++) {
      for (let c = 0; c < this.grid.cols; c++) {
        const tile = this.grid.get(c, r);
        if (!tile) continue;
        const b = getBuildingByTileType(tile.type);
        if (!b) continue;

        const { x, y } = this.grid.pixelFromTile(c, r);

        // 치료방 미배정 경고 뱃지 (우상단) — 점멸 tween + N/M 카운터 + 클릭 진입.
        if (b.category === 'treat' && !this.staff.isRoomCovered(c, r)) {
          const sp = this.add.image(x + 22, y - 22, 'tex_badge_no_staff').setDepth(25);
          const tw = this.tweens.add({
            targets: sp, alpha: 0.5, duration: 700, yoyo: true, repeat: -1, ease: 'Sine.easeInOut'
          });
          sp._tween = tw;
          // G 보정: 0/1 카운터 텍스트 — 부분배정 확장 대비(현 치료방은 필요 1).
          const label = this.add.text(x + 22, y - 22, '0/1', {
            fontFamily: 'monospace', fontSize: '9px',
            color: '#ffffff', fontStyle: 'bold',
            stroke: '#c02020', strokeThickness: 2
          }).setOrigin(0.5).setDepth(26);
          label._tween = tw; // 같은 tween 을 참조만 (별도 stop 대상 아님)
          // F 보정: 뱃지 클릭 시 StaffPanel 오픈 — select 툴 경유 없이 한번에 진입.
          const hit = this.add.zone(x + 22, y - 22, 22, 22)
            .setInteractive({ useHandCursor: true }).setDepth(27);
          hit.on('pointerdown', () => {
            if (this.staffPanel) {
              this.staffPanel.open(b, c, r);
              this._advanceTutorial('panel');
            }
          });
          this._badgeSprites.push(sp, label, hit);
        }
        // 약방 + 우물 활성 뱃지 (좌상단).
        if (b.key === 'herb' && this.patients._isWellNearby?.(c, r,
              BALANCE.wellBonus.radius, BALANCE.wellBonus.shape)) {
          const sp = this.add.image(x - 22, y - 22, 'tex_badge_well').setDepth(25);
          this._badgeSprites.push(sp);
        }
      }
    }
  }

  _destroyBadges() {
    if (!this._badgeSprites) return;
    for (const s of this._badgeSprites) {
      if (s && s._tween) s._tween.stop();
      if (s && s.destroy) s.destroy();
    }
    this._badgeSprites.length = 0;
  }

  _onTileHover(tile) {
    if (!tile) {
      this.hoverCursor.setVisible(false);
      this._clearAdjPreview();
      return;
    }
    const { x, y } = this.grid.pixelFromTile(tile.col, tile.row);
    this.hoverCursor.setPosition(x, y).setVisible(true);
    this._renderAdjPreview(tile, x, y);
  }

  // Phase 7-B3: 배치 모드 인접 보너스/페널티 미리보기 — 영향 받는 타일에 색 후광 + 요약 라벨.
  //   - 치료방 도구: 주변 소나무(+점수) / 우물(+점수 또는 +전) / 같은 치료방(-전 혼잡) 표시.
  //   - 우물 도구:   주변 치료방에 줄 보너스를 청색 후광으로.
  //   - 소나무 도구: 주변 건물에 줄 보너스를 녹색 후광으로.
  //   - 마루·select·기존 점유 타일은 표시 X (의미 없음).
  _renderAdjPreview(tile, hoverX, hoverY) {
    this._clearAdjPreview();
    if (tile.type !== TILE_EMPTY) return;
    const tool = this._selectedTool;
    if (!tool || tool === 'select' || tool === 'maru') return;
    const b = getBuildingByKey(tool);
    if (!b) return;

    if (!this._adjPreviewGfx) {
      this._adjPreviewGfx = this.add.graphics().setDepth(48);
      this._adjPreviewLabels = [];
    }
    const TREAT_TYPES = [TILE_MOXA, TILE_ACU, TILE_HERB];
    const halos = [];
    const summary = [];

    if (b.category === 'treat') {
      // 소나무 인접 (4방, stack X — 첫 1개만)
      for (const [dc, dr] of [[1,0],[-1,0],[0,1],[0,-1]]) {
        const nt = this.grid.get(tile.col + dc, tile.row + dr);
        if (nt && nt.type === TILE_PINE) {
          halos.push({ col: nt.col, row: nt.row, color: 0x4ac06a });
          summary.push(`+${BALANCE.pineBonusPerRoom || 1} 점수 (소나무)`);
          break;
        }
      }
      // 우물 인접 (Chebyshev r=1)
      const cfg = BALANCE.wellBonus || { radius: 1 };
      let foundWell = false;
      for (let dr = -cfg.radius; dr <= cfg.radius && !foundWell; dr++) {
        for (let dc = -cfg.radius; dc <= cfg.radius && !foundWell; dc++) {
          if (dc === 0 && dr === 0) continue;
          const nt = this.grid.get(tile.col + dc, tile.row + dr);
          if (nt && nt.type === TILE_WELL) {
            halos.push({ col: nt.col, row: nt.row, color: 0x3ca0e0 });
            if (b.key === 'herb' && cfg.herbFee > 0) summary.push(`+${cfg.herbFee} 전 (우물)`);
            else if (b.key === 'acu' && cfg.acuScore > 0) summary.push(`+${cfg.acuScore} 점수 (우물)`);
            else if (b.key === 'moxa' && cfg.moxaScore > 0) summary.push(`+${cfg.moxaScore} 점수 (우물)`);
            foundWell = true;
          }
        }
      }
      // 같은 치료방 4방 인접 — 혼잡 페널티
      let cluster = 0;
      for (const [dc, dr] of [[1,0],[-1,0],[0,1],[0,-1]]) {
        const nt = this.grid.get(tile.col + dc, tile.row + dr);
        if (nt && nt.type === b.tileType) {
          halos.push({ col: nt.col, row: nt.row, color: 0xc04040 });
          cluster++;
        }
      }
      if (cluster > 0) {
        const per = BALANCE.clusterPenaltyPerRoom || 0;
        if (per > 0) summary.push(`-${cluster * per} 전 (혼잡)`);
      }
    } else if (b.key === 'pine') {
      for (const [dc, dr] of [[1,0],[-1,0],[0,1],[0,-1]]) {
        const nt = this.grid.get(tile.col + dc, tile.row + dr);
        if (nt && TREAT_TYPES.includes(nt.type)) {
          halos.push({ col: nt.col, row: nt.row, color: 0x4ac06a });
        }
      }
      if (halos.length > 0) {
        summary.push(`치료방 ${halos.length}곳 +${BALANCE.pineBonusPerRoom || 1} 점수`);
      }
    } else if (b.key === 'well') {
      const cfg = BALANCE.wellBonus || { radius: 1 };
      for (let dr = -cfg.radius; dr <= cfg.radius; dr++) {
        for (let dc = -cfg.radius; dc <= cfg.radius; dc++) {
          if (dc === 0 && dr === 0) continue;
          const nt = this.grid.get(tile.col + dc, tile.row + dr);
          if (nt && TREAT_TYPES.includes(nt.type)) {
            halos.push({ col: nt.col, row: nt.row, color: 0x3ca0e0 });
          }
        }
      }
      if (halos.length > 0) summary.push(`치료방 ${halos.length}곳에 보너스`);
    }

    // 후광 렌더 — 64×64 타일 가운데 기준.
    const half = TILE_SIZE / 2;
    for (const h of halos) {
      const p = this.grid.pixelFromTile(h.col, h.row);
      this._adjPreviewGfx.fillStyle(h.color, 0.28);
      this._adjPreviewGfx.fillRect(p.x - half, p.y - half, TILE_SIZE, TILE_SIZE);
      this._adjPreviewGfx.lineStyle(2, h.color, 0.9);
      this._adjPreviewGfx.strokeRect(p.x - half, p.y - half, TILE_SIZE, TILE_SIZE);
    }

    if (summary.length > 0) {
      const label = this.add.text(hoverX, hoverY - half - 4, summary.join(' · '), {
        fontFamily: 'Noto Serif KR, serif', fontSize: '11px',
        color: '#fdf0d0', backgroundColor: '#402010',
        padding: { x: 6, y: 3 }
      }).setOrigin(0.5, 1).setDepth(49);
      this._adjPreviewLabels.push(label);
    }
  }

  _clearAdjPreview() {
    if (this._adjPreviewGfx) this._adjPreviewGfx.clear();
    if (this._adjPreviewLabels) {
      for (const l of this._adjPreviewLabels) l.destroy();
      this._adjPreviewLabels.length = 0;
    }
  }

  // ─── Phase 1-C 테스트 ────────────────────────────
  _spawnTestWalker() {
    const spawn = this.grid.get(SPAWN_COL, SPAWN_ROW);
    if (!spawn || spawn.type !== TILE_MARU) {
      this._toast('스폰 포인트(주황 원)에 마루를 먼저 놓으세요.');
      return;
    }

    // 대문에서 가장 먼 마루 타일을 목적지로
    const gateToSpawnPath = this.path.findPath(GATE_COL, GATE_ROW, SPAWN_COL, SPAWN_ROW);
    if (!gateToSpawnPath) {
      this._toast('대문→스폰 경로가 없습니다(내부 오류).');
      return;
    }

    const marus = this.grid.listByType(TILE_MARU);
    if (marus.length === 0) {
      this._toast('마루가 없습니다.');
      return;
    }

    // 대문에서 도달 가능한 마루 중 가장 먼 것 선택 (gate 자체 start 기반)
    let farthest = null;
    let farthestLen = -1;
    for (const m of marus) {
      const p = this.path.findPath(GATE_COL, GATE_ROW, m.col, m.row);
      if (p && p.length > farthestLen) { farthest = m; farthestLen = p.length; }
    }
    if (!farthest) {
      this._toast('대문에서 도달 가능한 마루가 없습니다.');
      return;
    }

    // 대문→farthest 직접 경로 (gate→spawn 세그먼트 누락 방지)
    const fullPath = this.path.findPath(GATE_COL, GATE_ROW, farthest.col, farthest.row);
    if (!fullPath) {
      this._toast('경로를 찾지 못했습니다.');
      return;
    }
    const start = this.grid.pixelFromTile(GATE_COL, GATE_ROW);
    const walker = this.add.image(start.x, start.y, 'tex_walker').setDepth(40);
    this.testWalkerCount += 1;
    this._toast(`테스트 환자 #${this.testWalkerCount} 이동 — 경로 ${fullPath.length}칸`);
    this._walkAlong(walker, fullPath, 0);
    this._advanceTutorial('walker');
  }

  _walkAlong(sprite, path, idx) {
    if (idx >= path.length) {
      // 끝나면 사라지는 연출
      this.tweens.add({
        targets: sprite, alpha: 0, duration: 400,
        onComplete: () => sprite.destroy()
      });
      return;
    }
    const { col, row } = path[idx];
    const { x, y } = this.grid.pixelFromTile(col, row);
    this.tweens.add({
      targets: sprite, x, y, duration: 220, ease: 'Linear',
      onComplete: () => this._walkAlong(sprite, path, idx + 1)
    });
  }

  _clearAllMaru() {
    let cleared = 0;
    const refundEach = Math.floor(BALANCE.costs.maru / 2);
    for (let r = 0; r < this.grid.rows; r++) {
      for (let c = 0; c < this.grid.cols; c++) {
        if (this.grid.tiles[r][c].type === TILE_MARU) {
          this.grid.setType(c, r, TILE_EMPTY);
          this._applyGold(+refundEach);
          cleared++;
        }
      }
    }
    this._toast(`마루 ${cleared}개 철거 — 환급 ${cleared * refundEach}전`);
  }

  // 토스트 큐잉: 메시지 연타(예: 동시 해금 2건) 시 이전 메시지가 덮여 사라지는 문제 해결.
  // 활성 메시지 1.5초 유지 후 다음 큐 항목 표시. 큐 비면 기본 힌트 복귀.
  _toast(msg) {
    if (!this.hudHint || !this.hudHint.scene) return;
    if (!this._toastQueue) this._toastQueue = [];
    this._toastQueue.push(msg);
    if (!this._toastTimer) this._toastTick();
  }

  _toastTick() {
    if (!this.hudHint || !this.hudHint.scene) return;
    const next = this._toastQueue && this._toastQueue.shift();
    if (!next) {
      this._toastTimer = null;
      this.hudHint.setText(this._defaultHintText());
      return;
    }
    this.hudHint.setText(next);
    const dwell = this._toastQueue.length > 0 ? 1500 : 3000;
    this._toastTimer = this.time.delayedCall(dwell, () => {
      this._toastTimer = null;
      this._toastTick();
    });
  }

  // ─── Phase 1-F: 튜토리얼 ────────────────────────────
  // 4-step action-gated. localStorage 플래그로 재세션 재노출 방지.
  _initTutorial() {
    if (this._readTutorialFlag()) { this._tutorial = null; return; }
    this._tutorial = { step: 0, nodes: null };
    this._tutorialSteps = [
      { key: 'tool',   text: '① 우측 툴바에서 도구를 골라 보세요 (마루·뜸방)' },
      { key: 'maru',   text: '② 빈 타일을 클릭해 마루를 놓아 보세요' },
      { key: 'moxa',   text: '③ 뜸방을 대문과 마루로 연결해 보세요' },
      { key: 'walker', text: '④ T 키로 환자를 시험 소환해 보세요' },
      { key: 'panel',  text: '⑤ 치료방의 빨간 0/1 뱃지를 클릭해 직원을 관리해 보세요' }
    ];
    this._showTutorialStep(0);
  }

  _readTutorialFlag() {
    try {
      return typeof localStorage !== 'undefined'
          && localStorage.getItem('kario_v06_tutorial_done') === '1';
    } catch (_) { return false; }
  }

  _writeTutorialFlag() {
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem('kario_v06_tutorial_done', '1');
      }
    } catch (_) { /* privacy mode 등 — 무시 */ }
  }

  _showTutorialStep(idx) {
    if (!this._tutorial) return;
    this._destroyTutorialNodes();
    const spec = this._tutorialSteps[idx];
    if (!spec) { this._finishTutorial(); return; }

    // 주간 배너(y=HUD_TOP_H+28, h=36) 와 겹치지 않도록 +110 으로 하강.
    // 두 배너 사이 clearance 36px 확보.
    const x = GAME_WIDTH / 2;
    const y = HUD_TOP_H + 110;
    const w = 520, h = 56;

    const bg = this.add.graphics().setDepth(495);
    bg.fillStyle(0xfdf0d0, 0.96);
    bg.fillRoundedRect(x - w / 2, y - h / 2, w, h, 10);
    bg.lineStyle(2, 0xd08020, 1);
    bg.strokeRoundedRect(x - w / 2, y - h / 2, w, h, 10);

    const label = this.add.text(x - 20, y, spec.text, {
      fontFamily: 'Noto Serif KR, serif', fontSize: '15px',
      color: '#604010', fontStyle: 'bold'
    }).setOrigin(0.5).setDepth(496);

    // 우측 × 버튼 (건너뛰기)
    const closeX = x + w / 2 - 18;
    const closeY = y;
    const closeLabel = this.add.text(closeX, closeY, '✕', {
      fontFamily: 'monospace', fontSize: '18px', color: '#8b4010', fontStyle: 'bold'
    }).setOrigin(0.5).setDepth(497);
    const closeHit = this.add.zone(closeX, closeY, 24, 24)
      .setOrigin(0.5).setInteractive({ useHandCursor: true }).setDepth(497);
    closeHit.on('pointerdown', () => this._finishTutorial());

    this._tutorial.step = idx;
    this._tutorial.nodes = [bg, label, closeLabel, closeHit];
  }

  _destroyTutorialNodes() {
    if (!this._tutorial || !this._tutorial.nodes) return;
    for (const n of this._tutorial.nodes) { if (n && n.destroy) n.destroy(); }
    this._tutorial.nodes = null;
  }

  // 액션 키 ('tool' | 'maru' | 'moxa' | 'walker') 를 넘겨받아 매칭되는 첫 스텝(현재 이후)로 점프.
  // out-of-order 허용 — 유저가 '마루 놓기' 안내 중 뜸방을 먼저 놓아도 step 을 건너뛰어 따라감.
  _advanceTutorial(actionKey) {
    if (!this._tutorial) return;
    const idx = this._tutorialSteps.findIndex(
      (s, i) => i >= this._tutorial.step && s.key === actionKey
    );
    if (idx < 0) return;
    this._showTutorialStep(idx + 1);
  }

  _finishTutorial() {
    if (!this._tutorial) return;
    this._destroyTutorialNodes();
    // 완료 토스트(HUD hint) + 자동 소멸
    this._toast('튜토리얼 완료! 15초마다 주간 결산이 뜹니다.');
    this._writeTutorialFlag();
    this._tutorial = null;
  }
}
