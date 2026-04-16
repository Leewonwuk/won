export class Gorani {
  constructor(scene, x, y) {
    this.scene = scene
    this._jumpCount = 0
    this._lastGroundState = true

    this.sprite = scene.physics.add.sprite(x, y, 'gorani-run-1')
    this.sprite.setOrigin(0.5, 1)
    this.sprite.setScale(1)
    this.sprite.body.setCollideWorldBounds(true)
    this.sprite.body.setSize(34, 48, true)
    this.sprite.setDepth(9)

    this.isInvincible = false
    this._hurtTimer = null
    scene.events.once('shutdown', () => this.destroy(), this)
  }

  jump() {
    if (this.isOnGround()) {
      this.sprite.body.setVelocityY(-500)
      this._jumpCount = 1
    } else if (this._jumpCount < 2) {
      // 2단 점프: 1단보다 살짝 약하게
      this.sprite.body.setVelocityY(-420)
      this._jumpCount = 2
    }
  }

  isOnGround() {
    return this.sprite.body.blocked.down
  }

  setNormalState() {
    this.isInvincible = false
    this._applyStateAnimation()
  }

  setHurtState() {
    if (this.isInvincible) return
    this.isInvincible = true
    this.sprite.anims.play('gorani-hurt', true)
    this._hurtTimer = this.scene.time.delayedCall(2000, () => this.setNormalState())
  }

  get body() { return this.sprite.body }

  _applyStateAnimation() {
    if (this.isInvincible) {
      this.sprite.anims.play('gorani-hurt', true)
      return
    }
    if (!this.isOnGround()) {
      const vy = this.sprite.body.velocity.y
      this.sprite.setTexture(vy < 0 ? 'gorani-jump-up' : 'gorani-jump-down')
      return
    }
    this.sprite.anims.play('gorani-run', true)
  }

  update() {
    const grounded = this.isOnGround()
    if (grounded) {
      this._jumpCount = 0
    }
    if (this._lastGroundState !== grounded || !grounded || this.isInvincible) {
      this._applyStateAnimation()
    }
    this._lastGroundState = grounded
    this.sprite.alpha = (this.isInvincible && Math.sin(this.scene.time.now / 100) <= 0) ? 0.35 : 1
  }

  hide() {
    this.sprite.setVisible(false)
  }

  show() {
    this.sprite.setVisible(true)
    this._applyStateAnimation()
  }

  destroy() {
    if (this._hurtTimer) this._hurtTimer.remove()
    if (this.sprite && this.sprite.active) this.sprite.destroy()
  }
}
