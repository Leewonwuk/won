"""원본 건물 이미지를 Phaser 로딩용 스프라이트로 변환.

원본: `생성그림_꼉/건물/` (유저 공급).
출력: `src-v0.6/assets/buildings/`.

규칙
----
- PNG(정적): 종횡비 보존 스케일 → 64×64 투명 캔버스에 센터 배치 (짧은 쪽 여백 투명).
  * 건물 상부가 타일 위로 튀어나오는 "카이로 스타일" 은 GridSystem 개조 후 대응.
  * 현재는 1 타일 = 1 건물, 64×64 고정.
- GIF(애니): 모든 프레임을 개별 64×64 로 변환 후 가로로 이어붙인 1행 스프라이트시트.
  * Phaser 에서 `load.spritesheet(key, path, {frameWidth:64,frameHeight:64})` 로 로드,
    BootScene 이 `anims.create` 로 등록.
- .piskel: 내부 포맷, PIL 로 못 염. skip. (우물 — 기존 procedural 유지)
- 흰/근-흰색 배경은 chroma-key 로 투명화 (resize_chars 와 동일 규칙).

Manifest
--------
출력 끝에 `manifest.json` 을 생성. BootScene 이 이걸 읽어서 로더 설정.
  { key: 'tex_building_moxa', file: 'moxa.png', type: 'image' }
  { key: 'tex_building_gukbap', file: 'gukbap.png', type: 'spritesheet', frames: 12, fw:64, fh:64 }
"""
from PIL import Image, ImageSequence
import numpy as np
import os
import json

SRC = r'c:\Users\user\game\Kario\생성그림_꼉\건물'
DST = r'c:\Users\user\game\Kario\src-v0.6\assets\buildings'
TILE = 64
# Phase 7-B: 64×128 (power-of-two) 로 상향. 타일 위로 64px 오버플로 — 건물 상부가
# 확실히 윗 타일 영역을 덮어 카이로 특유의 "높은 건물" 실루엣 확보.
#   - 건물/나무 sprite 는 64(W)×128(H), 콘텐츠 bottom-align (발끝이 타일 바닥).
#   - 상단 64px 이 윗 타일 영역 오버행. GridSystem 이 origin=(0.5, 1) + row-based depth 로 처리.
#   - 강마루(바닥 타일)만 64×64 유지.
TILE_H = 128
CHROMA_THRESH = 18

os.makedirs(DST, exist_ok=True)

# 파일명 → 처리 스펙
#   key        : Phaser texture key
#   file       : 출력 파일명
#   sheet      : None(정적) | (cols, rows) (수동 grid 지정)
#   target     : 출력 프레임 크기 (w, h). None → TILE×TILE.
MAPPING = {
    '뜸방.png':     {'key': 'tex_building_moxa',    'file': 'moxa.png',    'sheet': (4, 4), 'target': (TILE, TILE_H)},
    '침방.png':     {'key': 'tex_building_acu',     'file': 'acu.png',     'sheet': None,   'target': (TILE, TILE_H)},
    '해우소.png':   {'key': 'tex_building_haewoso', 'file': 'haewoso.png', 'sheet': None,   'target': (TILE, TILE_H)},
    '국밥집.gif':   {'key': 'tex_building_gukbap',  'file': 'gukbap.png',  'sheet': 'gif',  'target': (TILE, TILE_H)},
    '소나무.gif':   {'key': 'tex_building_pine',    'file': 'pine.png',    'sheet': 'gif',  'target': (TILE, TILE_H)},
    '우물.gif':     {'key': 'tex_building_well',    'file': 'well.png',    'sheet': 'gif',  'target': (TILE, TILE_H)},
    '강마루.png':   {'key': 'tex_tile_maru',        'file': 'maru.png',    'sheet': None,   'target': (TILE, TILE)},  # 바닥타일 — 오버플로 없음
}


def chromakey_bg(im: Image.Image) -> Image.Image:
    arr = np.array(im.convert('RGBA'))
    bg = arr[0, 0, :3].astype(np.int16)
    # 이미 알파 0 인 픽셀은 diff 계산해도 마스크에 포함되지만 다시 0 되므로 무해
    diff = np.abs(arr[..., :3].astype(np.int16) - bg).max(axis=-1)
    mask = (diff <= CHROMA_THRESH) & (arr[..., 3] > 0)
    arr[mask, 3] = 0
    return Image.fromarray(arr, mode='RGBA')


def fit_on_canvas(im: Image.Image, tw: int, th: int) -> Image.Image:
    """종횡비 보존 + 투명 캔버스 배치.
    - 정사각형 타일(tw==th): 센터 배치 (기존 동작 유지).
    - 세로 긴 타일(th > tw, 카이로식 오버플로): bottom-align — 하단이 타일 바닥과 일치.
      이러면 GridSystem 이 origin=(0.5, 1)·y=타일바닥 으로 sprite 를 배치했을 때
      건물 발끝이 정확히 타일 경계에 맞고 상부가 위 타일로 자연스럽게 튀어나옴.
    """
    w, h = im.size
    scale = min(tw / w, th / h)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    resized = im.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
    px = (tw - nw) // 2
    py = (th - nh) if th > tw else (th - nh) // 2
    canvas.paste(resized, (px, py), resized)
    return canvas


def process_png_static(src_path: str, dst_name: str, target=(TILE, TILE)):
    im = Image.open(src_path).convert('RGBA')
    im = chromakey_bg(im)
    # 콘텐츠 bounding box 로 크롭 (원본에 넓은 투명 여백이 있는 경우 대비)
    bbox = im.getbbox()
    if bbox: im = im.crop(bbox)
    out = fit_on_canvas(im, target[0], target[1])
    out.save(os.path.join(DST, dst_name))
    return {'type': 'image'}


def process_png_grid(src_path: str, dst_name: str, cols: int, rows: int, target=(TILE, TILE)):
    """수동 grid 지정 PNG 스프라이트시트.
      각 셀을 (cw, ch) 로 자르고, 개별 셀을 target 크기로 fit 해서 가로 strip 으로 재구성.
      Phaser 가 `frameWidth=target[0]` 로 읽도록 통일.
    """
    im = Image.open(src_path).convert('RGBA')
    im = chromakey_bg(im)
    W, H = im.size
    cw, ch = W // cols, H // rows
    tw, th = target
    n = cols * rows
    sheet = Image.new('RGBA', (tw * n, th), (0, 0, 0, 0))
    idx = 0
    for r in range(rows):
        for c in range(cols):
            cell = im.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch))
            # 각 셀 개별 bbox 크롭 후 fit — 셀 내부 여백이 있는 경우에도 중앙정렬
            bbox = cell.getbbox()
            if bbox: cell = cell.crop(bbox)
            fitted = fit_on_canvas(cell, tw, th)
            sheet.paste(fitted, (tw * idx, 0), fitted)
            idx += 1
    sheet.save(os.path.join(DST, dst_name))
    return {'type': 'spritesheet', 'frames': n, 'fw': tw, 'fh': th}


def process_gif(src_path: str, dst_name: str, target=(TILE, TILE)):
    src = Image.open(src_path)
    tw, th = target
    frames = []
    for f in ImageSequence.Iterator(src):
        rgba = f.convert('RGBA')
        rgba = chromakey_bg(rgba)
        bbox = rgba.getbbox()
        if bbox: rgba = rgba.crop(bbox)
        frames.append(fit_on_canvas(rgba, tw, th))
    n = len(frames)
    sheet = Image.new('RGBA', (tw * n, th), (0, 0, 0, 0))
    for i, fr in enumerate(frames):
        sheet.paste(fr, (tw * i, 0), fr)
    sheet.save(os.path.join(DST, dst_name))
    return {'type': 'spritesheet', 'frames': n, 'fw': tw, 'fh': th}


manifest = []
for src_name, spec in MAPPING.items():
    src_path = os.path.join(SRC, src_name)
    if not os.path.exists(src_path):
        print(f'MISSING: {src_name}')
        continue
    key = spec['key']; dst_name = spec['file']
    target = spec.get('target', (TILE, TILE))
    sheet = spec.get('sheet')
    if sheet == 'gif':
        info = process_gif(src_path, dst_name, target)
    elif isinstance(sheet, tuple):
        cols, rows = sheet
        info = process_png_grid(src_path, dst_name, cols, rows, target)
    else:
        info = process_png_static(src_path, dst_name, target)
    entry = {'key': key, 'file': dst_name, **info}
    manifest.append(entry)
    print(f'{src_name} -> {dst_name} {info}')

with open(os.path.join(DST, 'manifest.json'), 'w', encoding='utf-8') as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print('DONE. manifest:', os.path.join(DST, 'manifest.json'))
