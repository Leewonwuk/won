import { BALANCE } from '../config.js';
import { FloatingText } from './FloatingText.js';

// 환자 상태 머신:
//   'arriving'  → walkTo(대기열)
//   'waiting'   → 인내심 타이머 작동, 방 배정 대기
//   'walking'   → 배정된 방으로 이동
//   'treating'  → 방에서 치료 받음 (Room이 진행)
//   'leaving'   → 화면 밖으로 퇴장

export class Patient {
  constructor(scene, x, y, type) {
    this.scene = scene;
    this.type = type;
    this.def = BALANCE.patients[type];
    if (!this.def) throw new Error('Unknown patient type: ' + type);

    this.state = 'arriving';
    this.assignedRoom = null;
    this.patienceMax = this.def.patience;
    this.patienceLeft = this.patienceMax;
    this.alive = true;

    // 스프라이트
    this.sprite = scene.add.sprite(x, y, `patient_${type}_1`);
    this.sprite.setOrigin(0.5, 1);
    this.sprite.setDepth(y);
    this.sprite.play(`walk_${type}`);

    // 산신령 후광 글로우
    if (this.def.aura) {
      this.sprite.setTint(0xffffff);
      scene.tweens.add({
        targets: this.sprite, alpha: { from: 1, to: 0.7 },
        duration: 900, yoyo: true, repeat: -1
      });
    }

    // 인내심 바 (머리 위)
    this.patienceBg = scene.add.rectangle(x, y - 48, 28, 4, 0x2a1810).setOrigin(0.5);
    this.patienceBar = scene.add.rectangle(x, y - 48, 26, 2, 0x4caf6f).setOrigin(0, 0.5);
    this.patienceBar.x = x - 13;
    this.patienceBg.setDepth(1000);
    this.patienceBar.setDepth(1001);

    // 환자 라벨
    this.label = scene.add.text(x, y - 58, this.def.label, {
      fontFamily: 'Noto Serif KR, serif',
      fontSize: '11px',
      color: '#e8dcc4',
      stroke: '#141414',
      strokeThickness: 2
    }).setOrigin(0.5).setDepth(1001);
  }

  // Phaser tween으로 이동. done 콜백 호출.
  // 메인 스프라이트만 tween, 부속 UI는 _syncUi()에서 따라옴.
  walkTo(tx, ty, done) {
    if (!this.alive) return;
    // 진행 중인 이전 tween 정지
    if (this._moveTween) { this._moveTween.stop(); this._moveTween = null; }

    // 방향에 따라 뒤집기
    this.sprite.setFlipX(tx < this.sprite.x);
    const dist = Phaser.Math.Distance.Between(this.sprite.x, this.sprite.y, tx, ty);
    const duration = Math.max(300, dist * 10);

    this._moveTween = this.scene.tweens.add({
      targets: this.sprite,
      x: tx,
      y: ty,
      duration,
      ease: 'Linear',
      onUpdate: () => this._syncUi(),
      onComplete: () => {
        this._moveTween = null;
        this._syncUi();
        this.sprite.setDepth(this.sprite.y);
        if (done) done();
      }
    });
  }

  _syncUi() {
    const x = this.sprite.x;
    const y = this.sprite.y;
    this.patienceBg.setPosition(x, y - 48);
    this.patienceBar.setPosition(x - 13, y - 48);
    this.label.setPosition(x, y - 58);
  }

  setState(s) { this.state = s; }

  updatePatience(dt) {
    if (!this.alive) return;
    if (this.state === 'waiting' || this.state === 'walking') {
      this.patienceLeft -= dt;
      if (this.patienceLeft <= 0 && !this._angered) {
        this.patienceLeft = 0;
        this._angered = true;
        this.onTimeout();
        return;
      }
    }
    const ratio = Phaser.Math.Clamp(this.patienceLeft / this.patienceMax, 0, 1);
    this.patienceBar.width = 26 * ratio;
    if (ratio > 0.5)       this.patienceBar.fillColor = 0x4caf6f;
    else if (ratio > 0.25) this.patienceBar.fillColor = 0xf7d05b;
    else                   this.patienceBar.fillColor = 0xe84a4a;
  }

  onTimeout() {
    if (!this.alive) return;
    if (this.onAngry) this.onAngry();
  }

  showSatisfaction(stars) {
    if (!this.alive) return;
    const x = this.sprite.x, y = this.sprite.y;
    // 별 아이콘 표시
    const starGroup = [];
    for (let i = 0; i < stars; i++) {
      const s = this.scene.add.image(x - 14 + i * 14, y - 56, 'star').setScale(1.2).setDepth(1100);
      s.setScale(0);
      this.scene.tweens.add({
        targets: s, scale: 1.4, duration: 200, delay: i * 80, yoyo: true,
        onComplete: () => { s.setScale(1.2); }
      });
      starGroup.push(s);
    }
    this.scene.time.delayedCall(900, () => starGroup.forEach(s => s.destroy()));
    FloatingText.spawn(this.scene, x, y - 30, stars === 3 ? '완벽!' : (stars === 2 ? '좋음!' : '괜찮음'),
      { color: stars === 3 ? '#f7d05b' : '#e8dcc4' });
  }

  showAnger() {
    if (!this.alive) return;
    const x = this.sprite.x, y = this.sprite.y;
    const a = this.scene.add.image(x, y - 56, 'anger').setScale(1.5).setDepth(1100);
    this.scene.tweens.add({
      targets: a, scale: 2, duration: 200, yoyo: true, repeat: 1,
      onComplete: () => a.destroy()
    });
    FloatingText.spawn(this.scene, x, y - 30, '불만!', { color: '#e84a4a' });
  }

  // 퇴장(화면 밖으로 걸어가 소멸)
  leave(exitX, exitY) {
    this.setState('leaving');
    // 치료 중 애니메이션이 멈춰있을 수 있으므로 걷기 애니메이션 재시작
    if (this.alive && this.sprite.anims) {
      this.sprite.play(`walk_${this.type}`, true);
    }
    this.walkTo(exitX, exitY, () => this.destroy());
  }

  destroy() {
    if (!this.alive) return;
    this.alive = false;
    this.sprite.destroy();
    this.patienceBg.destroy();
    this.patienceBar.destroy();
    this.label.destroy();
  }
}
