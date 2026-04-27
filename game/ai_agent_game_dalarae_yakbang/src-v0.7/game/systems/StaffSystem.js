import { BALANCE } from '../config.js';
import { TILE_EMPTY, TILE_MARU } from './GridSystem.js';
import { getBuildingByTileType, getBuildingByKey } from './BuildingRegistry.js';

// Phase 3-B 직원 시스템 골격.
// · 4종(musuri/chimgu/uinyeo/uigwan) — BALANCE.staff 참조.
// · hire(type, col, row): 지정 maru 타일에 스폰. 성공 시 staff 엔트리 반환.
// · assign(staff, col, row): Manhattan radius 1, covers 일치, maxRooms/중복 가드.
// · isRoomCovered(col, row): PatientSystem 이 `_beginUsing` 에서 게이트로 사용.
// · getMonthlyWage(): 고용 중 staff.wage 합. 월간 결산에서 차감.
// · tile_changed 구독: 배정 방이 퇴행/이탈되면 entry 자동 정리.
//
// 설계 메모:
// · staff 엔트리는 hire 시 스펙 스냅샷 복사 → 향후 업그레이드 대비.
// · 거리 함수는 Manhattan — 환자의 _adjacentReachableMaru(4방향)와 일관.
// · sprite 는 maru 타일 중앙 위에 살짝 오프셋, depth 18 (환자=20 보다 뒤).

const STAFF_SPRITE_DEPTH = 18;
// Phase 7-D: 유저 공급 PNG(무수리/의녀) + 색 틴트로 4종 시각 구분.
//   musuri: char_staff 원색(파란 저고리 원본).
//   chimgu: char_staff + 녹색 틴트 — 침 조수 구분.
//   uinyeo: char_uinyeo 원색(분홍 저고리 원본).
//   uigwan: char_staff + 금색 틴트 — 의관(남성 PNG 부재 → 임시). 실제 의관 PNG 공급 시 교체.
//   isSheet=true 면 RPG Maker 4방향 애니(walk/idle) 사용. false 면 단일 image(구 procedural).
const STAFF_CONFIG = {
  musuri: { tex: 'char_staff',   isSheet: true, tint: null },
  chimgu: { tex: 'char_staff',   isSheet: true, tint: 0x80e0a0 },
  uinyeo: { tex: 'char_uinyeo',  isSheet: true, tint: null },
  uigwan: { tex: 'char_staff',   isSheet: true, tint: 0xffd060 }
};
// RPG Maker MV 4×3: 행=down/left/right/up, 열=step1/idle/step2. idle = row*3+1.
const DIR_ROW = { down: 0, left: 1, right: 2, up: 3 };

export class StaffSystem {
  constructor(scene, grid) {
    this.scene = scene;
    this.grid = grid;
    this.events = new Phaser.Events.EventEmitter();
    this.staff = [];

    this._onTileChanged = this._onTileChanged.bind(this);
    this.grid.events.on('tile_changed', this._onTileChanged);
  }

  // 고용. col/row 는 staff 본체가 설 maru 타일. 가격은 호출측에서 gold 차감하고 hire 호출.
  // 반환: 성공 시 staff entry, 실패 시 null.
  hire(type, col, row) {
    const spec = BALANCE.staff[type];
    if (!spec) return null;
    if (!this.grid.inBounds(col, row)) return null;
    const tile = this.grid.get(col, row);
    if (!tile || tile.type !== TILE_MARU) return null;
    // 동일 타일 중복 거주 방지 — 한 maru 에 직원 1명.
    if (this.staff.some((s) => s.col === col && s.row === row)) return null;

    const cfg = STAFF_CONFIG[type] || STAFF_CONFIG.musuri;
    const tex = this.scene.textures.exists(cfg.tex) ? cfg.tex : 'tex_staff_musuri';
    const { x, y } = this.grid.pixelFromTile(col, row);
    // 64×64 스프라이트 기준 타일 중심 배치 — 환자(depth 40) 아래에 깔림(18).
    const sprite = this.scene.add.sprite(x, y - 4, tex).setDepth(STAFF_SPRITE_DEPTH);
    if (cfg.isSheet) sprite.setFrame(DIR_ROW.down * 3 + 1);  // idle 중간 프레임
    if (cfg.tint) sprite.setTint(cfg.tint);

    const entry = {
      type, col, row, sprite,
      tex, isSheet: cfg.isSheet, facing: 'down',
      spec: { ...spec },
      assignedRooms: [],
      // Phase 7-D 순찰 상태 — _tickPatrol 에서 소비.
      //   state: 'idle' (대기중 waitMs 감소) | 'moving' (targetX/Y 로 보간).
      patrol: { state: 'idle', waitMs: 800 + Math.random() * 1200, idx: 0, targetX: 0, targetY: 0 }
    };
    this.staff.push(entry);
    this.events.emit('staff_hired', { staff: entry });
    return entry;
  }

  // 치료방 배정. 게이트:
  //   1) staff 존재 + building.category === 'treat' + covers 일치
  //   2) Manhattan distance == 1
  //   3) maxRooms 미만 + 중복 배정 불가
  // 반환: { ok: bool, reason?: string }
  assign(staff, col, row) {
    if (!staff || !this.staff.includes(staff)) return { ok: false, reason: 'invalid' };
    const tile = this.grid.get(col, row);
    if (!tile) return { ok: false, reason: 'out_of_bounds' };
    const building = getBuildingByTileType(tile.type);
    if (!building || building.category !== 'treat') {
      return { ok: false, reason: 'not_treat_room' };
    }
    if (building.key !== staff.spec.covers) {
      const req = getBuildingByKey(staff.spec.covers);
      return { ok: false, reason: 'wrong_covers', required: req ? req.label : staff.spec.covers };
    }
    const dist = Math.abs(col - staff.col) + Math.abs(row - staff.row);
    if (dist !== 1) return { ok: false, reason: 'out_of_range' };
    if (staff.assignedRooms.length >= staff.spec.maxRooms) {
      return { ok: false, reason: 'max_rooms' };
    }
    if (this.isRoomCovered(col, row)) return { ok: false, reason: 'already_covered' };

    staff.assignedRooms.push({ col, row });
    this.events.emit('staff_assigned', { staff, col, row });
    return { ok: true };
  }

  unassign(staff, col, row) {
    if (!staff) return false;
    const before = staff.assignedRooms.length;
    staff.assignedRooms = staff.assignedRooms.filter(
      (r) => !(r.col === col && r.row === row)
    );
    const changed = staff.assignedRooms.length < before;
    // 2차 Bug Hunter A 보정: topology 변화를 뱃지/패널에 전파.
    // 기존 'staff_assigned' 구독자들이 재렌더 트리거로 사용 — dedicated event 대신 재사용.
    if (changed) this.events.emit('staff_assigned', { staff, col, row, unassigned: true });
    return changed;
  }

  isRoomCovered(col, row) {
    for (const s of this.staff) {
      for (const r of s.assignedRooms) {
        if (r.col === col && r.row === row) return true;
      }
    }
    return false;
  }

  getMonthlyWage() {
    let sum = 0;
    for (const s of this.staff) sum += s.spec.wage || 0;
    return sum;
  }

  count() { return this.staff.length; }

  // Phase 7-D 직원 순찰 — GameScene.update 가 매 프레임 호출.
  //   · 배정 방 없음: 홈 maru 에 정지.
  //   · 배정 방 있음: [홈, ...배정방] 사이클을 idle↔moving 으로 반복.
  //   · 목표 좌표는 매 tick 재계산 (assign/unassign 실시간 반영, idx 는 모듈로).
  update(deltaMs) {
    for (const s of this.staff) this._tickPatrol(s, deltaMs);
  }

  _tickPatrol(s, delta) {
    if (!s.sprite || !s.patrol) return;
    const waypoints = [{ col: s.col, row: s.row }, ...s.assignedRooms];
    const p = s.patrol;

    // 배정 0 → 홈에 스냅 + 정지 프레임.
    if (waypoints.length <= 1) {
      const home = this.grid.pixelFromTile(s.col, s.row);
      const tx = home.x, ty = home.y - 4;
      if (s.sprite.x !== tx || s.sprite.y !== ty) {
        s.sprite.x = tx; s.sprite.y = ty;
      }
      this._setIdleFrame(s);
      p.state = 'idle';
      p.waitMs = 1200;
      return;
    }

    if (p.state === 'idle') {
      this._setIdleFrame(s);
      p.waitMs -= delta;
      if (p.waitMs <= 0) {
        p.idx = (p.idx + 1) % waypoints.length;
        const next = waypoints[p.idx % waypoints.length];
        const { x, y } = this.grid.pixelFromTile(next.col, next.row);
        p.targetX = x; p.targetY = y - 4;
        p.state = 'moving';
      }
      return;
    }

    // moving — 선형 보간 ~48 px/s (타일 1.3초). 방향에 맞는 walk 애니 재생.
    const sp = s.sprite;
    const dx = p.targetX - sp.x, dy = p.targetY - sp.y;
    const dist = Math.hypot(dx, dy);
    if (dist < 1.5) {
      sp.x = p.targetX; sp.y = p.targetY;
      p.state = 'idle';
      p.waitMs = 900 + Math.random() * 1500;
      return;
    }
    // facing 결정: dx/dy 중 절댓값 큰 축.
    s.facing = Math.abs(dx) >= Math.abs(dy)
      ? (dx >= 0 ? 'right' : 'left')
      : (dy >= 0 ? 'down' : 'up');
    if (s.isSheet) {
      const animKey = `${s.tex}_${s.facing}`;
      const cur = sp.anims && sp.anims.currentAnim ? sp.anims.currentAnim.key : null;
      if (cur !== animKey && this.scene.anims.exists(animKey)) {
        sp.anims.play(animKey, true);
      }
    }
    const step = 0.048 * delta;
    const t = Math.min(1, step / dist);
    sp.x += dx * t; sp.y += dy * t;
  }

  _setIdleFrame(s) {
    if (!s.sprite || !s.isSheet) return;
    if (s.sprite.anims && s.sprite.anims.isPlaying) s.sprite.anims.stop();
    s.sprite.setFrame(DIR_ROW[s.facing || 'down'] * 3 + 1);
  }

  // 타일 변경 시 assignedRooms 정리 + 직원 본체가 서 있는 maru 가 사라지면 자동 해고.
  _onTileChanged(tile) {
    if (!tile) return;
    // 직원이 서 있던 maru 가 퇴행/승격되면 해당 직원 제거 (sprite 파괴, 배정 정리).
    for (let i = this.staff.length - 1; i >= 0; i--) {
      const s = this.staff[i];
      if (s.col === tile.col && s.row === tile.row && tile.type !== TILE_MARU) {
        if (s.sprite) s.sprite.destroy();
        this.staff.splice(i, 1);
        this.events.emit('staff_fired', { staff: s, reason: 'tile_lost' });
      }
    }
    // 배정된 방이 covers 타입에서 이탈 → 배정 정리.
    const building = getBuildingByTileType(tile.type);
    for (const s of this.staff) {
      s.assignedRooms = s.assignedRooms.filter((r) => {
        if (r.col !== tile.col || r.row !== tile.row) return true;
        // 현재 타일이 여전히 같은 covers 건물이면 유지, 아니면 제거.
        return building && building.key === s.spec.covers;
      });
    }
  }

  destroy() {
    if (this.grid && this.grid.events) {
      this.grid.events.off('tile_changed', this._onTileChanged);
    }
    for (const s of this.staff) {
      if (s.sprite) s.sprite.destroy();
    }
    this.staff.length = 0;
    if (this.events) {
      this.events.removeAllListeners();
      this.events = null;
    }
    this.scene = null;
    this.grid = null;
  }
}
