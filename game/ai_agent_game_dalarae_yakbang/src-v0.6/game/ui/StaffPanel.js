import { BALANCE, GAME_WIDTH, GAME_HEIGHT } from '../config.js';
import { TILE_MARU } from '../systems/GridSystem.js';
import { getBuildingByKey } from '../systems/BuildingRegistry.js';
import { audioSystem } from '../systems/AudioSystem.js';

// Phase 3-C: 치료방 직원 투입/해제 UI.
// GameScene 가 open(building, col, row) 호출 → 배정/가용/신규 고용 3영역 표시.
// 모든 gold/hire 변경은 scene._applyGold 경유 (경제 단일 진입점 유지).
// 월간 결산(scene.pause) 직전 강제 close — Bug Hunter C-2 회피.

const PANEL_W = 520;
const PANEL_H = 360;
const DEPTH_OVERLAY = 450;
const DEPTH_PANEL   = 460;
const DEPTH_CONTENT = 465;

// 건물별 추천 staff 타입(신규 고용 기본). moxa 는 musuri/chimgu 둘 다 목록화.
const HIRE_OPTIONS_BY_ROOM = {
  moxa: ['musuri', 'chimgu'],
  acu:  ['uinyeo'],
  herb: ['uigwan']
};

const STAFF_LABEL = {
  musuri: '무수리', chimgu: '침구',
  uinyeo: '의녀',   uigwan: '의관'
};

export class StaffPanel {
  constructor(scene, staffSystem, grid) {
    this.scene = scene;
    this.staff = staffSystem;
    this.grid = grid;
    this.target = null;   // { building, col, row }
    this.nodes = [];
    this.isOpen = false;
    this._escKey = null;
  }

  isOpened() { return this.isOpen; }

  open(building, col, row) {
    if (this.isOpen) this.close();
    this.target = { building, col, row };
    this.isOpen = true;
    audioSystem.playSFX?.('panel_open');
    this._build();

    // ESC 로 닫기 — 손맛 폴리시(M1 조건부).
    this._escKey = this.scene.input.keyboard?.on('keydown-ESC', this._onEsc, this);
  }

  close() {
    if (!this.isOpen) return;
    this._clearNodes();
    if (this._escKey) {
      this.scene.input.keyboard?.off('keydown-ESC', this._onEsc, this);
      this._escKey = null;
    }
    this.isOpen = false;
    this.target = null;
  }

  _onEsc() { this.close(); }

  // staff 상태 변경 후 호출 — 리스트 재렌더.
  refresh() {
    if (!this.isOpen || !this.target) return;
    const t = this.target;
    this._clearNodes();
    this._build();
    // target 자체는 유지. close→open 재호출이 아님.
    this.target = t;
  }

  _clearNodes() {
    for (const n of this.nodes) { if (n && n.destroy) n.destroy(); }
    this.nodes.length = 0;
  }

  _build() {
    const { building, col, row } = this.target;
    const px = (GAME_WIDTH - PANEL_W) / 2;
    const py = (GAME_HEIGHT - PANEL_H) / 2;

    // 오버레이 — 게임 뒤 입력 블록.
    const overlay = this.scene.add.graphics().setDepth(DEPTH_OVERLAY);
    overlay.fillStyle(0x000000, 0.55);
    overlay.fillRect(0, 0, GAME_WIDTH, GAME_HEIGHT);
    const overlayHit = this.scene.add.zone(0, 0, GAME_WIDTH, GAME_HEIGHT)
      .setOrigin(0, 0).setInteractive().setDepth(DEPTH_OVERLAY);
    overlayHit.on('pointerdown', () => {/* 배경 클릭은 무동작 — 실수 close 방지 */});
    this.nodes.push(overlay, overlayHit);

    // 패널 프레임
    const panel = this.scene.add.graphics().setDepth(DEPTH_PANEL);
    panel.fillStyle(0xfdf0d0, 1);
    panel.fillRoundedRect(px, py, PANEL_W, PANEL_H, 12);
    panel.fillStyle(0xd08020, 1);
    panel.fillRoundedRect(px, py, PANEL_W, 44, 12);
    panel.fillRect(px, py + 32, PANEL_W, 12);
    panel.lineStyle(3, 0xd08020);
    panel.strokeRoundedRect(px, py, PANEL_W, PANEL_H, 12);
    this.nodes.push(panel);

    // 제목
    const title = this.scene.add.text(GAME_WIDTH / 2, py + 22,
      `${building.label} — 직원 배치`, {
        fontFamily: 'Noto Serif KR, serif',
        fontSize: '20px', fontStyle: 'bold',
        color: '#ffffff', stroke: '#8b4010', strokeThickness: 3
      }).setOrigin(0.5).setDepth(DEPTH_CONTENT);
    this.nodes.push(title);

    // 좌측: 배정 목록
    this._buildAssignedList(px + 16, py + 56, 240, 200);

    // 우측: 가용 목록
    this._buildAvailableList(px + PANEL_W - 256, py + 56, 240, 200);

    // 하단: 신규 고용
    this._buildHireSection(px + 16, py + 266, PANEL_W - 32, 52);

    // 닫기
    this._buildCloseButton(px + PANEL_W - 120, py + PANEL_H - 36, 100, 28);
  }

  _buildAssignedList(x, y, w, h) {
    const { building, col, row } = this.target;
    const depth = DEPTH_CONTENT;

    const hdr = this.scene.add.text(x + 4, y, '배정된 직원', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '14px',
      color: '#604010', fontStyle: 'bold'
    }).setDepth(depth);
    this.nodes.push(hdr);

    // 박스
    const box = this.scene.add.graphics().setDepth(DEPTH_PANEL);
    box.fillStyle(0xf6e0b0, 0.7);
    box.fillRoundedRect(x, y + 20, w, h - 20, 6);
    box.lineStyle(1, 0xc08040);
    box.strokeRoundedRect(x, y + 20, w, h - 20, 6);
    this.nodes.push(box);

    const assigned = this.staff.staff.filter((s) =>
      s.assignedRooms.some((r) => r.col === col && r.row === row)
    );

    if (assigned.length === 0) {
      const empty = this.scene.add.text(x + w / 2, y + h / 2 + 10,
        '배정된 직원이 없습니다', {
          fontFamily: 'Noto Serif KR, serif', fontSize: '13px', color: '#806040'
        }).setOrigin(0.5).setDepth(depth);
      this.nodes.push(empty);
      return;
    }

    assigned.forEach((s, i) => {
      const ry = y + 32 + i * 32;
      const label = `${STAFF_LABEL[s.type] || s.type} (임금 ${s.spec.wage})`;
      const text = this.scene.add.text(x + 10, ry + 8, label, {
        fontFamily: 'Noto Serif KR, serif', fontSize: '13px', color: '#604010'
      }).setDepth(depth);
      this.nodes.push(text);

      // [해제] 버튼
      this._button(x + w - 64, ry, 54, 22, '해제', 0xc05020, () => {
        this.staff.unassign(s, col, row);
        audioSystem.playSFX?.('staff_assign');
        // J 보정: 수동 unassign 시 토스트 재교육 플래그 리셋.
        // Phase 4-B ⑦C: 가드 키가 `${buildingKey}_${tier}` 튜플로 바뀌어 prefix 매칭.
        //   이 건물에 대한 모든 계층별 가드를 일괄 해제 — 재고용 후 첫 계층 재안내 보장.
        const guard = this.scene._noStaffToastShownByBuildingTier;
        if (guard) {
          const prefix = `${building.key}_`;
          for (const k of Array.from(guard)) {
            if (k.startsWith(prefix)) guard.delete(k);
          }
        }
        // I 보정: USING 중 환자는 그대로 완주(_tickState 재체크 없음). 토스트 고지.
        this.scene._toast?.('진행 중 진료는 마저 완료됩니다');
        this.refresh();
      });
    });
  }

  _buildAvailableList(x, y, w, h) {
    const { building, col, row } = this.target;
    const depth = DEPTH_CONTENT;

    const hdr = this.scene.add.text(x + 4, y, '가용 직원', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '14px',
      color: '#604010', fontStyle: 'bold'
    }).setDepth(depth);
    this.nodes.push(hdr);

    const box = this.scene.add.graphics().setDepth(DEPTH_PANEL);
    box.fillStyle(0xf6e0b0, 0.7);
    box.fillRoundedRect(x, y + 20, w, h - 20, 6);
    box.lineStyle(1, 0xc08040);
    box.strokeRoundedRect(x, y + 20, w, h - 20, 6);
    this.nodes.push(box);

    const available = this.staff.staff.filter((s) => {
      if (s.spec.covers !== building.key) return false;
      if (s.assignedRooms.length >= s.spec.maxRooms) return false;
      if (s.assignedRooms.some((r) => r.col === col && r.row === row)) return false;
      const dist = Math.abs(s.col - col) + Math.abs(s.row - row);
      return dist === 1;
    });

    if (available.length === 0) {
      const empty = this.scene.add.text(x + w / 2, y + h / 2 + 10,
        '가용 직원이 없습니다', {
          fontFamily: 'Noto Serif KR, serif', fontSize: '13px', color: '#806040'
        }).setOrigin(0.5).setDepth(depth);
      this.nodes.push(empty);
      return;
    }

    available.forEach((s, i) => {
      const ry = y + 32 + i * 32;
      const label = `${STAFF_LABEL[s.type] || s.type} · 방 ${s.assignedRooms.length}/${s.spec.maxRooms}`;
      const text = this.scene.add.text(x + 10, ry + 8, label, {
        fontFamily: 'Noto Serif KR, serif', fontSize: '13px', color: '#604010'
      }).setDepth(depth);
      this.nodes.push(text);

      // [투입] 버튼
      this._button(x + w - 64, ry, 54, 22, '투입', 0x408040, () => {
        const res = this.staff.assign(s, col, row);
        audioSystem.playSFX?.('staff_assign');
        if (!res.ok) {
          this.scene._toast?.(`투입 실패: ${this._localizeReason(res.reason)}`);
        }
        this.refresh();
      });
    });
  }

  _buildHireSection(x, y, w, h) {
    const { building, col, row } = this.target;
    const depth = DEPTH_CONTENT;

    const hdr = this.scene.add.text(x + 4, y, '신규 고용', {
      fontFamily: 'Noto Serif KR, serif', fontSize: '14px',
      color: '#604010', fontStyle: 'bold'
    }).setDepth(depth);
    this.nodes.push(hdr);

    const types = HIRE_OPTIONS_BY_ROOM[building.key] || [];
    const btnW = Math.max(150, Math.floor((w - types.length * 8) / Math.max(1, types.length)));
    types.forEach((type, i) => {
      const bx = x + i * (btnW + 8);
      const by = y + 22;
      const spec = BALANCE.staff[type];
      if (!spec) return;

      // D/E 보정: enable 조건 = 비용 충족 + 빈 인접 maru 존재.
      const vacantAdj = this._firstVacantAdjacentMaru(col, row);
      const affordable = this.scene.gold >= spec.hire;
      const enabled = affordable && !!vacantAdj;
      const reason = !affordable ? `돈 부족 (${spec.hire}전)`
                     : !vacantAdj ? '인접 빈 마루 필요' : null;

      const label = `${STAFF_LABEL[type] || type} (${spec.hire}전 · 임금 ${spec.wage})`;
      const color = enabled ? 0x8050c0 : 0x807060;
      this._button(bx, by, btnW, 26, label, color, () => {
        this._doHire(type, col, row);
      }, enabled, reason);
    });
  }

  _buildCloseButton(x, y, w, h) {
    this._button(x, y, w, h, '닫기', 0x804000, () => this.close());
  }

  _firstVacantAdjacentMaru(col, row) {
    const deltas = [[-1, 0], [1, 0], [0, -1], [0, 1]];
    for (const [dc, dr] of deltas) {
      const nc = col + dc, nr = row + dr;
      if (!this.grid.inBounds(nc, nr)) continue;
      const tile = this.grid.get(nc, nr);
      if (!tile || tile.type !== TILE_MARU) continue;
      // 이미 다른 staff 가 거주 중이면 skip (H-1 보정)
      if (this.staff.staff.some((s) => s.col === nc && s.row === nr)) continue;
      return { col: nc, row: nr };
    }
    return null;
  }

  _doHire(type, roomCol, roomRow) {
    const spec = BALANCE.staff[type];
    if (!spec) return;
    if (this.scene.gold < spec.hire) {
      this.scene._toast?.(`고용 실패: 돈 부족 (${spec.hire}전 필요)`);
      return;
    }
    const slot = this._firstVacantAdjacentMaru(roomCol, roomRow);
    if (!slot) {
      this.scene._toast?.('인접 빈 마루 필요');
      return;
    }
    const s = this.staff.hire(type, slot.col, slot.row);
    if (!s) {
      this.scene._toast?.('고용 실패 (내부 오류)');
      return;
    }
    // E 보정: assign 실패 시 hire 롤백 (환급 + staff 제거).
    const res = this.staff.assign(s, roomCol, roomRow);
    if (!res.ok) {
      // staff 직접 제거 — StaffSystem.staff 배열에서 삭제 + sprite destroy.
      const idx = this.staff.staff.indexOf(s);
      if (idx >= 0) this.staff.staff.splice(idx, 1);
      if (s.sprite) s.sprite.destroy();
      // 2차 Bug Hunter B 보정: 롤백도 staff_fired 로 알려 뱃지/리스너 동기화.
      this.staff.events?.emit('staff_fired', { staff: s, reason: 'rollback' });
      this.scene._toast?.(`배정 실패: ${this._localizeReason(res.reason) || '알 수 없음'}`);
      return;
    }
    this.scene._applyGold(-spec.hire);
    audioSystem.playSFX?.('coin');
    this.scene._toast?.(`${STAFF_LABEL[type] || type} 고용 (-${spec.hire}전)`);
    this.refresh();
  }

  _button(x, y, w, h, label, color, onClick, enabled = true, disabledReason = null) {
    const bg = this.scene.add.graphics().setDepth(DEPTH_CONTENT);
    bg.fillStyle(enabled ? color : 0x706060, 1);
    bg.fillRoundedRect(x, y, w, h, 6);
    bg.lineStyle(2, 0x402010, 1);
    bg.strokeRoundedRect(x, y, w, h, 6);
    const txt = this.scene.add.text(x + w / 2, y + h / 2, label, {
      fontFamily: 'Noto Serif KR, serif', fontSize: '13px',
      color: enabled ? '#ffffff' : '#d8cfc0', fontStyle: 'bold',
      stroke: '#402010', strokeThickness: 2
    }).setOrigin(0.5).setDepth(DEPTH_CONTENT + 1);

    const hit = this.scene.add.zone(x + w / 2, y + h / 2, w, h)
      .setOrigin(0.5).setDepth(DEPTH_CONTENT + 2);
    if (enabled) {
      hit.setInteractive({ useHandCursor: true });
      hit.on('pointerdown', () => onClick());
    } else if (disabledReason) {
      hit.setInteractive({ useHandCursor: false });
      hit.on('pointerover', () => this.scene._toast?.(disabledReason));
    }
    this.nodes.push(bg, txt, hit);
  }

  // E 보정: StaffSystem.assign 의 reason code 를 플레이어 대상 문구로 변환.
  _localizeReason(reason) {
    switch (reason) {
      case 'invalid':         return '잘못된 직원';
      case 'out_of_bounds':   return '유효하지 않은 타일';
      case 'not_treat_room':  return '치료방이 아님';
      case 'wrong_covers':    return '담당 분야 불일치';
      case 'out_of_range':    return '인접 거리 초과';
      case 'max_rooms':       return '최대 담당 방 도달';
      case 'already_covered': return '이미 커버 중';
      default:                return reason || '알 수 없음';
    }
  }

  destroy() {
    this.close();
    this.scene = null;
    this.staff = null;
    this.grid = null;
  }
}
