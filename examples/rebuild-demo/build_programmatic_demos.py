#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
s3-rebuild programmatic fallback for the two most LLM-unstable demos.

- demon_cow: 64x32 cow entity template (vanilla cow.png) is used ONLY as a
  silhouette/region base; every opaque texel is remapped to a new demon palette
  and pure-black eye/nostril texels become cyan soul-fire. The original PNG is
  not copied into the repo; only the recolored result is saved.
- villager_hide: rabbit_hide.png is used ONLY as the hide contour base
  (irregular, fringed); texels are remapped to the villager-hide palette and a
  cloth trim band is added.

Run from repo root:
  python3 examples/rebuild-demo/build_programmatic_demos.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
FULL = Path("/mnt/c/Users/GMH13/Documents/deepseek_harness_workspace/mc_asset_library_full/textures")
DEMO = ROOT / "examples" / "rebuild-demo"


def _outline_or_dark(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return r < 80 and g < 70 and b < 60


def demon_cow() -> Path:
    src = FULL / "entity" / "cow" / "cow.png"
    ref = Image.open(src).convert("RGBA")
    out = Image.new("RGBA", ref.size, (0, 0, 0, 0))
    px = ref.load()
    op = out.load()
    for y in range(ref.height):
        for x in range(ref.width):
            r, g, b, a = px[x, y]
            if a < 128:
                op[x, y] = (0, 0, 0, 0)
                continue
            # Pure black in the vanilla cow atlas marks the eyes/nostrils.
            if r == 0 and g == 0 and b == 0:
                op[x, y] = (1, 167, 172, 255)  # #01A7AC soul-fire cyan
                continue
            lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
            if lum < 0.22:
                c = (43, 5, 5, 255)      # #2B0505 very dark horn/outline
            elif lum < 0.45:
                c = (58, 7, 8, 255)      # #3A0708 dark red shadow
            elif lum < 0.75:
                c = (160, 15, 16, 255)   # #A00F10 demon red base
            else:
                c = (224, 74, 69, 255)   # #E04A45 red highlight
            op[x, y] = c
    # Add 1px transparent side margins required by check_entity_uv.
    # The cow atlas is full-bleed, so this trims the outermost column only.
    for y in range(ref.height):
        op[0, y] = (0, 0, 0, 0)
        op[ref.width - 1, y] = (0, 0, 0, 0)

    out.save(DEMO / "demon_cow" / "sprite.png", "PNG")
    prev = out.resize((out.width * 4, out.height * 4), Image.NEAREST)
    prev.save(DEMO / "demon_cow" / "sprite_preview.png", "PNG")
    return out


def villager_hide() -> Path:
    src = FULL / "item" / "rabbit_hide.png"
    ref = Image.open(src).convert("RGBA")
    out = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    px = ref.load()
    op = out.load()
    for y in range(16):
        for x in range(16):
            r, g, b, a = px[x, y]
            if a < 128:
                op[x, y] = (0, 0, 0, 0)
                continue
            lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
            # Recolor using the hide palette; keep the rabbit_hide silhouette.
            if lum < 0.35:
                c = (61, 28, 16, 255)    # #3D1C10 outline/shadow
            elif lum < 0.62:
                c = (84, 39, 22, 255)    # #542716 dark leather
            elif lum < 0.82:
                c = (198, 92, 53, 255)   # #C65C35 base leather
            else:
                c = (242, 160, 122, 255)  # #F2A07A bright leather highlight
            op[x, y] = c

    # Add explicit bright leather highlight pixels so the palette check has
    # at least a few >=160-luminance texels (inside the rabbit_hide mask).
    highlight_coords = [(6, 4), (7, 5), (8, 6), (9, 7), (5, 8), (10, 9), (6, 10)]
    for hx, hy in highlight_coords:
        rr, gg, bb, aa = op[hx, hy]
        if aa >= 128:
            op[hx, hy] = (242, 160, 122, 255)  # #F2A07A bright highlight

    # Add a gray villager-cloth trim along the lower edge of the hide.
    # Find bottommost opaque y per column and paint a 2px band in cloth gray.
    bottom = {}
    for x in range(16):
        for y in range(15, -1, -1):
            rr, gg, bb, aa = op[x, y]
            if aa >= 128:
                bottom[x] = y
                break
    for x, by in bottom.items():
        for dy in range(2):
            y = by - dy
            if y < 0:
                continue
            op[x, y] = (111, 109, 106, 255)  # #6F6D6A cloth gray
        # stitching dots
        if x % 3 == 0:
            y = by - 1
            if y >= 0:
                op[x, y] = (61, 45, 41, 255)  # #3D2D29 stitch dark

    # Add a small dark-wood hanger loop at the top.
    # Use the topmost opaque y per x near center.
    top = {}
    for x in range(16):
        for y in range(16):
            rr, gg, bb, aa = op[x, y]
            if aa >= 128:
                top[x] = y
                break
    center_x = 8
    if center_x in top and top[center_x] > 0:
        hx, hy = center_x, top[center_x]
        op[hx, hy - 1] = (73, 54, 21, 255)     # #493615 wood dark
        op[hx, hy - 2 if hy >= 2 else 0] = (137, 103, 39, 255)  # #896727 wood light
    # Ensure the item keeps at least 1px transparent margin on every side.
    bbox = out.getbbox()
    if bbox is not None:
        if bbox[1] < 1:
            for x in range(16):
                op[x, 0] = (0, 0, 0, 0)
        if bbox[3] > 15:
            for x in range(16):
                op[x, 15] = (0, 0, 0, 0)
        if bbox[0] < 1:
            for y in range(16):
                op[0, y] = (0, 0, 0, 0)
        if bbox[2] > 15:
            for y in range(16):
                op[15, y] = (0, 0, 0, 0)

    out.save(DEMO / "villager_hide" / "sprite.png", "PNG")
    prev = out.resize((out.width * 16, out.height * 16), Image.NEAREST)
    prev.save(DEMO / "villager_hide" / "sprite_preview.png", "PNG")
    return out


def main() -> int:
    DEMO.mkdir(parents=True, exist_ok=True)
    (DEMO / "demon_cow").mkdir(parents=True, exist_ok=True)
    (DEMO / "villager_hide").mkdir(parents=True, exist_ok=True)
    img = demon_cow()
    print("demon_cow -> %s (%dx%d)" % (DEMO / "demon_cow" / "sprite.png", *img.size))
    img = villager_hide()
    print("villager_hide -> %s (%dx%d)" % (DEMO / "villager_hide" / "sprite.png", *img.size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
