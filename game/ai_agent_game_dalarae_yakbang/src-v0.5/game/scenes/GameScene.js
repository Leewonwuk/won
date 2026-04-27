import { BALANCE, GAME_WIDTH, GAME_HEIGHT } from '../config.js';
import { EconomySystem } from '../systems/EconomySystem.js';
import { RoomSystem } from '../systems/RoomSystem.js';
import { PatientSystem } from '../systems/PatientSystem.js';
import { audioSystem } from '../systems/AudioSystem.js';
import { FloatingText } from '../objects/FloatingText.js';

export class GameScene extends Phaser.Scene {
  constructor() { super({ key: 'GameScene' }); }

  init(data) {
    this.savedState = data && data.savedState ? data.savedState : null;
  }

  create() {
    this.day = this.savedState ? this.savedState.day : 1;
    this.dayElapsed = 0;
    this.dayEnded = false;

    this.audioSys = audioSystem;

    // 시스템 초기화
    this.econ = new EconomySystem(this);
    if (this.savedState) {
      this.econ.gold = this.savedState.gold;
      this.econ.totalSatisfied = this.savedState.totalSatisfied;
      this.econ.royalSatisfied = this.savedState.royalSatisfied;
      this.econ.actUnlocked = this.savedState.actUnlocked;
    }
    this.roomSys = new RoomSystem(this);
    this.patientSys = new PatientSystem(this);

    // 배경 그리기
    this._drawBackground();

    // 방 생성
    this.roomSys.createRooms();

    // 방이 만들어진 뒤 이전에 해금된 방 복원
    if (this.savedState && this.savedState.unlockedRooms) {
      for (const t of this.savedState.unlockedRooms) {
        const r = this.roomSys.rooms[t];
        if (r && r.state === 'locked') { r.state = 'idle'; r.sprite.setTexture(`room_${t}`); r.label.setColor('#f7d05b'); if (r.lockLabel) { r.lockLabel.destroy(); r.lockLabel = null; } }
      }
    }

    // 대기열 팻말
    this.add.image(716, 370, 'signpost').setOrigin(0.5, 1).setDepth(90);

    // HUD
    this._createHud();

    // 환자 소환 시작
    this.patientSys.start();

    // 이벤트 배선
    this.events.on('patient_satisfied', this._onPatientSatisfied, this);

    // 환자 인내심 타임아웃 처리 — Patient.onTimeout → Patient.onAngry() hook
    // (Patient 인스턴스마다 onAngry 훅 세팅)
    this._wireAngryHandler();

    // 하루 타이머
    this.dayTimer = this.time.addEvent({
      delay: BALANCE.dayDurationMs,
      callback: () => this._endDay()
    });

    // Act 2 해금 체크 타이머 (1초마다)
    this.time.addEvent({
      delay: 1000, loop: true,
      callback: () => this._checkAct2Unlock()
    });

    // BGM
    this.audioSys.switchTheme('day').catch(() => {});
  }

  update(time, delta) {
    if (this.dayEnded) return;
    this.dayElapsed += delta;
    this.roomSys.update(delta);
    this.patientSys.update(delta);
    this._updateHud();
    this._assignPendingNewPatients();
  }

  // 새로 생성된 환자 객체에 onAngry 훅을 자동으로 꽂기 위한 프록시
  _wireAngryHandler() {
    const sys = this.patientSys;
    const origSpawn = sys.spawnPatient.bind(sys);
    sys.spawnPatient = (forcedType = null) => {
      const before = sys.active.length;
      origSpawn(forcedType);
      const p = sys.active[sys.active.length - 1];
      if (p && sys.active.length > before) {
        p.onAngry = () => {
          if (!p.alive) return;
          // 치료 중엔 angry 방지
          if (p.state === 'treating') return;
          this.econ.onAngry(p);
          sys.onAngry(p);
        };
      }
    };
  }

  // 방이 막 비었을 때 대기열에서 누군가를 즉시 배정하기 위한 보조 로직
  _assignPendingNewPatients() {
    // RoomSystem.update 내부에선 방 상태만 변경.
    // 빈 방 + 대기 환자 조합 체크는 여기서.
    if (this.patientSys.waiting.length === 0) return;
    const hasIdle = this.roomSys.list.some(r => r.state === 'idle');
    if (hasIdle) this.patientSys.tryAssignWaiting();
  }

  _onPatientSatisfied({ patient, room, stars, gold }) {
    this.econ.addGold(gold);
    this.econ.onSatisfied(room, patient);
    this.patientSys.onSatisfied(patient, room);

    // 해금 체크
    const newly = this.roomSys.checkUnlocks(this.econ.totalSatisfied);
    if (newly) {
      FloatingText.spawn(this, GAME_WIDTH / 2, 100,
        `${newly.spec.label} 해금!`, { color: '#f7d05b', size: 28, rise: 30, duration: 1800 });
    }
  }

  _checkAct2Unlock() {
    if (this.econ.canUnlockAct2()) {
      this.econ.actUnlocked = 2;
      FloatingText.spawn(this, GAME_WIDTH / 2, 140,
        'Act II — 요괴의 방문', { color: '#ff8a3c', size: 30, rise: 40, duration: 2400 });
      if (this.audioSys) this.audioSys.playSFX('levelup');
    }
  }

  _endDay() {
    if (this.dayEnded) return;
    this.dayEnded = true;

    // 잔여 환자 즉시 퇴장 — 씬 pause 전에 처리해야 tween이 살아있음
    const snapshot = this.patientSys.active.slice();
    for (const p of snapshot) {
      if (p.alive && p.state !== 'leaving') {
        p.leave(this.patientSys.exitX, this.patientSys.exitY);
      }
    }

    // 씬 상태 저장해 ResultScene으로 전달
    const unlockedRooms = this.roomSys.list.filter(r => r.state !== 'locked').map(r => r.type);
    const summary = {
      day: this.day,
      gold: this.econ.gold,
      todayIncome: this.econ.todayIncome,
      todaySatisfied: this.econ.todaySatisfied,
      todayAngry: this.econ.todayAngry,
      totalSatisfied: this.econ.totalSatisfied,
      royalSatisfied: this.econ.royalSatisfied,
      actUnlocked: this.econ.actUnlocked,
      unlockedRooms
    };

    // 짧은 딜레이 후 결과 화면 — 환자들이 걷기 시작하는 모습 잠깐 보여줌
    this.time.delayedCall(400, () => {
      this.scene.launch('ResultScene', { summary });
      this.scene.pause();
    });
  }

  // -------------------------------------------------------------------------
  // 배경 — 온천골 스토리 탑다운 실내 뷰
  //   y 50..130  : 상단 정원/외벽 (바깥이 살짝 보이는 느낌)
  //   y 130..510 : 건물 내부 나무 바닥
  //   통로 및 각 방 위치를 색조로 구분
  // -------------------------------------------------------------------------
  _drawBackground() {
    const g = this.add.graphics();

    // ── 정원/외벽 (HUD 아래 ~ 건물 상단)
    g.fillGradientStyle(0x68b848, 0x68b848, 0x50a030, 0x50a030, 1);
    g.fillRect(0, 50, GAME_WIDTH, 90);
    // 잔디 텍스처 라인
    g.fillStyle(0x48a020, 0.5);
    for (let y = 58; y < 140; y += 10) {
      for (let x = 0; x < GAME_WIDTH; x += 16) {
        g.fillRect(x + (y % 16), y, 8, 2);
      }
    }
    // 꽃 장식 (정원)
    this._drawFlower(g, 50, 90);  this._drawFlower(g, 110, 75);
    this._drawFlower(g, 680, 85); this._drawFlower(g, 740, 70);
    this._drawFlower(g, 400, 78); this._drawFlower(g, 350, 100);

    // 외벽 (건물 상단 경계)
    g.fillStyle(0x8b5a2a, 1); g.fillRect(0, 132, GAME_WIDTH, 10);
    g.fillStyle(0xc87828, 1); g.fillRect(0, 130, GAME_WIDTH, 4);

    // ── 실내 나무 바닥 (메인 플레이 영역)
    g.fillStyle(0xe8c880, 1);
    g.fillRect(0, 140, GAME_WIDTH, 370);

    // 나무 판자 가로 라인
    g.fillStyle(0xd0a858, 0.55);
    for (let y = 152; y < 510; y += 26) {
      g.fillRect(0, y, GAME_WIDTH, 2);
    }
    // 세로 이음새 라인 (엇갈림)
    g.fillStyle(0xba9040, 0.22);
    for (let y = 152; y < 510; y += 52) {
      for (let x = 0; x < GAME_WIDTH; x += 80) {
        g.fillRect(x, y, 2, 26);
        g.fillRect(x + 40, y + 26, 2, 26);
      }
    }

    // ── 방 위치 바닥 마커 (방 텍스처 밑 살짝 다른 색)
    const rooms = [
      { x: 150, y: 220 }, { x: 530, y: 220 }, // 상단 행
      { x: 150, y: 380 }, { x: 530, y: 380 }  // 하단 행
    ];
    for (const r of rooms) {
      g.fillStyle(0xf4dca0, 0.5);
      g.fillRect(r.x, r.y, 80, 80);
      // 방 가장자리 어두운 테두리
      g.fillStyle(0xb89040, 0.4);
      g.fillRect(r.x, r.y, 80, 3);
      g.fillRect(r.x, r.y, 3, 80);
      g.fillRect(r.x + 77, r.y, 3, 80);
    }

    // ── 중앙 통로 (두 방 사이)
    g.fillStyle(0xdcb870, 0.35);
    g.fillRect(230, 140, 300, 370);  // 가운데 복도
    g.fillRect(0, 310, GAME_WIDTH, 80); // 가로 복도 (두 행 사이)

    // 복도 경계선
    g.fillStyle(0xb89040, 0.3);
    g.fillRect(230, 140, 2, 370);
    g.fillRect(530, 140, 2, 370);

    // ── 대기 구역 (우측)
    g.fillStyle(0xe0c070, 0.25);
    g.fillRect(620, 140, 180, 370);
    g.fillStyle(0xb89040, 0.35);
    g.fillRect(620, 140, 2, 370);

    // ── 입구 화살표 (우측)
    g.fillStyle(0xb04010, 0.6);
    g.fillTriangle(790, 355, 790, 385, 810, 370);

    // ── 외벽 (건물 하단 경계)
    g.fillStyle(0x8b5a2a, 1); g.fillRect(0, 506, GAME_WIDTH, 4);

    // ── 전면 장식 나무 (탑다운 — 원형)
    this._drawTreeTopDown(g, 50, 500);
    this._drawTreeTopDown(g, GAME_WIDTH - 50, 500);
  }

  _drawFlower(g, x, y) {
    // 꽃 (탑다운)
    g.fillStyle(0xff6090, 0.9);
    g.fillCircle(x, y, 4); g.fillCircle(x + 5, y - 3, 3); g.fillCircle(x - 5, y - 3, 3);
    g.fillCircle(x + 5, y + 3, 3); g.fillCircle(x - 5, y + 3, 3);
    g.fillStyle(0xffee60, 1); g.fillCircle(x, y, 2);
  }

  _drawTreeTopDown(g, x, y) {
    // 나무 (탑다운 — 원형 그림자 + 잎)
    g.fillStyle(0x304010, 0.3); g.fillEllipse(x + 4, y + 4, 52, 38);
    g.fillStyle(0x40a020, 1); g.fillCircle(x, y, 22);
    g.fillStyle(0x58c030, 1); g.fillCircle(x - 8, y - 7, 14); g.fillCircle(x + 10, y - 5, 12);
    g.fillStyle(0x78e048, 1); g.fillCircle(x - 4, y - 10, 9);
    g.fillStyle(0xa0f070, 0.6); g.fillCircle(x - 6, y - 12, 6);
  }

  // -------------------------------------------------------------------------
  // HUD
  // -------------------------------------------------------------------------
  _createHud() {
    const HUD_DEPTH = 500; // 방(100) 및 환자(~280)보다 확실히 위

    // 상단 바 배경 (카이로 스타일 — 따뜻한 갈색)
    const topBg = this.add.graphics().setDepth(HUD_DEPTH);
    topBg.fillStyle(0x8b4a10, 1);
    topBg.fillRect(0, 0, GAME_WIDTH, 50);
    topBg.fillStyle(0x6a3208, 1);
    topBg.fillRect(0, 46, GAME_WIDTH, 4);

    // 하단 바 배경
    const botBg = this.add.graphics().setDepth(HUD_DEPTH);
    botBg.fillStyle(0x8b4a10, 1);
    botBg.fillRect(0, 510, GAME_WIDTH, 50);
    botBg.fillStyle(0x6a3208, 1);
    botBg.fillRect(0, 510, GAME_WIDTH, 4);

    // 날짜
    this.hudDay = this.add.text(16, 15, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '20px', color: '#f7d05b', fontStyle: 'bold'
    }).setDepth(HUD_DEPTH + 1);

    // 골드 아이콘 + 텍스트
    this.add.image(260, 25, 'coin').setScale(1.4).setDepth(HUD_DEPTH + 1);
    this.hudGold = this.add.text(276, 15, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '20px', color: '#f7d05b', fontStyle: 'bold'
    }).setDepth(HUD_DEPTH + 1);

    // Act 표시
    this.hudAct = this.add.text(GAME_WIDTH - 16, 15, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '18px', color: '#e8dcc4', fontStyle: 'bold'
    }).setOrigin(1, 0).setDepth(HUD_DEPTH + 1);

    // 날짜 게이지 바 (상단 아래)
    this.dayBarBg = this.add.rectangle(GAME_WIDTH / 2, 45, 400, 4, 0x1a1410)
      .setOrigin(0.5, 0.5).setDepth(HUD_DEPTH + 1);
    this.dayBarFg = this.add.rectangle(GAME_WIDTH / 2 - 200, 45, 0, 4, 0xf7d05b)
      .setOrigin(0, 0.5).setDepth(HUD_DEPTH + 2);

    // 하단 바 — 만족/불만/수입
    this.hudSat = this.add.text(16, 525, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '15px', color: '#4caf6f'
    }).setDepth(HUD_DEPTH + 1);
    this.hudAngry = this.add.text(200, 525, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '15px', color: '#e84a4a'
    }).setDepth(HUD_DEPTH + 1);
    this.hudIncome = this.add.text(GAME_WIDTH - 16, 525, '', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '15px', color: '#f7d05b'
    }).setOrigin(1, 0).setDepth(HUD_DEPTH + 1);
  }

  _updateHud() {
    this.hudDay.setText(`第 ${this.day} 日`);
    this.hudGold.setText(`${this.econ.gold}`);
    this.hudAct.setText(this.econ.actUnlocked === 2 ? 'Act II' : 'Act I');
    this.hudSat.setText(`만족: ${this.econ.todaySatisfied}명`);
    this.hudAngry.setText(`불만: ${this.econ.todayAngry}명`);
    this.hudIncome.setText(`오늘 수입: ${this.econ.todayIncome}`);

    const ratio = Phaser.Math.Clamp(this.dayElapsed / BALANCE.dayDurationMs, 0, 1);
    this.dayBarFg.width = 400 * ratio;
  }
}
