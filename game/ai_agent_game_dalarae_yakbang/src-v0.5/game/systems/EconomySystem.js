import { BALANCE } from '../config.js';

// 골드, 누적 만족/불만, 레벨업 카운팅 담당
export class EconomySystem {
  constructor(scene) {
    this.scene = scene;
    this.gold = BALANCE.startGold;
    this.todayIncome = 0;
    this.todaySatisfied = 0;
    this.todayAngry = 0;

    // 방별 누적 만족 환자 수 (해금 판정용)
    this.totalSatisfied = { moxa: 0, acupuncture: 0, herb: 0, bath: 0 };

    // Act 2 해금 판정용
    this.royalSatisfied = 0;
    this.actUnlocked = 1;
  }

  addGold(amount) {
    this.gold += amount;
    this.todayIncome += amount;
  }

  spendGold(amount) {
    if (this.gold < amount) return false;
    this.gold -= amount;
    return true;
  }

  onSatisfied(room, patient) {
    this.totalSatisfied[room.type]++;
    this.todaySatisfied++;
    if (patient.type === 'royal') this.royalSatisfied++;
  }

  onAngry(patient) {
    this.todayAngry++;
  }

  resetDay() {
    this.todayIncome = 0;
    this.todaySatisfied = 0;
    this.todayAngry = 0;
  }

  canUnlockAct2() {
    return this.actUnlocked === 1 && this.royalSatisfied >= BALANCE.act2RoyalNeeded;
  }
}
