export class BootScene extends Phaser.Scene {
  constructor() {
    super({ key: 'BootScene' });
  }

  preload() {
    // 주인공은 런타임 픽셀 텍스처로 생성한다.
  }

  create() {
    this._createGoraniPixelTextures();
    this._createGoraniAnimations();

    // 쓰레기통 텍스처 생성
    const g1 = this.add.graphics();
    g1.fillStyle(0x8B4513); g1.fillRect(0, 10, 32, 40);  // 몸통
    g1.fillStyle(0x5C3317); g1.fillRect(-4, 0, 40, 12);  // 뚜껑
    g1.generateTexture('trash', 36, 50);
    g1.destroy();

    // 주사기 텍스처 생성
    const g2 = this.add.graphics();
    g2.fillStyle(0xDDEEFF); g2.fillRect(0, 8, 12, 32);   // 실린더
    g2.fillStyle(0xCCCCCC); g2.fillRect(4, 40, 4, 12);   // 바늘
    g2.generateTexture('syringe', 12, 52);
    g2.destroy();

    // 도토리 텍스처 생성
    const g3 = this.add.graphics();
    g3.fillStyle(0x8B6914); g3.fillCircle(12, 16, 12);   // 몸통
    g3.fillStyle(0x5C4A1E); g3.fillRect(9, 0, 6, 8);     // 꼭지
    g3.generateTexture('acorn', 24, 24);
    g3.destroy();

    // 나뭇잎 텍스처 생성
    const g4 = this.add.graphics();
    g4.fillStyle(0x44BB44); g4.fillEllipse(14, 10, 28, 20);
    g4.generateTexture('leaf', 28, 20);
    g4.destroy();

    // 지면 static body용 텍스처 (투명 1px)
    const gg = this.add.graphics();
    gg.fillStyle(0xffffff, 0); gg.fillRect(0, 0, 1, 1);
    gg.generateTexture('ground-px', 1, 1);
    gg.destroy();

    this.scene.start('IntroScene');
  }

  _createGoraniPixelTextures() {
    const drawPixels = (key, pixels, scale = 4) => {
      const g = this.add.graphics();
      for (const p of pixels) {
        g.fillStyle(p.c);
        g.fillRect(p.x * scale, p.y * scale, scale, scale);
      }
      g.generateTexture(key, 20 * scale, 20 * scale);
      g.destroy();
    };

    const C = {
      o: 0x1f1f1f,
      b: 0xb07a52,
      d: 0x8e5f3e,
      h: 0xd8a67a,
      e: 0x121212,
      g: 0xffffff,
      r: 0xdb6262
    };

    const makeBase = () => {
      const px = [];
      // 몸통
      for (let y = 8; y <= 17; y++) {
        for (let x = 5; x <= 14; x++) px.push({ x, y, c: C.b });
      }
      // 머리
      for (let y = 3; y <= 10; y++) {
        for (let x = 6; x <= 13; x++) px.push({ x, y, c: C.h });
      }
      // 뿔
      px.push({ x: 7, y: 2, c: C.d }, { x: 12, y: 2, c: C.d });
      px.push({ x: 6, y: 1, c: C.d }, { x: 13, y: 1, c: C.d });
      // 얼굴
      px.push({ x: 8, y: 6, c: C.e }, { x: 11, y: 6, c: C.e });
      px.push({ x: 9, y: 7, c: C.g }, { x: 10, y: 7, c: C.g });
      // 털 무늬
      for (let y = 10; y <= 15; y++) px.push({ x: 8, y, c: C.d });
      return px;
    };

    const addOutline = (px) => {
      const out = [...px];
      for (const p of px) {
        const neighbors = [[1,0],[-1,0],[0,1],[0,-1]];
        for (const [dx, dy] of neighbors) {
          const nx = p.x + dx;
          const ny = p.y + dy;
          const exists = px.some(v => v.x === nx && v.y === ny);
          if (!exists) out.push({ x: p.x, y: p.y, c: C.o });
        }
      }
      return out;
    };

    const run1 = makeBase();
    run1.push({ x: 6, y: 18, c: C.d }, { x: 7, y: 18, c: C.d }, { x: 12, y: 17, c: C.d }, { x: 13, y: 17, c: C.d });
    const run2 = makeBase();
    run2.push({ x: 6, y: 17, c: C.d }, { x: 7, y: 17, c: C.d }, { x: 12, y: 18, c: C.d }, { x: 13, y: 18, c: C.d });
    const jumpUp = makeBase();
    jumpUp.push({ x: 6, y: 16, c: C.d }, { x: 7, y: 16, c: C.d }, { x: 12, y: 16, c: C.d }, { x: 13, y: 16, c: C.d });
    const jumpDown = makeBase();
    jumpDown.push({ x: 5, y: 18, c: C.d }, { x: 6, y: 18, c: C.d }, { x: 13, y: 18, c: C.d }, { x: 14, y: 18, c: C.d });
    const hurt = makeBase();
    hurt.push({ x: 8, y: 6, c: C.r }, { x: 11, y: 6, c: C.r }, { x: 9, y: 10, c: C.r }, { x: 10, y: 10, c: C.r });

    drawPixels('gorani-run-1', addOutline(run1));
    drawPixels('gorani-run-2', addOutline(run2));
    drawPixels('gorani-jump-up', addOutline(jumpUp));
    drawPixels('gorani-jump-down', addOutline(jumpDown));
    drawPixels('gorani-hurt-1', addOutline(hurt));
    drawPixels('gorani-hurt-2', addOutline(run1));
  }

  _createGoraniAnimations() {
    if (!this.anims.exists('gorani-run')) {
      this.anims.create({
        key: 'gorani-run',
        frames: [{ key: 'gorani-run-1' }, { key: 'gorani-run-2' }],
        frameRate: 10,
        repeat: -1
      });
    }
    if (!this.anims.exists('gorani-hurt')) {
      this.anims.create({
        key: 'gorani-hurt',
        frames: [{ key: 'gorani-hurt-1' }, { key: 'gorani-hurt-2' }],
        frameRate: 12,
        repeat: -1
      });
    }
  }
}
