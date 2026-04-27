import { GAME_WIDTH, GAME_HEIGHT } from '../config.js';
import { audioSystem } from '../systems/AudioSystem.js';

export class ResultScene extends Phaser.Scene {
  constructor() { super({ key: 'ResultScene' }); }

  init(data) {
    this.summary = data.summary;
  }

  create() {
    // 불투명 오버레이 (환자들이 뒤에 보이지 않도록)
    const overlay = this.add.graphics();
    overlay.fillStyle(0x000000, 0.55);
    overlay.fillRect(0, 0, GAME_WIDTH, GAME_HEIGHT);

    // 패널 (카이로 스타일 — 따뜻한 크림색)
    const pw = 520, ph = 380;
    const px = (GAME_WIDTH - pw) / 2;
    const py = (GAME_HEIGHT - ph) / 2;
    const panel = this.add.graphics();
    panel.fillStyle(0xfdf0d0, 1);
    panel.fillRoundedRect(px, py, pw, ph, 12);
    panel.fillStyle(0xd08020, 1);
    panel.fillRoundedRect(px, py, pw, 44, 12);
    panel.fillRect(px, py + 32, pw, 12);
    panel.lineStyle(3, 0xd08020);
    panel.strokeRoundedRect(px, py, pw, ph, 12);

    // 제목
    this.add.text(GAME_WIDTH / 2, py + 22, `第 ${this.summary.day} 日 결산`, {
      fontFamily: 'Noto Serif KR, serif',
      fontSize: '28px', fontStyle: 'bold',
      color: '#ffffff', stroke: '#8b4010', strokeThickness: 4
    }).setOrigin(0.5);

    // 서브타이틀 — 분위기 카피
    const copies = [
      '오늘도 수고하셨습니다. 내일도 환자들이 기다립니다!',
      '향약 냄새가 골목에 가득 퍼졌네요.',
      '오늘의 치료, 내일의 소문이 됩니다.',
      '온천 김처럼 명성이 퍼져나가고 있어요.',
      '뜸 한 첩, 침 한 자리가 사람을 살립니다.'
    ];
    const copy = copies[(this.summary.day - 1) % copies.length];
    this.add.text(GAME_WIDTH / 2, py + 66, copy, {
      fontFamily: 'Noto Serif KR, serif',
      fontSize: '14px', color: '#8b4010', fontStyle: 'italic'
    }).setOrigin(0.5);

    // 항목들
    const rows = [
      ['오늘 수입',  `+${this.summary.todayIncome} G`, '#c06000'],
      ['만족 환자',  `${this.summary.todaySatisfied} 명`,     '#208030'],
      ['불만 환자',  `${this.summary.todayAngry} 명`,     '#c03020'],
      ['보유 금화',  `${this.summary.gold} G`,         '#604010']
    ];

    rows.forEach(([k, v, c], i) => {
      const ry = py + 112 + i * 38;
      // 항목 구분선
      const rowBg = this.add.graphics();
      rowBg.fillStyle(i % 2 === 0 ? 0xf8e8c0 : 0xfdf0d0, 1);
      rowBg.fillRect(px + 20, ry - 4, pw - 40, 34);
      this.add.text(px + 50, ry + 8, k, {
        fontFamily: 'Noto Serif KR, serif', fontSize: '17px', color: '#604010'
      }).setOrigin(0, 0.5);
      this.add.text(px + pw - 50, ry + 8, v, {
        fontFamily: 'Noto Serif KR, serif', fontSize: '20px', color: c, fontStyle: 'bold'
      }).setOrigin(1, 0.5);
    });

    // 누적 만족 (4개 방 해금 현황)
    const ts = this.summary.totalSatisfied;
    const tsPanel = this.add.graphics();
    tsPanel.fillStyle(0xe8d0a0, 1); tsPanel.fillRoundedRect(px + 20, py + 268, pw - 40, 30, 6);
    this.add.text(GAME_WIDTH / 2, py + 283,
      `누적 — 뜸 ${ts.moxa} | 침 ${ts.acupuncture} | 약 ${ts.herb} | 탕 ${ts.bath}`,
      { fontFamily: 'Noto Serif KR, serif', fontSize: '13px', color: '#804010' }
    ).setOrigin(0.5);

    if (this.summary.actUnlocked === 2) {
      this.add.text(GAME_WIDTH / 2, py + 308, '★ Act II 해금 — 요괴가 찾아옵니다!', {
        fontFamily: 'Noto Serif KR, serif', fontSize: '14px', color: '#c04000', fontStyle: 'bold'
      }).setOrigin(0.5);
    }

    // 다음 날 버튼
    const btnY = py + ph - 52;
    const btnW = 220, btnH = 44;
    const btnX = GAME_WIDTH / 2 - btnW / 2;

    const btnBg = this.add.graphics();
    const draw = (hover) => {
      btnBg.clear();
      btnBg.fillStyle(hover ? 0xf0a020 : 0xd08010, 1);
      btnBg.fillRoundedRect(btnX, btnY, btnW, btnH, 8);
      btnBg.fillStyle(hover ? 0xffc840 : 0xe89020, 1);
      btnBg.fillRoundedRect(btnX + 2, btnY + 2, btnW - 4, 18, 6);
      btnBg.lineStyle(2, 0x804000, 1);
      btnBg.strokeRoundedRect(btnX, btnY, btnW, btnH, 8);
    };
    draw(false);
    const btnLabel = this.add.text(GAME_WIDTH / 2, btnY + btnH / 2, '다음 날로 →', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '18px', color: '#ffffff', fontStyle: 'bold',
      stroke: '#804000', strokeThickness: 3
    }).setOrigin(0.5);

    const hit = this.add.zone(GAME_WIDTH / 2, btnY + btnH / 2, btnW, btnH)
      .setOrigin(0.5).setInteractive({ useHandCursor: true });
    hit.on('pointerover', () => { draw(true); btnLabel.setScale(1.05); });
    hit.on('pointerout', () => { draw(false); btnLabel.setScale(1); });
    hit.on('pointerdown', () => this._goNextDay());

    // BGM
    audioSystem.switchTheme('result').catch(() => {});
  }

  _goNextDay() {
    // 현재 씬 스택 정리 후 GameScene 재시작
    audioSystem.switchTheme('day').catch(() => {});
    this.scene.stop();
    this.scene.stop('GameScene');
    this.scene.start('GameScene', {
      savedState: {
        day: this.summary.day + 1,
        gold: this.summary.gold,
        totalSatisfied: this.summary.totalSatisfied,
        royalSatisfied: this.summary.royalSatisfied,
        actUnlocked: this.summary.actUnlocked,
        unlockedRooms: this.summary.unlockedRooms
      }
    });
  }
}
