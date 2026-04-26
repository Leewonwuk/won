# Cover Image

The cover image for the lablab.ai submission is [`cover_image.svg`](./cover_image.svg) — 1600×900 (16:9, matches YouTube + lablab card dimensions).

## Layout

- **Left column** — producer agents (`kimchi_agent` + `dual_quote_agent`), raw tier $0.002, cyan accent.
- **Centre** — Arc Bridge, x402 + signal registry, gradient-outlined card.
- **Right column** — consumer agents (`meta_agent` Gemini+GBM + `executor_agent`), premium tier $0.01, purple accent.
- **Bottom band** — five headline metrics: per-signal price, 50+ tx per 2-min demo, 87-pair / 7.5M-row GBM training set, gas/price ratio on Arc, chain name.
- **Background** — deep-navy gradient + faint grid + a subtle radial glow centered on the Bridge.

## Rendering to PNG for submission

Most lablab / YouTube upload forms want a raster. Choose whichever is easiest:

### Option A — Chrome/Edge (no install)
1. Open `cover_image.svg` in a browser.
2. Right-click → *Save as PNG* (on Chrome, use the "Capture screenshot" devtools command at 1600×900).

### Option B — Inkscape CLI
```bash
inkscape docs/cover_image.svg --export-type=png --export-filename=docs/cover_image.png -w 1600 -h 900
```

### Option C — ImageMagick
```bash
magick -background none -density 150 docs/cover_image.svg -resize 1600x900 docs/cover_image.png
```

### Option D — Python (cairosvg)
```bash
pip install cairosvg
python -c "import cairosvg; cairosvg.svg2png(url='docs/cover_image.svg', write_to='docs/cover_image.png', output_width=1600, output_height=900)"
```

Any of these produces a 1600×900 PNG suitable for the submission card and YouTube thumbnail.

## Colour palette (for any downstream use)

| Purpose | Hex |
|---|---|
| Background base | `#0b1020` |
| Background mid | `#0f1a3a` |
| Card fill | `#111a35` |
| Cyan (raw producers) | `#22d3ee` |
| Purple (premium / consumers) | `#a855f7` |
| Green (positive metric) | `#4ade80` |
| Primary text | `#ffffff` / `#f8fafc` |
| Secondary text | `#94a3c4` |

Feel free to regenerate the SVG with different metrics — the five bottom-band values are plain `<text>` elements, easy to edit.
