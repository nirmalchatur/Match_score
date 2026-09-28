"""
Generate TailorUp's static image assets.

Run from the repository root:  python scripts/generate_brand_assets.py

Why a generator and not just committed binaries
-----------------------------------------------
The previous favicon was a purple gradient bolt -- a design-tool default, not
TailorUp's mark, and the brand is teal (#245F73). Regenerating fixes that, but
committing only the outputs means a colour change needs a drawing program. The
sources live here as code instead, so it is a one-line edit and a re-run.

Outputs, and why each exists
----------------------------
favicon.ico            Legacy request, still made by some browsers/crawlers
favicon-16x16/32x32    Modern browsers request these explicitly
apple-touch-icon       iOS home screen; iOS does not read the SVG favicon
icon-192/512           PWA / installable, referenced by the web manifest
og-image.png           Link previews. Crawlers do NOT render SVG for og:image,
                       so this must be a real raster image.

Pillow is needed to run this but is NOT a runtime dependency. Nothing that
serves the application imports it.
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# --- Brand -----------------------------------------------------------------
PRIMARY = (0x24, 0x5F, 0x73)  # #245F73
PRIMARY_DEEP = (0x18, 0x3E, 0x4C)  # darker teal for the gradient foot
WARM = (0x73, 0x3E, 0x24)  # #733E24, used sparingly
PAPER = (0xF2, 0xF0, 0xEF)  # #F2F0EF
MUTED = (0xBB, 0xBD, 0xBC)  # #BBBDBC
INK = (0x0A, 0x0A, 0x0A)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "public"

# The IconLogo bolt on its 24x24 viewBox, kept identical to the React
# component's path so the favicon and the in-app mark cannot drift apart.
BOLT_24 = [
    (13.6, 2.0), (4.8, 13.2), (9.9, 13.2), (8.9, 22.0),
    (19.2, 10.4), (13.8, 10.4), (15.1, 2.0),
]


def _scale(points, size: float, pad_ratio: float = 0.22):
    """Scale the 24x24 bolt into a size x size box with padding."""
    inner = size * (1 - pad_ratio * 2)
    scale = inner / 24.0
    offset = size * pad_ratio
    return [(x * scale + offset, y * scale + offset) for x, y in points]


def _rounded_gradient(size: int, radius_ratio: float = 0.22) -> Image.Image:
    """A rounded square with a vertical teal gradient.

    Drawn as a gradient masked by a rounded rectangle, so the corners are
    genuinely transparent rather than approximated with corner pixels.
    """
    base = Image.new("RGB", (size, size), PRIMARY)
    draw = ImageDraw.Draw(base)
    for y in range(size):
        t = y / max(1, size - 1)
        colour = tuple(
            round(PRIMARY[i] + (PRIMARY_DEEP[i] - PRIMARY[i]) * t) for i in range(3)
        )
        draw.line([(0, y), (size, y)], fill=colour)

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=round(size * radius_ratio), fill=255
    )
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(base, (0, 0), mask)
    return out


def _bolt_image(size: int) -> Image.Image:
    """The mark alone, transparent background."""
    img = _rounded_gradient(size)
    ImageDraw.Draw(img).polygon(_scale(BOLT_24, size), fill=PAPER + (255,))
    return img


def _find_font(size: int) -> ImageFont.FreeTypeFont:
    """A real font if one is available, else Pillow's bitmap default.

    The default is ugly at 100px, so the common Windows and macOS paths are
    tried first. Degrading to the default keeps this working on a machine with
    none of them installed.
    """
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def og_image() -> Image.Image:
    """1200x630 link-preview card.

    Sized to the Open Graph recommendation, which is what Facebook, LinkedIn,
    Slack and X crop against. Left-aligned on a light ground so it survives
    being cropped to a square in some timelines.
    """
    w, h = 1200, 630
    img = Image.new("RGB", (w, h), PAPER)
    draw = ImageDraw.Draw(img)

    # A teal band down the left edge, so the card still reads as TailorUp when
    # a timeline crops the text away entirely.
    draw.rectangle([0, 0, 18, h], fill=PRIMARY)
    draw.rectangle([18, 0, 26, h], fill=WARM)

    mark = _bolt_image(132)
    img.paste(mark, (96, 84), mark)

    draw.text((96, 268), "TailorUp", font=_find_font(78), fill=PRIMARY)
    draw.text((96, 366), "Know how well you fit", font=_find_font(46), fill=INK)
    draw.text((96, 420), "before you apply.", font=_find_font(46), fill=INK)
    draw.text(
        (96, 512),
        "Open-source job analysis. Runs locally with Ollama.",
        font=_find_font(26),
        fill=MUTED,
    )
    return img


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    def save(img: Image.Image, name: str, **kw) -> None:
        path = OUT / name
        img.save(path, **kw)
        written.append(f"{name} ({path.stat().st_size:,} b)")

    for size, name in (
        (16, "favicon-16x16.png"),
        (32, "favicon-32x32.png"),
        (180, "apple-touch-icon.png"),
        (192, "icon-192.png"),
        (512, "icon-512.png"),
    ):
        save(_bolt_image(size), name, optimize=True)

    # Multi-resolution ICO. A 16px ICO is unreadable as a single 512px image
    # downscaled by the OS, so the sizes are embedded explicitly.
    ico_sizes = [16, 32, 48]
    _bolt_image(48).save(
        OUT / "favicon.ico", format="ICO", sizes=[(s, s) for s in ico_sizes]
    )
    written.append(f"favicon.ico (sizes {ico_sizes})")

    save(og_image(), "og-image.png", optimize=True)

    print("Wrote to frontend/public/:")
    for line in written:
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
