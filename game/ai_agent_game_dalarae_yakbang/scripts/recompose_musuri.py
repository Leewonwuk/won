"""무수리.png 재조립 — 2026-04-20.

문제: 원본 무수리.png 는 3×4 격자에 정확히 맞지 않게 그려졌음.
    각 캐릭터 center 가 격자 cell 중앙과 어긋남 → 기존 (0,0) 기준 cell 분할 시
    캐릭터가 여러 cell 에 걸치고, 잘린 것처럼 보이는 현상 발생.

해결: connected component 로 12개 캐릭터를 각자 검출하고, center 기준으로
    동일 크기 cell 에 재배치해 깨끗한 sprite sheet 를 생성.

출력: `생성그림_꼉/캐릭터도트버전/무수리_recomposed.png` (192×256 × 스케일)
    이 파일을 palette_transfer.py 의 입력으로 사용.
"""
from PIL import Image
import numpy as np
from scipy.ndimage import label
from pathlib import Path

SRC = Path(r'c:\Users\user\game\Kario\생성그림_꼉\캐릭터도트버전\무수리.png')
DST = Path(r'c:\Users\user\game\Kario\생성그림_꼉\캐릭터도트버전\무수리_recomposed.png')

# 재조립 cell 크기 — 최대 캐릭터 173×315 보다 충분히 크게.
CELL_W = 240
CELL_H = 400
COLS = 3
ROWS = 4
# 발 기준선 — cell 하단에서 위로 이 만큼 떨어진 곳에 캐릭터 발 아래선을 맞춤.
BOTTOM_PAD = 30
# 머리 최상단 여백도 비슷하게 — cell 상단 여백은 BOTTOM_PAD 기준으로 캐릭터 중앙정렬 후 자동.


def main():
    im = Image.open(SRC).convert('RGBA')
    arr = np.array(im)
    r, g, b, a = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]
    mn = np.minimum(np.minimum(r, g), b).astype(np.int16)
    mx = np.maximum(np.maximum(r, g), b).astype(np.int16)
    # 체커보드(밝고 무채색)는 배경, 나머지는 캐릭터
    char_mask = ~((mn >= 200) & ((mx - mn) <= 35)) & (a > 0)

    labeled, n = label(char_mask, structure=np.ones((3, 3), dtype=np.int8))
    comps = []
    for i in range(1, n + 1):
        ys, xs = np.where(labeled == i)
        if ys.size < 500:  # 노이즈 필터 (작은 장식 픽셀 방지)
            continue
        comps.append({
            'id': i,
            'size': int(ys.size),
            'x0': int(xs.min()), 'y0': int(ys.min()),
            'x1': int(xs.max()), 'y1': int(ys.max()),
            'cx': (int(xs.min()) + int(xs.max())) / 2,
            'cy': (int(ys.min()) + int(ys.max())) / 2,
        })
    assert len(comps) == 12, f'expected 12 characters, got {len(comps)}'

    # Y 센터로 4개 행 클러스터링 (y 정렬 후 3개씩 묶기)
    comps.sort(key=lambda c: c['cy'])
    rows = [comps[i*3:(i+1)*3] for i in range(4)]
    # 각 행 내에서 X 센터로 3개 열 정렬
    for row in rows:
        row.sort(key=lambda c: c['cx'])

    # 빈 캔버스 — 완전 투명
    out_w = CELL_W * COLS
    out_h = CELL_H * ROWS
    out = Image.new('RGBA', (out_w, out_h), (0, 0, 0, 0))

    # 캐릭터 픽셀만 mask 로 추출 (체커보드 배경 제거)
    char_only = arr.copy()
    char_only[~char_mask] = (0, 0, 0, 0)
    char_im = Image.fromarray(char_only, 'RGBA')

    # 각 캐릭터를 (cx, y1) 기준 발 아래선 → cell 하단에서 BOTTOM_PAD 위로 맞춤
    for r_idx, row in enumerate(rows):
        for c_idx, comp in enumerate(row):
            x0, y0, x1, y1 = comp['x0'], comp['y0'], comp['x1'], comp['y1']
            sub = char_im.crop((x0, y0, x1 + 1, y1 + 1))
            sw, sh = sub.size
            # cell 내 배치: 수평 중앙, 수직 하단+패딩
            cell_origin_x = c_idx * CELL_W
            cell_origin_y = r_idx * CELL_H
            paste_x = cell_origin_x + (CELL_W - sw) // 2
            paste_y = cell_origin_y + (CELL_H - BOTTOM_PAD - sh)
            out.paste(sub, (paste_x, paste_y), sub)
            print(f'row{r_idx} col{c_idx}: size={sw}x{sh} paste=({paste_x},{paste_y}) char_bbox=({x0},{y0})-({x1},{y1})')

    out.save(DST)
    print(f'\nsaved: {DST} ({out_w}×{out_h})')
    print(f'cell: {CELL_W}×{CELL_H}  bottom_pad={BOTTOM_PAD}')


if __name__ == '__main__':
    main()
