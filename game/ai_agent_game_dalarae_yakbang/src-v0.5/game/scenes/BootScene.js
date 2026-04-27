// 모든 픽셀아트 텍스처를 Phaser Graphics API로 런타임 생성.
// 외부 이미지 에셋 0개 — CDN만 의존.

export class BootScene extends Phaser.Scene {
  constructor() {
    super({ key: 'BootScene' });
  }

  preload() { /* 런타임 텍스처만 사용 */ }

  create() {
    this._createPatientTextures();
    this._createRoomTextures();
    this._createUiTextures();

    this.scene.start('TitleScene');
  }

  // ---------------------------------------------------------------------------
  // 공통 유틸: 픽셀 배열 → 텍스처
  // ---------------------------------------------------------------------------
  _drawPixels(key, pixels, w, h, scale = 2) {
    const g = this.add.graphics();
    for (const p of pixels) {
      g.fillStyle(p.c, p.a == null ? 1 : p.a);
      g.fillRect(p.x * scale, p.y * scale, scale, scale);
    }
    g.generateTexture(key, w * scale, h * scale);
    g.destroy();
  }

  _rect(px, x0, y0, x1, y1, c) {
    for (let y = y0; y <= y1; y++) {
      for (let x = x0; x <= x1; x++) px.push({ x, y, c });
    }
  }

  // ---------------------------------------------------------------------------
  // 환자 텍스처 — 16×20 그리드, scale 2 → 32×40 최종
  // ---------------------------------------------------------------------------
  _createPatientTextures() {
    // 각 환자 고유의 의상/피부/특징을 색조로 구분.
    // 공통 실루엣(머리+몸통+다리) 위에 덧칠.
    const defs = {
      noble:    { skin: 0xd8a67a, robe: 0x7a6b55, accent: 0x3d3428, hat: null,       special: null },
      commoner: { skin: 0xe0b98c, robe: 0xd8d0bd, accent: 0x8a816e, hat: null,       special: null },
      yangban:  { skin: 0xe8c29c, robe: 0x6fa8d1, accent: 0x2f5d82, hat: 0x141414,   special: 'gat' },
      royal:    { skin: 0xeac8a0, robe: 0xc93f3f, accent: 0xf7d05b, hat: 0xf7d05b,   special: 'crown' },
      dokkaebi: { skin: 0x4caf6f, robe: 0x6f3d2a, accent: 0xf7d05b, hat: null,       special: 'horns' },
      gumiho:   { skin: 0xf2c2a6, robe: 0xff8a3c, accent: 0xd85d1a, hat: null,       special: 'tail' },
      tiger:    { skin: 0xf0c070, robe: 0xe67a2e, accent: 0x141414, hat: null,       special: 'stripes' },
      sanshin:  { skin: 0xeac8a0, robe: 0xf6e9a8, accent: 0xb28a2a, hat: null,       special: 'halo' }
    };

    for (const [name, d] of Object.entries(defs)) {
      // 정지/걷기 두 프레임
      this._drawPatient(`patient_${name}_1`, d, 0);
      this._drawPatient(`patient_${name}_2`, d, 1);
      // 걷기 애니메이션 등록
      if (!this.anims.exists(`walk_${name}`)) {
        this.anims.create({
          key: `walk_${name}`,
          frames: [{ key: `patient_${name}_1` }, { key: `patient_${name}_2` }],
          frameRate: 4,
          repeat: -1
        });
      }
    }
  }

  _drawPatient(key, d, frame) {
    const W = 16, H = 20;
    const px = [];

    // 후광(산신령)
    if (d.special === 'halo') {
      this._rect(px, 2, 1, 13, 2, 0xf7d05b);
      this._rect(px, 1, 2, 14, 3, 0xf7d05b);
    }

    // 머리
    this._rect(px, 5, 3, 10, 8, d.skin);
    // 눈
    px.push({ x: 6, y: 5, c: 0x141414 }, { x: 9, y: 5, c: 0x141414 });

    // 모자/특수
    if (d.special === 'gat') {
      this._rect(px, 3, 1, 12, 2, d.hat);
      this._rect(px, 4, 2, 11, 2, d.hat);
    } else if (d.special === 'crown') {
      this._rect(px, 4, 1, 11, 2, d.hat);
      px.push({ x: 5, y: 0, c: d.hat }, { x: 8, y: 0, c: d.hat }, { x: 10, y: 0, c: d.hat });
    } else if (d.special === 'horns') {
      px.push({ x: 4, y: 1, c: d.accent }, { x: 4, y: 2, c: d.accent });
      px.push({ x: 11, y: 1, c: d.accent }, { x: 11, y: 2, c: d.accent });
    } else if (d.special === 'stripes') {
      // 호랑이 얼굴 줄무늬
      this._rect(px, 5, 4, 10, 4, d.accent);
      this._rect(px, 5, 7, 10, 7, d.accent);
    } else if (d.special === 'halo') {
      // 수염
      this._rect(px, 5, 9, 10, 10, 0xffffff);
    }

    // 몸통(도포)
    this._rect(px, 4, 9, 11, 15, d.robe);
    // 허리띠(악센트)
    this._rect(px, 4, 12, 11, 12, d.accent);
    // 소매
    this._rect(px, 3, 10, 3, 13, d.robe);
    this._rect(px, 12, 10, 12, 13, d.robe);
    // 손
    px.push({ x: 3, y: 14, c: d.skin });
    px.push({ x: 12, y: 14, c: d.skin });

    // 다리 — 프레임별로 살짝 어긋남
    if (frame === 0) {
      this._rect(px, 5, 16, 7, 19, d.accent);
      this._rect(px, 8, 16, 10, 19, d.accent);
    } else {
      this._rect(px, 5, 16, 7, 18, d.accent);
      this._rect(px, 8, 17, 10, 19, d.accent);
      px.push({ x: 5, y: 19, c: d.accent }, { x: 10, y: 16, c: d.accent });
    }

    // 구미호 꼬리
    if (d.special === 'tail') {
      px.push({ x: 13, y: 11, c: d.accent }, { x: 14, y: 10, c: d.accent }, { x: 14, y: 11, c: d.accent });
      px.push({ x: 15, y: 9, c: d.robe }, { x: 15, y: 10, c: d.robe });
    }

    this._drawPixels(key, px, W, H, 2);
  }

  // ---------------------------------------------------------------------------
  // 방 텍스처 — 탑다운 뷰, 80×80
  //   [y 0..14]  뒷벽 슬림 띠 (약간 보이는 벽면)
  //   [y 14..72] 바닥 (방 내부를 위에서 내려봄)
  //   [y 72..80] 앞 계단/테두리 (원근 효과)
  // ---------------------------------------------------------------------------
  _createRoomTextures() {
    this._drawRoomMoxa();
    this._drawRoomAcu();
    this._drawRoomHerb();
    this._drawRoomBath();
    this._drawRoomLocked();
  }

  // 탑다운 공통 프레임: 뒷벽 + 바닥 + 앞 테두리
  _drawRoomFrameTD(g, wallDark, wallMid, floorColor, lipColor) {
    // ── 뒷벽 (얇은 띠)
    g.fillStyle(wallDark, 1);  g.fillRect(0, 0, 80, 14);
    g.fillStyle(wallMid, 1);   g.fillRect(0, 10, 80, 5);
    // ── 바닥
    g.fillStyle(floorColor, 1); g.fillRect(0, 14, 80, 58);
    // 좌우 벽 기둥 그림자
    g.fillStyle(wallMid, 0.55); g.fillRect(0, 14, 4, 58); g.fillRect(76, 14, 4, 58);
    // ── 앞 테두리 (원근 그림자)
    g.fillStyle(lipColor, 1);  g.fillRect(0, 72, 80, 8);
  }

  _drawRoomMoxa() {
    const g = this.add.graphics();
    // 뜸방 — 따뜻한 붉은 벽 + 베이지 바닥
    this._drawRoomFrameTD(g, 0xa82010, 0xd04020, 0xf4e4c0, 0xb8905a);
    // 다다미 격자 (바닥 패턴)
    g.fillStyle(0xd8c090, 0.5);
    for (let y = 22; y < 72; y += 18) g.fillRect(4, y, 72, 2);
    g.fillRect(4, 14, 2, 58); g.fillRect(39, 14, 2, 58); g.fillRect(74, 14, 2, 58);
    // 화로 (탑다운 — 원형 그릇)
    g.fillStyle(0x5a3010, 1); g.fillEllipse(40, 47, 34, 22);
    g.fillStyle(0x3a1c08, 1); g.fillEllipse(40, 46, 28, 18);
    g.fillStyle(0xff6010, 1); g.fillEllipse(40, 44, 18, 12);
    g.fillStyle(0xffcc20, 1); g.fillEllipse(40, 43, 10, 7);
    g.fillStyle(0xffffff, 0.7); g.fillEllipse(37, 42, 5, 3);
    // 연기 (위로 퍼짐)
    g.fillStyle(0xeeeeee, 0.7);
    g.fillCircle(32, 30, 5); g.fillCircle(44, 24, 6); g.fillCircle(38, 18, 4);
    g.generateTexture('room_moxa', 80, 80);
    g.destroy();
  }

  _drawRoomAcu() {
    const g = this.add.graphics();
    // 침방 — 파란 벽 + 하늘색 바닥
    this._drawRoomFrameTD(g, 0x0c3880, 0x1858b0, 0xe0eff8, 0x8090b0);
    // 바닥 타일 라인
    g.fillStyle(0xb8d0e8, 0.5);
    for (let y = 22; y < 72; y += 18) g.fillRect(4, y, 72, 2);
    // 치료 매트 (탑다운 — 직사각형)
    g.fillStyle(0x3060a0, 1); g.fillRect(12, 30, 56, 32);
    g.fillStyle(0x5090d0, 1); g.fillRect(14, 32, 52, 28);
    g.fillStyle(0x80b8f0, 1); g.fillRect(16, 34, 48, 4);
    // 침 (위에서 보면 점처럼 보임)
    g.fillStyle(0xd0d0d0, 1);
    for (let i = 0; i < 7; i++) { g.fillRect(18 + i * 7, 38, 2, 8); }
    g.fillStyle(0xffd060, 1);
    for (let i = 0; i < 7; i++) { g.fillRect(18 + i * 7, 38, 2, 3); }
    g.generateTexture('room_acupuncture', 80, 80);
    g.destroy();
  }

  _drawRoomHerb() {
    const g = this.add.graphics();
    // 약방 — 초록 벽 + 연두 바닥
    this._drawRoomFrameTD(g, 0x185010, 0x2a8020, 0xe4f2d8, 0x80a060);
    // 돌바닥 패턴
    g.fillStyle(0xc8e0b0, 0.5);
    for (let y = 22; y < 72; y += 18) g.fillRect(4, y, 72, 2);
    g.fillRect(4, 14, 2, 58); g.fillRect(39, 14, 2, 58); g.fillRect(74, 14, 2, 58);
    // 약솥 (탑다운 — 큰 원)
    g.fillStyle(0x4a3010, 1); g.fillEllipse(40, 48, 44, 30);
    g.fillStyle(0x2a1808, 1); g.fillEllipse(40, 47, 38, 24);
    g.fillStyle(0x507030, 1); g.fillEllipse(40, 45, 30, 18);
    g.fillStyle(0x78b040, 1); g.fillEllipse(38, 44, 16, 10);
    // 약재 (점점이)
    g.fillStyle(0x90d050, 1);
    g.fillRect(34, 42, 4, 4); g.fillRect(42, 43, 3, 3); g.fillRect(38, 40, 3, 3);
    // 증기
    g.fillStyle(0xb0e888, 0.75);
    g.fillCircle(28, 28, 5); g.fillCircle(40, 20, 6); g.fillCircle(52, 26, 4);
    g.generateTexture('room_herb', 80, 80);
    g.destroy();
  }

  _drawRoomBath() {
    const g = this.add.graphics();
    // 약탕방 — 보라 벽 + 라벤더 바닥
    this._drawRoomFrameTD(g, 0x4a1880, 0x7030b0, 0xf0e8ff, 0x9870b0);
    // 돌타일 바닥
    g.fillStyle(0xd0c0e8, 0.5);
    for (let y = 22; y < 72; y += 18) g.fillRect(4, y, 72, 2);
    g.fillRect(4, 14, 2, 58); g.fillRect(74, 14, 2, 58);
    // 온천 욕조 (탑다운 — 큰 직사각형 풀)
    g.fillStyle(0x5020a0, 1); g.fillRect(8, 24, 64, 40);
    g.fillStyle(0x1848c0, 1); g.fillRect(10, 26, 60, 36);
    g.fillStyle(0x2880e0, 1); g.fillRect(10, 26, 60, 6);
    // 물결 무늬
    g.fillStyle(0x70b8ff, 0.9);
    g.fillEllipse(24, 36, 16, 6); g.fillEllipse(46, 42, 14, 5); g.fillEllipse(58, 32, 12, 4);
    // 증기 (보랏빛)
    g.fillStyle(0xe0c8ff, 0.85);
    g.fillCircle(22, 20, 5); g.fillCircle(38, 16, 6); g.fillCircle(56, 19, 4);
    g.fillStyle(0xffffff, 0.5);
    g.fillCircle(24, 18, 3); g.fillCircle(40, 14, 3);
    g.generateTexture('room_bath', 80, 80);
    g.destroy();
  }

  _drawRoomLocked() {
    const g = this.add.graphics();
    // 잠긴 방 — 회색 탑다운
    this._drawRoomFrameTD(g, 0x404040, 0x606060, 0xb0b0a8, 0x707068);
    // 나무 판자 (X자)
    g.fillStyle(0x484030, 0.8);
    g.fillRect(4, 14, 72, 4); g.fillRect(4, 68, 72, 4);
    for (let i = 0; i < 4; i++) g.fillRect(4, 26 + i * 12, 72, 3);
    // 자물쇠 (탑다운 — 원형)
    g.fillStyle(0xc8a840, 1); g.fillEllipse(40, 46, 24, 18);
    g.fillStyle(0xa88030, 1); g.fillEllipse(40, 46, 18, 14);
    g.fillStyle(0x101008, 1); g.fillCircle(40, 46, 4);
    g.fillStyle(0xc8a840, 1); g.lineStyle(4, 0xc8a840, 1); g.strokeCircle(40, 38, 7);
    g.generateTexture('room_locked', 80, 80);
    g.destroy();
  }

  // ---------------------------------------------------------------------------
  // UI 텍스처
  // ---------------------------------------------------------------------------
  _createUiTextures() {
    // 골드 동전
    const g = this.add.graphics();
    g.fillStyle(0xf7d05b); g.fillCircle(8, 8, 7);
    g.fillStyle(0xd9a83a); g.fillCircle(8, 8, 7); g.fillCircle(8, 8, 5);
    g.fillStyle(0xf7d05b); g.fillCircle(8, 8, 5);
    g.fillStyle(0xb07f1e); g.fillRect(7, 4, 2, 8);
    g.fillRect(4, 7, 8, 2);
    g.generateTexture('coin', 16, 16);
    g.destroy();

    // 별 (만족도)
    const gs = this.add.graphics();
    gs.fillStyle(0xf7d05b);
    const cx = 8, cy = 8, r1 = 7, r2 = 3;
    const points = [];
    for (let i = 0; i < 10; i++) {
      const r = (i % 2 === 0) ? r1 : r2;
      const a = -Math.PI / 2 + (i * Math.PI) / 5;
      points.push(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
    }
    gs.fillPoints(points, true);
    gs.generateTexture('star', 16, 16);
    gs.destroy();

    // 분노 말풍선
    const gr = this.add.graphics();
    gr.fillStyle(0xe84a4a);
    gr.fillRect(2, 2, 12, 12);
    gr.fillStyle(0xffffff);
    gr.fillRect(6, 4, 4, 6);
    gr.fillRect(6, 11, 4, 2);
    gr.generateTexture('anger', 16, 16);
    gr.destroy();

    // 치료 게이지 배경/전경 (1x1 사용)
    const g1 = this.add.graphics();
    g1.fillStyle(0x2a1810); g1.fillRect(0, 0, 1, 1);
    g1.generateTexture('px_dark', 1, 1);
    g1.destroy();

    const g2 = this.add.graphics();
    g2.fillStyle(0xffffff); g2.fillRect(0, 0, 1, 1);
    g2.generateTexture('px_white', 1, 1);
    g2.destroy();

    // 대기 줄 팻말 — 기둥(중앙) + 표판(가로 전체)
    const gp = this.add.graphics();
    gp.fillStyle(0x5a3e22); gp.fillRect(6, 0, 4, 24);   // 기둥 중앙
    gp.fillStyle(0xc9a66b); gp.fillRect(0, 0, 16, 10);  // 표판 전폭
    gp.fillStyle(0x3d2818); gp.fillRect(1, 1, 14, 8);   // 표판 내부(어두운 테두리)
    gp.fillStyle(0xf7d05b); gp.fillRect(3, 3, 10, 4);   // 글씨 자리
    gp.generateTexture('signpost', 16, 24);
    gp.destroy();
  }
}
