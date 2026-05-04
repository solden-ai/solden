#!/usr/bin/env python3
"""Build favicon variants as a teal tile + solid lowercase 's' glyph.

The architectural S-mark loses readable detail below 32px — its three
parallelogram bars need sub-pixel gaps that anti-aliasing destroys.
Stripe / Linear / Notion / Vercel all solve this the same way: a
separate simplified favicon mark, distinct from the full lockup.

Solden's wordmark is "solden" in lowercase Inter Bold. The favicon
mirrors that: a solid lowercase 's' in Inter Black on the brand teal
tile, with rounded corners. Brand-consistent (color + typography),
unambiguous at 16px.

Sources:
- Inter font already loaded by the workspace SPA via rsms.me. We need
  the woff2 / ttf locally to render. Try a few common system paths;
  fall back to PIL's default if Inter isn't available (last-resort).
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = Path("ui/web-app/public")

TEAL = (24, 191, 176, 255)   # #18BFB0
WHITE = (255, 255, 255, 255)

CORNER_RADIUS_RATIO = 0.18
SUPERSAMPLE = 8


# Inter typeface candidates. Black weight (900) reads cleanest at
# 16px — heavier strokes survive downscaling. Path search is best-
# effort; the system Mac install ships Inter via the SF system or
# user-installed copies. Try a sequence and fall back gracefully.
INTER_CANDIDATES = [
    # Vendored alongside the brand-kit source so the build is
    # reproducible regardless of system font installation.
    "brand-kit-source/fonts/Inter-Black.ttf",
    "/Library/Fonts/Inter-Black.ttf",
    str(Path.home() / "Library/Fonts/Inter-Black.ttf"),
    # Last-resort: system sans (will look noticeably different but
    # won't crash the build).
    "/System/Library/Fonts/SFNS.ttf",
]


def _load_font(size_px: int) -> ImageFont.FreeTypeFont:
    for candidate in INTER_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size_px)
            except OSError:
                continue
    # Last resort — Pillow's bundled bitmap default. Will look terrible
    # at small sizes but at least won't crash.
    return ImageFont.load_default()


def _render_glyph_layer(target_size: int) -> Image.Image:
    """Render the white 's' centred inside a target-size canvas, using
    SUPERSAMPLE × resolution for clean anti-aliasing on downscale."""
    high = target_size * SUPERSAMPLE
    canvas = Image.new("RGBA", (high, high), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Fit the 's' to ~62% of the tile height — leaves enough breathing
    # room for the rounded-rect corners while keeping the glyph
    # dominant. Inter Black at this size renders bold curves that
    # survive downscaling to 16px.
    glyph_height = int(round(high * 0.62))
    font = _load_font(glyph_height)

    text = "s"
    # Use textbbox so we can centre exactly using the glyph's actual
    # ink bounds (not the font's vertical metrics, which include space
    # for ascenders/descenders the 's' doesn't use).
    bbox = draw.textbbox((0, 0), text, font=font)
    ink_w = bbox[2] - bbox[0]
    ink_h = bbox[3] - bbox[1]
    x = (high - ink_w) // 2 - bbox[0]
    y = (high - ink_h) // 2 - bbox[1]

    draw.text((x, y), text, font=font, fill=WHITE)

    return canvas.resize((target_size, target_size), Image.LANCZOS)


def _rounded_tile(size: int) -> Image.Image:
    high = size * SUPERSAMPLE
    radius = max(1, int(round(high * CORNER_RADIUS_RATIO)))
    tile = Image.new("RGBA", (high, high), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)
    draw.rounded_rectangle(
        ((0, 0), (high - 1, high - 1)),
        radius=radius,
        fill=TEAL,
    )
    return tile.resize((size, size), Image.LANCZOS)


def build(size: int, out_path: Path) -> None:
    tile = _rounded_tile(size)
    glyph = _render_glyph_layer(size)
    composite = Image.alpha_composite(tile, glyph)
    composite.save(out_path, format="PNG", optimize=True)
    print(f"  wrote {out_path.name} ({size}×{size})")


def main() -> None:
    build(128, OUTPUT_DIR / "favicon.png")
    build(32, OUTPUT_DIR / "favicon-32x32.png")
    build(16, OUTPUT_DIR / "favicon-16x16.png")


if __name__ == "__main__":
    main()
