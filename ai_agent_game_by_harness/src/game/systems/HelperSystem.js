export class HelperSystem {
  constructor(scene) {
    this.scene = scene
    this.elapsed = 0
    this.SPAWN_INTERVAL = 16000
    this.activeHelpers = []
  }

  spawnHelper(phase) {
    const scene = this.scene

    if (phase === 'day') {
      // 참새: 갈색 타원, 화면 오른쪽에서 왼쪽으로 날아가며 장애물 1개 제거
      const sparrow = scene.add.ellipse(820, 200, 28, 16, 0x8B6914)
      this.activeHelpers.push(sparrow)
      scene.tweens.add({
        targets: sparrow,
        x: -50,
        duration: 2000,
        ease: 'Linear',
        onUpdate: () => {
          // 장애물과 겹치면 제거
          const obs = scene.obstacles.find(o =>
            o.active && Math.abs(o.x - sparrow.x) < 40 && Math.abs(o.y - sparrow.y) < 80
          )
          if (obs) {
            obs.destroy()
            scene.obstacles = scene.obstacles.filter(o => o.active)
          }
        },
        onComplete: () => sparrow.destroy()
      })

    } else {
      // 쥐: 회색 원+꼬리, 지면 위를 달리며 아이템 1개 추가 스폰
      const rat = scene.add.circle(820, 340, 10, 0x888888)
      const tail = scene.add.rectangle(832, 342, 14, 3, 0x888888)
      this.activeHelpers.push(rat)
      scene.tweens.add({
        targets: [rat, tail],
        x: '-=600',
        duration: 3000,
        ease: 'Linear',
        onComplete: () => {
          rat.destroy()
          tail.destroy()
          if (scene.items !== undefined && scene.itemGroup) {
            const acorn = scene.physics.add.sprite(
              Phaser.Math.Between(300, 600), 290, 'acorn'
            )
            acorn.itemType = 'acorn'
            acorn.body.allowGravity = false
            scene.items.push(acorn)
            scene.itemGroup.add(acorn)
          }
        }
      })
    }
  }

  tryHitBoss(boss) {
    if (!boss || !boss.active) return
    this.activeHelpers = this.activeHelpers.filter(h => h && h.active)
    for (const helper of this.activeHelpers) {
      if (Math.abs(helper.x - boss.x) < 46 && Math.abs(helper.y - boss.y) < 56) {
        if (this.scene._checkHelperHitsBoss) this.scene._checkHelperHitsBoss(helper)
        helper.destroy()
      }
    }
  }

  update(delta) {
    this.elapsed += delta
    if (this.elapsed >= this.SPAWN_INTERVAL) {
      this.elapsed = 0
      const phase = this.scene.dayNight ? this.scene.dayNight.phase : 'day'
      this.spawnHelper(phase)
    }
  }
}
