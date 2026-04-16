// 싱글톤 패턴으로 작성
// Tone은 CDN 전역 변수 — import 하지 말 것
export class AudioSystem {
  constructor() {
    this._currentTheme = null
    this._lead = null
    this._pad = null
    this._bass = null
    this._sequence = null   // 현재 재생 중인 Tone.Sequence
    this._padSequence = null
    this._bassSequence = null
    this._sfxSynth = null
    this._initialized = false
  }

  async init() {
    if (this._initialized) return  // 중복 초기화 방지
    await Tone.start()  // 브라우저 AudioContext 활성화 (사용자 인터랙션 후 호출 필수)
    this._lead = new Tone.Synth({
      oscillator: { type: 'triangle' },
      envelope: { attack: 0.02, decay: 0.08, sustain: 0.25, release: 0.25 }
    }).toDestination()
    this._pad = new Tone.Synth({
      oscillator: { type: 'sine' },
      envelope: { attack: 0.05, decay: 0.2, sustain: 0.35, release: 0.6 }
    }).toDestination()
    this._bass = new Tone.Synth({
      oscillator: { type: 'square' },
      envelope: { attack: 0.01, decay: 0.1, sustain: 0.3, release: 0.15 }
    }).toDestination()
    this._lead.volume.value = -12
    this._pad.volume.value = -16
    this._bass.volume.value = -17
    this._sfxSynth = new Tone.Synth({ oscillator: { type: 'square' } }).toDestination()
    this._sfxSynth.volume.value = -6
    this._initialized = true
  }

  async switchTheme(themeName) {
    if (!this._initialized) return
    if (this._currentTheme === themeName) return  // 같은 테마 재호출 방지

    // 이전 시퀀스 반드시 정리 (안 하면 BGM 중복 재생)
    if (this._sequence) {
      this._sequence.stop()
      this._sequence.dispose()
      this._sequence = null
    }
    if (this._padSequence) {
      this._padSequence.stop()
      this._padSequence.dispose()
      this._padSequence = null
    }
    if (this._bassSequence) {
      this._bassSequence.stop()
      this._bassSequence.dispose()
      this._bassSequence = null
    }
    Tone.Transport.stop()
    Tone.Transport.cancel()

    this._currentTheme = themeName
    // 카이로소프트풍 아련한 감성: 느린 코드톤 + 가벼운 펄스 베이스 + 단순 리드
    const themes = {
      day: {
        bpm: 122,
        lead: ['E4','G4','A4','G4','E4','D4','E4',null,'B3','D4','E4','G4','A4','G4','E4',null],
        pad:  ['C4',null,'Am3',null,'F3',null,'G3',null],
        bass: ['C2','C2','A1','A1','F1','F1','G1','G1']
      },
      night: {
        bpm: 104,
        lead: ['D4','F4','A4','F4','D4','C4','D4',null,'A3','C4','D4','F4','G4','F4','D4',null],
        pad:  ['Dm3',null,'Bb2',null,'F3',null,'C3',null],
        bass: ['D2','D2','Bb1','Bb1','F1','F1','C2','C2']
      },
      boss: {
        bpm: 146,
        lead: ['E4','G4','B4','A4','G4','E4','D4',null,'E4','A4','B4','A4','G4','E4','D4',null],
        pad:  ['Em3',null,'C3',null,'G3',null,'D3',null],
        bass: ['E2','E2','C2','C2','G1','G1','D2','D2']
      },
      intro: {
        bpm: 96,
        lead: ['G4','A4','B4','A4','G4','E4','D4',null,'G4','A4','B4','D5','B4','A4','G4',null],
        pad:  ['G3',null,'Em3',null,'C3',null,'D3',null],
        bass: ['G2','G2','E2','E2','C2','C2','D2','D2']
      },
      gameover: {
        bpm: 72,
        lead: ['E4','D4','C4','A3',null,null,null,null],
        pad:  ['Am3',null,'F3',null,'C3',null,'E3',null],
        bass: ['A1','A1','F1','F1','C1','C1','E1','E1']
      },
    }
    const t = themes[themeName]
    if (!t) return

    Tone.Transport.bpm.value = t.bpm

    this._sequence = new Tone.Sequence((time, note) => {
      if (note) this._lead.triggerAttackRelease(note, '8n', time)
    }, t.lead, '8n')

    this._padSequence = new Tone.Sequence((time, note) => {
      if (note) this._pad.triggerAttackRelease(note, '2n', time)
    }, t.pad, '2n')

    this._bassSequence = new Tone.Sequence((time, note) => {
      if (note) this._bass.triggerAttackRelease(note, '8n', time)
    }, t.bass, '8n')

    this._sequence.start(0)
    this._padSequence.start(0)
    this._bassSequence.start(0)
    Tone.Transport.start()
  }

  playSFX(name) {
    if (!this._initialized) return
    const sfx = {
      jump:        () => { this._sfxSynth.triggerAttackRelease('C5', '16n'); setTimeout(() => this._sfxSynth.triggerAttackRelease('G5', '16n'), 80) },
      collect:     () => { this._sfxSynth.triggerAttackRelease('E5', '32n'); setTimeout(() => this._sfxSynth.triggerAttackRelease('G5', '32n'), 60) },
      hurt:        () => { this._sfxSynth.triggerAttackRelease('G4', '8n'); setTimeout(() => this._sfxSynth.triggerAttackRelease('C4', '8n'), 150) },
      boss_appear: () => { this._sfxSynth.triggerAttackRelease('C3', '4n') },
    }
    if (sfx[name]) sfx[name]()
  }

  stop() {
    if (this._sequence) { this._sequence.stop(); this._sequence.dispose(); this._sequence = null }
    if (this._padSequence) { this._padSequence.stop(); this._padSequence.dispose(); this._padSequence = null }
    if (this._bassSequence) { this._bassSequence.stop(); this._bassSequence.dispose(); this._bassSequence = null }
    Tone.Transport.stop()
  }
}

export const audioSystem = new AudioSystem()
