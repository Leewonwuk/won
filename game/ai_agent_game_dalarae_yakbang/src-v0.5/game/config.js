import { BootScene } from './scenes/BootScene.js';
import { TitleScene } from './scenes/TitleScene.js';
import { GameScene } from './scenes/GameScene.js';
import { ResultScene } from './scenes/ResultScene.js';

export const GAME_WIDTH = 800;
export const GAME_HEIGHT = 560;

export const gameConfig = {
  type: window.Phaser.AUTO,
  parent: 'game-root',
  width: GAME_WIDTH,
  height: GAME_HEIGHT,
  backgroundColor: '#1a1428',
  pixelArt: true,
  roundPixels: true,
  scale: {
    mode: window.Phaser.Scale.FIT,
    autoCenter: window.Phaser.Scale.CENTER_BOTH,
    width: GAME_WIDTH,
    height: GAME_HEIGHT
  },
  scene: [BootScene, TitleScene, GameScene, ResultScene]
};

// ----------------------------------------------------------------------------
// 게임 밸런스 상수 — 한 곳에서 튜닝 가능하도록 모아둠
// ----------------------------------------------------------------------------
export const BALANCE = {
  startGold: 300,
  dayDurationMs: 60_000,   // 1일 = 60초
  spawnIntervalBase: 5500, // 환자 스폰 기본 간격(ms)
  spawnIntervalMin: 1800,  // 방이 많을수록 단축
  clickBoostMs: 350,       // 클릭 1회당 치료 게이지 진행량(ms)
  introDelayMs: 3000,      // 소개받은 환자가 등장하기까지 지연

  // 방 스펙
  rooms: {
    moxa:        { key: 'moxa',        label: '뜸방',  treatMs: 8000,  fee: 50,  unlockNeed: 0,  parent: null },
    acupuncture: { key: 'acupuncture', label: '침방',  treatMs: 12000, fee: 120, unlockNeed: 15, parent: 'moxa' },
    herb:        { key: 'herb',        label: '약방',  treatMs: 15000, fee: 200, unlockNeed: 10, parent: 'acupuncture' },
    bath:        { key: 'bath',        label: '약탕',  treatMs: 18000, fee: 300, unlockNeed: 8,  parent: 'herb' }
  },

  // 환자 스펙 — tier 1~4 = Act 1, tier 5~8 = Act 2
  // patience는 하루(60초) 안에 소진될 수 있어야 긴장감이 생김
  patients: {
    noble:     { tier: 1, label: '노비',     patience: 35000, feeMul: 0.8, satNeed: 0.4, color: 0x7a6b55 },
    commoner:  { tier: 2, label: '백성',     patience: 28000, feeMul: 1.0, satNeed: 0.5, color: 0xd8d0bd },
    yangban:   { tier: 3, label: '양반',     patience: 20000, feeMul: 2.0, satNeed: 0.7, color: 0x6fa8d1 },
    royal:     { tier: 4, label: '왕족',     patience: 12000, feeMul: 4.0, satNeed: 0.8, color: 0xc93f3f },
    dokkaebi:  { tier: 5, label: '도깨비',   patience: 22000, feeMul: 3.0, satNeed: 0.6, color: 0x4caf6f },
    gumiho:    { tier: 6, label: '구미호',   patience: 18000, feeMul: 5.0, satNeed: 0.75, color: 0xff8a3c },
    tiger:     { tier: 7, label: '호랑이',   patience: 28000, feeMul: 4.0, satNeed: 0.7, color: 0xe67a2e, requireBath: true },
    sanshin:   { tier: 8, label: '산신령',   patience: 55000, feeMul: 10.0, satNeed: 0.9, color: 0xf6e9a8, aura: true }
  },

  // Act 1 스폰 확률
  act1Probs: { noble: 0.40, commoner: 0.35, yangban: 0.20, royal: 0.05 },
  act2Probs: { dokkaebi: 0.30, gumiho: 0.25, tiger: 0.25, sanshin: 0.20 },

  // 소개(referral) 확률 — 방 만족 시 다음 tier 환자 데려올 확률
  referral: { moxa: 0.70, acupuncture: 0.30, herb: 0.20 },

  // Act 2 해금 조건 — 왕족 만족 누적 5명
  act2RoyalNeeded: 5
};
