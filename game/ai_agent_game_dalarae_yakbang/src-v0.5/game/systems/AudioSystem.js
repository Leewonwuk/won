// 싱글톤 패턴. Tone은 CDN 전역 변수 — import 금지.
// 동양 펜타토닉(D E G A B) 기반 차분한 칩튠 BGM + SFX

export class AudioSystem {
  constructor() {
    this._currentTheme = null;
    this._lead = null;
    this._pad = null;
    this._bass = null;
    this._sequence = null;
    this._padSequence = null;
    this._bassSequence = null;
    this._sfxSynth = null;
    this._initialized = false;
  }

  async init() {
    if (this._initialized) return;
    if (typeof window.Tone === 'undefined') return; // Tone 없으면 조용히 패스

    await window.Tone.start();
    const T = window.Tone;

    this._lead = new T.Synth({
      oscillator: { type: 'triangle' },
      envelope: { attack: 0.03, decay: 0.12, sustain: 0.25, release: 0.4 }
    }).toDestination();
    this._pad = new T.Synth({
      oscillator: { type: 'sine' },
      envelope: { attack: 0.08, decay: 0.3, sustain: 0.4, release: 1.0 }
    }).toDestination();
    this._bass = new T.Synth({
      oscillator: { type: 'square' },
      envelope: { attack: 0.02, decay: 0.15, sustain: 0.25, release: 0.3 }
    }).toDestination();

    this._lead.volume.value = -14;
    this._pad.volume.value = -20;
    this._bass.volume.value = -18;

    this._sfxSynth = new T.Synth({
      oscillator: { type: 'square' },
      envelope: { attack: 0.005, decay: 0.08, sustain: 0.05, release: 0.1 }
    }).toDestination();
    this._sfxSynth.volume.value = -10;

    this._initialized = true;
  }

  async switchTheme(themeName) {
    if (!this._initialized) return;
    if (this._currentTheme === themeName) return;

    const T = window.Tone;

    // 이전 시퀀스 정리
    if (this._sequence) { this._sequence.stop(); this._sequence.dispose(); this._sequence = null; }
    if (this._padSequence) { this._padSequence.stop(); this._padSequence.dispose(); this._padSequence = null; }
    if (this._bassSequence) { this._bassSequence.stop(); this._bassSequence.dispose(); this._bassSequence = null; }
    T.Transport.stop();
    T.Transport.cancel();

    this._currentTheme = themeName;

    // 펜타토닉(D E G A B) 기반 동양풍 테마
    const themes = {
      day: {
        bpm: 96,
        lead: ['D4','E4','G4','A4','B4','A4','G4',null,'E4','G4','A4','B4','D5','B4','A4',null],
        pad:  ['D3',null,'G3',null,'A3',null,'D3',null],
        bass: ['D2','D2','G2','G2','A2','A2','D2','D2']
      },
      busy: {
        bpm: 118,
        lead: ['G4','A4','B4','D5','A4','B4','G4',null,'D4','E4','G4','A4','B4','A4','G4',null],
        pad:  ['G3',null,'D3',null,'A3',null,'E3',null],
        bass: ['G2','G2','D2','D2','A2','A2','E2','E2']
      },
      result: {
        bpm: 88,
        lead: ['D5','B4','A4','G4','E4','D4',null,null,'D5','A4','G4','E4',null,null,null,null],
        pad:  ['D3',null,'G3',null,'A3',null,'D3',null],
        bass: ['D2','D2','G2','G2','A2','A2','D2','D2']
      }
    };

    const t = themes[themeName];
    if (!t) return;

    T.Transport.bpm.value = t.bpm;

    this._sequence = new T.Sequence((time, note) => {
      if (note) this._lead.triggerAttackRelease(note, '8n', time);
    }, t.lead, '8n');

    this._padSequence = new T.Sequence((time, note) => {
      if (note) this._pad.triggerAttackRelease(note, '2n', time);
    }, t.pad, '2n');

    this._bassSequence = new T.Sequence((time, note) => {
      if (note) this._bass.triggerAttackRelease(note, '8n', time);
    }, t.bass, '8n');

    this._sequence.start(0);
    this._padSequence.start(0);
    this._bassSequence.start(0);
    T.Transport.start();
  }

  playSFX(name) {
    if (!this._initialized || !this._sfxSynth) return;
    const s = this._sfxSynth;
    const sfx = {
      coin:     () => { s.triggerAttackRelease('E5', '32n'); setTimeout(() => s.triggerAttackRelease('A5', '32n'), 60); },
      treat:    () => { s.triggerAttackRelease('G4', '16n'); setTimeout(() => s.triggerAttackRelease('B4', '16n'), 80); setTimeout(() => s.triggerAttackRelease('D5', '8n'), 160); },
      unlock:   () => { s.triggerAttackRelease('D4', '16n'); setTimeout(() => s.triggerAttackRelease('G4', '16n'), 90); setTimeout(() => s.triggerAttackRelease('B4', '16n'), 180); setTimeout(() => s.triggerAttackRelease('D5', '8n'), 270); },
      angry:    () => { s.triggerAttackRelease('A3', '8n'); setTimeout(() => s.triggerAttackRelease('E3', '8n'), 140); },
      levelup:  () => { s.triggerAttackRelease('G4', '16n'); setTimeout(() => s.triggerAttackRelease('B4', '16n'), 80); setTimeout(() => s.triggerAttackRelease('D5', '16n'), 160); setTimeout(() => s.triggerAttackRelease('G5', '8n'), 240); },
      spawn:    () => { s.triggerAttackRelease('B4', '32n'); },
    };
    if (sfx[name]) sfx[name]();
  }

  stop() {
    if (this._sequence) { this._sequence.stop(); this._sequence.dispose(); this._sequence = null; }
    if (this._padSequence) { this._padSequence.stop(); this._padSequence.dispose(); this._padSequence = null; }
    if (this._bassSequence) { this._bassSequence.stop(); this._bassSequence.dispose(); this._bassSequence = null; }
    if (typeof window.Tone !== 'undefined') window.Tone.Transport.stop();
    this._currentTheme = null;
  }
}

export const audioSystem = new AudioSystem();
