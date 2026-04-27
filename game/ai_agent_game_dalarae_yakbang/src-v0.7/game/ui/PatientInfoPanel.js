import { GAME_WIDTH, GAME_HEIGHT, BALANCE } from '../config.js';
import { audioSystem } from '../systems/AudioSystem.js';
import { PATIENT_STATE } from '../objects/Patient.js';

// Phase 6: 환자 클릭 → 두루마기 스타일 상태창.
// 참조 이미지: 생성그림_꼉/환자상태창/여자노비.png
//   · 상단 "환자 정보" 배너
//   · 좌측 초상화(스프라이트 확대)
//   · 우측 계층/상태/만족도/의욕 게이지
//   · 바깥 클릭/ESC 로 닫힘
// 경제·FSM 에 영향 없음 — 읽기 전용 뷰.

const PANEL_W = 420;
const PANEL_H = 320;
const DEPTH_OVERLAY = 450;
const DEPTH_PANEL = 460;
const DEPTH_CONTENT = 465;

const TIER_LABEL = {
  nobi: '노비', nongmin: '농민', sangin: '상인', seonbi: '선비', yangban: '양반'
};
const TIER_COLOR = {
  nobi: '#9aa0a8', nongmin: '#c08040', sangin: '#20a0a0',
  seonbi: '#a068d0', yangban: '#d0a020'
};
const STATE_LABEL = {
  spawning: '도착 중', walking: '이동 중',
  using: '이용 중', leaving: '귀가 중', done: '—'
};
const ILLNESS_LABEL = { moxa: '경증', acu: '중증', herb: '위중' };

export class PatientInfoPanel {
  constructor(scene) {
    this.scene = scene;
    this.patient = null;
    this.nodes = [];
    this.isOpen = false;
    this._escKey = null;
    this._tickEvt = null;
  }

  isOpened() { return this.isOpen; }

  open(patient) {
    if (this.isOpen) this.close();
    if (!patient) return;
    // HIGH-06: LEAVING/DONE 환자는 곧 사라지므로 패널 거절. open/close SFX 스팸 방지.
    if (patient.state === PATIENT_STATE.DONE || patient.state === PATIENT_STATE.LEAVING) return;
    this.patient = patient;
    this.isOpen = true;
    audioSystem.playSFX?.('panel_open');
    this._build();
    this._escKey = this.scene.input.keyboard?.on('keydown-ESC', this._onEsc, this);
    // 매 0.2s 게이지/상태 갱신.
    this._tickEvt = this.scene.time.addEvent({
      delay: 200, loop: true, callback: () => this._refresh()
    });
    // W3-Gap2: USING 진입/종료 이벤트로 0.2s tick 지연 없이 즉시 진행률 갱신.
    if (this.scene.patients && this.scene.patients.events) {
      this._onUsingChange = ({ patient: ep }) => {
        if (ep === this.patient) this._refresh();
      };
      this.scene.patients.events.on('patient_using', this._onUsingChange);
      this.scene.patients.events.on('patient_served', this._onUsingChange);
    }
  }

  close() {
    if (!this.isOpen) return;
    this.isOpen = false;
    // HIGH-02: scene 이 이미 shutdown 됐으면 input/keyboard 가 null 이므로 방어.
    if (this._escKey && this.scene && this.scene.input && this.scene.input.keyboard) {
      this.scene.input.keyboard.off('keydown-ESC', this._onEsc, this);
    }
    this._escKey = null;
    if (this._tickEvt) { this._tickEvt.remove(false); this._tickEvt = null; }
    if (this._onUsingChange && this.scene && this.scene.patients && this.scene.patients.events) {
      this.scene.patients.events.off('patient_using', this._onUsingChange);
      this.scene.patients.events.off('patient_served', this._onUsingChange);
    }
    this._onUsingChange = null;
    for (const n of this.nodes) { if (n && n.destroy) n.destroy(); }
    this.nodes.length = 0;
    this.patient = null;
    audioSystem.playSFX?.('panel_close');
  }

  _onEsc() { this.close(); }

  _build() {
    const s = this.scene;
    const cx = GAME_WIDTH / 2;
    const cy = GAME_HEIGHT / 2 - 40;
    const x0 = cx - PANEL_W / 2;
    const y0 = cy - PANEL_H / 2;

    // 오버레이 — 클릭 시 닫힘.
    const overlay = s.add.rectangle(0, 0, GAME_WIDTH, GAME_HEIGHT, 0x000000, 0.45)
      .setOrigin(0, 0).setDepth(DEPTH_OVERLAY).setInteractive();
    overlay.on('pointerdown', () => this.close());
    this.nodes.push(overlay);

    // 두루마기 프레임.
    const g = s.add.graphics().setDepth(DEPTH_PANEL);
    // 외곽 나무 프레임.
    g.fillStyle(0x5a3314, 1);
    g.fillRoundedRect(x0 - 12, y0 - 6, PANEL_W + 24, PANEL_H + 12, 6);
    // 한지 배경.
    g.fillStyle(0xf3e3b6, 1);
    g.fillRoundedRect(x0, y0, PANEL_W, PANEL_H, 4);
    // 상단 배너 — 자주색.
    g.fillStyle(0x8a4a90, 1);
    g.fillRoundedRect(x0 + 90, y0 - 16, PANEL_W - 180, 36, 6);
    g.lineStyle(2, 0x4a2050, 1);
    g.strokeRoundedRect(x0 + 90, y0 - 16, PANEL_W - 180, 36, 6);
    // 양쪽 나무 롤러(고리).
    g.fillStyle(0xd9a84a, 1);
    g.fillCircle(x0 - 6, y0, 4);
    g.fillCircle(x0 - 6, y0 + PANEL_H, 4);
    g.fillCircle(x0 + PANEL_W + 6, y0, 4);
    g.fillCircle(x0 + PANEL_W + 6, y0 + PANEL_H, 4);
    // 패널 내부에 overlay 차단 zone — 본체 클릭이 overlay 에 전파되지 않도록.
    const blocker = s.add.zone(x0, y0, PANEL_W, PANEL_H)
      .setOrigin(0, 0).setDepth(DEPTH_PANEL + 1).setInteractive();
    blocker.on('pointerdown', (p, lx, ly, evt) => { if (evt) evt.stopPropagation(); });
    this.nodes.push(g, blocker);

    // 배너 타이틀.
    this.nodes.push(
      s.add.text(cx, y0 + 3, '환자 정보', {
        fontFamily: 'Noto Serif KR, serif', fontSize: '18px', color: '#fff8e0',
        fontStyle: 'bold', stroke: '#4a2050', strokeThickness: 2
      }).setOrigin(0.5).setDepth(DEPTH_CONTENT)
    );

    // 좌측 초상화 프레임(대나무 배경).
    const portraitX = x0 + 22;
    const portraitY = y0 + 36;
    const portraitW = 140;
    const portraitH = 230;
    const pg = s.add.graphics().setDepth(DEPTH_CONTENT);
    pg.fillStyle(0xdac492, 1);
    pg.fillRoundedRect(portraitX, portraitY, portraitW, portraitH, 4);
    pg.lineStyle(2, 0x8b5a28, 1);
    pg.strokeRoundedRect(portraitX, portraitY, portraitW, portraitH, 4);
    // 세로 대나무 줄.
    pg.lineStyle(1, 0xb08050, 0.5);
    for (let lx = 10; lx < portraitW - 10; lx += 10) {
      pg.lineBetween(portraitX + lx, portraitY + 6, portraitX + lx, portraitY + portraitH - 6);
    }
    this.nodes.push(pg);

    // 우측 스탯 영역 — 텍스트 + 게이지를 _refresh 에서 갱신.
    // 미리 틀을 만들고 객체 참조 저장.
    const statX = x0 + 182;
    const statYTop = y0 + 44;
    const stat = {};
    stat.tier = s.add.text(statX, statYTop, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '26px',
      fontStyle: 'bold', color: '#2a1808', stroke: '#fff0d0', strokeThickness: 3
    }).setDepth(DEPTH_CONTENT);
    stat.state = s.add.text(statX, statYTop + 36, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '14px', color: '#5a3314'
    }).setDepth(DEPTH_CONTENT);

    // 만족도 라벨 + 숫자 + 바.
    stat.satLabel = s.add.text(statX, statYTop + 68, '♥ 만족도', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '13px', color: '#a02040',
      fontStyle: 'bold'
    }).setDepth(DEPTH_CONTENT);
    stat.satVal = s.add.text(statX + 180, statYTop + 68, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '14px', color: '#2a1808',
      fontStyle: 'bold'
    }).setOrigin(1, 0).setDepth(DEPTH_CONTENT);
    stat.satBarG = s.add.graphics().setDepth(DEPTH_CONTENT);

    // 의욕(체류 잔량) 라벨 + 숫자 + 바.
    stat.motLabel = s.add.text(statX, statYTop + 110, '☺ 의욕', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '13px', color: '#408040',
      fontStyle: 'bold'
    }).setDepth(DEPTH_CONTENT);
    stat.motVal = s.add.text(statX + 180, statYTop + 110, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '14px', color: '#2a1808',
      fontStyle: 'bold'
    }).setOrigin(1, 0).setDepth(DEPTH_CONTENT);
    stat.motBarG = s.add.graphics().setDepth(DEPTH_CONTENT);

    // W3: 치료 진행률 라벨 + 숫자 + 바. USING 일 때만 의미, 그 외엔 "대기 중".
    stat.useLabel = s.add.text(statX, statYTop + 150, '✚ 치료 진행', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '13px', color: '#a06020',
      fontStyle: 'bold'
    }).setDepth(DEPTH_CONTENT);
    stat.useVal = s.add.text(statX + 180, statYTop + 150, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '14px', color: '#2a1808',
      fontStyle: 'bold'
    }).setOrigin(1, 0).setDepth(DEPTH_CONTENT);
    stat.useBarG = s.add.graphics().setDepth(DEPTH_CONTENT);

    // 소지금.
    stat.gold = s.add.text(statX, statYTop + 192, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '13px', color: '#604010'
    }).setDepth(DEPTH_CONTENT);
    // 병세.
    stat.ill = s.add.text(statX, statYTop + 212, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '12px', color: '#604010'
    }).setDepth(DEPTH_CONTENT);

    // 바 배경·전경은 refresh 가 clear/draw.
    stat.barGeo = {
      x: statX, y1: statYTop + 86, y2: statYTop + 128, y3: statYTop + 168, w: 180, h: 10
    };
    this._stat = stat;
    this.nodes.push(
      stat.tier, stat.state,
      stat.satLabel, stat.satVal, stat.satBarG,
      stat.motLabel, stat.motVal, stat.motBarG,
      stat.useLabel, stat.useVal, stat.useBarG,
      stat.gold, stat.ill
    );

    // 초상화 스프라이트 — 실제 환자 sprite 를 복제(프레임·텍스처 공유).
    // W3-Gap1 (P3/P4): 정수 배율 + 좌표 정수 스냅으로 발 jitter / 1px 아웃라인 비대칭 방지.
    const p = this.patient;
    const charX = Math.round(portraitX + portraitW / 2);
    const charY = Math.round(portraitY + portraitH - 16);  // 발을 프레임 하단 16px 위에 정렬.
    if (p.spriteKey && s.textures.exists(p.spriteKey)) {
      const ch = s.add.sprite(charX, charY, p.spriteKey)
        .setOrigin(0.5, 1).setScale(3).setDepth(DEPTH_CONTENT);
      // idle down 프레임.
      ch.setFrame(1);
      this.nodes.push(ch);
    } else if (s.textures.exists('tex_walker')) {
      // HIGH-05: 스프라이트시트 로드 실패 시 폴백 — 초상화 영역 텅빔 방지.
      const ch = s.add.image(charX, charY, 'tex_walker')
        .setOrigin(0.5, 1).setScale(3).setDepth(DEPTH_CONTENT);
      this.nodes.push(ch);
    }

    // X 닫기 버튼 — 우상단.
    const close = s.add.text(x0 + PANEL_W - 14, y0 + 4, '✕', {
      fontFamily: 'sans-serif', fontSize: '20px', color: '#8b2020', fontStyle: 'bold'
    }).setOrigin(1, 0).setDepth(DEPTH_CONTENT + 1).setInteractive({ useHandCursor: true });
    close.on('pointerdown', () => this.close());
    this.nodes.push(close);

    this._refresh();
  }

  _refresh() {
    if (!this.isOpen || !this.patient || !this._stat) return;
    const p = this.patient;
    const s = this._stat;

    s.tier.setText(TIER_LABEL[p.tier] || p.tier);
    s.tier.setColor(TIER_COLOR[p.tier] || '#2a1808');
    const illStr = ILLNESS_LABEL[p.illness] || '';
    const stateStr = STATE_LABEL[p.state] || p.state;
    s.state.setText(illStr ? `${illStr} · ${stateStr}` : stateStr);

    // 만족도 스코어 — treat + amenity 합. need 대비 비율로 게이지.
    const score = (p.treatScoreSum || 0) + (p.amenityScoreSum || 0);
    const needTreat = (BALANCE.satisfyNeedTreat?.[p.tier]) || 1;
    const needAmen = (BALANCE.satisfyNeedAmenity?.[p.tier]) || 1;
    const maxScore = needTreat + needAmen;
    const satRatio = Math.max(0, Math.min(1, score / maxScore));
    s.satVal.setText(`${score} / ${maxScore}`);
    this._drawBar(s.satBarG, s.barGeo.x, s.barGeo.y1, s.barGeo.w, s.barGeo.h,
      satRatio, 0xf0c8d0, 0xe04870);

    // 의욕(체류 잔량) — stayRemaining / _maxStayMs.
    const maxStay = p._maxStayMs || BALANCE.patientStayMs;
    const motRatio = Math.max(0, Math.min(1, (p.stayRemaining || 0) / maxStay));
    const elapsedSec = Math.max(0, (maxStay - (p.stayRemaining || 0)) / 1000);
    s.motVal.setText(`${Math.round(motRatio * 100)} (${elapsedSec.toFixed(1)}s 경과)`);
    // W3-Gap2: 임계 경고색. 30% 이하 주황, 10% 이하 빨강 + 라벨도 동조.
    let motFg = 0x60b040, motBg = 0xdce8c8, motLabelColor = '#408040';
    if (motRatio <= 0.10) { motFg = 0xc02020; motBg = 0xf0c8c8; motLabelColor = '#a02020'; }
    else if (motRatio <= 0.30) { motFg = 0xe09020; motBg = 0xf0dcb0; motLabelColor = '#a06010'; }
    s.motLabel.setColor(motLabelColor);
    this._drawBar(s.motBarG, s.barGeo.x, s.barGeo.y2, s.barGeo.w, s.barGeo.h,
      motRatio, motBg, motFg);

    // W3: 치료 진행률 — USING 일 때만 의미. 그 외엔 회색 바 + 상태 라벨.
    if (p.state === PATIENT_STATE.USING && p.useTotal > 0) {
      const useDone = Math.max(0, p.useTotal - (p.useRemaining || 0));
      const useRatio = Math.max(0, Math.min(1, useDone / p.useTotal));
      s.useVal.setText(`${Math.round(useRatio * 100)}%`);
      s.useVal.setColor('#2a1808');
      this._drawBar(s.useBarG, s.barGeo.x, s.barGeo.y3, s.barGeo.w, s.barGeo.h,
        useRatio, 0xf0d8b0, 0xe09040);
    } else {
      const stateMsg = p.state === PATIENT_STATE.LEAVING ? '귀가 중'
        : p.state === PATIENT_STATE.WALKING ? '이동 중'
        : '대기 중';
      s.useVal.setText(stateMsg);
      s.useVal.setColor('#806040');
      this._drawBar(s.useBarG, s.barGeo.x, s.barGeo.y3, s.barGeo.w, s.barGeo.h,
        0, 0xe8e0d0, 0xe09040);
    }

    s.gold.setText(`소지금: ${p.gold ?? 0} 전`);
    s.ill.setText(`선호 치료: ${ILLNESS_LABEL[p.illness] || '—'}`);

    // 환자가 DONE 되면 자동 닫힘.
    if (p.state === PATIENT_STATE.DONE) this.close();
  }

  _drawBar(g, x, y, w, h, ratio, bgColor, fgColor) {
    g.clear();
    g.fillStyle(bgColor, 1);
    g.fillRoundedRect(x, y, w, h, 3);
    g.lineStyle(1, 0x8b5a28, 1);
    g.strokeRoundedRect(x, y, w, h, 3);
    const fw = Math.floor((w - 2) * ratio);
    if (fw > 0) {
      g.fillStyle(fgColor, 1);
      g.fillRoundedRect(x + 1, y + 1, fw, h - 2, 2);
    }
  }

  destroy() {
    this.close();
    this.scene = null;
  }
}
