// 싱글톤 패턴. Tone은 CDN 전역 변수 — import 금지.
// Phase 7-D BGM 개편(춘설풍): 거문고 pluck + 대금 AM + 드론 sine + 목어 membrane + 절종 FM,
//   FX bus(reverb 5s + delay '4n.' + lowpass 2400Hz) 통과. 펜타토닉 D 유지, 32스텝 루프.
//   카이로 비트감(거문고·목어 8n) + 동양 호흡(대금 긴 음 + 드론 sustain) 합성.

export class AudioSystem {
  constructor() {
    this._currentTheme = null;
    this._koto = null;     // 거문고 — pluck lead
    this._flute = null;    // 대금 — sustained melody
    this._drone = null;    // 저음 sine 지속
    this._taiko = null;    // 목어/북 — membrane bass
    this._bell = null;     // 절종 — sparse FM accent
    this._fxBus = null;    // reverb→delay→lowpass→destination
    this._kotoSeq = null;
    this._fluteSeq = null;
    this._taikoSeq = null;
    this._bellSeq = null;
    this._droneNote = null; // 현재 드론 음 (테마별 토닉)
    this._sfxSynth = null;
    this._initialized = false;
    // BGM mute 상태. switchTheme 호출 중에도 muted 면 시퀀스 가동 skip.
    //   _pendingTheme: mute 해제 시 복귀할 마지막 요청 테마. stop() 과 달리 테마 기억 유지.
    this._muted = false;
    this._pendingTheme = null;
  }

  async init() {
    if (this._initialized) return;
    if (typeof window.Tone === 'undefined') return; // Tone 없으면 조용히 패스

    await window.Tone.start();
    const T = window.Tone;

    // ── FX bus (절 마당 같은 공간감) ──
    // signal flow: voice → filter → delay → reverb → destination
    const reverb = new T.Reverb({ decay: 5, wet: 0.38 }).toDestination();
    const delay = new T.FeedbackDelay({ delayTime: '4n.', feedback: 0.22, wet: 0.18 }).connect(reverb);
    const filter = new T.Filter({ frequency: 2400, type: 'lowpass', rolloff: -12 }).connect(delay);
    this._fxBus = filter;

    // ── 거문고 (PluckSynth — Karplus-Strong 발현음) ──
    this._koto = new T.PluckSynth({
      attackNoise: 0.6, dampening: 3800, resonance: 0.92
    }).connect(filter);

    // ── 대금 (AMSynth — sine 베이스 + AM 트레몰로로 피리 호흡) ──
    this._flute = new T.AMSynth({
      harmonicity: 1.5,
      oscillator: { type: 'sine' },
      modulation: { type: 'sine' },
      envelope: { attack: 0.35, decay: 0.25, sustain: 0.7, release: 1.4 },
      modulationEnvelope: { attack: 0.5, decay: 0.4, sustain: 0.5, release: 1.0 }
    }).connect(filter);

    // ── 드론 (저음 sustained sine) — reverb 직접 연결로 깊이 강조 ──
    this._drone = new T.Synth({
      oscillator: { type: 'sine' },
      envelope: { attack: 2.5, decay: 0, sustain: 1, release: 4 }
    }).connect(reverb);

    // ── 목어/북 (MembraneSynth — pitch-decay 둔탁한 저음 타격) ──
    //   destination 직결: dry kick 으로 박자 명확.
    this._taiko = new T.MembraneSynth({
      pitchDecay: 0.08,
      octaves: 4,
      oscillator: { type: 'sine' },
      envelope: { attack: 0.001, decay: 0.45, sustain: 0, release: 0.9 }
    }).toDestination();

    // ── 절종 (FMSynth — 짧은 어택 + 긴 release reverb tail) ──
    this._bell = new T.FMSynth({
      harmonicity: 3.5,
      modulationIndex: 8,
      oscillator: { type: 'sine' },
      envelope: { attack: 0.001, decay: 1.4, sustain: 0, release: 1.6 },
      modulation: { type: 'sine' },
      modulationEnvelope: { attack: 0.001, decay: 0.5, sustain: 0, release: 0.6 }
    }).connect(reverb);

    // ── 음량 밸런스 (거문고 lead 우선, 대금·드론·종은 배경 ambience) ──
    this._koto.volume.value = -10;
    this._flute.volume.value = -14;
    this._drone.volume.value = -22;
    this._taiko.volume.value = -14;
    this._bell.volume.value = -16;

    // ── SFX (기존 칩튠 톤 유지 — 즉발 피드백 명확성 위해 dry) ──
    this._sfxSynth = new T.Synth({
      oscillator: { type: 'square' },
      envelope: { attack: 0.005, decay: 0.08, sustain: 0.05, release: 0.1 }
    }).toDestination();
    this._sfxSynth.volume.value = -10;

    this._initialized = true;
  }

  async switchTheme(themeName) {
    if (!this._initialized) return;
    // mute 중이어도 의도한 테마를 기억 → 해제 시 이 테마로 복귀.
    this._pendingTheme = themeName;
    if (this._muted) return;
    if (this._currentTheme === themeName) return;

    const T = window.Tone;

    // 이전 시퀀스/드론 정리
    this._stopSequences();
    T.Transport.stop();
    T.Transport.cancel();

    this._currentTheme = themeName;

    // ── 펜타토닉 D (D E G A B) 기반 3테마. 32스텝 루프(8n × 32 = 16박). ──
    //   거문고: 8n 발현음, 카이로 비트감 유지. 호흡 위해 약 30% null.
    //   대금: 2n 긴 호흡, 16스텝(8박)당 4-6개 음. 트레몰로로 피리 느낌.
    //   목어: 4n 박자감(저음 D2/A1).
    //   종: 매우 sparse — 16스텝당 1회.
    //   드론: 토닉 음 sustained(테마 시작 시 1회 trigger).
    const themes = {
      day: {
        bpm: 92,
        drone: 'D2',
        koto: ['D4',null,'A4',null,'G4','E4','D4',null,'A4',null,'B4',null,'A4','G4','E4',null,
               'D4',null,'A4',null,'G4',null,'E4','D4','A3',null,'D4','E4','G4',null,'A4',null],
        flute: ['D5',null,null,null,null,null,null,null,'A4',null,null,null,'B4',null,null,null,
                'A4',null,null,null,'G4',null,null,null,'E4',null,null,null,'D5',null,null,null],
        taiko: ['D2',null,null,null,'A1',null,null,null,'D2',null,null,null,'A1',null,'D2',null],
        bell: [null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,'D5']
      },
      busy: {
        bpm: 110,
        drone: 'G2',
        koto: ['G4','D4','A4','D4','B4','A4','G4','D4','A4','D4','B4','D5','A4','G4','E4','D4',
               'G4','A4','B4','D5','A4','B4','G4','A4','D4','E4','G4','A4','B4','A4','G4',null],
        flute: ['G5',null,null,null,'D5',null,null,null,'B4',null,null,null,'A4',null,null,null,
                'B4',null,null,null,'D5',null,null,null,'A4',null,null,null,'G4',null,null,null],
        taiko: ['G2',null,'D2',null,'G2','G2','D2',null,'G2',null,'D2',null,'A2',null,'G2',null],
        bell: [null,null,null,null,null,null,null,'G5',null,null,null,null,null,null,null,'D5']
      },
      result: {
        bpm: 80,
        drone: 'D2',
        koto: ['D5',null,'B4',null,'A4',null,'G4',null,'E4',null,'D4',null,null,null,null,null,
               'D5',null,'A4',null,'G4',null,'E4',null,'D4',null,null,null,null,null,null,null],
        flute: ['D5',null,null,null,null,null,null,null,'B4',null,null,null,null,null,null,null,
                'A4',null,null,null,null,null,null,null,'D4',null,null,null,null,null,null,null],
        taiko: ['D2',null,null,null,null,null,null,null,'A1',null,null,null,null,null,null,null],
        bell: ['D5',null,null,null,null,null,null,null,null,null,null,null,null,null,null,'A5']
      }
    };

    const t = themes[themeName];
    if (!t) return;

    T.Transport.bpm.value = t.bpm;

    // 거문고 — 8n 32스텝
    this._kotoSeq = new T.Sequence((time, note) => {
      if (note) this._koto.triggerAttackRelease(note, '8n', time);
    }, t.koto, '8n');

    // 대금 — 8n 32스텝, 긴 음(2n) 으로 트리거해 sustain 연출
    this._fluteSeq = new T.Sequence((time, note) => {
      if (note) this._flute.triggerAttackRelease(note, '2n', time);
    }, t.flute, '8n');

    // 목어 — 4n 16스텝
    this._taikoSeq = new T.Sequence((time, note) => {
      if (note) this._taiko.triggerAttackRelease(note, '4n', time);
    }, t.taiko, '4n');

    // 종 — 4n 16스텝, sparse accent
    this._bellSeq = new T.Sequence((time, note) => {
      if (note) this._bell.triggerAttackRelease(note, '2n', time);
    }, t.bell, '4n');

    // 드론 — 테마 시작과 함께 토닉 음을 sustained 로 트리거
    //   triggerAttack(release 없음) → 다음 stop/switchTheme 에서 triggerRelease.
    this._droneNote = t.drone;
    this._drone.triggerAttack(t.drone);

    this._kotoSeq.start(0);
    this._fluteSeq.start(0);
    this._taikoSeq.start(0);
    this._bellSeq.start(0);
    T.Transport.start();
  }

  _stopSequences() {
    if (this._kotoSeq)  { this._kotoSeq.stop();  this._kotoSeq.dispose();  this._kotoSeq  = null; }
    if (this._fluteSeq) { this._fluteSeq.stop(); this._fluteSeq.dispose(); this._fluteSeq = null; }
    if (this._taikoSeq) { this._taikoSeq.stop(); this._taikoSeq.dispose(); this._taikoSeq = null; }
    if (this._bellSeq)  { this._bellSeq.stop();  this._bellSeq.dispose();  this._bellSeq  = null; }
    if (this._drone && this._droneNote) {
      this._drone.triggerRelease();
      this._droneNote = null;
    }
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
      // Phase 3-C: StaffPanel open/assign + well bonus 앵커.
      panel_open:   () => { s.triggerAttackRelease('D4', '16n'); setTimeout(() => s.triggerAttackRelease('A4', '16n'), 50); },
      staff_assign: () => { s.triggerAttackRelease('E5', '32n'); setTimeout(() => s.triggerAttackRelease('B5', '32n'), 40); },
      well_bonus:   () => { s.triggerAttackRelease('G5', '32n'); setTimeout(() => s.triggerAttackRelease('D6', '32n'), 50); }
    };
    if (sfx[name]) sfx[name]();
  }

  stop() {
    this._stopSequences();
    if (typeof window.Tone !== 'undefined') window.Tone.Transport.stop();
    this._currentTheme = null;
  }

  // BGM 토글. mute 시 시퀀스 정리(SFX 는 유지), 해제 시 _pendingTheme(또는 'day')로 복귀.
  //   반환: 새 muted 상태.
  isMuted() { return this._muted; }
  toggleMute() { return this.setMuted(!this._muted); }
  setMuted(muted) {
    this._muted = !!muted;
    if (this._muted) {
      this.stop();
    } else if (this._initialized) {
      const theme = this._pendingTheme || 'day';
      // switchTheme 는 async — muted=false 전환 직후 즉시 복귀시키려고 fire-and-forget.
      Promise.resolve(this.switchTheme(theme)).catch(() => {});
    }
    return this._muted;
  }
}

export const audioSystem = new AudioSystem();
