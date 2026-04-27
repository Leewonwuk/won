"""무수리 AI 재생성 (Replicate) — 2026-04-20.

전략: 스프라이트시트 한 방 생성은 AI 가 거의 실패 → 4방향 × 3프레임을 **쪼개서 생성** 후
    Python 으로 3×4 시트 조립.
    - Down / Left / Right / Up 4개 포즈를 각각 생성 (idle center frame 만, step frame 은 프로토타입이라 복제)
    - SDXL + pixel art LoRA 계열 모델 사용
    - 생성 후 palette_transfer.py 로 정제 투입 가능하도록 `생성그림_꼉/캐릭터도트버전/무수리.png` 덮어쓰기

출력:
    - `scripts/ai_out/musuri_down.png` (생성 원본 1024×1024)
    - `scripts/ai_out/musuri_left.png`
    - `scripts/ai_out/musuri_right.png`
    - `scripts/ai_out/musuri_up.png`
    - `scripts/ai_out/musuri_sheet.png` (3×4 조립 결과 — 각 행은 동일 idle 3 복제)
"""
import os
import sys
import urllib.request
from pathlib import Path

# .env 로드 (HotSpringsGodot_v031 의 .env 를 공유)
ENV_PATH = Path(r'c:\Users\user\game\HotSpringsGodot_v031\.env')
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        os.environ.setdefault(k.strip(), v.strip())

if not os.environ.get('REPLICATE_API_TOKEN'):
    print('ERROR: REPLICATE_API_TOKEN not found', file=sys.stderr)
    sys.exit(1)

import replicate  # noqa: E402

OUT_DIR = Path(r'c:\Users\user\game\Kario\scripts\ai_out')
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 카이로소프트 스타일 + Pedro [P2][P3] 준수를 위한 공통 prompt 프리앰블.
COMMON = (
    "pixel art, 16-bit, hard edges, no anti-aliasing, no gradient, limited palette 12 colors, "
    "1px black outline, flat shading, Kairosoft hot springs story style, Pedro Medeiros celeste style, "
    "Korean Joseon dynasty hanbok, transparent background, centered full body, feet visible, "
    "head top visible, no cropping, no letterbox, tiny sprite character"
)
NEG = (
    "anti-aliasing, smooth shading, gradient, blur, soft edges, realistic, photo, 3d render, "
    "watermark, text, multiple characters, grid, cell borders, signature, logo, nsfw, cut off feet, "
    "cropped head, bob hair bounce"
)

SUBJECT = (
    "a young Korean Joseon maidservant named musuri, female early 20s, "
    "light blue hanbok jeogori short jacket, white apron, dark navy chima long skirt, "
    "simple tied-back hair, holding a small broom"
)

POSES = {
    'down':  "facing forward, front view, looking at camera, arms at sides",
    'left':  "facing left, left profile side view, walking stance",
    'right': "facing right, right profile side view, walking stance",
    'up':    "facing away, back view, seen from behind",
}

# SDXL 기반 빠른 모델 — pixel art 프리셋 강하게 반영. 비용 저렴(약 $0.005/img).
MODEL = "bytedance/sdxl-lightning-4step:5599ed30703defd1d160a25a63321b4dec97101d98b4674bcc56e41f62f35637"


def _download(url: str, dst: Path):
    urllib.request.urlretrieve(url, dst)
    print(f'  saved: {dst} ({dst.stat().st_size} bytes)')


def _gen_pose(name: str, pose: str) -> Path:
    prompt = f"{SUBJECT}, {pose}, {COMMON}"
    print(f'\n[{name}] prompting…')
    print(f'  > {prompt[:160]}…')
    out = replicate.run(
        MODEL,
        input={
            "prompt": prompt,
            "negative_prompt": NEG,
            "width": 1024,
            "height": 1024,
            "scheduler": "K_EULER",
            "num_inference_steps": 4,
            "guidance_scale": 0,
            "num_outputs": 1,
        },
    )
    # replicate.run returns a list of FileOutput / URL strings depending on client version
    if isinstance(out, list):
        first = out[0]
    else:
        first = out
    if hasattr(first, 'read'):
        dst = OUT_DIR / f'musuri_{name}.png'
        with open(dst, 'wb') as fp:
            fp.write(first.read())
        print(f'  saved: {dst}')
        return dst
    url = str(first)
    dst = OUT_DIR / f'musuri_{name}.png'
    _download(url, dst)
    return dst


def _assemble_sheet(files: dict, out_path: Path):
    """4방향 × 3프레임 시트 조립. 각 행은 동일 idle 3회 복제(프로토타입)."""
    from PIL import Image
    CELL = 480  # 160 의 3배 해상도 — palette_transfer 에서 NEAREST 로 다운스케일 여지
    sheet_w = CELL * 3
    sheet_h = CELL * 4
    sheet = Image.new('RGBA', (sheet_w, sheet_h), (0, 0, 0, 0))
    rows = ['down', 'left', 'right', 'up']
    for r, key in enumerate(rows):
        img = Image.open(files[key]).convert('RGBA')
        # 정사각형 중앙 crop → CELL 로 리사이즈 (NEAREST 보존)
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        sq = img.crop((left, top, left + side, top + side))
        sq = sq.resize((CELL, CELL), Image.NEAREST)
        for c in range(3):
            sheet.paste(sq, (c * CELL, r * CELL))
    sheet.save(out_path)
    print(f'\nsheet assembled: {out_path} ({sheet_w}×{sheet_h})')


def main():
    files = {}
    for name, pose in POSES.items():
        files[name] = _gen_pose(name, pose)
    sheet_path = OUT_DIR / 'musuri_sheet.png'
    _assemble_sheet(files, sheet_path)
    print('\nDONE. 다음:')
    print(f'  1) 확인: {sheet_path}')
    print('  2) 육안 검수 PASS 시 → 생성그림_꼉/캐릭터도트버전/무수리.png 로 복사')
    print('  3) python scripts/palette_transfer.py 실행')


if __name__ == '__main__':
    main()
