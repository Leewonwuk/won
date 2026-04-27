import { audioSystem } from '../systems/AudioSystem.js'

export class IntroScene extends Phaser.Scene {
  constructor() {
    super({ key: 'IntroScene' })
  }

  create() {
    this.cameras.main.setBackgroundColor('#000000')

    // 타이틀
    this.add.text(400, 60, 'GO RUNNING', {
      fontFamily: "'Press Start 2P'",
      fontSize: '28px',
      color: '#ffffff'
    }).setOrigin(0.5)

    // 스토리 라인 3줄 (타이핑 효과)
    const lines = [
      '고라니는 동물협회에 발각되었다...',
      '마취총을 맞고 안락사 직전...',
      '정신이 번쩍! 수프리를 향해 달려라!'
    ]
    const lineY = [140, 200, 260]
    const lineObjects = []

    // 각 줄 텍스트 오브젝트를 먼저 빈 문자열로 생성
    lines.forEach((_, i) => {
      const t = this.add.text(400, lineY[i], '', {
        fontFamily: 'sans-serif',
        fontSize: '16px',
        color: i === 2 ? '#FFD700' : '#cccccc',
        wordWrap: { width: 680 }
      }).setOrigin(0.5)
      lineObjects.push(t)
    })

    // 타이핑 효과: 각 줄을 순차적으로 출력
    const typeText = (index) => {
      if (index >= lines.length) {
        // 모든 줄 출력 완료 → 시작 버튼 표시
        showStartPrompt()
        return
      }
      const fullText = lines[index]
      const textObj = lineObjects[index]
      let charIndex = 0
      const timer = this.time.addEvent({
        delay: 60,
        repeat: fullText.length - 1,
        callback: () => {
          charIndex++
          textObj.setText(fullText.slice(0, charIndex))
          if (charIndex >= fullText.length) {
            // 1.5초 후 다음 줄
            this.time.delayedCall(1500, () => typeText(index + 1))
          }
        }
      })
    }

    const showStartPrompt = () => {
      const prompt = this.add.text(400, 330, '[ SPACE or TAP to RUN ]', {
        fontFamily: "'Press Start 2P'",
        fontSize: '12px',
        color: '#aaaaaa'
      }).setOrigin(0.5)

      // 깜빡임
      this.tweens.add({
        targets: prompt,
        alpha: 0,
        duration: 500,
        yoyo: true,
        repeat: -1
      })

      // 입력 대기
      this.input.keyboard.once('keydown-SPACE', startGame)
      this.input.once('pointerdown', startGame)
    }

    const startGame = async () => {
      // audioSystem.init()은 반드시 사용자 인터랙션(스페이스/클릭) 콜백 안에서 호출
      await audioSystem.init()
      audioSystem.switchTheme('intro')
      this.scene.start('GameScene')
    }

    // 타이핑 시작
    typeText(0)
  }
}
