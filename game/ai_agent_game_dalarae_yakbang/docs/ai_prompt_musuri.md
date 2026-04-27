# ⚠️ DEPRECATED — 무수리 AI 재생성 프롬프트

> **2026-04-20 폐기.** 무수리 원본은 정상이었음 (파이프라인 오진). 재생성 불필요.
> `recompose_via_components()` 자동 재조립으로 해결됨. 유효 규약: `docs/character_pipeline_spec.md`.

---

# (히스토리) 무수리 AI 재생성 프롬프트 (2026-04-20)

> `docs/ai_regen_spec.md` 기반. 복사해서 AI 이미지 생성기(Replicate / Midjourney / NovelAI 등)에 그대로 투입.

## 첨부 파일 (reference images)

1. `c:\Users\user\game\Kario\생성그림_꼉\캐릭터원본\의녀.png` — **스타일·팔레트 시드**
2. `c:\Users\user\game\Kario\scripts\palette_out\_compare\uinyeo_vs_musuri.png` — 좋은 예(왼쪽) vs 실패 예(오른쪽)

## Prompt (English — 권장, AI 도트 모델 호환성↑)

```
Pixel art character sprite sheet, RPG Maker format, 3 columns × 4 rows = 12 frames.
Subject: "무수리" (musuri) - a Korean Joseon-dynasty maidservant. Female, early 20s,
wearing a light blue hanbok jeogori (short jacket) with a white apron over a
dark navy chima (long skirt). Hair tied back simply. Holding a small broom or
water jar as a role marker.

Layout:
- Row 0 (top): facing DOWN / front view (3 frames: left-step, idle, right-step)
- Row 1: facing LEFT (3 frames)
- Row 2: facing RIGHT (3 frames)
- Row 3 (bottom): facing UP / back view (3 frames)

Cell size: 160×160 pixels. Total canvas: 480×640 pixels.
CRITICAL: Each cell must have at least 20px top/bottom padding and 10px left/right
padding. Character feet must NEVER touch the bottom edge of a cell. Character head
hair must NEVER touch the top edge. No grid lines, no cell borders drawn.

Walking animation: arms and legs move only. Body vertical position is FIXED
(no bob, no head bounce). Idle frame = both feet level. Step frames = one foot lifted.
All 12 frames share the same foot-baseline Y coordinate (±1px maximum variance).

Color palette: LIMITED 8-12 colors only, NO anti-aliasing, NO gradients, NO blur.
Hard-edge pixel art only. All outlines pure black #000000, exactly 1 pixel wide.
Skin tones: use #f9cba1 (base), #eedde4 (highlight), #d28844 (shadow).
Outline shadow color: #47413b.
Maintain palette consistency with the reference 의녀 image (first attachment).

Background: completely transparent (alpha=0). No background color, no checkerboard,
no grid, no guide lines.

Style: authentic 16-bit pixel art in the style of Kairosoft "Hot Springs Story"
(온천골 스토리) and Pedro Medeiros' Celeste sprites. Clean silhouette readable even
as a pure black shape. Korean traditional hanbok silhouette clearly distinguishable
from merchant/noble/scholar classes.

Do NOT include: AA smoothing, drop shadows, lighting gradients, grid lines,
cell borders, watermarks, text, UI elements, or multiple characters per frame.
```

## 검증 체크리스트 (AI 출력 수령 후)

- [ ] 파일 크기: 정확히 480×640 (또는 480×480 / 192×256 등 3:4 비율)
- [ ] 프레임 12개가 각 셀에 완전히 포함되는가? (경계 침범 0픽셀)
- [ ] 머리 꼭대기 ~ 상단 경계 ≥ 20px?
- [ ] 발 밑 ~ 하단 경계 ≥ 20px?
- [ ] 12 프레임 발 밑선 Y 일정 (±1px)?
- [ ] 색 수 ≤ 12?
- [ ] 의녀 팔레트의 피부·그림자 색 공유되었는가?
- [ ] AA / 그라데이션 / 블러 0건?
- [ ] 배경 완전 투명?

**PASS 시** → `생성그림_꼉/캐릭터도트버전/무수리.png` 덮어쓰기 → `python scripts/palette_transfer.py` 실행 → 출력 재검수.

**FAIL 시** → 실패 항목을 프롬프트에 강조 추가하여 재요청. 예: "CRITICAL FAILURE IN PREVIOUS ATTEMPT: feet were cropped at cell boundary. Ensure 20px bottom padding."

## 추가 변형 (성공 후 나머지 9종 일괄 생성용)

위 프롬프트에서 "무수리" 부분만 아래로 교체:

| 키 | 영문 교체 문구 |
|---|---|
| nobi_m | a Korean Joseon male slave/servant (노비). Rough hemp clothing, barefoot or straw sandals, tied hair bun, carrying a jige (wooden A-frame carrier) on back |
| nobi_f | a Korean Joseon female slave/servant. Plain undyed hemp jeogori and chima, simple braided hair |
| nongmin_m | a Korean Joseon male peasant farmer (농민). Cotton work clothes, wide straw hat, carrying a hoe or sickle |
| sangin_m | a Korean Joseon male merchant (상인). Dark gray hanbok with silk trim, carrying a small wooden abacus or money pouch |
| sangin_f | a Korean Joseon female merchant. Colorful hanbok, carrying a cloth-wrapped bundle (bojagi) |
| seonbi_m | a Korean Joseon male scholar (선비). White hanbok, black gat (horsehair hat), holding a book scroll |
| seonbi_f | a Korean Joseon female scholar/student (서생). Subdued pastel hanbok, carrying a book |
| yangban_m | a Korean Joseon male noble/official (관원). Elaborate dark silk hanbok with insignia, formal black gat |
| yangban_f | a Korean Joseon female noble (여자관원). Rich silk hanbok with embroidery, ornate binyeo (hairpin) |

**나머지 프롬프트 본문(레이아웃·색·해상도·배경)은 모두 동일** — 이것이 공유 팔레트·셀 규격을 보장하는 핵심.
