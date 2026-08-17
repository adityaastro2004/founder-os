#!/usr/bin/env python3
"""Derive the Founder OS icon set from the founder-supplied source art.

The recipe was first applied by hand in 161c540; it is scripted here so that a
new logo drop is one command instead of an afternoon in an image editor. Trim
the white margin, convert the white background to alpha, recolour to the brand
tokens, then emit every asset Next.js expects.

    python3 scripts/generate-brand-assets.py                  # docs/brand/founderos-logo.png
    python3 scripts/generate-brand-assets.py path/to/new.png  # a fresh drop

Outputs, relative to founder-os/apps/web/:

    public/logo-mark.png  tight transparent ink mark, for the in-app <LogoMark>
    public/logo-icon.png  512 square ink badge, mark knocked out in paper (OG/social)
    app/icon.png          512 badge  ) wired by the App Router file convention,
    app/apple-icon.png    180 badge  ) so adding one needs no metadata change
    app/favicon.ico       16/32/48 badge

After running, check the reported mark size against the width/height props in
app/_components/logo-mark.tsx - Next.js uses them for the aspect ratio, so art
with new proportions needs them updated or the mark renders distorted.

Requires Pillow (already in apps/api/requirements.txt; any venv with it works).
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

INK = (31, 30, 29)  # --color-ink   #1f1e1d
PAPER = (250, 249, 245)  # --color-paper #faf9f5

MARK_HEIGHT = 256  # intrinsic height of public/logo-mark.png
BADGE = 512  # the master badge; every icon size is rendered from the mark
CORNER_RATIO = 0.22  # rounded-square radius, as a fraction of the badge edge
CONTENT_RATIO = 0.58  # the mark is fitted inside this fraction of the badge
ALPHA_FLOOR = 8  # alpha below this is margin, not art, when trimming


def load_mark(source: Path) -> Image.Image:
    """White-background source art -> tight RGBA mark, ink on transparent.

    Alpha is derived from luminance so the type keeps its antialiasing rather
    than getting a hard keyed edge.

    The white point is the source's *modal* luminance, not 255. The supplied
    art sits on an off-white that varies 252-255; mapping that to alpha 2-3
    instead of 0 leaves a faint paper wash across the mark's bounding box,
    which is the ghost rectangle visible behind the mark in the hand-made
    161c540 badges. The black point is the 0.5th percentile, so a few stray
    dark pixels cannot stop the body of the ink from reaching full opacity.
    """
    src = Image.open(source).convert("L")
    histogram = src.histogram()
    white = max(range(256), key=histogram.__getitem__)

    floor = 0.005 * sum(histogram)
    running = 0
    black = 0
    for value, count in enumerate(histogram):
        running += count
        if running >= floor:
            black = value
            break

    span = max(1, white - black)
    alpha = src.point(lambda v: max(0, min(255, round((white - v) * 255 / span))))

    mark = Image.new("RGBA", src.size, INK + (0,))
    mark.putalpha(alpha)

    bbox = alpha.point(lambda v: 255 if v > ALPHA_FLOOR else 0).getbbox()
    if bbox is None:
        raise SystemExit(f"{source}: no artwork found - is it a blank canvas?")
    return mark.crop(bbox)


def rounded_badge(mark: Image.Image, size: int) -> Image.Image:
    """Ink rounded square with the mark knocked out in paper."""
    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(badge).rounded_rectangle(
        (0, 0, size - 1, size - 1),
        radius=size * CORNER_RATIO,
        fill=INK + (255,),
    )

    box = size * CONTENT_RATIO
    ratio = min(box / mark.width, box / mark.height)
    width = max(1, round(mark.width * ratio))
    height = max(1, round(mark.height * ratio))

    knockout = Image.new("RGBA", (width, height), PAPER + (0,))
    knockout.putalpha(mark.resize((width, height), Image.LANCZOS).split()[3])
    badge.alpha_composite(knockout, ((size - width) // 2, (size - height) // 2))
    return badge


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "docs/brand/founderos-logo.png"
    web = root / "founder-os/apps/web"

    mark = load_mark(source)
    width = max(1, round(mark.width * MARK_HEIGHT / mark.height))
    flat = mark.resize((width, MARK_HEIGHT), Image.LANCZOS)
    flat.save(web / "public/logo-mark.png")

    badge = rounded_badge(mark, BADGE)
    badge.save(web / "public/logo-icon.png")
    badge.save(web / "app/icon.png")
    rounded_badge(mark, 180).save(web / "app/apple-icon.png")
    # Pillow downsamples the .ico members from whatever image it is handed, so
    # hand it the 512 badge rather than a 48 one.
    badge.save(web / "app/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])

    print(f"source                  {source} ({mark.width}x{mark.height} trimmed)")
    print(f"public/logo-mark.png    {width}x{MARK_HEIGHT}")
    print("public/logo-icon.png    512x512")
    print("app/icon.png            512x512")
    print("app/apple-icon.png      180x180")
    print("app/favicon.ico         16/32/48")
    print(f"\n<LogoMark> must declare width={width} height={MARK_HEIGHT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
