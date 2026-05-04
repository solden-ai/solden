#!/usr/bin/env python3
"""Crop the Solden brand PNGs to remove the whitespace padding that
makes them look small at every render size.

Each asset has 30-50% padding around the actual mark/wordmark in the
source export — at small render sizes (16px favicon, 36px sidebar)
that translates to a glyph that's only 8-20px of visible content,
which reads as "tiny" against industry-standard logos that fill
their canvas.

This script computes the bounding box of the non-background content
in each asset and crops to that + a small symmetric margin (4% of
the larger side). Original assets are backed up alongside.
"""
from pathlib import Path
from PIL import Image, ImageChops

ASSETS_DIR = Path("ui/web-app/public")
TARGETS = [
    "favicon.png",
    "solden-lockup-dark.png",
    "solden-lockup-white.png",
    # apple-touch-icon.png intentionally excluded — Apple's home-screen
    # tile spec is full-canvas (the OS applies its own rounded-rect
    # mask). Cropping it would break iOS/iPadOS home-screen rendering.
]

# 4% margin keeps the lockup from butting against the edge but doesn't
# reintroduce the whitespace problem. Experiment-derived: above 6%
# starts looking padded again at small sizes.
MARGIN_RATIO = 0.04

# Alpha-channel content threshold. Real-world brand exports can have a
# faint anti-aliased fringe (alpha=10-90 in otherwise-empty pixels)
# that defeats naive bbox detection. Half-opacity (128) is the
# break-point: anything ≥ 128 is reliably real content; anything below
# is fringe / export artifact.
ALPHA_CONTENT_THRESHOLD = 128

# RGB diff threshold for solid-background exports. Same rationale:
# JPEG-style noise sits in the 0-31 range; real content typically
# diffs by >64 from the background colour.
RGB_DIFF_THRESHOLD = 32


def content_bbox(img: Image.Image):
    """Return (left, upper, right, lower) of the visible content.

    Real-world brand exports have two pathologies that break naive
    bbox detection:
      - Faint alpha fringe (anti-aliased export with alpha=10-30 in
        otherwise-empty pixels) defeats RGBA bbox, which treats any
        non-zero alpha as content.
      - JPEG/PNG compression introduces near-background-color pixels
        across nominally-empty space, defeating RGB diff bbox.

    Strategy:
      - RGBA: threshold alpha at 32; only pixels above that count as
        content. Mark pixels are normally alpha=255 with anti-aliased
        edges still well above 32.
      - RGB: threshold the diff at 16 per channel; pixels within that
        of the corner colour are treated as background.
    """
    if img.mode == "RGBA":
        alpha = img.split()[-1]
        binary_alpha = alpha.point(
            lambda p: 255 if p >= ALPHA_CONTENT_THRESHOLD else 0
        )
        bbox = binary_alpha.getbbox()
        if bbox:
            return bbox
        # Fully transparent — no detectable content. Caller should
        # treat this as "skip"; we return None as a sentinel.
        return None

    if img.mode != "RGB":
        img = img.convert("RGB")

    bg = Image.new("RGB", img.size, img.getpixel((0, 0)))
    diff = ImageChops.difference(img, bg).convert("L")
    binary = diff.point(lambda p: 255 if p >= RGB_DIFF_THRESHOLD else 0)
    bbox = binary.getbbox()
    return bbox or (0, 0, *img.size)


def crop_with_margin(path: Path) -> tuple[tuple[int, int], tuple[int, int]] | None:
    img = Image.open(path)
    original_size = img.size

    bbox = content_bbox(img)
    if bbox is None:
        return None
    left, upper, right, lower = bbox
    content_w = right - left
    content_h = lower - upper

    # Symmetric margin so the lockup isn't visually shifted off-centre
    margin = int(round(MARGIN_RATIO * max(content_w, content_h)))
    new_left = max(0, left - margin)
    new_upper = max(0, upper - margin)
    new_right = min(img.size[0], right + margin)
    new_lower = min(img.size[1], lower + margin)

    cropped = img.crop((new_left, new_upper, new_right, new_lower))

    backup = path.with_suffix(path.suffix + ".original")
    if not backup.exists():
        path.replace(backup)
    else:
        path.unlink(missing_ok=True)
    cropped.save(path, format="PNG", optimize=True)
    return original_size, cropped.size


def main():
    for name in TARGETS:
        path = ASSETS_DIR / name
        if not path.exists():
            print(f"  skip {name} (missing)")
            continue
        result = crop_with_margin(path)
        if result is None:
            print(f"  skip {name} (no content above alpha threshold)")
            continue
        before, after = result
        ratio_w = after[0] / before[0]
        ratio_h = after[1] / before[1]
        print(
            f"  {name}: {before[0]}×{before[1]} → {after[0]}×{after[1]} "
            f"(was {ratio_w:.0%} × {ratio_h:.0%} of canvas)"
        )


if __name__ == "__main__":
    main()
