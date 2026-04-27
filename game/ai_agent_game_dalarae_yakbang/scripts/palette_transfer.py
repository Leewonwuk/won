"""팔레트 전이 + NEAREST 축소 파이프라인 — 카이로/온천골 스타일 복원.

문제: 기존 resize_chars.py 는 원본 362×362 프레임을 LANCZOS 로 48×48 축소.
  LANCZOS 가 안티에일리어싱된 중간 색을 만들어 도트 엣지가 흐려짐.
  아내분 원본(캐릭터도트버전/)은 실제 픽셀 아트인데 파이프라인에서 블러 처리됨.

해법 (B방안):
  1) flood-fill 로 배경 제거 (기존 로직 재사용)
  2) 셀별 tight-crop + bbox 수집
  3) 원본 프레임의 알파>0 영역에서 **팔레트 추출 (N=12색, MAXCOVERAGE)**
  4) 원본 프레임을 해당 팔레트로 **quantize** → AA 중간색을 12색으로 강제 매핑
  5) quantized 프레임을 **NEAREST** 로 목표 크기 축소 → 온천골급 하드 엣지

기본값: 프레임 64×64 (TILE_SIZE 와 일치). 필요 시 --frame 으로 변경.

출력: palette_out/<name>.png (12프레임 시트) + palette_out/_compare/<name>_ba.png (before/after 비교).
"""
from PIL import Image
import numpy as np
from scipy.ndimage import label
import os
import sys
import argparse
from collections import Counter

SRC = r'c:\Users\user\game\Kario\생성그림_꼉\캐릭터도트버전'
DST = r'c:\Users\user\game\Kario\scripts\palette_out'
CMP = os.path.join(DST, '_compare')
CUR = r'c:\Users\user\game\Kario\src-v0.6\assets\chars'  # 기존(LANCZOS) 결과 — 비교 대상

COLS = 3
ROWS = 4
BG_MIN_RGB = 200
BG_MAX_SAT = 35


def remove_bg_flood(im: Image.Image) -> Image.Image:
    arr = np.array(im.convert('RGBA'))
    r = arr[..., 0].astype(np.int16)
    g = arr[..., 1].astype(np.int16)
    b = arr[..., 2].astype(np.int16)
    mn = np.minimum(np.minimum(r, g), b)
    mx = np.maximum(np.maximum(r, g), b)
    bg_candidate = (mn >= BG_MIN_RGB) & ((mx - mn) <= BG_MAX_SAT)
    if not bg_candidate.any():
        return Image.fromarray(arr, mode='RGBA')
    labeled, _ = label(bg_candidate, structure=np.ones((3, 3), dtype=np.int8))
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


def cell_bbox(cell_arr: np.ndarray):
    alpha = cell_arr[..., 3]
    ys, xs = np.where(alpha > 0)
    if ys.size == 0:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def recompose_via_components(src_path: str, cell_w: int = 240, cell_h: int = 400, bottom_pad: int = 30):
    """AI 생성 시트는 캐릭터 중심이 (0,0) 기준 격자 cell 에 정렬되지 않는 경우가 많음.
    → connected component 로 12개 캐릭터 자동 검출 → Y center 로 행, X center 로 열 정렬 →
      동일 cell(cell_w × cell_h) 에 수직 하단+pad 앵커로 재배치해 깨끗한 3×4 시트 반환.

    반환: (재조립 PIL.Image, 검출 성공 여부). 12개 검출 실패 시 원본을 그대로 반환 + False.
    """
    im = Image.open(src_path).convert('RGBA')
    arr = np.array(im)
    r = arr[..., 0].astype(np.int16)
    g = arr[..., 1].astype(np.int16)
    b = arr[..., 2].astype(np.int16)
    alpha = arr[..., 3]
    mn = np.minimum(np.minimum(r, g), b)
    mx = np.maximum(np.maximum(r, g), b)
    # 체커보드/회색 배경 제외 = 캐릭터 픽셀
    char_mask = ~((mn >= BG_MIN_RGB) & ((mx - mn) <= BG_MAX_SAT)) & (alpha > 0)
    labeled, n = label(char_mask, structure=np.ones((3, 3), dtype=np.int8))
    comps = []
    for i in range(1, n + 1):
        ys, xs = np.where(labeled == i)
        if ys.size < 500:  # 노이즈(미세 장식) 필터
            continue
        comps.append({
            'size': int(ys.size),
            'x0': int(xs.min()), 'y0': int(ys.min()),
            'x1': int(xs.max()), 'y1': int(ys.max()),
            'cx': (int(xs.min()) + int(xs.max())) / 2,
            'cy': (int(ys.min()) + int(ys.max())) / 2,
        })
    if len(comps) != COLS * ROWS:
        return im, False

    # Y 센터로 4행 그룹화 → 각 행 내에서 X 센터로 3열 정렬.
    comps.sort(key=lambda c: c['cy'])
    rows_list = [comps[i * COLS:(i + 1) * COLS] for i in range(ROWS)]
    for row in rows_list:
        row.sort(key=lambda c: c['cx'])

    # 캐릭터 픽셀만 남긴 투명 버전 (배경 체커보드 제거된 RGBA)
    char_only = arr.copy()
    char_only[~char_mask] = (0, 0, 0, 0)
    char_im = Image.fromarray(char_only, 'RGBA')

    out_w = cell_w * COLS
    out_h = cell_h * ROWS
    out = Image.new('RGBA', (out_w, out_h), (0, 0, 0, 0))
    for r_idx, row in enumerate(rows_list):
        for c_idx, comp in enumerate(row):
            sub = char_im.crop((comp['x0'], comp['y0'], comp['x1'] + 1, comp['y1'] + 1))
            sw, sh = sub.size
            # 캐릭터가 cell_w/cell_h 보다 크면 축소 (가로·세로 비율 유지)
            max_w = cell_w - 4
            max_h = cell_h - bottom_pad - 4
            if sw > max_w or sh > max_h:
                cs = min(max_w / sw, max_h / sh)
                sub = sub.resize((max(1, int(sw * cs)), max(1, int(sh * cs))), Image.NEAREST)
                sw, sh = sub.size
            paste_x = c_idx * cell_w + (cell_w - sw) // 2
            paste_y = r_idx * cell_h + (cell_h - bottom_pad - sh)
            out.paste(sub, (paste_x, paste_y), sub)
    return out, True


def keep_largest_component(cell_arr: np.ndarray) -> np.ndarray:
    """캐릭터 본체(가장 큰 alpha>0 연결 성분) 만 유지, 나머지(위/아래 행 침범 잔재)는 alpha=0.
    원본 RPG Maker 시트에 행 경계 어긋남이 있을 때, 인접 셀의 발/머리 조각이 침범하는 문제 해소.
    8-connectivity 로 대각선 연결도 같은 성분 취급.
    """
    out = cell_arr.copy()
    alpha = out[..., 3]
    mask = alpha > 0
    if not mask.any():
        return out
    labeled, n = label(mask, structure=np.ones((3, 3), dtype=np.int8))
    if n <= 1:
        return out
    # 각 라벨 크기 계산 → 가장 큰 것만 남김.
    sizes = np.bincount(labeled.ravel())
    sizes[0] = 0                                             # label 0 = 배경 제외
    largest = int(np.argmax(sizes))
    keep = labeled == largest
    out[..., 3] = np.where(keep, alpha, 0)
    return out


def extract_palette_from_arr(arr: np.ndarray, n_colors: int) -> np.ndarray:
    """알파>0 픽셀에서만 N색 팔레트 추출. MAXCOVERAGE = 드문 색도 살리는 Pillow 알고리즘."""
    alpha = arr[..., 3]
    mask = alpha > 0
    if not mask.any():
        return np.array([[0, 0, 0]], dtype=np.uint8)
    # 불투명 픽셀만 담은 임시 이미지로 quantize
    rgb = arr[..., :3][mask]          # (K, 3)
    # PIL quantize 는 이미지 필요 — 1-row 이미지로 변환
    tmp = Image.fromarray(rgb.reshape(1, -1, 3).astype(np.uint8), 'RGB')
    quant = tmp.quantize(colors=n_colors, method=Image.Quantize.MAXCOVERAGE)
    pal = quant.getpalette()[: n_colors * 3]
    return np.array(pal, dtype=np.uint8).reshape(-1, 3)


def apply_palette(arr: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """각 픽셀 RGB 를 팔레트에서 가장 가까운 색으로 대체 (알파 유지)."""
    out = arr.copy()
    h, w = arr.shape[:2]
    # int32 필수: (a-b)**2 최대 65025 로 int16(max 32767) 오버플로 발생 → 거리 계산 음수/무의미.
    flat = arr[..., :3].reshape(-1, 3).astype(np.int32)
    p = palette.astype(np.int32)                          # (N, 3)
    # 벡터화 거리: (K,1,3) - (1,N,3) -> (K,N,3) -> sum axis=-1
    #   K=h*w 가 대형일 수 있어 청크 단위로 처리.
    CHUNK = 65536
    nearest = np.empty(flat.shape[0], dtype=np.int32)
    for i in range(0, flat.shape[0], CHUNK):
        chunk = flat[i:i + CHUNK]                         # (k, 3)
        d = np.sum((chunk[:, None, :] - p[None, :, :]) ** 2, axis=-1)  # (k, N)
        nearest[i:i + CHUNK] = np.argmin(d, axis=-1)
    new_rgb = p[nearest].reshape(h, w, 3).astype(np.uint8)
    out[..., :3] = new_rgb
    return out


def render_frame(cell_arr: np.ndarray, bbox, scale: float, fw: int, fh: int, pad: int) -> Image.Image:
    canvas = Image.new('RGBA', (fw, fh), (0, 0, 0, 0))
    if bbox is None:
        return canvas
    x0, y0, x1, y1 = bbox
    sub = Image.fromarray(cell_arr[y0:y1, x0:x1], 'RGBA')
    w, h = sub.size
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    max_w, max_h = fw - 2 * pad, fh - 2 * pad
    if nw > max_w or nh > max_h:
        cs = min(max_w / nw, max_h / nh)
        nw = max(1, int(nw * cs)); nh = max(1, int(nh * cs))
    # 여기가 B방안 핵심: LANCZOS → NEAREST
    resized = sub.resize((nw, nh), Image.NEAREST)
    px = (fw - nw) // 2
    py = fh - pad - nh
    canvas.paste(resized, (px, py), resized)
    return canvas


def process_sheet(src_path: str, dst_path: str, frame_w: int, frame_h: int, pad: int, n_colors: int, recompose: bool = True):
    # 1) (옵션) connected component 기반 자동 재조립.
    #    AI 생성 시트는 캐릭터 중심이 cell 격자와 어긋나 (0,0) 고정 분할 시 여러 cell 에 걸침 →
    #    12개 검출되면 균일 cell(240×400)로 재배치한 시트로 교체. 검출 실패 시 원본 유지.
    if recompose:
        im, ok = recompose_via_components(src_path)
        if not ok:
            print(f'  [recompose] 12 components not found — using original grid split')
    else:
        im = Image.open(src_path).convert('RGBA')
    arr = np.array(im)
    sh, sw = arr.shape[:2]
    cw, ch = sw // COLS, sh // ROWS

    # 1) **셀 단위** flood-fill — 원본 도트버전은 체크보드(grayscale)가 실제 칠해진 배경이라
    #    전역 flood 시 셀 경계를 타고 얼굴 흰색까지 drain 됨. 셀마다 외곽만 처리.
    #    추가: flood 직후 **가장 큰 연결 성분만 유지** → 원본의 행 경계 침범 조각(예: Row 0 발이 Row 1 상단에 삐져나옴) 제거.
    for r in range(ROWS):
        for c in range(COLS):
            y0, y1 = r * ch, (r + 1) * ch
            x0, x1 = c * cw, (c + 1) * cw
            cell_im = Image.fromarray(arr[y0:y1, x0:x1].copy(), 'RGBA')
            cleaned = np.array(remove_bg_flood(cell_im))
            cleaned = keep_largest_component(cleaned)
            arr[y0:y1, x0:x1] = cleaned

    # 2) 시트 전체(배경 제거 후)에서 팔레트 추출 — 12프레임 공통 팔레트.
    palette = extract_palette_from_arr(arr, n_colors)

    # 3) 팔레트로 quantize (AA 중간색 제거) — NEAREST 축소 전에 해야 효과.
    arr = apply_palette(arr, palette)

    # 4) 각 셀 bbox 수집 후 공통 scale 산출 (기존 resize_chars v4 방식).
    max_w, max_h = frame_w - 2 * pad, frame_h - 2 * pad
    cells = []
    scale_candidates = []
    for r in range(ROWS):
        for c in range(COLS):
            cell = arr[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw].copy()
            bb = cell_bbox(cell)
            cells.append((cell, bb))
            if bb is not None:
                bw, bh = bb[2] - bb[0], bb[3] - bb[1]
                if bw > 0 and bh > 0:
                    scale_candidates.append(min(max_w / bw, max_h / bh))
    scale = min(scale_candidates) if scale_candidates else 1.0

    # 4) 각 셀 NEAREST 축소해 시트 생성.
    out = Image.new('RGBA', (frame_w * COLS, frame_h * ROWS), (0, 0, 0, 0))
    for idx, (cell, bb) in enumerate(cells):
        r, c = divmod(idx, COLS)
        frame = render_frame(cell, bb, scale, frame_w, frame_h, pad)
        out.paste(frame, (c * frame_w, r * frame_h), frame)
    out.save(dst_path)
    return scale, palette


def make_compare(name: str, old_path: str, new_path: str, out_path: str, scale_view: int = 3):
    """현재(LANCZOS) vs 새(B방안) 나란히 비교. 폴더 구분 라벨 + 3배 확대."""
    imgs = []
    for p in (old_path, new_path):
        if os.path.exists(p):
            im = Image.open(p).convert('RGBA')
            # 3배 확대 (NEAREST) — 픽셀 차이 보기 쉬움
            im = im.resize((im.width * scale_view, im.height * scale_view), Image.NEAREST)
            imgs.append(im)
        else:
            imgs.append(Image.new('RGBA', (200, 200), (64, 0, 0, 255)))
    # 나란히 배치 + 상단 라벨 여백
    gap = 24
    label_h = 28
    W = imgs[0].width + imgs[1].width + gap * 3
    H = max(imgs[0].height, imgs[1].height) + label_h + gap * 2
    canvas = Image.new('RGBA', (W, H), (30, 30, 36, 255))
    canvas.paste(imgs[0], (gap, label_h + gap), imgs[0])
    canvas.paste(imgs[1], (gap * 2 + imgs[0].width, label_h + gap), imgs[1])
    # 라벨은 ImageDraw 로 간단히
    from PIL import ImageDraw
    d = ImageDraw.Draw(canvas)
    d.text((gap, gap // 2), f'{name} — BEFORE (LANCZOS, current)', fill=(255, 220, 180, 255))
    d.text((gap * 2 + imgs[0].width, gap // 2), f'{name} — AFTER (palette+NEAREST, B방안)', fill=(180, 255, 200, 255))
    canvas.save(out_path)


def process_single(src_path: str, dst_path: str, frame_w: int, frame_h: int, n_colors: int):
    """단일 프레임 원본(예: 의녀.png 64×64)을 팔레트 reduce 후 12프레임 정지 시트로 복제.
    원본이 이미 투명 처리된 픽셀 아트 완성본이므로 flood-fill·largest-component 단계 불필요.
    팔레트 quantize 로 색수만 8-12 로 축소 → 다른 캐릭터와 스타일 통일.
    """
    im = Image.open(src_path).convert('RGBA')
    arr = np.array(im)
    # 팔레트 reduce
    pal = extract_palette_from_arr(arr, n_colors)
    arr = apply_palette(arr, pal)
    # 프레임 크기 맞추기 (NEAREST)
    if im.size != (frame_w, frame_h):
        im2 = Image.fromarray(arr, 'RGBA').resize((frame_w, frame_h), Image.NEAREST)
        arr = np.array(im2)
    frame_im = Image.fromarray(arr, 'RGBA')
    # 12프레임 동일 복제 (3 cols × 4 rows)
    out = Image.new('RGBA', (frame_w * COLS, frame_h * ROWS), (0, 0, 0, 0))
    for r in range(ROWS):
        for c in range(COLS):
            out.paste(frame_im, (c * frame_w, r * frame_h))
    out.save(dst_path)
    return pal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frame', type=int, default=64, help='출력 프레임 크기(정사각). 기본 64 (TILE_SIZE 일치)')
    ap.add_argument('--pad', type=int, default=2)
    ap.add_argument('--colors', type=int, default=12, help='팔레트 색 수 (8~16 권장)')
    ap.add_argument('--names', nargs='*', default=None, help='처리할 원본 파일명(확장자 제외). 미지정 시 매핑 전체(10종) 처리')
    ap.add_argument('--single', nargs='*', default=[], help='단일 프레임 원본 (캐릭터원본/ 폴더) — 12프레임 정지 시트로 복제. 예: --single 의녀')
    ap.add_argument('--no-recompose', action='store_true', help='connected-component 자동 재조립 비활성 (기존 동작)')
    args = ap.parse_args()

    os.makedirs(DST, exist_ok=True)
    os.makedirs(CMP, exist_ok=True)

    # 매핑 (기존 resize_chars MAPPING 과 동일 키만 허용).
    mapping = {
        '남자노비':   'nobi_m',
        '여자노비':   'nobi_f',
        '남자농민':   'nongmin_m',
        '남자상인':   'sangin_m',
        '여자상인':   'sangin_f',
        '남자선비':   'seonbi_m',
        '여자서생':   'seonbi_f',
        '남자관원':   'yangban_m',
        '여자관원':   'yangban_f',
        '무수리':     'staff',
    }

    # 단일 프레임 모드 — 의녀 등
    SRC_SINGLE = r'c:\Users\user\game\Kario\생성그림_꼉\캐릭터원본'
    single_mapping = {
        '의녀': 'uinyeo',
        '무수리': 'staff_single',   # 참고용 — 실제 무수리는 도트버전 시트 사용
    }
    for name in args.single:
        src = os.path.join(SRC_SINGLE, f'{name}.png')
        if not os.path.exists(src):
            print(f'MISSING (single): {src}')
            continue
        dst_key = single_mapping.get(name, name)
        dst = os.path.join(DST, f'{dst_key}.png')
        palette = process_single(src, dst, args.frame, args.frame, args.colors)
        pal_hex = ' '.join(f'#{r:02x}{g:02x}{b:02x}' for r, g, b in palette)
        print(f'[single] {name} -> {dst_key}.png ({args.frame}x{args.frame} × 12 static) palette={pal_hex}')

    names = args.names if args.names else list(mapping.keys())
    for name in names:
        if name not in mapping:
            print(f'SKIP: {name} — mapping 에 없음')
            continue
        src = os.path.join(SRC, f'{name}.png')
        if not os.path.exists(src):
            print(f'MISSING: {src}')
            continue
        dst_key = mapping[name]
        dst = os.path.join(DST, f'{dst_key}.png')
        scale, palette = process_sheet(src, dst, args.frame, args.frame, args.pad, args.colors, recompose=not args.no_recompose)
        pal_hex = ' '.join(f'#{r:02x}{g:02x}{b:02x}' for r, g, b in palette)
        print(f'{name} -> {dst_key}.png ({args.frame}x{args.frame} × 12) scale={scale:.3f} palette={pal_hex}')

        # 비교 이미지
        old = os.path.join(CUR, f'{dst_key}.png')
        cmp_path = os.path.join(CMP, f'{dst_key}_ba.png')
        make_compare(name, old, dst, cmp_path)
        print(f'  compare: {cmp_path}')

    print('DONE')


if __name__ == '__main__':
    main()
