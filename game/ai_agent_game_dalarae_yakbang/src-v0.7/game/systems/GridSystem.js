import {
  TILE_SIZE, GRID_COLS, GRID_ROWS,
  GRID_ORIGIN_X, GRID_ORIGIN_Y,
  GRID_PIXEL_W, GRID_PIXEL_H,
  GATE_COL, GATE_ROW
} from '../config.js';

// ─── 타일 타입 상수 ────────────────────────────────────
export const TILE_EMPTY   = 'empty';
export const TILE_MARU    = 'maru';
export const TILE_GATE    = 'gate';
// Phase 2+에서 쓰일 건물 타입들 — 지금은 place/remove 훅만 존재
export const TILE_MOXA    = 'moxa';
export const TILE_HAEWOSO = 'haewoso';
export const TILE_ACU     = 'acu';
export const TILE_HERB    = 'herb';
export const TILE_WELL    = 'well';
export const TILE_GUKBAP  = 'gukbap';
export const TILE_PINE    = 'pine';

const TEXTURE_BY_TYPE = {
  [TILE_EMPTY]:   'tex_tile_empty',
  [TILE_MARU]:    'tex_tile_maru',
  [TILE_GATE]:    'tex_gate',
  [TILE_MOXA]:    'tex_building_moxa',
  [TILE_HAEWOSO]: 'tex_building_haewoso',
  [TILE_ACU]:     'tex_building_acu',
  [TILE_HERB]:    'tex_building_herb',
  [TILE_WELL]:    'tex_building_well',
  [TILE_GUKBAP]:  'tex_building_gukbap',
  [TILE_PINE]:    'tex_building_pine'
};

// BootScene 이 `${texKey}_anim` 으로 등록한 애니메이션이 존재하면 sprite 에 재생.
//   image 가 아닌 sprite 를 써야 anim 재생 가능 — _createTileSprites 는 add.sprite 사용.
function _applyAnim(scene, sprite, texKey) {
  if (!sprite || !sprite.play) return;
  const animKey = `${texKey}_anim`;
  if (scene.anims && scene.anims.exists(animKey)) {
    sprite.play(animKey, true);
  } else if (sprite.anims && sprite.anims.isPlaying) {
    sprite.stop();
  }
}

// 환자가 이 타일 위에 '걸어갈 수 있는가' — pathfinding 판정용
export function isWalkableType(type) {
  return type === TILE_MARU || type === TILE_GATE;
}

// 건물 타일(환자가 진입 대상으로 삼는) — Phase 2+
export function isBuildingType(type) {
  return (
    type === TILE_MOXA || type === TILE_HAEWOSO ||
    type === TILE_ACU  || type === TILE_HERB    ||
    type === TILE_WELL || type === TILE_GUKBAP
  );
}

// 카이로식 세로 오버플로 sprite 대상 — 64×128 에셋(Phase 7-B), bottom-anchor 로 타일 바닥에 발끝 고정.
// 건물 6종 + 소나무(장식). 상단 64px 이 위 타일을 덮으므로 row 기반 depth 정렬 필수.
function isTallSprite(type) {
  return isBuildingType(type) || type === TILE_PINE;
}

export class GridSystem {
  constructor(scene) {
    this.scene = scene;
    this.cols = GRID_COLS;
    this.rows = GRID_ROWS;

    // tiles[row][col] = { type, col, row, sprite }
    this.tiles = [];
    for (let r = 0; r < this.rows; r++) {
      const row = [];
      for (let c = 0; c < this.cols; c++) {
        row.push({ type: TILE_EMPTY, col: c, row: r, sprite: null });
      }
      this.tiles.push(row);
    }

    // 대문 고정 배치
    this.tiles[GATE_ROW][GATE_COL].type = TILE_GATE;

    this.events = new Phaser.Events.EventEmitter();

    this._createTileSprites();
    this._bindInput();
  }

  // ─── 좌표 변환 ─────────────────────────────────────
  pixelFromTile(col, row) {
    return {
      x: GRID_ORIGIN_X + col * TILE_SIZE + TILE_SIZE / 2,
      y: GRID_ORIGIN_Y + row * TILE_SIZE + TILE_SIZE / 2
    };
  }

  tileFromPixel(x, y) {
    const col = Math.floor((x - GRID_ORIGIN_X) / TILE_SIZE);
    const row = Math.floor((y - GRID_ORIGIN_Y) / TILE_SIZE);
    if (col < 0 || col >= this.cols) return null;
    if (row < 0 || row >= this.rows) return null;
    return { col, row };
  }

  inBounds(col, row) {
    return col >= 0 && col < this.cols && row >= 0 && row < this.rows;
  }

  get(col, row) {
    return this.inBounds(col, row) ? this.tiles[row][col] : null;
  }

  // ─── 스프라이트 초기화 ────────────────────────────
  // 2레이어 구조: baseSprite(항상 tex_tile_empty, depth 4) + sprite(type-specific, depth 5~10).
  //   건물·마루의 투명 픽셀이 scene bg(어두운 보라) 대신 empty 타일(아이보리 톤)을 드러내도록.
  //   기존 단일 sprite 구조에선 건물 sprite 의 투명부가 scene bg 를 노출 → 갈색 배경 인상.
  _createTileSprites() {
    for (let r = 0; r < this.rows; r++) {
      for (let c = 0; c < this.cols; c++) {
        const t = this.tiles[r][c];
        const { x, y } = this.pixelFromTile(c, r);
        // 베이스(항상 empty): 건물·마루 sprite 의 투명부가 이 위를 노출.
        t.baseSprite = this.scene.add.sprite(x, y, 'tex_tile_empty').setDepth(4);
        const tex = TEXTURE_BY_TYPE[t.type] || 'tex_tile_empty';
        t.sprite = this.scene.add.sprite(x, y, tex);
        this._applySpriteAnchor(t, r);
        _applyAnim(this.scene, t.sprite, tex);
      }
    }
  }

  // 타일 sprite 의 origin/position/depth 를 type 에 맞춰 세팅.
  //   - Tall(건물·소나무): origin=(0.5,1), y=타일 바닥, depth=20+row (아래 행이 앞).
  //   - 일반(마루·공터·대문): origin 기본(0.5,0.5), y=타일 중심, depth 기존값.
  _applySpriteAnchor(tile, r) {
    const sp = tile.sprite;
    if (!sp) return;
    const { x, y } = this.pixelFromTile(tile.col, r);
    if (isTallSprite(tile.type)) {
      sp.setOrigin(0.5, 1);
      sp.x = x;
      sp.y = GRID_ORIGIN_Y + (r + 1) * TILE_SIZE;   // 타일 하단 경계
      sp.setDepth(20 + r);                          // 아래 행이 위 행을 가림
    } else {
      sp.setOrigin(0.5, 0.5);
      sp.x = x; sp.y = y;
      sp.setDepth(tile.type === TILE_GATE ? 10 : 5);
    }
  }

  // 전역 scene.input 을 점유하지 않도록 그리드 영역 Zone 에만 리스너를 붙인다.
  // HUD·메뉴·결산 팝업 등 다른 UI가 자유롭게 input 을 쓸 수 있도록 격리.
  _bindInput() {
    const zone = this.scene.add.zone(
      GRID_ORIGIN_X, GRID_ORIGIN_Y, GRID_PIXEL_W, GRID_PIXEL_H
    ).setOrigin(0, 0).setInteractive();
    zone.setDepth(1); // 타일 스프라이트 위, 커서/HUD 아래
    zone.on('pointerdown', (pointer) => {
      const t = this.tileFromPixel(pointer.worldX, pointer.worldY);
      if (!t) return;
      // 우클릭은 철거, 좌/중클릭은 설치 — Phaser pointer.button: 0=left, 2=right.
      const button = pointer.button === 2 ? 'right' : 'left';
      this.events.emit('tile_clicked', this.tiles[t.row][t.col], button);
    });
    zone.on('pointermove', (pointer) => {
      const t = this.tileFromPixel(pointer.worldX, pointer.worldY);
      if (!t) { this.events.emit('tile_hover', null); return; }
      this.events.emit('tile_hover', this.tiles[t.row][t.col]);
    });
    zone.on('pointerout', () => this.events.emit('tile_hover', null));
    this.inputZone = zone;
  }

  // ─── 타일 변경 ─────────────────────────────────────
  // 대문 타일은 변경 불가.
  setType(col, row, type) {
    const t = this.get(col, row);
    if (!t) return false;
    if (t.type === TILE_GATE) return false;

    t.type = type;
    const tex = TEXTURE_BY_TYPE[type];
    if (tex && t.sprite) {
      t.sprite.setTexture(tex);
      this._applySpriteAnchor(t, row);
      _applyAnim(this.scene, t.sprite, tex);
    }
    this.events.emit('tile_changed', t);
    return true;
  }

  // 씬 종료 시 호출 — EventEmitter·Zone 구독을 전부 해제
  destroy() {
    if (this.events) {
      this.events.removeAllListeners();
      this.events = null;
    }
    if (this.inputZone) {
      this.inputZone.removeAllListeners();
      this.inputZone.destroy();
      this.inputZone = null;
    }
    // 타일 스프라이트는 씬이 정리하지만 명시적 참조 해제
    for (let r = 0; r < this.rows; r++) {
      for (let c = 0; c < this.cols; c++) {
        this.tiles[r][c].sprite = null;
        this.tiles[r][c].baseSprite = null;
      }
    }
  }

  // 유틸: 특정 타입 타일 위치들 모으기
  listByType(type) {
    const out = [];
    for (let r = 0; r < this.rows; r++) {
      for (let c = 0; c < this.cols; c++) {
        if (this.tiles[r][c].type === type) out.push({ col: c, row: r });
      }
    }
    return out;
  }
}
