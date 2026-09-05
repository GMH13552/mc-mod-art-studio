#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_entity_margin.py — 通用实体 atlas 画布边距后处理。

把 64x32（或任意 WxH）atlas 内容向中心收缩 `--margin` 像素：
- 裁剪最外圈 `margin` px（如果内容贴边，则该边会产生 1px 透明边距）；
- 再居中粘贴到同等大小的透明画布上。

这样 creeper/pig 等实体贴图满足 `check_entity_uv.py` 的左右至少 1px 透明边距，
同时不改变内部布局/区域坐标；中心区域内容保持原绝对坐标。

用法：

    python3 fix_entity_margin.py tests/runs/v3/creeper/sprite.png \
        --out tests/runs/v4/creeper/sprite.png
    python3 fix_entity_margin.py --self-test
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


def fix_entity_margin(
    img: Image.Image,
    margin: int = 1,
) -> Image.Image:
    """返回新图：去掉最外圈 margin px 并居中粘贴到原尺寸透明画布。"""
    img = img.convert("RGBA")
    width, height = img.size
    if margin <= 0:  # 无操作或非法
        return img.copy()
    crop_w = max(1, width - 2 * margin)
    crop_h = max(1, height - 2 * margin)
    inner = img.crop((margin, margin, margin + crop_w, margin + crop_h))
    out = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    out.paste(inner, (margin, margin))
    return out


def _run_self_test() -> int:
    """自测：内容贴左右边 -> 修复后左右边距 >= 1，且区域非空。"""
    failures = 0
    lines: list[str] = []

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        status = "PASS" if cond else "FAIL"
        lines.append("[%s] %s%s" % (status, label, (" — " + detail) if detail else ""))
        if not cond:
            failures += 1

    import check_entity_uv as ck

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        img = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
        px = img.load()
        # 内容贴满左右、顶部、底部边缘，构成 creeper-like atlas
        for y in range(0, 32):
            px[0, y] = (100, 120, 60, 255)
            px[63, y] = (100, 120, 60, 255)
        for x in range(0, 64):
            px[x, 0] = (100, 120, 60, 255)
            px[x, 31] = (100, 120, 60, 255)
        # head/body/legs 非空（简单填块）
        for x in range(2, 30):
            for y in range(2, 14):
                px[x, y] = (100, 120, 60, 255)  # head
        for x in range(18, 38):
            for y in range(18, 30):
                px[x, y] = (100, 120, 60, 255)  # body
        for x in range(2, 14):
            for y in range(18, 24):
                px[x, y] = (100, 120, 60, 255)  # legs

        # 未修复时左右为 0
        before = ck._check_image_obj(img, "creeper", "<selftest>")
        check("before creeper margin FAIL", before["status"] == "FAIL", before["summary"])
        check("before left/right margin 0", before["margins"]["left"] == 0 and before["margins"]["right"] == 0,
              str(before["margins"]))

        fixed = fix_entity_margin(img, margin=1)
        fixed.save(d / "fixed.png")
        after = ck._check_image(d / "fixed.png", "creeper")
        check("after creeper margin PASS", after["status"] == "PASS", after["summary"])
        check("after left/right margin >=1", after["margins"]["left"] >= 1 and after["margins"]["right"] >= 1,
              str(after["margins"]))

    print("\n".join(lines))
    print("fix_entity_margin selftest: %s" % ("PASS" if failures == 0 else "FAIL (%d)" % failures))
    return 0 if failures == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inset entity UV atlas by N transparent pixels to satisfy canvas margin checks.",
    )
    parser.add_argument("png", nargs="?", help="input entity atlas PNG")
    parser.add_argument("--out", default=None, help="output PNG path")
    parser.add_argument("--margin", type=int, default=1, help="inset pixels (default 1)")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test()

    if not args.png or not args.out:
        parser.error("PNG path and --out are required")

    img = Image.open(args.png).convert("RGBA")
    fixed = fix_entity_margin(img, margin=args.margin)
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fixed.save(out_path, "PNG")
    print("Wrote %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
