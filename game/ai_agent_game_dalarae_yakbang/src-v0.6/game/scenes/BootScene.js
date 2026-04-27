// 런타임 생성 텍스처(Graphics API) + PNG 스프라이트시트(캐릭터) 하이브리드.
// 캐릭터 스프라이트: scripts/palette_transfer.py (connected-component 재조립 + 12색 quantize + NEAREST)
//   로 원본을 64×64 프레임으로 변환한 것. Phase 7-A 적용.
//   RPG Maker MV 포맷(3열×4행) — 행 0=down, 1=left, 2=right, 3=up.
//   만약 실제 좌/우가 반전돼 보이면 CHAR_DIRS 배열에서 left/right 스왑.

const CHAR_SHEETS = [
  'char_nobi_m', 'char_nobi_f',
  'char_nongmin_m',
  'char_sangin_m', 'char_sangin_f',
  'char_seonbi_m', 'char_seonbi_f',
  'char_yangban_m', 'char_yangban_f',
  'char_staff',     // 무수리 — assets/chars/staff.png
  'char_uinyeo'     // 의녀 — assets/chars/uinyeo.png
];
const CHAR_FRAME_W = 64;
const CHAR_FRAME_H = 64;
const CHAR_DIRS = ['down', 'left', 'right', 'up'];

// 유저 공급 건물 에셋 매니페스트 (scripts/resize_buildings.py 출력과 동기).
// procedural texture(tex_building_*) 를 동일 key 로 덮어씀. 누락 건물(well/herb)은
// 기존 procedural 유지 — _createV06Textures 가 textures.exists 로 skip 판정.
// spritesheet 타입은 _createBuildingAnims 에서 `${key}_anim` 으로 등록.
// 건물/나무 스프라이트는 카이로식 오버플로를 위해 64×128 (Phase 7-B). GridSystem 이 bottom-anchor 로 배치.
// 단일 image 타입(acu/haewoso/maru)은 Phaser 가 원본 크기대로 로드 → 별도 fw/fh 불필요.
const BUILDING_ASSETS = [
  { key: 'tex_building_moxa',    file: 'moxa.png',    type: 'spritesheet', frames: 16, fw: 64, fh: 128 },
  { key: 'tex_building_acu',     file: 'acu.png',     type: 'image' },
  { key: 'tex_building_haewoso', file: 'haewoso.png', type: 'image' },
  { key: 'tex_building_gukbap',  file: 'gukbap.png',  type: 'spritesheet', frames: 12, fw: 64, fh: 128 },
  { key: 'tex_building_pine',    file: 'pine.png',    type: 'spritesheet', frames: 21, fw: 64, fh: 128 },
  { key: 'tex_building_well',    file: 'well.png',    type: 'spritesheet', frames: 5,  fw: 64, fh: 128 },
  { key: 'tex_tile_maru',        file: 'maru.png',    type: 'image' }   // 강마루 바닥 타일 교체
];

export class BootScene extends Phaser.Scene {
  constructor() {
    super({ key: 'BootScene' });
  }

  preload() {
    // 캐릭터 스프라이트시트 로드 — key 는 파일명에서 char_ 접두사 제외 부분.
    for (const key of CHAR_SHEETS) {
      const fname = key.replace('char_', '') + '.png';
      this.load.spritesheet(key, `assets/chars/${fname}`, {
        frameWidth: CHAR_FRAME_W, frameHeight: CHAR_FRAME_H
      });
    }
    // 건물 PNG/스프라이트시트. procedural(_createV06Textures) 생성 전에 먼저 로드돼
    //   동일 key 를 차지. _createV06Textures 의 textures.exists 가드로 중복 생성 skip.
    for (const a of BUILDING_ASSETS) {
      const path = `assets/buildings/${a.file}`;
      if (a.type === 'spritesheet') {
        this.load.spritesheet(a.key, path, { frameWidth: a.fw, frameHeight: a.fh });
      } else {
        this.load.image(a.key, path);
      }
    }
  }

  create() {
    this._createPatientTextures();
    this._createRoomTextures();
    this._createUiTextures();
    this._createV06Textures();
    this._createCharAnims();
    this._createBuildingAnims();

    this.scene.start('TitleScene');
  }

  // 애니메이션 건물(gukbap/pine) 의 걸음 애니 등록.
  //   키 포맷: `${texKey}_anim` 예: tex_building_gukbap_anim
  //   GridSystem 이 타일에 sprite 를 배치한 뒤 해당 anim 존재 시 재생.
  _createBuildingAnims() {
    for (const a of BUILDING_ASSETS) {
      if (a.type !== 'spritesheet') continue;
      if (!this.textures.exists(a.key)) continue;
      const animKey = `${a.key}_anim`;
      if (this.anims.exists(animKey)) continue;
      this.anims.create({
        key: animKey,
        frames: this.anims.generateFrameNumbers(a.key, { start: 0, end: a.frames - 1 }),
        frameRate: 8,
        repeat: -1
      });
    }
  }

  // 각 스프라이트시트에 대해 4방향 walk 애니메이션 등록.
  //   키 포맷: `${sheetKey}_${dir}` 예: char_nobi_m_down
  //   프레임: 각 행의 3컬럼을 6fps 로 반복 재생. 정지 시 가운데 프레임(col=1)으로 복귀.
  _createCharAnims() {
    for (const key of CHAR_SHEETS) {
      if (!this.textures.exists(key)) continue;  // 로드 실패 시 안전
      CHAR_DIRS.forEach((dir, row) => {
        const animKey = `${key}_${dir}`;
        if (this.anims.exists(animKey)) return;
        this.anims.create({
          key: animKey,
          frames: this.anims.generateFrameNumbers(key, { start: row * 3, end: row * 3 + 2 }),
          frameRate: 6,
          repeat: -1
        });
      });
    }
  }

  // ---------------------------------------------------------------------------
  // v0.6 — 그리드 타일·대문·마루 텍스처 (64×64)
  // ---------------------------------------------------------------------------
  _createV06Textures() {
    // ── 빈 타일 (공터: 아이보리 톤 — 유저 지시 "뒷배경 아이보리")
    //   건물 sprite 투명부가 이 타일을 드러냄(베이스 레이어). 너무 진하면 건물 실루엣이
    //   오염 — 부드러운 크림색 + 아주 옅은 결/테두리만 유지.
    const e = this.add.graphics();
    e.fillStyle(0xf2e8cc, 1); e.fillRect(0, 0, 64, 64);
    e.fillStyle(0xd8c898, 0.25);
    for (let y = 4; y < 64; y += 8) {
      for (let x = (y % 16 ? 2 : 6); x < 62; x += 12) e.fillRect(x, y, 3, 1);
    }
    // 테두리 — 아주 옅은 라인(격자 구조 가시화용, 건물 투명부 오염 최소화)
    e.fillStyle(0xb09868, 0.2);
    e.fillRect(0, 0, 64, 1); e.fillRect(0, 63, 64, 1);
    e.fillRect(0, 0, 1, 64); e.fillRect(63, 0, 1, 64);
    e.generateTexture('tex_tile_empty', 64, 64);
    e.destroy();

    // ── 마루 (통행로: 나무 판자) — 강마루.png 로딩 시 skip
    if (!this.textures.exists('tex_tile_maru')) {
    const m = this.add.graphics();
    m.fillStyle(0xc88a4a, 1); m.fillRect(0, 0, 64, 64);
    // 나뭇결 (세로)
    m.fillStyle(0xa76a32, 0.35);
    for (let x = 6; x < 64; x += 12) m.fillRect(x, 0, 1, 64);
    // 판자 이음새 (가로)
    m.fillStyle(0x6e4420, 0.7);
    m.fillRect(0, 20, 64, 2);
    m.fillRect(0, 42, 64, 2);
    // 옅은 하이라이트 (위쪽)
    m.fillStyle(0xe2a666, 0.4);
    m.fillRect(0, 0, 64, 2);
    m.fillRect(0, 22, 64, 1);
    m.fillRect(0, 44, 64, 1);
    m.generateTexture('tex_tile_maru', 64, 64);
    m.destroy();
    }

    // ── 대문 (임시 플레이스홀더 — 추후 PNG 교체 예정)
    const g = this.add.graphics();
    // 바탕 (하늘 느낌 — 대문 밖이 살짝 보임)
    g.fillStyle(0x3a2818, 1); g.fillRect(0, 0, 64, 64);
    // 지붕 (붉은 기와)
    g.fillStyle(0xa82018, 1); g.fillRect(2, 4, 60, 14);
    g.fillStyle(0xd8301c, 1); g.fillRect(2, 4, 60, 5);
    g.fillStyle(0x601208, 1); g.fillRect(2, 16, 60, 2);
    // 기와 결
    g.fillStyle(0x8a1810, 0.7);
    for (let x = 4; x < 60; x += 8) g.fillRect(x, 6, 1, 10);
    // 기둥 좌/우
    g.fillStyle(0x5a2e18, 1); g.fillRect(4, 18, 8, 42); g.fillRect(52, 18, 8, 42);
    g.fillStyle(0x3a1a0c, 1); g.fillRect(4, 18, 8, 2);  g.fillRect(52, 18, 8, 2);
    // 문짝 (가운데, 열린 듯 어두움)
    g.fillStyle(0x2a160a, 1); g.fillRect(12, 20, 40, 40);
    g.fillStyle(0x18090a, 1); g.fillRect(14, 22, 36, 36);
    // 문고리 (금색)
    g.fillStyle(0xf7d05b, 1);
    g.fillCircle(24, 42, 2); g.fillCircle(40, 42, 2);
    // 문턱
    g.fillStyle(0x18090a, 1); g.fillRect(2, 60, 60, 4);
    g.generateTexture('tex_gate', 64, 64);
    g.destroy();

    // ── 하이라이트 커서 (마우스 hover 용)
    const h = this.add.graphics();
    h.lineStyle(3, 0xf7d05b, 1);
    h.strokeRect(2, 2, 60, 60);
    h.generateTexture('tex_tile_hover', 64, 64);
    h.destroy();

    // ── 스폰 포인트 마커 (대문 바로 위 타일 오버레이)
    const s = this.add.graphics();
    s.fillStyle(0xff8a3c, 0.25); s.fillCircle(32, 32, 16);
    s.lineStyle(2, 0xff8a3c, 0.9); s.strokeCircle(32, 32, 14);
    s.generateTexture('tex_spawn_mark', 64, 64);
    s.destroy();

    // ── 테스트 워커 (Phase 1-C 테스트용 더미)
    const w = this.add.graphics();
    w.fillStyle(0xf7d05b, 1); w.fillCircle(12, 12, 10);
    w.fillStyle(0x8b4a10, 1); w.fillCircle(12, 12, 6);
    w.generateTexture('tex_walker', 24, 24);
    w.destroy();

    // ── 직원 스프라이트 (Phase 7-D 시각 구분) 4종 공통 템플릿으로 색만 바꿔 생성.
    //   역할별 색 구분: musuri 남색(잡역)·chimgu 녹색(침 조수)·uinyeo 자주(치료 조수)·uigwan 흑갈+금띠(의관).
    //   24×24 정사각, 환자 티어(원형 캐릭터)와 비슷한 크기지만 사각 저고리로 실루엣 대조.
    const drawStaff = (key, bodyColor, apronColor, hairColor, accentColor, accentType) => {
      const g = this.add.graphics();
      // 몸(저고리)
      g.fillStyle(bodyColor, 1); g.fillRect(5, 10, 14, 12);
      // 앞치마/띠
      g.fillStyle(apronColor, 1);
      if (accentType === 'belt') {
        // 도포 스타일 — 허리띠만 가로로
        g.fillRect(5, 16, 14, 3);
      } else {
        g.fillRect(8, 14, 8, 8);
      }
      // 액센트 (띠 금색·침 은빛·계급장 등)
      if (accentColor != null) {
        if (accentType === 'needle') {
          // 침: 가슴에 세로 은색 획
          g.fillStyle(accentColor, 1); g.fillRect(11, 12, 2, 5);
        } else if (accentType === 'cross') {
          // 의녀: 가슴에 작은 ×(붉은) 무늬
          g.fillStyle(accentColor, 1); g.fillRect(11, 15, 2, 2);
        } else if (accentType === 'belt') {
          // 금색 버클
          g.fillStyle(accentColor, 1); g.fillRect(11, 17, 2, 2);
        }
      }
      // 머리(피부)
      g.fillStyle(0xf2d3a8, 1); g.fillCircle(12, 7, 5);
      // 머리카락
      g.fillStyle(hairColor, 1); g.fillRect(7, 2, 10, 4); g.fillRect(6, 4, 12, 2);
      // 테두리
      g.lineStyle(1, 0x1a1a1a, 1); g.strokeRect(5, 10, 14, 12);
      g.generateTexture(`tex_staff_${key}`, 24, 24);
      g.destroy();
    };
    drawStaff('musuri', 0x1f3a7a, 0xf4f4e8, 0x2a1a10, null,       null);
    drawStaff('chimgu', 0x2a6040, 0xf4f4e8, 0x2a1a10, 0xd0d8e0,   'needle');
    drawStaff('uinyeo', 0xa03858, 0xf4f4e8, 0x2a1a10, 0xd03030,   'cross');
    drawStaff('uigwan', 0x2a1a10, 0x3a2a18, 0x1a1008, 0xd8a030,   'belt');

    // ── 뜸방 건물 (붉은 기와 + 크림색 벽 + 굴뚝 연기)
    // 마루 실루엣과 명확히 구분되도록 지붕·연기·창문 추가 (K1 주의)
    // BUILDING_ASSETS 로딩 시 이 블록은 skip — 로드된 PNG 우선.
    if (!this.textures.exists('tex_building_moxa')) {
    const mo = this.add.graphics();
    // 기반 — 흙 바닥 (빈 타일과 살짝 다른 톤)
    mo.fillStyle(0xb89868, 1); mo.fillRect(0, 0, 64, 64);
    // 건물 벽 (크림색)
    mo.fillStyle(0xf2e0b8, 1); mo.fillRect(8, 22, 48, 36);
    mo.fillStyle(0xd8c090, 1); mo.fillRect(8, 22, 48, 3);
    mo.fillStyle(0xb89868, 0.5); mo.fillRect(8, 55, 48, 3);
    // 지붕 (붉은 기와)
    mo.fillStyle(0xa82018, 1); mo.fillRect(4, 14, 56, 12);
    mo.fillStyle(0xd8301c, 1); mo.fillRect(4, 14, 56, 5);
    mo.fillStyle(0x601208, 1); mo.fillRect(4, 25, 56, 2);
    // 기와 결
    mo.fillStyle(0x8a1810, 0.7);
    for (let x = 6; x < 60; x += 6) mo.fillRect(x, 16, 1, 9);
    // 지붕 처마 끝 그림자
    mo.fillStyle(0x3a1008, 1);
    mo.fillRect(2, 14, 2, 3); mo.fillRect(60, 14, 2, 3);
    // 문 (가운데)
    mo.fillStyle(0x4a2a10, 1); mo.fillRect(26, 38, 12, 20);
    mo.fillStyle(0x2a1608, 1); mo.fillRect(27, 39, 10, 18);
    mo.fillStyle(0xf7d05b, 1); mo.fillRect(29, 48, 1, 1);
    // 창문 좌우 (격자)
    mo.fillStyle(0x8090b0, 1); mo.fillRect(12, 32, 10, 8); mo.fillRect(42, 32, 10, 8);
    mo.fillStyle(0xc0d0e8, 1); mo.fillRect(13, 33, 8, 6); mo.fillRect(43, 33, 8, 6);
    mo.fillStyle(0x4a2a10, 1);
    mo.fillRect(16, 32, 2, 8); mo.fillRect(46, 32, 2, 8);
    mo.fillRect(12, 35, 10, 1); mo.fillRect(42, 35, 10, 1);
    // 굴뚝 (우상단)
    mo.fillStyle(0x404040, 1); mo.fillRect(46, 6, 8, 10);
    mo.fillStyle(0x202020, 1); mo.fillRect(46, 6, 8, 2);
    // 연기
    mo.fillStyle(0xdddddd, 0.8);
    mo.fillCircle(50, 4, 3); mo.fillCircle(54, 1, 2);
    mo.fillStyle(0xffffff, 0.6); mo.fillCircle(48, 2, 2);
    mo.generateTexture('tex_building_moxa', 64, 64);
    mo.destroy();
    }

    // ── 해우소(haewoso) 건물 — 짙은 청록 기와 + 나무 벽 + 작은 창
    if (!this.textures.exists('tex_building_haewoso')) {
    const ha = this.add.graphics();
    ha.fillStyle(0xb89868, 1); ha.fillRect(0, 0, 64, 64);
    ha.fillStyle(0x8a6434, 1); ha.fillRect(8, 22, 48, 36);          // 나무 벽
    ha.fillStyle(0x6a4a24, 1); ha.fillRect(8, 22, 48, 3);
    ha.fillStyle(0x4a3018, 1); ha.fillRect(8, 55, 48, 3);
    ha.fillStyle(0x204838, 1); ha.fillRect(4, 14, 56, 12);          // 청록 지붕
    ha.fillStyle(0x307060, 1); ha.fillRect(4, 14, 56, 5);
    ha.fillStyle(0x0e2820, 1); ha.fillRect(4, 25, 56, 2);
    ha.fillStyle(0x1a3830, 0.7);
    for (let x = 6; x < 60; x += 6) ha.fillRect(x, 16, 1, 9);
    ha.fillStyle(0x2a1808, 1); ha.fillRect(28, 38, 8, 20);          // 좁은 문
    ha.fillStyle(0x4a2a10, 1); ha.fillRect(29, 39, 6, 18);
    ha.fillStyle(0xd0e8c0, 1); ha.fillRect(18, 36, 6, 6); ha.fillRect(40, 36, 6, 6); // 창
    ha.fillStyle(0x4a2a10, 1); ha.fillRect(20, 36, 2, 6); ha.fillRect(42, 36, 2, 6);
    ha.generateTexture('tex_building_haewoso', 64, 64);
    ha.destroy();
    }

    // ── 침방(acu) 건물 — 푸른 기와 + 침 패널 창
    if (!this.textures.exists('tex_building_acu')) {
    const ac = this.add.graphics();
    ac.fillStyle(0xb89868, 1); ac.fillRect(0, 0, 64, 64);
    ac.fillStyle(0xeae0c8, 1); ac.fillRect(8, 22, 48, 36);
    ac.fillStyle(0xc8bc9a, 1); ac.fillRect(8, 22, 48, 3);
    ac.fillStyle(0x1a3878, 1); ac.fillRect(4, 14, 56, 12);
    ac.fillStyle(0x3068b8, 1); ac.fillRect(4, 14, 56, 5);
    ac.fillStyle(0x0a1c40, 1); ac.fillRect(4, 25, 56, 2);
    ac.fillStyle(0x0a1c40, 0.7);
    for (let x = 6; x < 60; x += 6) ac.fillRect(x, 16, 1, 9);
    ac.fillStyle(0x4a2a10, 1); ac.fillRect(26, 38, 12, 20);
    ac.fillStyle(0x2a1608, 1); ac.fillRect(27, 39, 10, 18);
    ac.fillStyle(0xc0d0e8, 1); ac.fillRect(12, 32, 10, 8); ac.fillRect(42, 32, 10, 8);
    ac.fillStyle(0xffd060, 1);
    ac.fillRect(13, 34, 1, 4); ac.fillRect(16, 34, 1, 4); ac.fillRect(19, 34, 1, 4);
    ac.fillRect(43, 34, 1, 4); ac.fillRect(46, 34, 1, 4); ac.fillRect(49, 34, 1, 4);
    ac.generateTexture('tex_building_acu', 64, 64);
    ac.destroy();
    }

    // ── 약방(herb) 건물 — 녹색 기와 + 약재 항아리. 64×128 bottom-align (상단 64px 투명, 오버플로 영역).
    const HB_OFF = 64;  // 콘텐츠 하단 정렬용 y offset (Phase 7-B: 32 → 64)
    const hb = this.add.graphics();
    hb.fillStyle(0xe8e0b8, 1); hb.fillRect(8, 22 + HB_OFF, 48, 36);
    hb.fillStyle(0xc8b888, 1); hb.fillRect(8, 22 + HB_OFF, 48, 3);
    hb.fillStyle(0x184a18, 1); hb.fillRect(4, 14 + HB_OFF, 56, 12);
    hb.fillStyle(0x308030, 1); hb.fillRect(4, 14 + HB_OFF, 56, 5);
    hb.fillStyle(0x082008, 1); hb.fillRect(4, 25 + HB_OFF, 56, 2);
    hb.fillStyle(0x082008, 0.7);
    for (let x = 6; x < 60; x += 6) hb.fillRect(x, 16 + HB_OFF, 1, 9);
    hb.fillStyle(0x4a2a10, 1); hb.fillRect(26, 38 + HB_OFF, 12, 20);
    hb.fillStyle(0x2a1608, 1); hb.fillRect(27, 39 + HB_OFF, 10, 18);
    hb.fillStyle(0x8a5020, 1); hb.fillEllipse(18, 40 + HB_OFF, 10, 12);
    hb.fillStyle(0x6a3810, 1); hb.fillEllipse(18, 43 + HB_OFF, 10, 8);
    hb.fillStyle(0x90d050, 1); hb.fillEllipse(18, 36 + HB_OFF, 6, 4);
    hb.fillStyle(0x8a5020, 1); hb.fillEllipse(46, 40 + HB_OFF, 10, 12);
    hb.fillStyle(0x6a3810, 1); hb.fillEllipse(46, 43 + HB_OFF, 10, 8);
    hb.fillStyle(0xd04040, 1); hb.fillEllipse(46, 36 + HB_OFF, 6, 4);
    hb.generateTexture('tex_building_herb', 64, 128);
    hb.destroy();

    // ── 우물(well) — PNG(우물.gif) 미로드 시에만 procedural 사용
    if (!this.textures.exists('tex_building_well')) {
    const wl = this.add.graphics();
    wl.fillStyle(0xb89868, 1); wl.fillRect(0, 0, 64, 64);
    wl.fillStyle(0x706860, 1); wl.fillRect(10, 14, 44, 44);            // 바깥 돌담
    wl.fillStyle(0x544a40, 1); wl.fillRect(10, 14, 44, 4);
    wl.fillStyle(0x8a8278, 1);
    for (let y = 18; y < 54; y += 8) {
      for (let x = 12; x < 52; x += 10) {
        wl.fillRect(x + ((y/8)%2 ? 0 : 4), y, 5, 4);
      }
    }
    wl.fillStyle(0x2058a0, 1); wl.fillRect(16, 22, 32, 28);            // 수면
    wl.fillStyle(0x3080d0, 1); wl.fillRect(16, 22, 32, 6);
    wl.fillStyle(0x70b8ff, 0.8); wl.fillEllipse(24, 32, 10, 3); wl.fillEllipse(40, 38, 8, 3);
    wl.fillStyle(0xffffff, 0.6); wl.fillEllipse(22, 28, 6, 2);
    // 지지대(도르래)
    wl.fillStyle(0x4a2a10, 1); wl.fillRect(20, 8, 2, 10); wl.fillRect(42, 8, 2, 10);
    wl.fillRect(18, 6, 28, 2);
    wl.fillStyle(0xf7d05b, 1); wl.fillCircle(32, 7, 2);
    wl.generateTexture('tex_building_well', 64, 64);
    wl.destroy();
    }

    // ── 국밥집(gukbap) — 간이 플레이스홀더 (Phase 3-C 우선순위 아님)
    if (!this.textures.exists('tex_building_gukbap')) {
    const gk = this.add.graphics();
    gk.fillStyle(0xb89868, 1); gk.fillRect(0, 0, 64, 64);
    gk.fillStyle(0xe8d098, 1); gk.fillRect(8, 22, 48, 36);
    gk.fillStyle(0xa87818, 1); gk.fillRect(4, 14, 56, 12);
    gk.fillStyle(0xd89838, 1); gk.fillRect(4, 14, 56, 5);
    gk.fillStyle(0x4a2a10, 1); gk.fillRect(26, 38, 12, 20);
    gk.fillStyle(0x2a1608, 1); gk.fillRect(27, 39, 10, 18);
    gk.fillStyle(0xf7d05b, 1); gk.fillRect(16, 32, 32, 4);           // 간판
    gk.fillStyle(0x8a5020, 1); gk.fillEllipse(32, 46, 20, 8);         // 솥
    gk.fillStyle(0xffcc66, 0.85); gk.fillEllipse(32, 44, 16, 5);
    gk.generateTexture('tex_building_gukbap', 64, 64);
    gk.destroy();
    }

    // ── 선택(select) 도구 아이콘 — 손가락 포인터
    const sl = this.add.graphics();
    sl.fillStyle(0xfdf0d0, 1); sl.fillRect(22, 8, 6, 18);              // 손가락 기둥
    sl.fillStyle(0xfdf0d0, 1); sl.fillRect(16, 18, 18, 12);            // 손바닥
    sl.fillStyle(0xc8a060, 1);                                         // 테두리
    sl.fillRect(22, 8, 6, 2); sl.fillRect(22, 24, 6, 2);
    sl.fillRect(16, 18, 2, 12); sl.fillRect(32, 18, 2, 12);
    sl.fillRect(16, 28, 18, 2);
    sl.lineStyle(2, 0x804020, 1); sl.strokeRect(14, 8, 22, 24);
    sl.generateTexture('tex_tool_select', 48, 48);
    sl.destroy();

    // ── 뱃지: 직원 미배정 경고 (! 노란 원)
    const bn = this.add.graphics();
    bn.fillStyle(0x000000, 0.35); bn.fillCircle(10, 10, 9);           // 그림자
    bn.fillStyle(0xf7d05b, 1); bn.fillCircle(9, 9, 8);
    bn.fillStyle(0x804000, 1); bn.fillRect(8, 4, 2, 7); bn.fillRect(8, 12, 2, 2);
    bn.lineStyle(1, 0x805020, 1); bn.strokeCircle(9, 9, 8);
    bn.generateTexture('tex_badge_no_staff', 20, 20);
    bn.destroy();

    // ── 뱃지: 약방+우물 활성 (물방울)
    const bw = this.add.graphics();
    bw.fillStyle(0x000000, 0.35); bw.fillCircle(10, 10, 9);
    bw.fillStyle(0x3080d0, 1); bw.fillCircle(9, 10, 7);
    bw.fillStyle(0x70b8ff, 1); bw.fillEllipse(7, 8, 5, 4);
    bw.fillStyle(0xffffff, 0.9); bw.fillCircle(7, 7, 2);
    bw.lineStyle(1, 0x1848a0, 1); bw.strokeCircle(9, 10, 7);
    bw.generateTexture('tex_badge_well', 20, 20);
    bw.destroy();

    // ── Phase 6 K1: 도트 하트 (소나무 인접 보너스 가시화). 24×24 픽셀, 한정 팔레트 4색.
    // Medeiros P1/P2: 실루엣 가독성 + 팔레트 통일. 중앙 반짝(#ffe0e8) + 본체(#ff4060)
    //   + 외곽(#800018) + 하이라이트(#ffa0b0). 그림자 깔지 않음 — 떠오르는 UI 요소.
    const heart = this.add.graphics();
    const H = {
      outline: 0x800018,
      body:    0xff4060,
      light:   0xffa0b0,
      shine:   0xffe0e8
    };
    // 24×24 픽셀 하트 — 2px 단위로 블록화 (가독성 우선, 도트감 유지).
    // 형태: 전형적 8bit 게임 하트. y=2~6 두 언덕, y=6~20 삼각형.
    const hpx = [
      // row, col (0~23) in 2px scale → draw 2×2 filled block.
      // outline layer.
      ...[[4,2],[6,2],[2,4],[8,4],[14,4],[20,4],[2,6],[10,6],[12,6],[20,6],[2,8],[20,8],[4,10],[18,10],[6,12],[16,12],[8,14],[14,14],[10,16],[12,16],[10,18]].map(([x,y])=>({x,y,c:H.outline})),
      // body.
      ...[[6,4],[4,6],[6,6],[8,6],[14,6],[16,6],[18,6],[4,8],[6,8],[8,8],[10,8],[12,8],[14,8],[16,8],[18,8],[6,10],[8,10],[10,10],[12,10],[14,10],[16,10],[8,12],[10,12],[12,12],[14,12],[10,14],[12,14]].map(([x,y])=>({x,y,c:H.body})),
      // light accent (위 언덕 상단).
      ...[[4,4],[16,4]].map(([x,y])=>({x,y,c:H.light})),
      // shine (작은 반짝).
      ...[[6,8]].map(([x,y])=>({x,y,c:H.shine}))
    ];
    for (const px of hpx) heart.fillStyle(px.c, 1).fillRect(px.x, px.y, 2, 2);
    heart.generateTexture('tex_pine_heart', 24, 24);
    heart.destroy();
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
