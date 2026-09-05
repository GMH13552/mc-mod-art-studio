#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_bow.py — 通用物品像素图“细弧+弦”后处理（当前专门用于 16x16 bow）。

生成一张可辨的 Minecraft 风格弓：左侧细弧 + 右侧竖直弦线。
- 弧线为深木色（暗部/描边一体），弦线为浅灰白，便于在 16x16 中区分。
- 四周保留透明边距（bbox 不贴边），满足 check_pixel_asset 的 bbox/margins。
- 负空间充足（opaque_ratio 明显 < 0.5），符合“细长部件”通用检查。

用法：
    python3 fix_bow.py --out tests/runs/v4/bow/sprite.png
    python3 fix_bow.py --self-test
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow is required: pip install pillow") from exc

SIZE = 16
WOOD = (90, 60, 35, 255)
WOOD_LIGHT = (120, 80, 45, 255)
STRING = (220, 220, 180, 255)

# 细弧：从左到中，从 (9,1) 到 (4,7) 再到 (9,13)
ARC = [
    (9, 1),
    (8, 2),
    (7, 3),
    (6, 4),
    (5, 5),
    (4, 6),
    (4, 7),
    (4, 8),
    (5, 9),
    (6, 10),
    (7, 11),
    (8, 12),
    (9, 13),
]
# 弧线上少量亮色，制造材质层次但不破坏细长剪影。
HIGHLIGHT = {
    (8, 3),
    (5, 6),
    (5, 7),
    (5, 8),
    (8, 11),
}
# 弦线：从弓顶到弓底的竖直细线（与弧两端相接，整体可辨）。
STRING_PIXELS = [(9, y) for y in range(1, 14)]


def make_bow(size: int = SIZE) -> Image.Image:
    """生成 16x16 bow PNG（RGBA）。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    for x, y in ARC:
        px[x, y] = WOOD
    for x, y in HIGHLIGHT:
        px[x, y] = WOOD_LIGHT
    for x, y in STRING_PIXELS:
        px[x, y] = STRING
    return img


def _run_self_test() -> int:
    failures = 0
    lines: list[str] = []

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        status = "PASS" if cond else "FAIL"
        lines.append("[%s] %s%s" % (status, label, (" — " + detail) if detail else ""))
        if not cond:
            failures += 1

    import check_pixel_asset as cpa
    import argparse as ap

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        img = make_bow()
        path = d / "bow.png"
        img.save(path, "PNG")
        args = ap.Namespace(
            alpha_min=cpa.DEFAULT_ALPHA_MIN,
            opaque_min=cpa.DEFAULT_OPAQUE_MIN,
            expected_size="16x16",
            min_margin=cpa.DEFAULT_MIN_MARGIN,
            border_dark_lum=cpa.DEFAULT_BORDER_DARK_LUM,
            min_border_dark_ratio=cpa.DEFAULT_MIN_BORDER_DARK_RATIO,
            min_border_px=2,
            dark_lum=cpa.DEFAULT_DARK_LUM,
            bright_lum=cpa.DEFAULT_BRIGHT_LUM,
            min_bucket_px=cpa.DEFAULT_MIN_BUCKET_PX,
            min_main_px=cpa.DEFAULT_MIN_MAIN_PX,
            min_components=2,
            require_separation=False,
            require_thin_part=True,
        )
        data = cpa.analyze_png(path, args)
        check("pixel asset PASS", data["verdict"]["overall"] == "PASS", data["verdict"]["overall"])
        check("bbox margins all >=1", all(v >= 1 for v in data["metrics"]["margins"].values()),
              str(data["metrics"]["margins"]))
        check("thin part recognized", data["metrics"]["thin_part"] is True,
              "bbox=%s ratio=%s" % (data["metrics"]["bbox"], data["metrics"]["opaque_ratio"]))
        check("opaques enough", data["metrics"]["opaque_count"] >= cpa.DEFAULT_OPAQUE_MIN,
              str(data["metrics"]["opaque_count"]))

    print("\n".join(lines))
    print("fix_bow selftest: %s" % ("PASS" if failures == 0 else "FAIL (%d)" % failures))
    return 0 if failures == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a recognizable thin bow with arc+string.")
    parser.add_argument("--out", default="bow.png", help="output PNG path")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test()

    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    make_bow().save(out, "PNG")
    print("Wrote %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
