// 골드 획득, +만족도 등이 위로 떠오르며 사라지는 이펙트
export class FloatingText {
  static spawn(scene, x, y, text, opts = {}) {
    const color = opts.color || '#f7d05b';
    const size = opts.size || 18;
    const rise = opts.rise || 40;
    const duration = opts.duration || 900;

    const t = scene.add.text(x, y, text, {
      fontFamily: 'Noto Serif KR, serif',
      fontSize: `${size}px`,
      fontStyle: 'bold',
      color,
      stroke: '#141414',
      strokeThickness: 3
    }).setOrigin(0.5);
    t.setDepth(900);

    scene.tweens.add({
      targets: t,
      y: y - rise,
      alpha: 0,
      duration,
      ease: 'Cubic.easeOut',
      onComplete: () => t.destroy()
    });
    return t;
  }
}
