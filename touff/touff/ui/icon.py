"""Draws Touff's face for the tray icon, no image files needed."""

from __future__ import annotations

from PIL import Image, ImageDraw


def tray_image(size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    d.ellipse((4 * s, 6 * s, 60 * s, 60 * s), fill=(167, 112, 255, 255))
    d.ellipse((10 * s, 10 * s, 40 * s, 32 * s), fill=(196, 160, 255, 255))  # shine
    for cx in (23, 41):
        d.ellipse(((cx - 5) * s, 26 * s, (cx + 5) * s, 38 * s), fill=(30, 20, 50, 255))
        d.ellipse(((cx - 2) * s, 28 * s, (cx + 1) * s, 31 * s), fill=(255, 255, 255, 255))
    d.arc((26 * s, 38 * s, 38 * s, 48 * s), 20, 160, fill=(30, 20, 50, 255), width=max(1, int(2 * s)))
    d.ellipse((12 * s, 38 * s, 18 * s, 43 * s), fill=(255, 140, 190, 200))  # cheeks
    d.ellipse((46 * s, 38 * s, 52 * s, 43 * s), fill=(255, 140, 190, 200))
    return img
