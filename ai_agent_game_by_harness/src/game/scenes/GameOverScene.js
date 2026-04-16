import { audioSystem } from '../systems/AudioSystem.js'

export class GameOverScene extends Phaser.Scene {
  constructor() { super({ key: 'GameOverScene' }) }

  init(data) {
    this.finalScore = data ? data.score : 0
    this.finalDistance = data ? data.distance : 0
  }

  create() {
    audioSystem.switchTheme('gameover')

    this.add.rectangle(400, 200, 800, 400, 0x000000)

    this.add.text(400, 100, 'GAME OVER', {
      fontSize: '32px', fill: '#FF4444', fontFamily: '"Press Start 2P"'
    }).setOrigin(0.5)

    this.add.text(400, 160, '고라니가 잡혔다...', {
      fontSize: '18px', fill: '#AAAAAA', fontFamily: 'sans-serif'
    }).setOrigin(0.5)

    this.add.text(400, 220, `거리: ${this.finalDistance}m`, {
      fontSize: '16px', fill: '#FFFFFF', fontFamily: '"Press Start 2P"'
    }).setOrigin(0.5)

    this.add.text(400, 260, `점수: ${this.finalScore}`, {
      fontSize: '16px', fill: '#FFFF00', fontFamily: '"Press Start 2P"'
    }).setOrigin(0.5)

    const retryText = this.add.text(400, 330, '[ SPACE to RETRY ]', {
      fontSize: '14px', fill: '#AAAAAA', fontFamily: '"Press Start 2P"'
    }).setOrigin(0.5)

    // 깜빡임
    this.tweens.add({
      targets: retryText, alpha: 0,
      duration: 600, yoyo: true, repeat: -1
    })

    this.input.keyboard.once('keydown-SPACE', () => {
      this.scene.start('GameScene')
    })
    this.input.once('pointerdown', () => {
      this.scene.start('GameScene')
    })
  }
}
