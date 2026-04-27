import { BALANCE, GATE_COL, GATE_ROW, SPAWN_COL, SPAWN_ROW } from '../config.js';
import { TILE_EMPTY, TILE_MARU, TILE_MOXA, TILE_WELL, TILE_PINE, isWalkableType } from './GridSystem.js';
import { getBuildingByTileType, getBuildingByKey, listBuildingsByCategory } from './BuildingRegistry.js';
import { Patient, PATIENT_STATE } from '../objects/Patient.js';

// Phase 2-A: 환자 자동 스폰 + 이동 골격.
// Phase 2-B 에서 시설 이용·수입·퇴장 트리거 통합.
//
// ─── 설계 ─────────────────────────────────────────
//  · GameScene.update(delta) 가 this.update(delta) 호출
//  · 스폰: autoSpawnIntervalMs 마다 조건 체크 → 생성
//  · 조건: 스폰 포인트(대문 바로 위)에 마루 존재 AND 맵 내 환자 수 < MAX
//  · 계층: Phase 2 에선 'nobi' 만 (티어 해금은 Phase 4)
//  · 목적지: 대문에서 도달 가능한 moxa → 없으면 랜덤 마루 → 없으면 즉시 퇴장
//  · 시설 이용·수입 처리는 Phase 2-B 에서 추가 (현재는 도착 후 바로 leaving)

const MAX_PATIENTS = BALANCE.maxPatients;
const MIN_SPAWN_GAP_MS = BALANCE.spawnMinGapMs;  // 같은 프레임 다중 스폰 방지
const FADE_OUT_MS = BALANCE.patientFadeOutMs;

export class PatientSystem {
  constructor(scene, grid, pathSystem, staffSystem = null) {
    this.scene = scene;
    this.grid = grid;
    this.pathSystem = pathSystem;
    this.staffSystem = staffSystem;
    this.patients = [];
    this.spawnAccum = 0;
    this.sinceLastSpawn = MIN_SPAWN_GAP_MS;  // 첫 스폰 지연 방지

    // Phase 4-B ④A: 해금된 계층 풀. GameScene 이 tier_unlocked 시 setUnlockedTiers 로 동기화.
    //   tierSpawnWeight 에서 선비·양반은 0 이라 해금돼도 자연 스폰 제외.
    this.unlockedTiers = new Set(['nobi']);
    // Phase 4-B ⑤B: 결정적 환영 스폰 예약 — 양반 해금 순간 1회만 세팅, 다음 _trySpawn 에서 소모.
    //   가중치 0 인 계층을 "처음 한 번" 보여주는 연출용. 소모 후 null 복귀.
    this._pendingWelcomeTier = null;

    // 이벤트 emitter — GameScene 이 수입/명의/FloatingText 용으로 구독
    this.events = new Phaser.Events.EventEmitter();

    // 타일 철거 대응 — grid 이벤트 구독. destroy 시 off.
    this._onTileChanged = this._onTileChanged.bind(this);
    this.grid.events.on('tile_changed', this._onTileChanged);
  }

  // Phase 4-B ④A: UnlockSystem.tier_unlocked → GameScene → 여기로 동기화.
  //   set 전체를 통째로 받아 덮어쓰기(부분 업데이트 아님) — 소스 단일화.
  setUnlockedTiers(tiers) {
    if (!tiers) return;
    this.unlockedTiers = new Set(tiers);
  }

  // Phase 4-B ⑤B: 양반 해금 순간 다음 스폰 슬롯을 결정적으로 양반으로 지정.
  //   이미 예약된 tier 가 있으면 덮어쓰지 않음(선착순) — 순간적 동시 해금 방어.
  requestWelcomeSpawn(tier) {
    if (!tier) return;
    if (this._pendingWelcomeTier) return;
    this._pendingWelcomeTier = tier;
  }

  // 타일이 퇴행/비통행 상태로 전환될 때 환자 재검증. 승격(마루 추가)은 무시.
  // EMPTY 와 통행 불가 타입(건물류) 모두 가드 — 향후 마루→건물 직접 승격 API 확장 대비.
  // Phase 4-A0 변경: USING 환자 시설 철거 시 집으로 대신 다음 편의시설 탐색(⑤A).
  //                  usedBuildings 에 철거된 건물 key 를 넣어 재시도 방지.
  //                  WALKING·LEAVING 은 경로 위험 → 중단 후 재계획(귀가 대신 다음 목적지).
  // 2차 검증 C-2 보정: "환자 발밑 마루가 철거된 경우"를 최우선 가드 — 환자가 허공 위에
  //                  유령처럼 남는 시각 이상 방지. 모든 상태 공통으로 즉시 페이드아웃.
  // 2차 검증 H-1 보정: USING → _planNextAction 재호출 전 useRemaining/wellBonus 초기화 +
  //                  state 를 WALKING 으로 바꿔 USING 중복 토스트·타이머 잔재 제거.
  _onTileChanged(tile) {
    if (!tile) return;
    if (tile.type !== TILE_EMPTY && isWalkableType(tile.type)) return;
    for (const p of this.patients) {
      if (p.state === PATIENT_STATE.DONE) continue;

      // (a) 발밑 마루 철거: 환자 스프라이트 위치 타일이 직접 손상된 경우.
      const curTile = this._patientTile(p);
      if (curTile && curTile.col === tile.col && curTile.row === tile.row) {
        if (p.fadeTween) continue;
        p.cancelMovement();
        p.targetBuilding = null;
        p.useRemaining = 0;
        p.wellBonus = 0;
        p.state = PATIENT_STATE.LEAVING;
        this._fadeOutAndDone(p);
        continue;
      }

      // (b) USING 중 건물 타일 철거: 다음 편의 재계획.
      if (p.state === PATIENT_STATE.USING) {
        const tb = p.targetBuilding;
        if (tb && tb.col === tile.col && tb.row === tile.row) {
          if (tb.key) p.usedBuildings.add(tb.key);
          p.targetBuilding = null;
          p.useRemaining = 0;
          p.useTotal = 0;  // HIGH-01: stale total 로 진행률 100% 깜빡임 방지.
          p.wellBonus = 0;
          p.state = PATIENT_STATE.WALKING;
          this._planNextAction(p);
        }
        continue;
      }

      // (c) WALKING/LEAVING 중 경로 타일 손상.
      if (p.state === PATIENT_STATE.WALKING || p.state === PATIENT_STATE.LEAVING) {
        if (p.fadeTween) continue;
        p.cancelMovement();
        if (p.state === PATIENT_STATE.LEAVING) {
          this._sendPatientHome(p);
        } else {
          this._planNextAction(p);
        }
      }
    }
  }

  update(delta) {
    // 스폰 타이머
    this.spawnAccum += delta;
    this.sinceLastSpawn += delta;
    if (this.spawnAccum >= BALANCE.autoSpawnIntervalMs) {
      this.spawnAccum -= BALANCE.autoSpawnIntervalMs;
      this._trySpawn();
    }

    // 각 환자 업데이트 + 상태 전이
    for (let i = this.patients.length - 1; i >= 0; i--) {
      const p = this.patients[i];
      p.update(delta);
      this._tickState(p);
      if (p.state === PATIENT_STATE.DONE) {
        p.destroy();
        this.patients.splice(i, 1);
      }
    }
  }

  _trySpawn() {
    if (this.patients.length >= MAX_PATIENTS) return;
    if (this.sinceLastSpawn < MIN_SPAWN_GAP_MS) return;

    // 스폰 포인트(대문 바로 위)가 마루가 아니면 진입 불가
    const spawnTile = this.grid.get(SPAWN_COL, SPAWN_ROW);
    if (!spawnTile || spawnTile.type !== TILE_MARU) return;

    // Phase 4-B ⑤B 우선: 환영 스폰이 예약돼 있으면 가중치 무시하고 해당 계층으로.
    //   양반은 tierSpawnWeight 0 이라 풀 샘플에선 절대 안 나옴 — 해금 순간만 이 경로로 한 번 노출.
    // Phase 4-B 보정-1: 환영 스폰은 isWelcomeSpawn 플래그로 추적. 경로 실패로 바로 abandoned
    //   되는 엣지 케이스에서 _evaluateSatisfaction 이 _pendingWelcomeTier 를 복구 → 다음 틱 재시도.
    let tier;
    if (this._pendingWelcomeTier) {
      tier = this._pendingWelcomeTier;
      this._pendingWelcomeTier = null;
      this.spawnOne(tier, { isWelcomeSpawn: true });
    } else {
      tier = this._pickTierByUnlock();
      this.spawnOne(tier);
    }
    this.sinceLastSpawn = 0;
  }

  // Phase 4-B ④A: 해금된 계층 풀에서 tierSpawnWeight 기반 가중치 샘플.
  //   선비·양반은 weight 0 이라 해금돼도 자연 스폰 대상 제외(⑤B 환영 경로만).
  //   풀이 비거나 총 가중치 0 이면 nobi 로 안전 폴백.
  _pickTierByUnlock() {
    const weights = BALANCE.tierSpawnWeight || {};
    const pool = [];
    let total = 0;
    for (const tier of this.unlockedTiers) {
      const w = weights[tier] || 0;
      if (w <= 0) continue;
      pool.push({ tier, w });
      total += w;
    }
    if (total <= 0) return 'nobi';
    let r = Math.random() * total;
    for (const { tier, w } of pool) {
      r -= w;
      if (r <= 0) return tier;
    }
    return pool[pool.length - 1].tier;
  }

  // QA/튜토리얼에서 호출 가능한 강제 스폰. MAX 초과 시 null.
  // GA Smoke 지적: _trySpawn 만 MAX 가드가 있어 debug/튜토리얼 강제 스폰이 우회 가능했음.
  // Phase 4-B 보정-1: options.isWelcomeSpawn 을 _planNextAction 호출 전에 세팅 — abandoned 분기가
  //   복구 여부 판단 시 플래그가 이미 설정돼 있어야 함(순서 중요).
  spawnOne(tier = 'nobi', options = {}) {
    if (this.patients.length >= MAX_PATIENTS) return null;
    const p = new Patient(this.scene, this.grid, tier);
    if (options.isWelcomeSpawn) p.isWelcomeSpawn = true;
    this.patients.push(p);
    this._planNextAction(p);
    return p;
  }

  // 현재 환자가 다음에 어디로 갈지 결정.
  // Phase 4-A0 흐름: (1) 치료방 미시도 → 치료방 / (2) 미이용 편의 → 가장 가까운 편의 / (3) 귀가.
  // ⑥A: 치료방 없어도 편의시설만 이용하고 귀가 허용.
  // Phase 4-B ⑥A: rejectedByStaff 환자는 편의 순회 skip — "직원이 없어 그냥 돌아가는" 서사.
  //   편의시설만 빌려 쓰는 무임승차 방지 + 직원 고용 압력을 직접 전달.
  _planNextAction(patient) {
    if (patient.state === PATIENT_STATE.DONE) return;
    if (patient.rejectedByStaff) {
      this._sendPatientHome(patient);
      return;
    }
    if (!this._hasUsedTreat(patient)) {
      const treat = this._findReachableTreatRoom(patient);
      if (treat) {
        this._sendPatientToFacility(patient, treat);
        return;
      }
    }
    const amenity = this._findReachableAmenity(patient);
    if (amenity) {
      this._sendPatientToFacility(patient, amenity);
      return;
    }
    this._sendPatientHome(patient);
  }

  // usedBuildings 에 치료방(category='treat') 하나라도 있으면 치료 시도 완료.
  _hasUsedTreat(patient) {
    for (const key of patient.usedBuildings) {
      const b = getBuildingByKey(key);
      if (b && b.category === 'treat') return true;
    }
    return false;
  }

  // Phase 4-A: treat 카테고리 전체(moxa·acu·herb) 최단거리 탐색으로 확장.
  // Phase 7-A1: 병세 매칭 가중치 추가 — 환자.illness 와 다른 치료방은 거리에
  //   illnessMismatchPenalty(=5) 가산. 의도: 병세가 의미 있는 의사결정이 되도록.
  //   matching 이 mismatch 보다 5 칸 이상 멀면 mismatch 가 이김 (현실적 동선).
  // 동률 시: 외부 루프가 BUILDINGS 등록순(moxa→acu→herb) 으로 돌고 `score<bestScore`
  //   strict less-than 이라 "먼저 본 것 유지" → 동률에선 낮은 등급 치료방 선호.
  // 반환: { col, row, viaCol, viaRow, key }.
  _findReachableTreatRoom(patient) {
    const treats = listBuildingsByCategory('treat');
    const ptile = this._patientTile(patient) || { col: GATE_COL, row: GATE_ROW };
    const penalty = BALANCE.illnessMismatchPenalty || 0;
    const wantKey = patient ? patient.illness : null;
    let best = null;
    let bestScore = Infinity;
    for (const bmeta of treats) {
      const tiles = this.grid.listByType(bmeta.tileType);
      const mismatchAdd = (wantKey && bmeta.key !== wantKey) ? penalty : 0;
      for (const t of tiles) {
        const adj = this._adjacentReachableMaru(t.col, t.row);
        if (!adj) continue;
        const dist = Math.abs(ptile.col - t.col) + Math.abs(ptile.row - t.row);
        const score = dist + mismatchAdd;
        if (score < bestScore) {
          bestScore = score;
          best = { col: t.col, row: t.row, viaCol: adj.col, viaRow: adj.row, key: bmeta.key };
        }
      }
    }
    return best;
  }

  // 미이용 편의시설 중 환자 현재 위치에서 가장 가까운 것(Manhattan). 우선순위 자동판단 Q4.
  _findReachableAmenity(patient) {
    const amenities = listBuildingsByCategory('amenity');
    const curTile = this._patientTile(patient);
    const fromCol = curTile ? curTile.col : GATE_COL;
    const fromRow = curTile ? curTile.row : GATE_ROW;
    let best = null;
    let bestDist = Infinity;
    for (const b of amenities) {
      if (patient.usedBuildings.has(b.key)) continue;
      const tiles = this.grid.listByType(b.tileType);
      for (const t of tiles) {
        const adj = this._adjacentReachableMaru(t.col, t.row);
        if (!adj) continue;
        const dist = Math.abs(t.col - fromCol) + Math.abs(t.row - fromRow);
        if (dist < bestDist) {
          bestDist = dist;
          best = { col: t.col, row: t.row, viaCol: adj.col, viaRow: adj.row, key: b.key };
        }
      }
    }
    return best;
  }

  // Phase 7-B2: 같은 종류 치료방 4방 직접 인접 개수 × clusterPenaltyPerRoom.
  //   _finishUsing 의 fee 계산이 (rawFee - 페널티) 후 max(1, ...) 보장.
  //   매개 key 는 building.key (moxa/acu/herb). 스태킹 가능(2개 인접이면 -2).
  _clusterPenalty(col, row, key) {
    const per = BALANCE.clusterPenaltyPerRoom || 0;
    if (per <= 0) return 0;
    const target = this._tileTypeOfKey(key);
    if (target == null) return 0;
    const deltas = [[1,0],[-1,0],[0,1],[0,-1]];
    let count = 0;
    for (const [dc, dr] of deltas) {
      const nc = col + dc, nr = row + dr;
      if (!this.grid.inBounds(nc, nr)) continue;
      const tile = this.grid.get(nc, nr);
      if (tile && tile.type === target) count++;
    }
    return count * per;
  }

  // building.key → tileType 역매핑. _clusterPenalty 가 grid 비교에 사용.
  _tileTypeOfKey(key) {
    const b = getBuildingByKey(key);
    return b ? b.tileType : null;
  }

  // Phase 6: 치료방 (col,row) 상하좌우 4방 인접 소나무 여부 → BALANCE.pineBonusPerRoom (=1) 가산.
  //   pineStack=false 라 인접 소나무가 여러 개여도 +1 만 (스태킹 금지).
  //   소나무 자체 cost 0(무료) 라도 _tryToggleBuilding 의 무료 카운터 가드로 무한 배치 차단.
  _pineAdjacentBonus(col, row) {
    const deltas = [[1,0],[-1,0],[0,1],[0,-1]];
    for (const [dc, dr] of deltas) {
      const nc = col + dc, nr = row + dr;
      if (!this.grid.inBounds(nc, nr)) continue;
      const tile = this.grid.get(nc, nr);
      if (tile && tile.type === TILE_PINE) return BALANCE.pineBonusPerRoom || 0;
    }
    return 0;
  }

  _adjacentReachableMaru(col, row) {
    const deltas = [[1,0],[-1,0],[0,1],[0,-1]];
    for (const [dc, dr] of deltas) {
      const nc = col + dc, nr = row + dr;
      if (!this.grid.inBounds(nc, nr)) continue;
      const tile = this.grid.get(nc, nr);
      if (!tile || tile.type !== TILE_MARU) continue;
      if (this.pathSystem.isTileReachable(nc, nr, GATE_COL, GATE_ROW)) {
        return { col: nc, row: nr };
      }
    }
    return null;
  }

  _sendPatientToFacility(patient, target) {
    // 환자 현 위치에서 탐색(귀가처럼 경로 단축). 첫 외출은 대문에서 출발.
    const curTile = this._patientTile(patient);
    const fromCol = curTile ? curTile.col : GATE_COL;
    const fromRow = curTile ? curTile.row : GATE_ROW;
    const pathTiles = this.pathSystem.findPath(
      fromCol, fromRow, target.viaCol, target.viaRow
    );
    if (!pathTiles) { this._sendPatientHome(patient); return; }
    patient.state = PATIENT_STATE.WALKING;
    // key 저장: 철거 시 usedBuildings 기록용 (_onTileChanged 참조).
    patient.targetBuilding = { col: target.col, row: target.row, key: target.key || null };
    patient.walkPath(pathTiles, () => {
      // 시설 인접 마루 도착 → USING 전환. 실제 fee 지급은 _tickState 에서 완료 시.
      this._beginUsing(patient);
    });
  }

  _beginUsing(patient) {
    if (patient.state === PATIENT_STATE.DONE) return;
    const t = patient.targetBuilding;
    if (!t) { this._planNextAction(patient); return; }
    const tile = this.grid.get(t.col, t.row);
    // 타일·건물 존재 가드 (USING 도중 철거된 경우 등)
    const building = tile ? getBuildingByTileType(tile.type) : null;
    if (!tile || !building) {
      // 도착 직전 철거된 케이스 — 다음 목적지 재계획.
      if (t.key) patient.usedBuildings.add(t.key);
      patient.targetBuilding = null;
      this._planNextAction(patient);
      return;
    }
    // Phase 3-B 직원 게이트: 치료방은 staff 커버 필수.
    // 편의시설(amenity)·장식(decor) 은 staff 불필요.
    if (building.category === 'treat'
        && this.staffSystem
        && !this.staffSystem.isRoomCovered(t.col, t.row)) {
      // Phase 4-B ⑥A 재해석: 거절된 환자는 세션 단위 귀가(편의 순회 차단). rejectedByStaff
      //   flag 로 _planNextAction 이 즉시 귀가 분기 선택, _evaluateSatisfaction 이 patient_rejected
      //   로 분리 집계. 기존 patient_turned_away 는 건물 단위 토스트 신호로 유지(계약 호환).
      //   토스트 가드는 `${buildingKey}_${tier}` 튜플 키라 새 계층 첫 거절마다 재노출(⑦C).
      this.events.emit('patient_turned_away', {
        patient, building, col: t.col, row: t.row, reason: 'no_staff',
        tier: patient.tier
      });
      patient.rejectedByStaff = true;
      patient.usedBuildings.add(building.key);
      patient.targetBuilding = null;
      this._planNextAction(patient);
      return;
    }

    patient.state = PATIENT_STATE.USING;
    // 건물별 이용시간 (amenityUseMs 기본, gukbap 만 4초, treat 는 treatUseMs).
    patient.useRemaining = building.useMs || BALANCE.treatUseMs;
    // W3: PatientInfoPanel 치료 진행률 게이지용 — 시작 시점 총 시간 스냅샷.
    patient.useTotal = patient.useRemaining;
    // 우물 보너스 스냅샷 (Phase 3-C 보정 F) — 시작 시점에 확정.
    // 이유: USING 도중 우물 철거/배치 익스플로잇 차단 + 환자가 "들어올 때 본 경관" 기준 스토리 일치.
    // Phase 7-B1: herb=fee 가산(기존), acu/moxa=만족도 점수 가산(신규). cfg 의 perKey 필드 사용.
    patient.wellBonus = 0;
    patient.wellScoreBonus = 0;
    {
      const cfg = BALANCE.wellBonus;
      if (cfg && this._isWellNearby(t.col, t.row, cfg.radius, cfg.shape)) {
        if (building.key === 'herb' && cfg.herbFee > 0) patient.wellBonus = cfg.herbFee;
        else if (building.key === 'acu' && cfg.acuScore > 0) patient.wellScoreBonus = cfg.acuScore;
        else if (building.key === 'moxa' && cfg.moxaScore > 0) patient.wellScoreBonus = cfg.moxaScore;
      }
    }
    // 플로팅 라벨 분기용으로 building 첨부(④A).
    this.events.emit('patient_using', { patient, building, col: t.col, row: t.row });
  }

  // 3×3 기본(Chebyshev r=1). staff 의 Manhattan r=1 과 의도적 구분.
  // 단일 적용: 첫 매칭 시 true 반환 → 여러 우물 배치해도 중첩 없음.
  _isWellNearby(col, row, radius = 1, shape = 'chebyshev') {
    for (let dr = -radius; dr <= radius; dr++) {
      for (let dc = -radius; dc <= radius; dc++) {
        if (dc === 0 && dr === 0) continue;
        const dist = shape === 'manhattan'
          ? Math.abs(dc) + Math.abs(dr)
          : Math.max(Math.abs(dc), Math.abs(dr));
        if (dist > radius) continue;
        const nc = col + dc, nr = row + dr;
        if (!this.grid.inBounds(nc, nr)) continue;
        const tile = this.grid.get(nc, nr);
        if (tile && tile.type === TILE_WELL) return true;
      }
    }
    return false;
  }

  // 이용 완료 시점 처리: fee 지급, 명의 가산, 이벤트 emit.
  // - patient_served: fee 무관 항상 emit (해금 카운터·통계용). 편의시설(fee=0)도 포함.
  // - patient_paid:   fee>0 또는 myGain>0 일 때만 emit (FloatingText·지갑 계산용).
  // Phase 4-A0: 이용 후 귀가 대신 _planNextAction 재호출(편의시설 순회 배관).
  //             amenity 는 stayBonusMs 만큼 체류시간 연장(기본 체류 위에 가산, 상한 없음).
  //             지갑 부족으로 fee 미지불이어도 이용 기록·체류 보너스는 부여(Q2 기본 동작).
  _finishUsing(patient) {
    const t = patient.targetBuilding;
    const tile = t ? this.grid.get(t.col, t.row) : null;
    const building = tile ? getBuildingByTileType(tile.type) : null;
    if (building) {
      const rawFee = building.fee || 0;
      // Phase 7-B2: 같은 종류 치료방 4방 인접 시 fee 페널티 (treat 만, 최소 1전 보장).
      let baseFee = rawFee;
      if (building.category === 'treat' && rawFee > 0) {
        const cluster = this._clusterPenalty(t.col, t.row, building.key);
        baseFee = Math.max(1, rawFee - cluster);
      }
      // 우물 보너스는 _beginUsing 시점 스냅샷 사용. 지갑 상한 내 지급.
      const wellBonus = patient.wellBonus || 0;
      const fee = Math.min(baseFee + wellBonus, patient.gold || 0);
      const paidWellBonus = Math.max(0, fee - Math.min(baseFee, patient.gold || 0));
      const myGain = building.myeonguiOnUse || 0;
      this.events.emit('patient_served', {
        patient, building, col: t.col, row: t.row
      });
      if (fee > 0 || myGain > 0) {
        this.events.emit('patient_paid', {
          patient, building, fee, myeongui: myGain,
          wellBonus: paidWellBonus,
          col: t.col, row: t.row
        });
      }
      // 지갑 차감 — patient_paid 가 없는 경우에도 내부 상태 정합 유지.
      if (fee > 0) patient.gold = Math.max(0, (patient.gold || 0) - fee);
      // 편의시설 체류 보너스: 기본 체류시간 위에 더해지는 개념(사용자 확정).
      if (building.category === 'amenity' && (building.stayBonusMs || 0) > 0) {
        patient.stayRemaining += building.stayBonusMs;
      }
      patient.usedBuildings.add(building.key);
      // Phase 4-A: 실제 이용 완료한 건물만 actuallyUsed 에 기록. 점수·명의는 여기서만 집계.
      patient.actuallyUsed.add(building.key);
      if (building.category === 'treat') {
        const baseScore = BALANCE.treatScore[building.key] || 0;
        // Phase 6: 인접 소나무 보너스 — pineBonusPerRoom (=1) 가산. 스태킹 금지(_pineAdjacentBonus 참조).
        const pineBonus = this._pineAdjacentBonus(t.col, t.row);
        // Phase 7-B1: 우물 인접 침방·뜸방 만족도 보너스 — _beginUsing 스냅샷 사용.
        const wellScoreBonus = patient.wellScoreBonus || 0;
        const score = baseScore + pineBonus + wellScoreBonus;
        patient.treatScoreSum += score;
        // 최고 등급(baseScore 기준) 치료실 갱신 — 명의 가산 기준은 base 만 (보너스 제외).
        const prev = patient.highestTreatUsed;
        const prevScore = prev ? (BALANCE.treatScore[prev] || 0) : 0;
        if (baseScore > prevScore) patient.highestTreatUsed = building.key;
      } else if (building.category === 'amenity') {
        patient.amenityScoreSum += BALANCE.amenityScore[building.key] || 0;
      }
    }
    patient.targetBuilding = null;
    this._planNextAction(patient);
  }

  // Phase 4-A: 만족도 3단 판정. fade 직전 1회 호출(satisfactionEvaluated flag 로 중복 차단).
  // 선비·양반은 satisfyPendingTiers 에 속해 patient_pending 만 emit(카운터 제외).
  // 판정 공식: 치료·편의 각 축의 need 대비 비율 = score/need, 두 축 MIN 을 tier 로 매핑.
  //   ok (≥1.0)  → 'satisfied'  — myeonguiOnSatisfy 100%
  //   mid (≥0.5) → 'neutral'    — myeonguiOnSatisfy 50%
  //   < mid      → 'dissatisfied' — 가산 0
  // 스폰 직후 경로 없어 즉시 fade 한 환자(actuallyUsed.size===0) 는 patient_abandoned 로 분리.
  _evaluateSatisfaction(patient) {
    if (patient.satisfactionEvaluated) return;
    patient.satisfactionEvaluated = true;

    // Phase 4-B ⑥A: 직원 부족으로 거절된 환자 — 세션 단위 귀가로 만족도 판정에서 제외.
    //   actuallyUsed 가비어도(치료 거절 후 편의 순회 skip) 이 분기가 먼저 먹어 abandoned 오염 방지.
    //   GameScene._onPatientRejected 가 tier 별로 월간 카운터 집계(⑨B).
    if (patient.rejectedByStaff) {
      this.events.emit('patient_rejected', { patient, tier: patient.tier });
      return;
    }

    // 아무 시설도 이용 못 한 환자(입장 실패) — 만족도 카운터에서 제외.
    // Phase 4-B 보정-1: 환영 스폰이 경로 실패로 바로 abandoned 된 경우, 예약 tier 를 복구해
    //   다음 _trySpawn 이 재시도. "명의 100 = 장기 보상" 의 단일 순간이 조용히 날아가는 걸 방지.
    //   rejectedByStaff 분기는 위에서 이미 return 됐으므로 여기선 순수 경로 실패만 잡힘.
    if (patient.actuallyUsed.size === 0) {
      if (patient.isWelcomeSpawn && !this._pendingWelcomeTier) {
        this._pendingWelcomeTier = patient.tier;
      }
      this.events.emit('patient_abandoned', { patient });
      return;
    }

    const tier = patient.tier || 'nobi';
    // 선비·양반: 현 빌딩으로 수학적 만족 불가 — Phase 6 소나무 편의 보너스 후 활성.
    if (BALANCE.satisfyPendingTiers.includes(tier)) {
      this.events.emit('patient_pending', {
        patient, tier,
        treatScore: patient.treatScoreSum,
        amenityScore: patient.amenityScoreSum
      });
      return;
    }

    const needT = BALANCE.satisfyNeedTreat[tier] || 0;
    const needA = BALANCE.satisfyNeedAmenity[tier] || 0;
    const ratioT = needT > 0 ? patient.treatScoreSum / needT : 1;
    const ratioA = needA > 0 ? patient.amenityScoreSum / needA : 1;
    const ratio = Math.min(ratioT, ratioA);

    let tierResult = 'dissatisfied';
    let myeonguiMul = 0;
    if (ratio >= BALANCE.satisfyTier.ok) { tierResult = 'satisfied'; myeonguiMul = 1.0; }
    else if (ratio >= BALANCE.satisfyTier.mid) { tierResult = 'neutral'; myeonguiMul = 0.5; }

    // 명의 가산: 이용한 최고 등급 치료실 기준 × myeonguiMul.
    let myeongui = 0;
    if (myeonguiMul > 0 && patient.highestTreatUsed) {
      const base = BALANCE.myeonguiOnSatisfy[patient.highestTreatUsed] || 0;
      myeongui = base * myeonguiMul;
    }

    this.events.emit('patient_satisfied', {
      patient, tier, result: tierResult,
      treatScore: patient.treatScoreSum,
      amenityScore: patient.amenityScoreSum,
      needTreat: needT, needAmenity: needA,
      myeongui
    });
  }

  _sendPatientHome(patient) {
    // 귀가 시점엔 targetBuilding 의미 없음 — 명시 초기화로 미래 재호출 혼란 방지.
    patient.targetBuilding = null;
    // 현재 위치에서 대문까지 경로
    const curTile = this._patientTile(patient);
    // Phase 4-A 2차 H1 보정: curTile==null 이어도 state=DONE 직행 금지.
    //   _fadeOutAndDone 를 거치지 않으면 _evaluateSatisfaction 스킵 → 월간 카운터 영구 누락.
    //   sprite 가 그리드 경계 밀린 극히 드문 경우에도 판정·이벤트 순서 계약 유지.
    if (!curTile) { patient.state = PATIENT_STATE.LEAVING; this._fadeOutAndDone(patient); return; }
    const pathTiles = this.pathSystem.findPath(
      curTile.col, curTile.row, GATE_COL, GATE_ROW
    );
    if (!pathTiles) {
      // 경로 없음 — 현장에서 fade-out
      patient.state = PATIENT_STATE.LEAVING;
      this._fadeOutAndDone(patient);
      return;
    }
    patient.state = PATIENT_STATE.LEAVING;
    patient.walkPath(pathTiles, () => {
      // 대문 도착 → 페이드 아웃 후 제거
      this._fadeOutAndDone(patient);
    });
  }

  // fade-out tween 을 Patient.fadeTween 으로 추적 — Patient.destroy 정리 대상.
  // Phase 4-A: 판정 훅은 tween add 이전(재진입 분기 전)에 1회만 실행.
  //            satisfactionEvaluated flag 로 C1·C2 경로 중복 차단.
  _fadeOutAndDone(patient) {
    this._evaluateSatisfaction(patient);
    if (!patient.sprite) { patient.state = PATIENT_STATE.DONE; return; }
    // 이전 fadeTween 누수 방지 (재진입 안전).
    if (patient.fadeTween) {
      const old = patient.fadeTween;
      patient.fadeTween = null;
      old.stop();
      old.remove();
    }
    // v0.5 이식 — 인내심 바/라벨도 함께 페이드. sprite 와 같은 타이밍으로 자연스럽게 사라짐.
    const fadeTargets = [patient.sprite];
    if (patient.patienceBg)  fadeTargets.push(patient.patienceBg);
    if (patient.patienceBar) fadeTargets.push(patient.patienceBar);
    if (patient.tierLabel)   fadeTargets.push(patient.tierLabel);
    patient.fadeTween = this.scene.tweens.add({
      targets: fadeTargets,
      alpha: 0, duration: FADE_OUT_MS,
      onComplete: () => {
        patient.fadeTween = null;
        patient.state = PATIENT_STATE.DONE;
      }
    });
  }

  // 스프라이트 픽셀 좌표를 타일 좌표로 역변환
  _patientTile(patient) {
    if (!patient.sprite) return null;
    return this.grid.tileFromPixel(patient.sprite.x, patient.sprite.y);
  }

  _tickState(patient) {
    // USING 완료 감지 → 수입 지급 + 복귀
    if (patient.state === PATIENT_STATE.USING && patient.useRemaining <= 0) {
      this._finishUsing(patient);
      return;
    }
    // 체류 타이머 초과 → 강제 복귀 (퇴장 트리거 #2: 체류시간 만료)
    // WALKING 중에만 가로채 (USING 중엔 진행 완료까지 보호).
    if (patient.stayRemaining <= 0 &&
        patient.state === PATIENT_STATE.WALKING) {
      patient.cancelMovement();
      this._sendPatientHome(patient);
      return;
    }
  }

  destroy() {
    if (this.grid && this.grid.events) {
      this.grid.events.off('tile_changed', this._onTileChanged);
    }
    // Phase 4-A C2 + Phase 4-B 자동-2: 씬 종료 시에도 아직 판정 안 한 환자는 1회 처리 보장.
    //   이벤트(patient_satisfied·rejected·abandoned) 는 GameScene 핸들러가 살아 있을 때만
    //   월간 카운터에 반영되므로 _onShutdown 은 반드시 "patients.destroy() 먼저 → events.off 뒤"
    //   순서를 지켜야 함. 반대로 하면 마지막 배치의 판정이 카운터에 누락됨.
    for (const p of this.patients) {
      if (!p.satisfactionEvaluated) this._evaluateSatisfaction(p);
      p.destroy();
    }
    this.patients.length = 0;
    if (this.events) {
      this.events.removeAllListeners();
      this.events = null;
    }
    this.scene = null;
    this.grid = null;
    this.pathSystem = null;
  }
}
