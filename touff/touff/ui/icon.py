"""Draws Touff's face for the tray icon, no image files needed."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter


def tray_image(size: int = 64) -> Image.Image:
    """A glossy purple orb with Touff's face, drawn 4x larger and scaled down so the edges are smooth."""
    k = 4
    big = size * k
    s = big / 64

    # body: vertical-ish gradient from light lilac (top left) to deep violet (bottom right)
    grad = Image.new("RGBA", (big, big))
    gd = ImageDraw.Draw(grad)
    top, bottom = (196, 166, 255), (98, 52, 230)
    for y in range(big):
        t = y / (big - 1)
        gd.line([(0, y), (big, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((4 * s, 5 * s, 60 * s, 61 * s), fill=255)
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)

    # soft shine
    shine = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(shine).ellipse((13 * s, 10 * s, 33 * s, 22 * s), fill=(255, 255, 255, 120))
    img.alpha_composite(shine.filter(ImageFilter.GaussianBlur(3 * s)))

    d = ImageDraw.Draw(img)
    ink = (29, 20, 48, 255)
    for cx in (23, 41):  # eyes with a sparkle
        d.ellipse(((cx - 4.5) * s, 25 * s, (cx + 4.5) * s, 37 * s), fill=ink)
        d.ellipse(((cx - 2.5) * s, 27 * s, (cx + 0.5) * s, 30 * s), fill=(255, 255, 255, 255))
    d.ellipse((11 * s, 38 * s, 18 * s, 43 * s), fill=(255, 130, 190, 210))  # cheeks
    d.ellipse((46 * s, 38 * s, 53 * s, 43 * s), fill=(255, 130, 190, 210))
    d.chord((26 * s, 36 * s, 38 * s, 47 * s), 0, 180, fill=ink)  # smile
    return img.resize((size, size), Image.LANCZOS)
