import { BALANCE } from '../config.js';
import { getBuildingByKey } from './BuildingRegistry.js';

// Phase 3 해금 체인.
// · 초기 해금: 마루 + 뜸방 (Phase 1-D 설정 유지).
// · 누적: patient_served 이벤트의 building.key 로 이용 카운터 증가 (fee 무관, 편의시설 포함).
//         patient_paid 가 아니라 patient_served 를 쓰는 이유: well(fee=0) 이용도
//         'any' 카운트에 반영돼야 스펙의 "전체 이용" 의미와 일치.
// · 해금 체크: BALANCE.unlockChain 을 매 이용마다 평가. 신규 해금 시 'unlocked' emit.
// · 'any' 방: 전체 이용 카운트 합 (well 포함).

const INITIAL_UNLOCKED = ['maru', 'moxa'];
const TRACKED_ROOMS = ['moxa', 'acu', 'herb', 'haewoso', 'well', 'gukbap'];
// Phase 4-B: 계층 해금 체인. 'nobi' 는 기본 해금. 순서는 tierThresholdByMyeongui 평가 순.
const INITIAL_TIERS = ['nobi'];
const TRACKED_TIERS = ['nongmin', 'sangin', 'seonbi', 'yangban'];

export class UnlockSystem {
  constructor(scene, patientsSystem) {
    this.scene = scene;
    this.events = new Phaser.Events.EventEmitter();
    this.unlocked = new Set(INITIAL_UNLOCKED);
    this.usageCount = Object.fromEntries(TRACKED_ROOMS.map((k) => [k, 0]));
    // Phase 4-B: 계층 해금 상태 — 명의 누적으로 확장.
    this.unlockedTiers = new Set(INITIAL_TIERS);

    this._patientsSystem = patientsSystem;
    this._onPatientServed = this._onPatientServed.bind(this);
    patientsSystem.events.on('patient_served', this._onPatientServed);
  }

  isUnlocked(key) { return this.unlocked.has(key); }
  isTierUnlocked(tier) { return this.unlockedTiers.has(tier); }

  // QA/튜토리얼/디버그용 직접 해금.
  forceUnlock(key) {
    if (this.unlocked.has(key)) return false;
    this.unlocked.add(key);
    this.events.emit('unlocked', { key, building: getBuildingByKey(key) });
    return true;
  }

  // Phase 4-B: 다음 미해금 계층. 월간 결산 "다음 계층 N/M" 진행률 라인용(⑧C).
  getNextTierTarget() {
    const th = BALANCE.tierThresholdByMyeongui || {};
    for (const tier of TRACKED_TIERS) {
      if (this.unlockedTiers.has(tier)) continue;
      return { tier, threshold: th[tier] || 0 };
    }
    return null;
  }

  // GameScene._applyMyeongui 가 호출. 누적 명의를 받아 임계 돌파한 계층 전부 해금.
  // 신규 해금마다 tier_unlocked emit — PatientSystem 동기화·환영 스폰(⑤B)·토스트 트리거.
  // 순서 계약: add 루프가 "전부" 끝난 뒤에만 emit 루프 진입. 같은 프레임에 여러 임계가
  //   동시에 돌파되어도 첫 emit 시점부터 unlockedTiers 는 이미 최종 상태(full set)이므로,
  //   GameScene._onTierUnlocked 가 매 emit 마다 setUnlockedTiers 를 호출해도 idempotent.
  //   Phaser EventEmitter 는 동기 dispatch — _trySpawn 같은 외부 루프가 중간에 끼어들 창 없음.
  checkTierUnlocks(currentMyeongui) {
    const th = BALANCE.tierThresholdByMyeongui || {};
    const newly = [];
    for (const tier of TRACKED_TIERS) {
      if (this.unlockedTiers.has(tier)) continue;
      const need = th[tier];
      if (need == null) continue;
      if (currentMyeongui >= need) {
        this.unlockedTiers.add(tier);
        newly.push(tier);
      }
    }
    for (const tier of newly) this.events.emit('tier_unlocked', { tier });
    return newly;
  }

  forceUnlockTier(tier) {
    if (!TRACKED_TIERS.includes(tier)) return false;
    if (this.unlockedTiers.has(tier)) return false;
    this.unlockedTiers.add(tier);
    this.events.emit('tier_unlocked', { tier });
    return true;
  }

  _onPatientServed({ building }) {
    if (!building) return;
    const key = building.key;
    if (this.usageCount[key] != null) {
      this.usageCount[key] += 1;
    }
    this._checkUnlocks();
  }

  _checkUnlocks() {
    const chain = BALANCE.unlockChain;
    if (!chain) return;
    const anyCount = TRACKED_ROOMS.reduce((sum, k) => sum + (this.usageCount[k] || 0), 0);
    for (const [target, req] of Object.entries(chain)) {
      if (this.unlocked.has(target)) continue;
      const cur = req.room === 'any' ? anyCount : (this.usageCount[req.room] || 0);
      if (cur >= req.count) {
        this.unlocked.add(target);
        this.events.emit('unlocked', { key: target, building: getBuildingByKey(target) });
      }
    }
  }

  destroy() {
    if (this._patientsSystem && this._patientsSystem.events) {
      this._patientsSystem.events.off('patient_served', this._onPatientServed);
    }
    if (this.events) {
      this.events.removeAllListeners();
      this.events = null;
    }
    this._patientsSystem = null;
    this.scene = null;
  }
}
