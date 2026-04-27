import { GAME_WIDTH, GAME_HEIGHT } from '../config.js';
import { audioSystem } from '../systems/AudioSystem.js';

export class TitleScene extends Phaser.Scene {
  constructor() { super({ key: 'TitleScene' }); }

  create() {
    this._drawBackground();

    // 타이틀
    const title = this.add.text(GAME_WIDTH / 2, 150, '東洋 韓醫院', {
      fontFamily: 'Noto Serif KR, serif',
      fontSize: '64px',
      fontStyle: 'bold',
      color: '#f7d05b',
      stroke: '#3d1f0a',
      strokeThickness: 8,
    }).setOrigin(0.5);
    title.setShadow(0, 4, '#000', 6, true, true);

    this.add.text(GAME_WIDTH / 2, 220, '동양 판타지 한의원', {
      fontFamily: 'Noto Serif KR, serif',
      fontSize: '28px',
      color: '#e8dcc4'
    }).setOrigin(0.5);

    this.add.text(GAME_WIDTH / 2, 260, '온천약방 이야기', {
      fontFamily: 'Noto Serif KR, serif',
      fontSize: '20px',
      color: '#c9a66b',
      fontStyle: 'italic'
    }).setOrigin(0.5);

    // 카피
    this.add.text(GAME_WIDTH / 2, 310,
      '"목욕은 한첩의 보약이요, 일구이침삼약이라 하였으니."',
      { fontFamily: 'Noto Serif KR, serif', fontSize: '14px', color: '#a39074' }
    ).setOrigin(0.5);

    // START 버튼
    const btnBg = this.add.graphics();
    const btnW = 220, btnH = 60;
    const btnX = GAME_WIDTH / 2 - btnW / 2;
    const btnY = 380;
    const drawBtn = (hover) => {
      btnBg.clear();
      btnBg.fillStyle(hover ? 0xd9a83a : 0xb07f1e, 1);
      btnBg.fillRoundedRect(btnX, btnY, btnW, btnH, 8);
      btnBg.lineStyle(3, 0x3d1f0a, 1);
      btnBg.strokeRoundedRect(btnX, btnY, btnW, btnH, 8);
    };
    drawBtn(false);

    const btnLabel = this.add.text(GAME_WIDTH / 2, btnY + btnH / 2, '開 門 (시작)', {
      fontFamily: 'Noto Serif KR, serif',
      fontSize: '26px',
      fontStyle: 'bold',
      color: '#2a1810'
    }).setOrigin(0.5);

    const hit = this.add.zone(GAME_WIDTH / 2, btnY + btnH / 2, btnW, btnH)
      .setOrigin(0.5).setInteractive({ useHandCursor: true });

    hit.on('pointerover', () => { drawBtn(true); btnLabel.setScale(1.05); });
    hit.on('pointerout',  () => { drawBtn(false); btnLabel.setScale(1.0); });
    hit.on('pointerdown', async () => {
      try {
        await audioSystem.init();
        audioSystem.switchTheme('day');
      } catch (e) { console.warn('audio init fail', e); }
      this.scene.start('GameScene');
    });

    // 조작 안내
    this.add.text(GAME_WIDTH / 2, 490,
      '방을 클릭하면 치료 속도가 빨라집니다.  환자의 인내심이 다하기 전에 치료를 완료하세요.',
      { fontFamily: 'Noto Serif KR, serif', fontSize: '13px', color: '#8a816e' }
    ).setOrigin(0.5);

    this.add.text(GAME_WIDTH / 2, 520,
      '뜸 → 침 → 약 → 약탕  순으로 해금됩니다.',
      { fontFamily: 'Noto Serif KR, serif', fontSize: '13px', color: '#8a816e' }
    ).setOrigin(0.5);

    // 타이틀 BGM 준비 (클릭 전엔 재생 불가 — 웹오디오 규약)
    this.add.text(GAME_WIDTH - 10, GAME_HEIGHT - 10, 'v1.0', {
      fontFamily: 'monospace', fontSize: '10px', color: '#5a4a34'
    }).setOrigin(1, 1);
  }

  _drawBackground() {
    const g = this.add.graphics();

    // ── 하늘 (밝은 낮)
    g.fillGradientStyle(0x4aa8e0, 0x4aa8e0, 0x88ccf0, 0xd8f0ff, 1);
    g.fillRect(0, 0, GAME_WIDTH, GAME_HEIGHT);

    // ── 구름
    g.fillStyle(0xffffff, 0.95);
    g.fillEllipse(100, 60, 100, 34); g.fillEllipse(148, 46, 80, 30); g.fillEllipse(60, 55, 60, 26);
    g.fillEllipse(560, 44, 120, 36); g.fillEllipse(616, 30, 90, 30); g.fillEllipse(510, 40, 70, 26);
    g.fillEllipse(720, 90, 80, 26); g.fillEllipse(760, 78, 60, 22);

    // ── 원경 산 (파스텔 녹색)
    g.fillStyle(0x80b870, 0.8);
    this._mountain(g, -20, 310, 280, 180);
    this._mountain(g, 180, 320, 260, 160);
    this._mountain(g, 380, 305, 300, 190);
    this._mountain(g, 600, 315, 280, 165);
    g.fillStyle(0xa0d080, 0.6);
    this._mountain(g, 80, 320, 200, 120);
    this._mountain(g, 480, 325, 220, 130);

    // ── 지평선 풀밭
    g.fillStyle(0x70c040, 1); g.fillRect(0, 300, GAME_WIDTH, 25);
    g.fillStyle(0x58a830, 1); g.fillRect(0, 316, GAME_WIDTH, 9);

    // ── 건물들 (밝은 색 한옥 스타일)
    // 왼쪽 한의원 본관
    g.fillStyle(0xfce8b0, 1); g.fillRect(60, 330, 200, 140);
    g.fillStyle(0xd03818, 1); g.fillRect(40, 310, 240, 26); g.fillTriangle(40, 310, 280, 310, 160, 270);
    g.fillStyle(0xa02010, 1); g.fillRect(40, 310, 240, 5);
    // 창문 (노란 불빛)
    g.fillStyle(0xffe090, 1); g.fillRect(80, 360, 30, 35); g.fillRect(128, 360, 30, 35); g.fillRect(176, 360, 30, 35);
    g.fillStyle(0xc87020, 0.4); g.fillRect(91, 360, 2, 35); g.fillRect(139, 360, 2, 35); g.fillRect(187, 360, 2, 35);

    // 오른쪽 별채
    g.fillStyle(0xecd8a8, 1); g.fillRect(500, 345, 240, 125);
    g.fillStyle(0x2050a0, 1); g.fillRect(480, 326, 280, 24); g.fillTriangle(480, 326, 760, 326, 620, 288);
    g.fillStyle(0x103080, 1); g.fillRect(480, 326, 280, 5);
    g.fillStyle(0xffe090, 1); g.fillRect(520, 370, 28, 32); g.fillRect(566, 370, 28, 32); g.fillRect(668, 370, 28, 32);

    // ── 땅/마당 (따뜻한 나무 바닥)
    g.fillStyle(0xe0b860, 1); g.fillRect(0, 450, GAME_WIDTH, GAME_HEIGHT - 450);
    g.fillStyle(0xc89840, 0.5);
    for (let y = 460; y < GAME_HEIGHT; y += 28) g.fillRect(0, y, GAME_WIDTH, 2);

    // ── 전경 나무 (밝은)
    this._drawTreeTitle(g, 30, 500);
    this._drawTreeTitle(g, GAME_WIDTH - 30, 505);
  }

  _drawTreeTitle(g, x, baseY) {
    g.fillStyle(0x8b5a2a, 1); g.fillRect(x - 5, baseY - 44, 10, 46);
    g.fillStyle(0x48c838, 1); g.fillCircle(x, baseY - 60, 28); g.fillCircle(x - 20, baseY - 46, 18); g.fillCircle(x + 20, baseY - 46, 18);
    g.fillStyle(0x68e850, 1); g.fillCircle(x - 8, baseY - 68, 16); g.fillCircle(x + 10, baseY - 64, 13);
    g.fillStyle(0x90ff70, 0.5); g.fillCircle(x - 4, baseY - 72, 9);
  }

  _mountain(g, x, y, w, h) {
    g.fillTriangle(x, y, x + w, y, x + w / 2, y - h);
  }
}
