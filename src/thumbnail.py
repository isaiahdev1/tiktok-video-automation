"""Generate a YouTube thumbnail using Pillow."""

from __future__ import annotations
import os
import textwrap
from PIL import Image, ImageDraw, ImageFont


_FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def generate_thumbnail(title: str, output_path: str) -> str:
    W, H = 1280, 720
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # Dark gradient background (left dark blue → right slightly lighter)
    for x in range(W):
        r = int(5 + 25 * (x / W))
        g = int(5 + 15 * (x / W))
        b = int(20 + 40 * (x / W))
        draw.line([(x, 0), (x, H)], fill=(r, g, b))

    # Yellow accent bar on the left
    draw.rectangle([45, 70, 62, H - 70], fill=(255, 215, 0))

    font = _load_font(88)
    small_font = _load_font(52)

    # Word-wrap title to fit within content area
    lines = textwrap.wrap(title.upper(), width=18)

    line_h = 100
    total_h = len(lines) * line_h
    y = (H - total_h) // 2

    for line in lines:
        # Drop shadow
        draw.text((92, y + 5), line, fill=(0, 0, 0), font=font)
        # Main white text
        draw.text((90, y), line, fill=(255, 255, 255), font=font)
        y += line_h

    # Yellow accent line under text
    draw.rectangle([90, y + 10, 90 + min(len(title) * 20, W - 150), y + 16], fill=(255, 215, 0))

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.save(output_path, "JPEG", quality=95)
    print(f"[thumbnail] Saved: {os.path.basename(output_path)}")
    return output_path
