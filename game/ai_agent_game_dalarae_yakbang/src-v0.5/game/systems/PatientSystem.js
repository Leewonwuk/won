import { BALANCE } from '../config.js';
import { Patient } from '../objects/Patient.js';

// 게임 씬 좌표 상수 — 씬에서도 공유.
export const GameBoundaries = {
  entry: { x: 820, y: 370 },  // 우측 바깥에서 등장 (두 줄 방의 중간 높이)
  exit:  { x: -40, y: 370 }   // 좌측 바깥으로 퇴장
};

// 환자 스폰/대기열/소개 로직
export class PatientSystem {
  constructor(scene) {
    this.scene = scene;
    this.waiting = [];      // 대기 중 환자
    this.active = [];       // 씬 위 모든 환자 (대기/치료/이동)
    this.spawnTimer = null;

    // 대기열 좌표 — 우측 복도 (두 줄 방 사이 중간)
    this.queueX0 = 710;
    this.queueY = 370;
    this.queueStep = -26;   // 한 자리당 왼쪽으로
    this.entryX = GameBoundaries.entry.x;
    this.entryY = GameBoundaries.entry.y;
    this.exitX = GameBoundaries.exit.x;
    this.exitY = GameBoundaries.exit.y;
  }

  start() {
    const scheduleNext = () => {
      if (!this.scene || !this.scene.scene.isActive()) return;
      const unlockedCount = this.scene.roomSys.list.filter(r => r.state !== 'locked').length;
      const base = BALANCE.spawnIntervalBase;
      const delay = Math.max(BALANCE.spawnIntervalMin, base - (unlockedCount - 1) * 900);
      this.scene.time.delayedCall(delay, () => {
        this.spawnPatient();
        scheduleNext();
      });
    };
    // 첫 환자는 바로
    this.scene.time.delayedCall(800, () => {
      this.spawnPatient();
      scheduleNext();
    });
  }

  _pickType() {
    const act = this.scene.econ.actUnlocked;
    const probs = (act === 2) ? BALANCE.act2Probs : BALANCE.act1Probs;
    // 가중 랜덤 선택
    let r = Math.random();
    for (const [type, p] of Object.entries(probs)) {
      if (r < p) return type;
      r -= p;
    }
    return Object.keys(probs)[0];
  }

  spawnPatient(forcedType = null) {
    const type = forcedType || this._pickType();
    const p = new Patient(this.scene, this.entryX, this.entryY, type);
    this.active.push(p);
    if (this.scene.audioSys) this.scene.audioSys.playSFX('spawn');

    // 대기열로 이동 시도 → 빈 방 있으면 바로 배정
    this._tryAssignOrQueue(p);
  }

  _tryAssignOrQueue(patient) {
    const room = this.scene.roomSys.findAvailableRoom(patient);
    if (room) {
      room.incomingPatient = patient; // 방 예약 — 이중 배정 방지
      patient.setState('walking');
      patient.walkTo(room.x, room.y - 40, () => {
        room.incomingPatient = null; // 도착 시 예약 해제
        if (!patient.alive || patient._angered) return; // 인내심 만료된 환자는 진입 차단
        if (room.state === 'idle') {
          room.startTreatment(patient);
        } else {
          // 도착했는데 누가 이미 들어갔다면 대기열로
          this._enqueue(patient);
        }
      });
    } else {
      this._enqueue(patient);
    }
  }

  _enqueue(patient) {
    patient.setState('waiting');
    this.waiting.push(patient);
    this._repositionQueue();
  }

  _repositionQueue() {
    for (let i = 0; i < this.waiting.length; i++) {
      const p = this.waiting[i];
      const tx = this.queueX0 + i * this.queueStep;
      const ty = this.queueY;
      if (Math.abs(p.sprite.x - tx) > 2 || Math.abs(p.sprite.y - ty) > 2) {
        p.walkTo(tx, ty, () => { /* arrived */ });
      }
    }
  }

  // 대기열에서 다음 환자를 빈 방에 배정
  tryAssignWaiting() {
    if (this.waiting.length === 0) return;
    for (let i = 0; i < this.waiting.length; i++) {
      const p = this.waiting[i];
      const r = this.scene.roomSys.findAvailableRoom(p);
      if (r) {
        r.incomingPatient = p; // 방 예약 — 이중 배정 방지
        this.waiting.splice(i, 1);
        p.setState('walking');
        p.walkTo(r.x, r.y - 8, () => {
          r.incomingPatient = null; // 도착 시 예약 해제
          if (!p.alive || p._angered) return; // 인내심 만료된 환자는 진입 차단
          if (r.state === 'idle') r.startTreatment(p);
          else this._enqueue(p);
        });
        this._repositionQueue();
        return;
      }
    }
  }

  update(dt) {
    // 인내심 업데이트 — updatePatience가 onAngry를 호출하면 active에서 splice될 수 있으므로
    // 스냅샷 복사 후 순회.
    const snapshot = this.active.slice();
    for (const p of snapshot) {
      if (p.alive) p.updatePatience(dt);
    }
  }

  // 만족 퇴장 + 소개 예약
  onSatisfied(patient, room) {
    const idx = this.active.indexOf(patient);
    if (idx >= 0) this.active.splice(idx, 1);

    // 퇴장
    patient.leave(this.exitX, this.exitY);

    // 소개: 방 종류별 확률로 다음 tier 환자 예약
    const refChance = BALANCE.referral[room.type];
    if (refChance && Math.random() < refChance) {
      this.scene.time.delayedCall(BALANCE.introDelayMs, () => {
        // 소개 환자 타입 결정 (해당 방의 "다음 단계"에 맞는 tier 선호)
        const introType = this._pickIntroTypeFor(room.type);
        this.spawnPatient(introType);
      });
    }

    // 대기열에서 다음 환자 배정 시도
    this.tryAssignWaiting();
  }

  _pickIntroTypeFor(fromRoomType) {
    const act = this.scene.econ.actUnlocked;
    if (act === 2) return this._pickType();
    // 뜸방 만족 → 침방 타겟 환자(백성/양반)
    // 침방 만족 → 약방 타겟 환자(양반/왕족)
    // 약방 만족 → 약탕 타겟 환자(왕족)
    const map = {
      moxa: ['commoner', 'yangban'],
      acupuncture: ['yangban', 'royal'],
      herb: ['royal', 'yangban'],
      bath: ['royal']
    };
    const pool = map[fromRoomType] || ['commoner'];
    return pool[Math.floor(Math.random() * pool.length)];
  }

  onAngry(patient) {
    // 이 환자가 예약 중인 방 해제 (걷는 도중 인내심 만료 시 방이 영구 잠기는 버그 방지)
    for (const r of this.scene.roomSys.list) {
      if (r.incomingPatient === patient) r.incomingPatient = null;
    }

    const idx = this.active.indexOf(patient);
    if (idx >= 0) this.active.splice(idx, 1);
    const qi = this.waiting.indexOf(patient);
    if (qi >= 0) { this.waiting.splice(qi, 1); this._repositionQueue(); }

    patient.showAnger();
    if (this.scene.audioSys) this.scene.audioSys.playSFX('angry');

    this.scene.time.delayedCall(400, () => {
      if (patient.alive) patient.leave(this.exitX, this.exitY);
    });
  }
}
