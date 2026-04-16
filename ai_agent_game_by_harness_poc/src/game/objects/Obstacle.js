export class Obstacle extends Phaser.Physics.Arcade.Sprite {
  constructor(scene, x, y, obstacleType) {
    super(scene, x, y, obstacleType)
    scene.add.existing(this)
    scene.physics.add.existing(this)
    this.obstacleType = obstacleType
    this.hit = false
    this.body.setImmovable(true)
    this.body.allowGravity = false
    this.setDepth(7)
    if (obstacleType === 'syringe') {
      this.body.setSize(10, 42, true)
      this.body.setOffset(1, 5)
    } else {
      this.body.setSize(30, 40, true)
      this.body.setOffset(3, 8)
    }
  }

  markHit() {
    if (!this.active || this.hit) return
    this.hit = true
    this.body.enable = false
    this.setVelocity(0, 0)
    this.setTint(0xffbbbb)
    this.scene.tweens.add({
      targets: this,
      alpha: 0,
      scaleX: 0.82,
      scaleY: 0.82,
      duration: 120,
      onComplete: () => this.destroy()
    })
  }

  update(scrollSpeed) {
    if (this.hit) return
    // body.setVelocityX 로 이동해야 물리 충돌체도 함께 이동함
    // (sprite.x 직접 수정 시 물리 엔진이 body 위치로 덮어써서 충돌 미작동)
    this.body.setVelocityX(-scrollSpeed)
    if (this.x < -100) this.destroy()
  }
}
