"""Generate kinetic-text image cards as video visuals — no external API needed."""
from __future__ import annotations
import os
import re
import random
import textwrap
import numpy as np
from PIL import Image, ImageDraw, ImageFont

TARGET_W = 1080
TARGET_H = 1920
PAD = 90

_FONT_PATH = "/System/Library/Fonts/HelveticaNeue.ttc"
_FONT_BOLD_IDX = 4   # Condensed Bold — tight, punchy, fills screen nicely
_FONT_FALLBACK_IDX = 1  # Regular Bold

# (bg_top, bg_bottom, accent_rgb)
_THEMES = [
    ((6,  6,  18), (20, 12, 50), (255, 205,  60)),   # indigo / gold
    ((5,  8,  28), (12, 25, 65), ( 80, 195, 255)),   # navy / ice blue
    ((20,  4,  4), (48, 10, 14), (255,  95,  95)),   # crimson / coral
    (( 8,  8,  8), (24, 24, 24), (195, 255, 115)),   # charcoal / lime
    ((14,  5, 22), (38, 14, 55), (195, 105, 255)),   # violet / purple
    (( 4, 16,  5), (10, 40, 15), ( 55, 235, 165)),   # forest / teal
]


def generate_kinetic_clips(script: dict, output_dir: str) -> list[str]:
    os.makedirs(output_dir, exist_ok=True)
    narration = script.get("narration", "")
    n = len(script.get("image_prompts", [])) or 6
    phrases = _extract_phrases(narration, n)
    theme = random.choice(_THEMES)
    paths = []
    for i, phrase in enumerate(phrases):
        path = os.path.join(output_dir, f"k_{i:02d}.png")
        _render_card(phrase, theme, path, index=i, total=n)
        paths.append(path)
        print(f"[kinetic] {i + 1}/{n} ready")
    return paths


# ── helpers ───────────────────────────────────────────────────────────────────

def _extract_phrases(text: str, n: int) -> list[str]:
    sents = re.split(r'(?<=[.!?])\s+', text.strip())
    sents = [s.strip() for s in sents if len(s.strip()) > 4]
    if not sents:
        return [text[:60].upper()] * n
    step = max(1, len(sents) / n)
    chosen = [sents[min(int(i * step), len(sents) - 1)] for i in range(n)]
    return [_headline(s) for s in chosen]


def _headline(s: str) -> str:
    words = s.split()
    if len(words) <= 7:
        return s.upper().rstrip('.,;')
    return ' '.join(words[:6]).upper().rstrip('.,;') + '...'


def _grad(w: int, h: int, top: tuple, bot: tuple) -> Image.Image:
    t = np.linspace(0, 1, h)[:, None]
    rows = (np.array(top, dtype=np.float32) * (1 - t)
            + np.array(bot, dtype=np.float32) * t).astype(np.uint8)
    return Image.fromarray(np.tile(rows[:, None, :], (1, w, 1)), 'RGB')


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for idx in (_FONT_BOLD_IDX, _FONT_FALLBACK_IDX, 0):
        try:
            return ImageFont.truetype(_FONT_PATH, size, index=idx)
        except Exception:
            pass
    return ImageFont.load_default()


def _best_layout(draw: ImageDraw.Draw, text: str) -> tuple:
    """Return (font, lines) that fit within TARGET_W - 2*PAD, never breaking mid-word."""
    max_px = TARGET_W - 2 * PAD
    for size in range(170, 55, -10):
        font = _load_font(size)
        # Try from widest to narrowest — fewest lines wins
        for chars in (60, 30, 20, 15, 12, 10, 8, 6):
            lines = textwrap.wrap(
                text, width=chars,
                break_long_words=False, break_on_hyphens=False
            ) or [text]
            if max(draw.textlength(l, font=font) for l in lines) <= max_px:
                return font, lines
    font = _load_font(60)
    return font, textwrap.wrap(text, width=10, break_long_words=False) or [text]


def _render_card(
    phrase: str,
    theme: tuple,
    path: str,
    index: int,
    total: int,
) -> None:
    bg_top, bg_bot, accent = theme
    img = _grad(TARGET_W, TARGET_H, bg_top, bg_bot)
    draw = ImageDraw.Draw(img)
    cx = TARGET_W // 2

    font, lines = _best_layout(draw, phrase)
    lh = font.size * 1.35
    block_h = len(lines) * lh
    text_top = TARGET_H / 2 - block_h / 2

    # Accent bar above text block
    ay = int(text_top - 60)
    draw.rectangle([cx - 80, ay, cx + 80, ay + 6], fill=accent)

    # Text lines (shadow + white)
    for j, line in enumerate(lines):
        y = int(text_top + j * lh + lh / 2)
        draw.text((cx + 3, y + 3), line, font=font, fill=(0, 0, 0), anchor="mm")
        draw.text((cx, y), line, font=font, fill=(255, 255, 255), anchor="mm")

    # Accent bar below text block
    by = int(text_top + block_h + 35)
    draw.rectangle([cx - 80, by, cx + 80, by + 6], fill=accent)

    # Progress dots near bottom
    dy = TARGET_H - 100
    for k in range(total):
        dx = cx + (k - total // 2) * 24 + 12
        r = 8 if k == index else 4
        c = accent if k == index else (70, 70, 70)
        draw.ellipse([dx - r, dy - r, dx + r, dy + r], fill=c)

    img.save(path, "PNG")
