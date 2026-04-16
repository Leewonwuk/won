import { gameConfig } from './config.js';

const statusEl = document.getElementById('load-status');
const loadingEl = document.getElementById('loading');

if (statusEl) statusEl.textContent = 'Phaser 초기화 중...';

try {
  if (typeof Phaser === 'undefined') throw new Error('Phaser CDN 로드 실패');

  const game = new Phaser.Game(gameConfig);

  // 게임 생성 성공 시 로딩 메시지 제거
  game.events.once('ready', () => {
    if (loadingEl) loadingEl.style.display = 'none';
  });
  // 2초 후에도 살아있으면 그냥 숨김
  setTimeout(() => { if (loadingEl) loadingEl.style.display = 'none'; }, 2000);

} catch (e) {
  if (statusEl) statusEl.textContent = 'ERROR: ' + e.message;
  console.error('Game init error:', e);
}
