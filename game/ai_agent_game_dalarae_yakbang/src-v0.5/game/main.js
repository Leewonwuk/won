import { gameConfig } from './config.js';

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

  const game = new window.Phaser.Game(gameConfig);

  game.events.once('ready', () => {
    if (loadingEl) loadingEl.style.display = 'none';
  });
  setTimeout(() => { if (loadingEl) loadingEl.style.display = 'none'; }, 2500);

} catch (e) {
  if (statusEl) statusEl.textContent = 'ERROR: ' + e.message;
  console.error('Game init error:', e);
}
