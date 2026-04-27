import { isWalkableType, isBuildingType, TILE_MARU, TILE_GATE } from './GridSystem.js';

// 4방향 이웃 델타 — 대각 허용/8방향 실험 시 여기만 바꾸면 됨
const DIRS4 = Object.freeze([[1,0], [-1,0], [0,1], [0,-1]]);

// 4방향 BFS — 최단 경로 탐색.
// 통행 가능 타일: 마루·대문.
// 건물 타일은 '진입 목적지'인 경우 도착점으로만 허용(경유 불가).
// 시설이 마루로 대문과 연결되지 않았다면 null 반환.
export class PathSystem {
  constructor(grid) {
    this.grid = grid;

    // ─── 대문 기준 도달 가능 타일 캐시 ───────────────
    // tile_changed 시 dirty 로 표시, 다음 쿼리에서 1회 BFS 로 재빌드.
    // 건물 B 개마다 BFS 돌리던 O(B·P) 부하를 O(P) + O(B) 로 축소.
    this.reachable = new Set();
    this.reachableDirty = true;
    this._cachedGate = null;
    this._onTileChanged = () => { this.reachableDirty = true; };
    if (grid.events) grid.events.on('tile_changed', this._onTileChanged);
  }

  // 씬 종료 시 호출 — grid.events 에 걸린 구독을 해제해 중복/좀비 방지
  destroy() {
    if (this.grid && this.grid.events && this._onTileChanged) {
      this.grid.events.off('tile_changed', this._onTileChanged);
    }
    this.reachable.clear();
    this._onTileChanged = null;
    this.grid = null;
  }

  _key(c, r) { return r * this.grid.cols + c; }

  findPath(startCol, startRow, targetCol, targetRow, { targetIsBuilding = false } = {}) {
    const g = this.grid;
    if (!g.inBounds(startCol, startRow)) return null;
    if (!g.inBounds(targetCol, targetRow)) return null;

    const startTile = g.tiles[startRow][startCol];
    // 출발점도 통행 가능 타일이어야 함(대문 또는 마루)
    if (!isWalkableType(startTile.type)) return null;

    const visited = new Set([this._key(startCol, startRow)]);
    const parent = new Map();
    const queue = [[startCol, startRow]];

    while (queue.length) {
      const [c, r] = queue.shift();
      if (c === targetCol && r === targetRow) {
        return this._reconstruct(parent, c, r);
      }
      for (const [dc, dr] of DIRS4) {
        const nc = c + dc;
        const nr = r + dr;
        if (!g.inBounds(nc, nr)) continue;
        const nk = this._key(nc, nr);
        if (visited.has(nk)) continue;

        const tile = g.tiles[nr][nc];
        const isTarget = (nc === targetCol && nr === targetRow);
        const walkable = isWalkableType(tile.type) || (isTarget && targetIsBuilding);
        if (!walkable) continue;

        visited.add(nk);
        parent.set(nk, this._key(c, r));
        queue.push([nc, nr]);
      }
    }
    return null;
  }

  _reconstruct(parent, endC, endR) {
    const g = this.grid;
    const path = [{ col: endC, row: endR }];
    let cur = this._key(endC, endR);
    while (parent.has(cur)) {
      cur = parent.get(cur);
      const pc = cur % g.cols;
      const pr = (cur - pc) / g.cols;
      path.push({ col: pc, row: pr });
    }
    return path.reverse();
  }

  // ─── 도달성 캐시 ─────────────────────────────────
  _rebuildReachable(gateCol, gateRow) {
    const g = this.grid;
    this.reachable.clear();
    this._cachedGate = { c: gateCol, r: gateRow };
    this.reachableDirty = false;
    if (!g.inBounds(gateCol, gateRow)) return;
    const startTile = g.tiles[gateRow][gateCol];
    if (!isWalkableType(startTile.type)) return;

    const queue = [[gateCol, gateRow]];
    this.reachable.add(this._key(gateCol, gateRow));
    while (queue.length) {
      const [c, r] = queue.shift();
      for (const [dc, dr] of DIRS4) {
        const nc = c + dc, nr = r + dr;
        if (!g.inBounds(nc, nr)) continue;
        const k = this._key(nc, nr);
        if (this.reachable.has(k)) continue;
        const tile = g.tiles[nr][nc];
        if (!isWalkableType(tile.type)) continue;
        this.reachable.add(k);
        queue.push([nc, nr]);
      }
    }
  }

  _ensureReachable(gateCol, gateRow) {
    const gateMoved = !this._cachedGate ||
                      this._cachedGate.c !== gateCol ||
                      this._cachedGate.r !== gateRow;
    if (this.reachableDirty || gateMoved) this._rebuildReachable(gateCol, gateRow);
  }

  // 특정 타일(마루/대문)이 대문에서 도달 가능한가 — O(1)
  isTileReachable(col, row, gateCol, gateRow) {
    this._ensureReachable(gateCol, gateRow);
    return this.reachable.has(this._key(col, row));
  }

  // 시설이 대문까지 마루로 연결되어 있는가 (Phase 1-C 핵심 체크)
  // 게임 설계상 환자는 반드시 마루로 걸어와야 하므로,
  // 건물 4이웃 중 "마루"가 대문과 연결된 경우만 도달 가능으로 인정.
  // (대문 인접 건물이 마루 없이 '도달 가능'으로 오판되는 엣지 차단)
  isBuildingReachable(targetCol, targetRow, gateCol, gateRow) {
    const g = this.grid;
    if (!g.inBounds(targetCol, targetRow)) return false;
    if (!g.inBounds(gateCol, gateRow)) return false;
    this._ensureReachable(gateCol, gateRow);

    for (const [dc, dr] of DIRS4) {
      const nc = targetCol + dc;
      const nr = targetRow + dr;
      if (!g.inBounds(nc, nr)) continue;
      const tile = g.tiles[nr][nc];
      if (tile.type !== TILE_MARU) continue;
      if (this.reachable.has(this._key(nc, nr))) return true;
    }
    return false;
  }
}
