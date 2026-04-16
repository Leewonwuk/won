export class DayNightSystem {
  constructor(scene) {
    this.scene = scene
    this.isDaytime = true
    this.elapsed = 0
    this.CYCLE_MS = 60000  // 60초 주기
    this.overlay = null    // 반투명 어둠 overlay (밤)
    this._tween = null
  }

  create() {
    // 반투명 검정 overlay rectangle (800x400) 생성, alpha=0
    this.overlay = this.scene.add.rectangle(400, 200, 800, 400, 0x000033)
    this.overlay.setAlpha(0)
    this.overlay.setDepth(5)  // 배경 위, HUD 아래
  }

  update(delta) {
    this.elapsed += delta
    if (this.elapsed >= this.CYCLE_MS) {
      this.elapsed = 0                        // 반드시 리셋 (없으면 매 프레임 toggle)
      this.isDaytime = !this.isDaytime
      const targetAlpha = this.isDaytime ? 0 : 0.4
      // 이전 Tween 있으면 중단
      if (this._tween) this._tween.stop()
      this._tween = this.scene.tweens.add({
        targets: this.overlay,
        alpha: targetAlpha,
        duration: 3000,
        ease: 'Linear'
      })
      const theme = this.isDaytime ? 'day' : 'night'
      if (this.scene.audioSystem) this.scene.audioSystem.switchTheme(theme)
    }
  }

  get phase() { return this.isDaytime ? 'day' : 'night' }
}
