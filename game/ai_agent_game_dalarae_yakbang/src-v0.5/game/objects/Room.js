import { BALANCE } from '../config.js';
import { FloatingText } from './FloatingText.js';

// 방 상태: 'locked' | 'idle' | 'treating'
export class Room {
  constructor(scene, x, y, type) {
    this.scene = scene;
    this.type = type;
    this.spec = BALANCE.rooms[type];
    this.x = x; this.y = y;
    this.state = this.spec.unlockNeed > 0 ? 'locked' : 'idle';

    // 컨테이너
    this.container = scene.add.container(x, y);
    this.container.setDepth(100);

    // 본체 스프라이트
    this.sprite = scene.add.image(0, 0, this.state === 'locked' ? 'room_locked' : `room_${type}`);
    this.sprite.setOrigin(0.5, 1);
    this.container.add(this.sprite);

    // 라벨 (방 위에 뜨는 이름표)
    this.label = scene.add.text(0, -86, this.spec.label, {
      fontFamily: 'Noto Serif KR, serif',
      fontSize: '14px',
      fontStyle: 'bold',
      color: this.state === 'locked' ? '#5a4a34' : '#f7d05b',
      stroke: '#2a1810',
      strokeThickness: 3
    }).setOrigin(0.5);
    this.container.add(this.label);

    // 치료 게이지 (방 하단에)
    this.gaugeBg = scene.add.rectangle(0, 8, 68, 6, 0x2a1810).setOrigin(0.5);
    this.gaugeFg = scene.add.rectangle(-34, 8, 0, 4, 0x4caf6f).setOrigin(0, 0.5);
    this.gaugeBg.visible = false;
    this.gaugeFg.visible = false;
    this.container.add([this.gaugeBg, this.gaugeFg]);

    // 해금 요구 텍스트 (방 중앙에)
    if (this.state === 'locked') {
      const parentSpec = BALANCE.rooms[this.spec.parent];
      const need = this.spec.unlockNeed;
      this.lockLabel = scene.add.text(0, -44, `${parentSpec.label}\n만족 ${need}명 필요`, {
        fontFamily: 'Noto Serif KR, serif',
        fontSize: '11px',
        color: '#e8dcc4',
        align: 'center',
        stroke: '#2a1810',
        strokeThickness: 3
      }).setOrigin(0.5);
      this.container.add(this.lockLabel);
    }

    // 인터랙션 영역 (80×80 탑다운 텍스처에 맞게)
    this.sprite.setInteractive(new Phaser.Geom.Rectangle(-40, -80, 80, 80), Phaser.Geom.Rectangle.Contains);
    this.sprite.on('pointerdown', () => this._onClick());
    this.sprite.on('pointerover', () => { if (this.state !== 'locked') this.container.setScale(1.04); });
    this.sprite.on('pointerout',  () => this.container.setScale(1.0));

    // 내부 상태
    this.currentPatient = null;
    this.incomingPatient = null; // 걸어오는 중인 예약 환자 (이중 배정 방지)
    this.treatElapsed = 0;
    this.treatTotal = this.spec.treatMs;
    this.clickCount = 0;
    this.boostBank = 0; // 미리 쌓아둔 클릭 가속분
  }

  _onClick() {
    if (this.state === 'locked') {
      FloatingText.spawn(this.scene, this.x, this.y - 40, '아직 열 수 없어요', { color: '#e84a4a', size: 14 });
      return;
    }
    if (this.state === 'treating') {
      this.clickBoost();
    } else {
      // 빈 방 클릭 피드백
      this.scene.tweens.add({
        targets: this.container, scale: 1.08, duration: 80, yoyo: true
      });
    }
  }

  unlock() {
    if (this.state !== 'locked') return;
    this.state = 'idle';
    this.sprite.setTexture(`room_${this.type}`);
    this.label.setColor('#f7d05b');
    if (this.lockLabel) { this.lockLabel.destroy(); this.lockLabel = null; }

    // 해금 이펙트
    FloatingText.spawn(this.scene, this.x, this.y - 80, '해금!', { color: '#f7d05b', size: 26, rise: 60, duration: 1400 });
    this.scene.tweens.add({
      targets: this.container, scale: { from: 1.3, to: 1 }, duration: 400, ease: 'Back.Out'
    });
    if (this.scene.audioSys) this.scene.audioSys.playSFX('unlock');
  }

  canAccept(patient) {
    if (this.state !== 'idle') return false;
    if (this.incomingPatient !== null) return false; // 이미 걸어오는 환자가 있으면 예약 불가
    // 호랑이는 약탕 필수
    if (patient.def.requireBath && this.type !== 'bath') return false;
    return true;
  }

  startTreatment(patient) {
    this.incomingPatient = null; // 예약 해제 (안전 처리)
    this.state = 'treating';
    this.currentPatient = patient;
    this.treatElapsed = 0;
    this.clickCount = 0;
    this.boostBank = 0;
    this.gaugeBg.visible = true;
    this.gaugeFg.visible = true;
    this.gaugeFg.width = 0;

    patient.setState('treating');
    // 환자를 방 바닥 중앙에 안착 (탑다운 — 방 중심)
    patient.sprite.setPosition(this.x, this.y - 40);
    patient._syncUi();
    patient.sprite.anims.stop();
    // setFrame(0) 대신 명시적으로 1번 프레임 텍스처 지정 — 멈춘 포즈 보장
    patient.sprite.setTexture(`patient_${patient.type}_1`);
  }

  clickBoost() {
    if (this.state !== 'treating') return;
    this.clickCount++;
    this.boostBank += BALANCE.clickBoostMs; // ms — 1 클릭 = 설정된 가속량
    // 피드백
    this.scene.tweens.add({
      targets: this.sprite, scale: 1.08, duration: 60, yoyo: true
    });
    FloatingText.spawn(this.scene, this.x + Phaser.Math.Between(-20, 20), this.y - 50,
      '+', { color: '#f7d05b', size: 14, rise: 20, duration: 400 });
  }

  update(dt) {
    if (this.state !== 'treating' || !this.currentPatient) return;

    // 시간 경과 + 클릭 가속 흡수
    let progress = dt;
    if (this.boostBank > 0) {
      const take = Math.min(this.boostBank, dt * 1.2);
      this.boostBank -= take;
      progress += take;
    }
    this.treatElapsed += progress;

    const ratio = Phaser.Math.Clamp(this.treatElapsed / this.treatTotal, 0, 1);
    this.gaugeFg.width = 68 * ratio;

    if (ratio >= 1) this.completeTreatment();
  }

  completeTreatment() {
    const patient = this.currentPatient;
    if (!patient) return;

    // 만족도 계산: 남은 인내심 비율 + 클릭 보너스
    const patienceRatio = patient.patienceLeft / patient.patienceMax;
    const clickBonus = Math.min(0.3, this.clickCount / 40);
    const satScore = Phaser.Math.Clamp(patienceRatio + clickBonus, 0, 1);

    let stars = 1;
    if (satScore >= patient.def.satNeed + 0.2) stars = 3;
    else if (satScore >= patient.def.satNeed) stars = 2;

    const gold = Math.round(this.spec.fee * patient.def.feeMul * stars);

    // 결과 표시
    patient.showSatisfaction(stars);
    FloatingText.spawn(this.scene, this.x, this.y - 90, `+${gold}`, { color: '#f7d05b', size: 22 });

    if (this.scene.audioSys) this.scene.audioSys.playSFX('coin');
    if (stars === 3 && this.scene.audioSys) this.scene.audioSys.playSFX('treat');

    // 방 초기화 — 이벤트 emit 전에 idle로 돌려야 tryAssignWaiting이 즉시 이 방을 사용 가능
    this.state = 'idle';
    this.currentPatient = null;
    this.gaugeBg.visible = false;
    this.gaugeFg.visible = false;

    // 씬에 결과 통보
    this.scene.events.emit('patient_satisfied', {
      patient, room: this, stars, gold
    });
  }

  // 환자가 치료 도중 포기(인내심 0) — 거의 일어나지 않지만 보호용
  abortTreatment() {
    if (!this.currentPatient) return;
    this.incomingPatient = null;
    this.state = 'idle';
    this.currentPatient = null;
    this.gaugeBg.visible = false;
    this.gaugeFg.visible = false;
  }
}
