import { BALANCE } from '../config.js';

// Phase 4-C — 티켓 풀 시스템 (카이로풍 평판 누적).
//
// ─── 설계 ─────────────────────────────────────────
//  · 치료티켓 풀: 치료 만족 시 발행 확률표(treatTicketIssuance) 적용 → 풀 적재.
//    - 15장 도달 시 tierSpawnWeight 가중치로 계층 결정 → spawn 요청 → 15장 차감.
//  · 편의티켓 풀: 편의 충족(ratioA≥1.0) 시 같은 계층 1장 발행.
//    - 15장 도달 시 풀에서 무작위 1장 추첨 → 그 계층 spawn + 수요 33/33/33 → 15장 차감.
//  · 만료: 발행 후 ticketLifeMs(120s) 경과 → 개별 제거 (update tick 마다 cutoff filter).
//
// ─── 외부 계약 ────────────────────────────────────
//  · GameScene 가 patient_satisfied 받아 onPatientSatisfied 호출.
//  · ticket_issued / ticket_redeem_treat / ticket_redeem_amenity emit.
//  · GameScene 가 redeem 이벤트를 PatientSystem.spawnOne 으로 라우팅.
//  · update(now) 는 GameScene.update 에서 매 프레임 호출.
export class TicketSystem {
  constructor(scene) {
    this.scene = scene;
    this.events = new Phaser.Events.EventEmitter();
    this.treatTickets = [];   // [{ kind, tier, createdAt }]
    this.amenityTickets = []; // [{ tier, createdAt }]
  }

  // patient_satisfied 이벤트 수신.
  // Q1 권장 A: result==='satisfied' 만 발행.
  // Q2 권장 B: 편의티켓은 ratioA≥1.0 충족 시만 발행 (amenityScore/needAmenity).
  onPatientSatisfied({ patient, tier, result, treatScore, amenityScore, needTreat, needAmenity }) {
    if (result !== 'satisfied') return;

    // 치료티켓: 사용한 최고등급 치료방 기준 확률표 적용.
    const top = patient.highestTreatUsed;
    if (top) {
      const kind = this._rollTreatKind(top);
      if (kind) {
        this.treatTickets.push({ kind, tier, createdAt: this.scene.time.now });
        this.events.emit('ticket_issued', { type: 'treat', kind, tier });
        this._tryRedeemTreat();
      }
    }

    // 편의티켓: ratioA ≥ 1.0 일 때만.
    if (needAmenity > 0 && amenityScore >= needAmenity) {
      this.amenityTickets.push({ tier, createdAt: this.scene.time.now });
      this.events.emit('ticket_issued', { type: 'amenity', tier });
      this._tryRedeemAmenity();
    }
  }

  // 발행 확률표에서 치료티켓 종류 1개 결정.
  _rollTreatKind(highest) {
    const table = BALANCE.treatTicketIssuance[highest];
    if (!table || table.length === 0) return null;
    const r = Math.random();
    let acc = 0;
    for (const { kind, prob } of table) {
      acc += prob;
      if (r < acc) return kind;
    }
    return table[table.length - 1].kind;
  }

  _tryRedeemTreat() {
    if (this.treatTickets.length < BALANCE.ticketsToSpawn) return;
    // 가중치 스폰 (Q3 권장 B: tierSpawnWeight, 미해금 계층 자연 차단).
    const tier = this._sampleTierByWeight();
    if (!tier) return; // 해금된 계층 없음 (이론상 nobi=6 항상 존재)
    this.treatTickets.splice(0, BALANCE.ticketsToSpawn);
    this.events.emit('ticket_redeem_treat', { tier });
  }

  _tryRedeemAmenity() {
    if (this.amenityTickets.length < BALANCE.ticketsToSpawn) return;
    // 풀 안에서 무작위 1장 추첨 — 그 티켓의 tier 가 새 환자 계층.
    const idx = Math.floor(Math.random() * this.amenityTickets.length);
    const picked = this.amenityTickets[idx];
    this.amenityTickets.splice(0, BALANCE.ticketsToSpawn);
    // 수요는 33/33/33 — 새 환자가 어떤 시설을 우선할지 메타(현 단계는 통계용).
    const demand = this._rollAmenityDemand();
    this.events.emit('ticket_redeem_amenity', { tier: picked.tier, demand });
  }

  _rollAmenityDemand() {
    const table = BALANCE.amenityRedeemDemand;
    const r = Math.random();
    let acc = 0;
    for (const [kind, prob] of Object.entries(table)) {
      acc += prob;
      if (r < acc) return kind;
    }
    return 'herb';
  }

  // PatientSystem._pickTierByUnlock 와 동일 로직 (가중치 + 해금 필터).
  // 중복 정의: TicketSystem 은 PatientSystem 의 내부 상태(unlockedTiers) 를 직접 모르므로
  // GameScene 이 setUnlockedTiers 로 동기화해줌.
  _sampleTierByWeight() {
    const weights = BALANCE.tierSpawnWeight || {};
    const unlocked = this._unlockedTiers || new Set(['nobi']);
    const pool = [];
    let total = 0;
    for (const tier of unlocked) {
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

  setUnlockedTiers(tiers) {
    this._unlockedTiers = new Set(tiers);
  }

  // 만료 검사 — GameScene.update 가 매 프레임 호출.
  update(now) {
    const cutoff = now - BALANCE.ticketLifeMs;
    const beforeT = this.treatTickets.length;
    const beforeA = this.amenityTickets.length;
    this.treatTickets   = this.treatTickets.filter((t) => t.createdAt > cutoff);
    this.amenityTickets = this.amenityTickets.filter((t) => t.createdAt > cutoff);
    if (this.treatTickets.length !== beforeT || this.amenityTickets.length !== beforeA) {
      this.events.emit('ticket_expired');
    }
  }

  counts() {
    return { treat: this.treatTickets.length, amenity: this.amenityTickets.length };
  }

  destroy() {
    if (this.events) {
      this.events.removeAllListeners();
      this.events = null;
    }
    this.treatTickets.length = 0;
    this.amenityTickets.length = 0;
    this.scene = null;
  }
}
