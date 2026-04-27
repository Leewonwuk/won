import { BALANCE } from '../config.js';
import { Room } from '../objects/Room.js';

// 방 4개를 생성하고 해금 체크를 담당
export class RoomSystem {
  constructor(scene) {
    this.scene = scene;
    this.rooms = {};
    this.list = [];
  }

  createRooms() {
    // 탑다운 2×2 그리드 배치
    // 방 텍스처 80×80, origin(0.5,1) → y는 방 하단 좌표
    const layout = [
      { type: 'moxa',        x: 190, y: 300 },  // 좌상
      { type: 'acupuncture', x: 570, y: 300 },  // 우상
      { type: 'herb',        x: 190, y: 460 },  // 좌하
      { type: 'bath',        x: 570, y: 460 }   // 우하
    ];
    for (const { type, x, y } of layout) {
      const r = new Room(this.scene, x, y, type);
      this.rooms[type] = r;
      this.list.push(r);
    }
    return this.list;
  }

  // 경제 시스템 스냅샷을 받아 방 해금 조건 체크
  checkUnlocks(totalSatisfied) {
    let newlyUnlocked = null;
    for (const r of this.list) {
      if (r.state !== 'locked') continue;
      const parent = r.spec.parent;
      if (!parent) continue;
      if ((totalSatisfied[parent] || 0) >= r.spec.unlockNeed) {
        r.unlock();
        newlyUnlocked = r;
      }
    }
    return newlyUnlocked;
  }

  // 환자를 받을 수 있는 빈 방 찾기 (환자 tier에 맞는 방 우선 배정)
  findAvailableRoom(patient) {
    // 호랑이는 약탕 필수
    if (patient.def.requireBath) {
      const bath = this.rooms.bath;
      if (bath && bath.canAccept(patient)) return bath;
      return null;
    }

    // 환자 tier → 적합한 방 순서 (낮은 tier는 저렴한 방부터, 높은 tier는 비싼 방부터)
    // tier 1~2(노비/백성) : moxa → acupuncture → herb → bath
    // tier 3(양반)        : acupuncture → herb → moxa → bath
    // tier 4+(왕족/요괴)  : herb → bath → acupuncture → moxa
    const tier = patient.def.tier || 1;
    let order;
    if (tier <= 2) {
      order = ['moxa', 'acupuncture', 'herb', 'bath'];
    } else if (tier === 3) {
      order = ['acupuncture', 'herb', 'moxa', 'bath'];
    } else {
      order = ['herb', 'bath', 'acupuncture', 'moxa'];
    }

    for (const t of order) {
      const r = this.rooms[t];
      if (r && r.canAccept(patient)) return r;
    }
    return null;
  }

  update(dt) {
    for (const r of this.list) r.update(dt);
  }
}
