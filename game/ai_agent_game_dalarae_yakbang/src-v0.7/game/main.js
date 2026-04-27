import { gameConfig } from './config.js';
import { BootScene } from './scenes/BootScene.js';
import { TitleScene } from './scenes/TitleScene.js';
import { GameScene } from './scenes/GameScene.js';
import { ResultScene } from './scenes/ResultScene.js';

const statusEl = document.getElementById('load-status');
const loadingEl = document.getElementById('loading');

if (statusEl) statusEl.textContent = 'Phaser 초기화 중...';

try {
  if (typeof window.Phaser === 'undefined') {
    throw new Error('Phaser CDN 로드 실패 — 네트워크를 확인해주세요.');
  }
  if (typeof window.Tone === 'undefined') {
    // Tone.js는 BGM 전용이므로 없어도 게임은 돌아감 — 경고만 출력.
    console.warn('Tone.js CDN 로드 실패 — 사운드가 비활성화됩니다.');
  }

  // scene 을 config 에서 import 하면 config→scene→BuildingRegistry→config 순환 → BALANCE TDZ.
  // 여기서 scene 배열을 주입해 사이클을 끊는다.
  const game = new window.Phaser.Game({
    ...gameConfig,
    scene: [BootScene, TitleScene, GameScene, ResultScene]
  });

  // 디버그/QA 훅: 콘솔/Preview eval 로 game.scene.scenes 접근. 프로덕션에 영향 없음.
  window.__game = game;

  game.events.once('ready', () => {
    if (loadingEl) loadingEl.style.display = 'none';
  });
  setTimeout(() => { if (loadingEl) loadingEl.style.display = 'none'; }, 2500);

} catch (e) {
  if (statusEl) statusEl.textContent = 'ERROR: ' + e.message;
  console.error('Game init error:', e);
}
