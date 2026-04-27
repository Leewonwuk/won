"""원본 캐릭터 스프라이트시트(3열×4행, RPG Maker 포맷)를 Phaser 로딩용 48×48 프레임으로 축소.

원본은 `생성그림_꼉/캐릭터도트버전/` 에 그대로 두고 축소본만 `src-v0.6/assets/chars/` 에 생성.
도트 느낌 보존을 위해 LANCZOS 다운샘플.

v3: 셀별 독립 처리 — 프레임 블리드(이웃 셀 실루엣 침범) 완전 차단.
  - 원본을 3×4 로 정수 분할(나머지 1-2px 은 우측/하단 버림).
  - 각 셀 내부에서:
      a) flood-fill 배경 제거 (외곽 닿은 밝은/회색 영역만 alpha=0) — 격자선도 함께 제거
      b) 알파>0 픽셀의 bounding box 로 캐릭터만 tight-crop
      c) 종횡비 유지한 채 48×48 투명 캔버스에 중앙 배치(여백 반드시 2px 이상)
  - 결과: 각 48×48 프레임에 캐릭터가 **절대** 이웃 프레임으로 새지 않음.
  - 격자선 있는 원본(여자상인 등)과 크기가 어긋난 원본(1024×1536 등) 모두 자동 수용.

v2 (폐기): 전체 이미지 flood-fill 후 일괄 리사이즈 — 캐릭터가 셀 밖으로 삐져나가면 그대로 잘림.
"""
from PIL import Image
import numpy as np
from scipy.ndimage import label
import os

MAPPING = {
    '남자노비.png':    'nobi_m.png',
    '여자노비.png':    'nobi_f.png',
    '남자농민.png':    'nongmin_m.png',
    '남자상인.png':    'sangin_m.png',
    '여자상인.png':    'sangin_f.png',
    '남자선비.png':    'seonbi_m.png',
    '여자서생.png':    'seonbi_f.png',
    '남자관원.png':    'yangban_m.png',
    '여자관원.png':    'yangban_f.png',
    '무수리.png':      'staff.png',
}

SRC = r'c:\Users\user\game\Kario\생성그림_꼉\캐릭터도트버전'
DST = r'c:\Users\user\game\Kario\src-v0.6\assets\chars'
FRAME_W = 48
FRAME_H = 48
COLS = 3
ROWS = 4
PADDING = 2           # 48×48 프레임 경계에 최소 이 픽셀만큼 여백(블리드 방지)
BG_MIN_RGB = 200      # 밝기 하한 — 이보다 밝아야 "배경 후보"
BG_MAX_SAT = 35       # max(RGB)-min(RGB) 가 이 이하여야 회색-계통(무채색 배경+격자선 포함)

os.makedirs(DST, exist_ok=True)


def remove_bg_flood(im: Image.Image) -> Image.Image:
    """외곽 연결 flood-fill 로 배경만 투명화.
    - chroma-key(단일 레퍼런스) 와 달리 캐릭터 내부의 밝은 하이라이트(옷 흰색·눈 반사)는 보존.
    - 격자선이 외곽에 닿아 있으면 함께 제거됨(대부분의 RPG Maker 셀 격자는 외곽 관통).
    - "배경 후보" 는 R/G/B 모두 BG_MIN_RGB 이상 + 채도 낮음(BG_MAX_SAT 이하).
    """
    arr = np.array(im.convert('RGBA'))
    r = arr[..., 0].astype(np.int16)
    g = arr[..., 1].astype(np.int16)
    b = arr[..., 2].astype(np.int16)
    mn = np.minimum(np.minimum(r, g), b)
    mx = np.maximum(np.maximum(r, g), b)
    bg_candidate = (mn >= BG_MIN_RGB) & ((mx - mn) <= BG_MAX_SAT)
    if not bg_candidate.any():
        return Image.fromarray(arr, mode='RGBA')
    structure = np.ones((3, 3), dtype=np.int8)
    labeled, _n = label(bg_candidate, structure=structure)
    border_labels = set()
    border_labels.update(labeled[0, :].tolist())
    border_labels.update(labeled[-1, :].tolist())
    border_labels.update(labeled[:, 0].tolist())
    border_labels.update(labeled[:, -1].tolist())
    border_labels.discard(0)
    if not border_labels:
        return Image.fromarray(arr, mode='RGBA')
    mask = np.isin(labeled, list(border_labels))
    arr[mask, 3] = 0
    return Image.fromarray(arr, mode='RGBA')


def cell_bbox(cell: Image.Image):
    """셀 내 알파>0 픽셀의 bbox 반환 (x0,y0,x1,y1) 또는 None."""
    arr = np.array(cell.convert('RGBA'))
    alpha = arr[..., 3]
    ys, xs = np.where(alpha > 0)
    if ys.size == 0:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def render_cell(cell: Image.Image, bbox, scale: float, fw: int, fh: int, pad: int) -> Image.Image:
    """주어진 bbox 로 셀을 crop 한 뒤 **공통 scale** 로 리사이즈해 fw×fh 캔버스에 bottom-align.
    - scale 은 시트 전체에서 산출한 값 → 12 프레임 크기가 자체적으로 일관됨
      (down 이 크고 left/right 가 작아 보이는 문제 해결).
    - bottom-pad 고정 → 발 높이 일관(걷기 애니 수직 흔들림 제거).
    """
    canvas = Image.new('RGBA', (fw, fh), (0, 0, 0, 0))
    if bbox is None:
        return canvas
    x0, y0, x1, y1 = bbox
    sub = cell.crop((x0, y0, x1, y1))
    w, h = sub.size
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    # 혹시나 여백을 넘지 않도록 최종 클램프 — scale 산출에서 이미 보장되지만 round 오차 방어.
    max_w, max_h = fw - 2 * pad, fh - 2 * pad
    if nw > max_w or nh > max_h:
        cs = min(max_w / nw, max_h / nh)
        nw = max(1, int(nw * cs)); nh = max(1, int(nh * cs))
    resized = sub.resize((nw, nh), Image.LANCZOS)
    px = (fw - nw) // 2
    py = fh - pad - nh
    canvas.paste(resized, (px, py), resized)
    return canvas


def process_sheet(src_path: str, dst_path: str) -> tuple:
    im = Image.open(src_path).convert('RGBA')
    sw, sh = im.size
    cw, ch = sw // COLS, sh // ROWS
    im = remove_bg_flood(im)

    # 1) 모든 셀의 bbox 수집 후 **공통 스케일** 산출.
    #    각 셀의 w/h 에 fw-2pad / fh-2pad 를 맞춰보고 그 중 최솟값(=가장 큰 캐릭터 프레임 기준)을 사용.
    #    이렇게 하면 어떤 프레임도 여백 밖으로 넘치지 않으면서 시트 전체 크기 비율이 동일.
    bboxes = {}
    max_w, max_h = FRAME_W - 2 * PADDING, FRAME_H - 2 * PADDING
    scale_candidates = []
    for r in range(ROWS):
        for c in range(COLS):
            cell = im.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
            bb = cell_bbox(cell)
            bboxes[(r, c)] = bb
            if bb is not None:
                bw = bb[2] - bb[0]
                bh = bb[3] - bb[1]
                if bw > 0 and bh > 0:
                    scale_candidates.append(min(max_w / bw, max_h / bh))
    scale = min(scale_candidates) if scale_candidates else 1.0

    # 2) 공통 스케일로 각 셀 렌더.
    out_w, out_h = FRAME_W * COLS, FRAME_H * ROWS
    out = Image.new('RGBA', (out_w, out_h), (0, 0, 0, 0))
    for r in range(ROWS):
        for c in range(COLS):
            cell = im.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
            fitted = render_cell(cell, bboxes[(r, c)], scale, FRAME_W, FRAME_H, PADDING)
            out.paste(fitted, (c * FRAME_W, r * FRAME_H), fitted)
    out.save(dst_path)
    return (sw, sh, cw, ch, scale)


for src_name, dst_name in MAPPING.items():
    src_path = os.path.join(SRC, src_name)
    if not os.path.exists(src_path):
        print(f'MISSING: {src_name}')
        continue
    dst_path = os.path.join(DST, dst_name)
    sw, sh, cw, ch, scale = process_sheet(src_path, dst_path)
    note = '' if (sw % COLS == 0 and sh % ROWS == 0) else ' (remainder cropped)'
    print(f'{src_name} {sw}x{sh} cell={cw}x{ch}{note} scale={scale:.3f} -> {dst_name} {FRAME_W * COLS}x{FRAME_H * ROWS} (frame {FRAME_W}x{FRAME_H})')

print('DONE')
