import { Gorani } from '../objects/Gorani.js'
import { Obstacle } from '../objects/Obstacle.js'
import { Item } from '../objects/Item.js'
import { audioSystem } from '../systems/AudioSystem.js'
import { DayNightSystem } from '../systems/DayNightSystem.js'
import { HelperSystem } from '../systems/HelperSystem.js'

export class GameScene extends Phaser.Scene {
  constructor() { super({ key: 'GameScene' }) }

  create() {
    // 배경 (스카이블루 rectangle, 800x350)
    this.add.rectangle(400, 175, 800, 350, 0x87CEEB)
    // 원거리 구름층 (느린 패럴랙스)
    this.clouds = []
    for (let i = 0; i < 4; i++) {
      const cloud = this.add.ellipse(i * 230 + 90, 90 + (i % 2) * 25, 120, 40, 0xffffff, 0.45)
      this.clouds.push(cloud)
    }

    // 도시 건물 실루엣 (6개, 각각 다른 높이의 회색 직사각형)
    this.buildings = []
    const heights = [80, 120, 60, 140, 90, 110]
    for (let i = 0; i < 6; i++) {
      const h = heights[i]
      const bld = this.add.rectangle(
        i * 140 + 70, 350 - h / 2,
        120, h, 0xAAAAAA
      )
      this.buildings.push(bld)
    }
    // 전경 빌딩(빠른 패럴랙스)
    this.frontBuildings = []
    for (let i = 0; i < 5; i++) {
      const h = 140 + (i % 3) * 30
      const fb = this.add.rectangle(i * 170 + 85, 350 - h / 2, 140, h, 0x7d7d7d, 0.65)
      this.frontBuildings.push(fb)
    }

    // 지면: physics static group으로 만들어야 고라니가 발판 위에 설 수 있다
    // invisible static body (y=358, 800x16)
    this.ground = this.physics.add.staticGroup()
    this.ground.create(400, 358, 'ground-px')
      .setVisible(false)
      .setDisplaySize(800, 16)
      .refreshBody()   // setDisplaySize 후 body 크기 재계산 — 필수

    // 보이는 지면 색상 바
    this.add.rectangle(400, 362, 800, 16, 0x7A5C3E)

    // 고라니 생성 (y=340: 지면 위)
    this.gorani = new Gorani(this, 150, 340)
    this._wasGrounded = true

    // 고라니 ↔ 지면 충돌 등록 (이것 없으면 고라니가 지면을 통과해 무한 낙하)
    this.physics.add.collider(this.gorani.sprite, this.ground)

    // 입력
    this.cursors = this.input.keyboard.createCursorKeys()
    this.spaceKey = this.input.keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.SPACE)
    this.pauseKey = this.input.keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.ESC)
    this.pKey     = this.input.keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.P)
    this.input.addPointer(2)
    this.input.on('pointerdown', (ptr) => {
      // 일시정지 버튼 영역(우상단) 클릭 시 점프 무시
      if (ptr.x > 740 && ptr.y < 50) return
      // 모바일 점프 버튼 영역(우하단) 클릭 시 글로벌 점프 중복 방지
      if (ptr.x > 680 && ptr.y > 300) return
      this._requestJump()
    })

    this.isPaused = false

    // 거리·점수
    this.distance = 0
    this.score = 0
    this.scrollSpeed = 290
    this.baseSpeed = 290
    this.maxSpeed = 640

    // HUD 텍스트
    this.distText = this.add.text(700, 10, '0m', {
      fontSize: '14px', fill: '#333', fontFamily: '"Press Start 2P"'
    }).setOrigin(1, 0).setDepth(10)
    this.speedText = this.add.text(700, 32, 'SPD 300', {
      fontSize: '11px', fill: '#555', fontFamily: '"Press Start 2P"'
    }).setOrigin(1, 0).setDepth(10)
    this.scoreText = this.add.text(700, 52, 'SCR 0', {
      fontSize: '11px', fill: '#4f4f4f', fontFamily: '"Press Start 2P"'
    }).setOrigin(1, 0).setDepth(10)

    // ① HP 및 배열 초기화
    this.hp = 3
    this.obstacles = []
    this.items = []

    // ② Physics group 먼저 선언 (overlap 등록 전에 반드시 먼저!)
    this.obstacleGroup = this.physics.add.group()
    this.itemGroup = this.physics.add.group()

    // ③ 충돌 처리 등록 (group이 선언된 후에만 가능)
    this.physics.add.overlap(
      this.gorani.sprite,
      this.obstacleGroup,
      this.onHit,
      (goraniSprite, obstacle) => !this.gorani.isInvincible,
      this
    )
    this.physics.add.overlap(
      this.gorani.sprite,
      this.itemGroup,
      this.onCollect,
      (goraniSprite, item) => item.active && !item.collected,
      this
    )

    // ④ HP 표시 텍스트
    this.hpText = this.add.text(10, 10, '♥♥♥', {
      fontSize: '20px', fill: '#FF4444'
    }).setDepth(10)
    this.updateScoreDisplay()

    // ⑤ 스폰 타이머
    this.time.addEvent({
      delay: 2200,
      loop: true,
      callback: () => {
        if (this.isPaused || this.boss) return
        const types = ['trash', 'syringe']
        const t = types[Math.floor(Math.random() * 2)]
        const y = t === 'syringe' ? 322 : 330
        const obs = new Obstacle(this, 830, y, t)
        this.obstacles.push(obs)
        this.obstacleGroup.add(obs)
      }
    })
    this.time.addEvent({
      delay: 2600,
      loop: true,
      callback: () => {
        if (this.isPaused) return
        const t = Math.random() < 0.68 ? 'acorn' : 'leaf'
        // 먹기 쉬운 2개 레인으로 제한 (지면 근접 낙하 체감 방지)
        const lanes = t === 'acorn' ? [258, 282] : [250, 272]
        const y = lanes[Math.floor(Math.random() * lanes.length)]
        const item = new Item(this, 920, y, t)
        item.setScale(t === 'acorn' ? 1 : 1.05)
        this.items.push(item)
        this.itemGroup.add(item)
      }
    })

    // audioSystem은 IntroScene에서 이미 init()됨 — 여기선 재호출 불필요
    audioSystem.switchTheme('day')
    this.audioSystem = audioSystem   // DayNightSystem이 this.scene.audioSystem으로 참조

    // 보스 초기화 (반드시 초기화 — spawnBoss의 if(this.boss) 가드용)
    this.boss = null
    this.nextMidBossAt = 200
    this.nextFinalBossAt = 400

    // 낮/밤 & 도우미 시스템 초기화
    this.dayNight = new DayNightSystem(this)
    this.dayNight.create()
    this.helper = new HelperSystem(this)

    // 보스 텍스처 미리 생성
    this._createBossTextures()

    // 일시정지 오버레이
    this._pauseOverlay = this.add.rectangle(400, 200, 800, 400, 0x000000, 0.6).setDepth(20).setVisible(false)
    this._pauseText = this.add.text(400, 180, 'PAUSED', {
      fontFamily: '"Press Start 2P"', fontSize: '36px', fill: '#ffffff'
    }).setOrigin(0.5).setDepth(21).setVisible(false)
    this.add.text(400, 240, 'ESC / P  to resume', {
      fontFamily: '"Press Start 2P"', fontSize: '11px', fill: '#aaaaaa'
    }).setOrigin(0.5).setDepth(21)

    // 일시정지 버튼 (우상단)
    const pauseBtn = this.add.text(770, 14, '⏸', {
      fontSize: '22px'
    }).setOrigin(1, 0).setDepth(20).setInteractive({ useHandCursor: true })
    pauseBtn.on('pointerdown', () => this.togglePause())
    this._pauseBtn = pauseBtn

    // 모바일 점프 버튼 (우하단)
    this._jumpBtnBg = this.add.circle(736, 332, 40, 0xffffff, 0.22)
      .setDepth(20).setInteractive({ useHandCursor: true })
    this._jumpBtnBorder = this.add.circle(736, 332, 42)
      .setStrokeStyle(2, 0xffffff, 0.45).setDepth(20)
    this._jumpBtnText = this.add.text(736, 332, 'JUMP', {
      fontFamily: '"Press Start 2P"',
      fontSize: '12px',
      color: '#ffffff'
    }).setOrigin(0.5).setDepth(21)
    this._jumpBtnBg.on('pointerdown', () => {
      this._jumpBtnBg.setFillStyle(0xffffff, 0.38)
      this._requestJump()
    })
    this._jumpBtnBg.on('pointerup', () => this._jumpBtnBg.setFillStyle(0xffffff, 0.22))
    this._jumpBtnBg.on('pointerout', () => this._jumpBtnBg.setFillStyle(0xffffff, 0.22))

    // 속도감 파티클 (먼지)
    if (!this.textures.exists('dust-dot')) {
      const g = this.add.graphics()
      g.fillStyle(0xf0f0f0)
      g.fillCircle(2, 2, 2)
      g.generateTexture('dust-dot', 4, 4)
      g.destroy()
    }
    this.dustEmitter = this.add.particles(0, 0, 'dust-dot', {
      speedX: { min: -240, max: -80 },
      speedY: { min: -20, max: 20 },
      scale: { start: 1, end: 0 },
      alpha: { start: 0.55, end: 0 },
      lifespan: 380,
      frequency: 55,
      quantity: 1
    })
    this.dustEmitter.startFollow(this.gorani.sprite, -14, 8)
  }

  togglePause() {
    this.isPaused = !this.isPaused
    if (this.isPaused) {
      this.physics.pause()
      audioSystem.stop()
      this._pauseOverlay.setVisible(true)
      this._pauseText.setVisible(true)
      this._pauseBtn.setText('▶')
      this.gorani.hide()
    } else {
      this.physics.resume()
      audioSystem.switchTheme(this.dayNight ? this.dayNight.phase : 'day')
      this._pauseOverlay.setVisible(false)
      this._pauseText.setVisible(false)
      this._pauseBtn.setText('⏸')
      this.gorani.show()
    }
  }

  update(time, delta) {
    // 일시정지 토글
    if (Phaser.Input.Keyboard.JustDown(this.pauseKey) ||
        Phaser.Input.Keyboard.JustDown(this.pKey)) {
      this.togglePause()
    }
    if (this.isPaused) return

    // 점프 입력
    if (Phaser.Input.Keyboard.JustDown(this.spaceKey) ||
        Phaser.Input.Keyboard.JustDown(this.cursors.up)) {
      this._requestJump()
    }

    this.gorani.update()
    const grounded = this.gorani.isOnGround()
    if (!this._wasGrounded && grounded) {
      // 착지 임팩트
      this.cameras.main.shake(80, 0.0015)
      this.cameras.main.flash(60, 255, 255, 255, false)
      this.dustEmitter.explode(7, this.gorani.sprite.x - 12, this.gorani.sprite.y + 8)
    }
    this._wasGrounded = grounded

    // 건물 스크롤
    this.clouds.forEach(c => {
      c.x -= this.scrollSpeed * 0.09 * delta / 1000
      if (c.x < -90) c.x += 4 * 230
    })
    this.buildings.forEach(b => {
      b.x -= this.scrollSpeed * 0.45 * delta / 1000
      if (b.x < -70) b.x += 6 * 140  // 오른쪽으로 재배치
    })
    this.frontBuildings.forEach(fb => {
      fb.x -= this.scrollSpeed * 0.8 * delta / 1000
      if (fb.x < -80) fb.x += 5 * 170
    })

    // 거리 증가
    this.distance += delta * this.scrollSpeed / 100000
    this.distText.setText(Math.floor(this.distance) + 'm')

    // 속도 난이도 증가: 120m마다 +14
    const targetSpeed = Math.min(this.baseSpeed + Math.floor(this.distance / 120) * 14, this.maxSpeed)
    this.scrollSpeed = targetSpeed
    this.speedText.setText(`SPD ${Math.floor(this.scrollSpeed)}`)

    this.obstacles.filter(o => o.active).forEach(o => o.update(this.scrollSpeed, delta))
    this.items.filter(i => i.active).forEach(i => i.update(this.scrollSpeed, delta))
    // 수집 판정 보정: 캐릭터 근접 아이템은 보조 수집 처리
    for (const item of this.items) {
      if (!item.active || item.collected) continue
      const dx = Math.abs(item.x - this.gorani.sprite.x)
      const dy = Math.abs(item.y - this.gorani.sprite.y)
      if (dx < 26 && dy < 58) {
        this.onCollect(this.gorani.sprite, item)
      }
    }
    this.obstacles = this.obstacles.filter(o => o.active)
    this.items = this.items.filter(i => i.active)

    // 낮/밤 & 도우미 시스템 업데이트
    this.dayNight.update(delta)
    this.helper.update(delta)
    this.helper.tryHitBoss(this.boss)

    // 보스 소환 간격: 중간보스 200m 주기, 최종보스 400m 주기
    if (!this.boss) {
      if (this.distance >= this.nextFinalBossAt) {
        this.spawnFinalBoss()
        this.nextFinalBossAt += 400
      } else if (this.distance >= this.nextMidBossAt) {
        this.spawnMidBoss()
        this.nextMidBossAt += 400
      }
    }
  }

  _requestJump() {
    if (this.isPaused) return
    this.gorani.jump()
    audioSystem.playSFX('jump')
  }

  onHit(goraniSprite, obstacle) {
    if (!obstacle || !obstacle.active || obstacle.hit) return
    this.hp = Math.max(0, this.hp - 1)
    this.gorani.setHurtState()
    audioSystem.playSFX('hurt')
    this.cameras.main.shake(180, 0.004)
    obstacle.markHit()
    this.obstacles = this.obstacles.filter(o => o.active)
    this.updateHpDisplay()
    if (this.hp <= 0) {
      if (this.bossAnimTimer) {
        this.bossAnimTimer.remove()
        this.bossAnimTimer = null
      }
      this.scene.start('GameOverScene', {
        score: this.score,
        distance: Math.floor(this.distance)
      })
    }
  }

  onCollect(goraniSprite, item) {
    if (!item || !item.active || item.collected) return
    if (item.itemType === 'acorn') {
      this.score += 100
    } else if (item.itemType === 'leaf') {
      this.hp = Math.min(3, this.hp + 1)
      this.updateHpDisplay()
      this.score += 30
    }
    audioSystem.playSFX('collect')
    this.updateScoreDisplay()
    item.collect()
    this.items = this.items.filter(i => i.active)
  }

  updateHpDisplay() {
    this.hpText.setText('♥'.repeat(this.hp) + '♡'.repeat(3 - this.hp))
  }

  updateScoreDisplay() {
    this.scoreText.setText(`SCR ${this.score}`)
  }

  // ── 보스 텍스처 생성 헬퍼 ──
  _createBossTextures() {
    // 발사체 텍스처 (마취 다트, 주황 막대기)
    if (!this.textures.exists('dart')) {
      const dg = this.add.graphics()
      dg.fillStyle(0xFF8800); dg.fillRect(0, 2, 18, 4)   // 몸통
      dg.fillStyle(0xCCCCCC); dg.fillRect(18, 0, 6, 8)   // 침
      dg.generateTexture('dart', 24, 8)
      dg.destroy()
    }

    // 픽셀 도트 텍스처 생성 헬퍼
    const drawPixels = (graphics, pixels, scale = 4) => {
      for (const p of pixels) {
        graphics.fillStyle(p.c)
        graphics.fillRect(p.x * scale, p.y * scale, scale, scale)
      }
    }

    // 중간 보스: 비숑 프리제 (도트 2프레임)
    if (!this.textures.exists('boss-bichon-1')) {
      const buildBichonFrame = (key, pawOffset = 0, earOffset = 0) => {
        const bg = this.add.graphics()
        const W = 24
        const H = 24
        const S = 4
        const C = {
          o: 0x2a2a2a,
          w: 0xf6f6f6,
          s: 0xe5e5e5,
          e: 0x111111,
          n: 0x333333
        }
        const px = []
        for (let y = 4; y <= 21; y++) {
          for (let x = 3; x <= 20; x++) {
            const dx = x - 12
            const dy = y - 13
            if ((dx * dx) / 78 + (dy * dy) / 58 <= 1.05) px.push({ x, y, c: C.w })
          }
        }
        for (let y = 1; y <= 11; y++) {
          for (let x = 6; x <= 17; x++) {
            const dx = x - 12
            const dy = y - 7
            if ((dx * dx) / 30 + (dy * dy) / 22 <= 1.05) px.push({ x, y, c: C.w })
          }
        }
        for (let y = 2 + earOffset; y <= 8 + earOffset; y++) {
          for (let x = 4; x <= 7; x++) px.push({ x, y, c: C.s })
          for (let x = 16; x <= 19; x++) px.push({ x, y, c: C.s })
        }
        for (let y = 12; y <= 20; y++) {
          px.push({ x: 8, y, c: C.s }); px.push({ x: 16, y, c: C.s })
        }
        // 발 프레임 차이
        for (let x = 8; x <= 10; x++) px.push({ x, y: 21 + pawOffset, c: C.w })
        for (let x = 13; x <= 15; x++) px.push({ x, y: 21 - pawOffset, c: C.w })
        px.push({ x: 9, y: 7, c: C.e }, { x: 14, y: 7, c: C.e })
        px.push({ x: 11, y: 9, c: C.n }, { x: 12, y: 9, c: C.n })
        for (let y = 0; y < H; y++) {
          for (let x = 0; x < W; x++) {
            const current = px.some(p => p.x === x && p.y === y)
            if (!current) continue
            const neighbors = [[1,0],[-1,0],[0,1],[0,-1]]
            for (const [dx, dy] of neighbors) {
              const nx = x + dx
              const ny = y + dy
              const exists = px.some(p => p.x === nx && p.y === ny)
              if (!exists) px.push({ x, y, c: C.o })
            }
          }
        }
        drawPixels(bg, px, S)
        bg.generateTexture(key, W * S, H * S)
        bg.destroy()
      }
      buildBichonFrame('boss-bichon-1', 0, 0)
      buildBichonFrame('boss-bichon-2', 1, -1)
    }

    // 최종 보스: 포메라니안 (도트 2프레임)
    if (!this.textures.exists('boss-pom-1')) {
      const buildPomFrame = (key, tailLift = 0, pawOffset = 0) => {
        const pg = this.add.graphics()
        const W = 24
        const H = 24
        const S = 4
        const C = {
          o: 0x2b1c12,
          b: 0xffbf7a,
          d: 0xe2954f,
          h: 0xffd7a6,
          e: 0x161616
        }
        const px = []
        for (let y = 7; y <= 22; y++) {
          for (let x = 3; x <= 20; x++) {
            const dx = x - 12
            const dy = y - 15
            if ((dx * dx) / 80 + (dy * dy) / 60 <= 1.05) px.push({ x, y, c: C.b })
          }
        }
        for (let y = 2; y <= 12; y++) {
          for (let x = 7; x <= 17; x++) {
            const dx = x - 12
            const dy = y - 7
            if ((dx * dx) / 28 + (dy * dy) / 26 <= 1.05) px.push({ x, y, c: C.h })
          }
        }
        for (let y = 3 - tailLift; y <= 9 - tailLift; y++) {
          for (let x = 17; x <= 22; x++) px.push({ x, y, c: C.b })
        }
        px.push({ x: 8, y: 1, c: C.d }, { x: 9, y: 1, c: C.d }, { x: 7, y: 2, c: C.d })
        px.push({ x: 15, y: 1, c: C.d }, { x: 16, y: 1, c: C.d }, { x: 17, y: 2, c: C.d })
        for (let y = 13; y <= 20; y++) {
          px.push({ x: 6, y, c: C.d }); px.push({ x: 18, y, c: C.d })
        }
        for (let x = 8; x <= 10; x++) px.push({ x, y: 22 + pawOffset, c: C.d })
        for (let x = 13; x <= 15; x++) px.push({ x, y: 22 - pawOffset, c: C.d })
        px.push({ x: 10, y: 7, c: C.e }, { x: 14, y: 7, c: C.e })
        px.push({ x: 11, y: 9, c: C.e }, { x: 12, y: 9, c: C.e })
        for (let y = 0; y < H; y++) {
          for (let x = 0; x < W; x++) {
            const current = px.some(p => p.x === x && p.y === y)
            if (!current) continue
            const neighbors = [[1,0],[-1,0],[0,1],[0,-1]]
            for (const [dx, dy] of neighbors) {
              const nx = x + dx
              const ny = y + dy
              const exists = px.some(p => p.x === nx && p.y === ny)
              if (!exists) px.push({ x, y, c: C.o })
            }
          }
        }
        drawPixels(pg, px, S)
        pg.generateTexture(key, W * S, H * S)
        pg.destroy()
      }
      buildPomFrame('boss-pom-1', 0, 0)
      buildPomFrame('boss-pom-2', 1, 1)
    }
  }

  // ── 중간 보스: 비숑 프리제 ──
  spawnMidBoss() {
    if (this.boss) return
    this._createBossTextures()

    this.boss = this.physics.add.sprite(880, 310, 'boss-bichon-1')
    this.boss.setScale(0.9)
    this.boss.body.allowGravity = false
    this.boss.body.setImmovable(true)
    this.boss.bossHp = 3

    // 왼쪽으로 천천히 다가옴
    this.boss.body.setVelocityX(-60)
    this.bossAnimTimer = this.time.addEvent({
      delay: 180,
      loop: true,
      callback: () => {
        if (!this.boss || !this.boss.active) return
        this.boss.setTexture(this.boss.texture.key === 'boss-bichon-1' ? 'boss-bichon-2' : 'boss-bichon-1')
      }
    })

    this._showBossWarning('MID BOSS: BICHON', 900)
    this._scheduleDart(1900)
    this._scheduleDart(4100)

    if (this.audioSystem) {
      this.audioSystem.playSFX('boss_appear')
      this.audioSystem.switchTheme('boss')
    }

    // 13초 후 미처치 시 퇴장
    this.time.delayedCall(13000, () => this._bossRetreat())
  }

  // ── 최종 보스: 포메라니안 ──
  spawnFinalBoss() {
    if (this.boss) return
    this._createBossTextures()

    this.boss = this.physics.add.sprite(880, 300, 'boss-pom-1')
    this.boss.setScale(1.1)
    this.boss.body.allowGravity = false
    this.boss.body.setImmovable(true)
    this.boss.bossHp = 7

    // 더 빠르게 다가오며 다트 2발 연속
    this.boss.body.setVelocityX(-80)
    this.bossAnimTimer = this.time.addEvent({
      delay: 150,
      loop: true,
      callback: () => {
        if (!this.boss || !this.boss.active) return
        this.boss.setTexture(this.boss.texture.key === 'boss-pom-1' ? 'boss-pom-2' : 'boss-pom-1')
      }
    })

    this._showBossWarning('FINAL BOSS: POM', 1200)
    this._scheduleDart(1600)
    this._scheduleDart(3000)
    this._scheduleDart(4400)

    if (this.audioSystem) {
      this.audioSystem.playSFX('boss_appear')
      this.audioSystem.switchTheme('boss')
    }

    // 20초 후 미처치 시 퇴장
    this.time.delayedCall(20000, () => this._bossRetreat())
  }

  // 마취 다트 발사 (delay ms 후)
  _scheduleDart(delay) {
    this.time.delayedCall(delay, () => {
      if (!this.boss || !this.boss.active) return

      const dart = this.physics.add.sprite(this.boss.x - 20, this.boss.y + 10, 'dart')
      dart.body.allowGravity = false
      dart.body.setVelocityX(-Math.min(560, this.scrollSpeed + 120))
      dart.setDepth(8)

      this.physics.add.overlap(
        this.gorani.sprite, dart,
        () => {
          if (!this.gorani.isInvincible) {
            dart.destroy()
            this.hp = Math.max(0, this.hp - 1)
            this.gorani.setHurtState()
            if (this.audioSystem) this.audioSystem.playSFX('hurt')
            this.updateHpDisplay()
            if (this.hp <= 0) {
              if (this.bossAnimTimer) {
                this.bossAnimTimer.remove()
                this.bossAnimTimer = null
              }
              this.scene.start('GameOverScene', {
                score: this.score,
                distance: Math.floor(this.distance)
              })
            }
          }
        },
        null, this
      )
      // 4초 후 자동 제거
      this.time.delayedCall(4000, () => { if (dart.active) dart.destroy() })
    })
  }

  _showBossWarning(label, duration = 1000) {
    const banner = this.add.rectangle(400, 86, 380, 44, 0x120000, 0.8).setDepth(26)
    const text = this.add.text(400, 86, label, {
      fontFamily: '"Press Start 2P"', fontSize: '14px', color: '#ffdd55'
    }).setOrigin(0.5).setDepth(27)
    this.cameras.main.shake(140, 0.0028)
    this.tweens.add({
      targets: [banner, text],
      alpha: 0,
      delay: duration,
      duration: 220,
      onComplete: () => {
        banner.destroy()
        text.destroy()
      }
    })
  }

  // 도우미가 보스에 닿으면 보스 HP 감소
  _checkHelperHitsBoss(helperObj) {
    if (!this.boss || !this.boss.active) return
    if (Math.abs(helperObj.x - this.boss.x) < 50) {
      this.boss.bossHp -= 1
      this.boss.setTintFill(0xffffff)
      this.time.delayedCall(90, () => {
        if (this.boss && this.boss.active) this.boss.clearTint()
      })
      if (this.boss.bossHp <= 0) {
        this.score += 500
        this._bossRetreat()
      }
    }
  }

  // 보스 퇴장 처리
  _bossRetreat() {
    if (!this.boss || !this.boss.active) return
    if (this.bossAnimTimer) {
      this.bossAnimTimer.remove()
      this.bossAnimTimer = null
    }
    this.boss.destroy()
    this.boss = null
    const theme = this.dayNight ? this.dayNight.phase : 'day'
    if (this.audioSystem) this.audioSystem.switchTheme(theme)
  }
}
