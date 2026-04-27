export class Item extends Phaser.Physics.Arcade.Sprite {
  constructor(scene, x, y, itemType) {
    super(scene, x, y, itemType)
    scene.add.existing(this)
    scene.physics.add.existing(this)
    this.itemType = itemType
    this.collected = false
    this.baseY = y
    this.floatPhase = Math.random() * Math.PI * 2
    this.body.allowGravity = false
    this.body.setVelocityY(0)
    this.setDepth(7)
    if (itemType === 'acorn') {
      this.body.setCircle(10, 2, 2)
    } else {
      this.body.setSize(20, 16, true)
    }
  }

  collect() {
    if (!this.active || this.collected) return
    this.collected = true
    this.body.enable = false
    this.setVelocity(0, 0)
    this.scene.tweens.add({
      targets: this,
      y: this.y - 16,
      alpha: 0,
      duration: 140,
      ease: 'Quad.easeOut',
      onComplete: () => this.destroy()
    })
  }

  update(scrollSpeed, delta = 16) {
    if (this.collected) return
    // 아이템 낙하 방지: 매 프레임 중력/수직속도 차단
    this.body.allowGravity = false
    this.body.setVelocityY(0)
    // 살짝 떠있는 느낌
    this.floatPhase += delta * 0.006
    const floatOffset = Math.sin(this.floatPhase) * 2.5
    this.setY(this.baseY + floatOffset)

    // body.setVelocityX 로 이동해야 물리 충돌체도 함께 이동함
    // 장애물보다 조금 느리게 흘려서 플레이어가 대응할 시간을 확보
    this.body.setVelocityX(-scrollSpeed * 0.82)
    if (this.x < -100) this.destroy()
  }
}
