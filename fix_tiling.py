#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_tiling.py — 通用 block_multi 方块贴图 seam-stitch 后处理。

目标：在不大改图案的前提下，把三张 16x16 方块面修成可拼贴（check_tiling PASS）：
1. ``side_wrap``：side 左右两列强制一致（取原左右两列的平均值）。
2. ``top_side``：把 top 的四条外边重写为 side 顶行向量（形成一个环绕 ring）。
3. ``bottom_side``：把 bottom 的四条外边重写为 side 底行向量（同理）。

只用 1px 边缘重写，保持内部图案与整体语义不变；适用于 LLM 已生成“非空方块面
但边缘不连续”的产物。用法：

    python3 fix_tiling.py --top orig_top.png --side orig_side.png --bottom orig_bottom.png \
        --out-dir fixed/

自测：``python3 fix_tiling.py --self-test``
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


def _avg_color(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """RGBA 平均值（保持 alpha 最大不透明度）。"""
    return (
        (a[0] + b[0]) // 2,
        (a[1] + b[1]) // 2,
        (a[2] + b[2]) // 2,
        max(a[3], b[3]),
    )


def fix_tiling(
    top: Image.Image,
    side: Image.Image,
    bottom: Image.Image,
    ensure_opaque: bool = True,
) -> tuple[Image.Image, Image.Image, Image.Image]:
    """返回 (new_top, new_side, new_bottom)，不修改输入对象。"""
    top = top.convert("RGBA")
    side = side.convert("RGBA")
    bottom = bottom.convert("RGBA")
    if top.size != side.size or top.size != bottom.size:
        raise ValueError("top/side/bottom must have the same size; got %s/%s/%s" % (top.size, side.size, bottom.size))
    width, height = top.size

    # 1) side 左右两列一致（平均），保证 side_wrap PASS。
    side = side.copy()
    px = side.load()
    for y in range(height):
        left = px[0, y]
        right = px[width - 1, y]
        avg = _avg_color(left, right)
        px[0, y] = avg
        px[width - 1, y] = avg

    # 2/3) top/bottom 外边 ring 重写为 side 顶/底行向量。
    top = top.copy()
    bottom = bottom.copy()
    side_px = side.load()
    top_px = top.load()
    bottom_px = bottom.load()

    side_top_row = [side_px[x, 0] for x in range(width)]
    side_bottom_row = [side_px[x, height - 1] for x in range(width)]

    # top: 四边全部使用 side 顶行。
    for x in range(width):
        top_px[x, 0] = side_top_row[x]
        top_px[x, height - 1] = side_top_row[x]
    for y in range(height):
        top_px[0, y] = side_top_row[y]
        top_px[width - 1, y] = side_top_row[y]

    # bottom: 四边全部使用 side 底行。
    for x in range(width):
        bottom_px[x, 0] = side_bottom_row[x]
        bottom_px[x, height - 1] = side_bottom_row[x]
    for y in range(height):
        bottom_px[0, y] = side_bottom_row[y]
        bottom_px[width - 1, y] = side_bottom_row[y]

    if ensure_opaque:
        # 若是透明棋盘格/剪影残留，把透明度抬到 255（边缘接缝后必须是方块面）。
        for img in (top, side, bottom):
            p = img.load()
            for y in range(height):
                for x in range(width):
                    r, g, b, a = p[x, y]
                    if a < 128:
                        p[x, y] = (r, g, b, 255)

    return top, side, bottom


def _run_self_test() -> int:
    """合成方块面：原始 top 四边与 side 顶行不一致，修复后应 PASS。"""
    import json

    import check_tiling as ct

    failures = 0
    lines: list[str] = []

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        status = "PASS" if cond else "FAIL"
        lines.append("[%s] %s%s" % (status, label, (" — " + detail) if detail else ""))
        if not cond:
            failures += 1

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        # side: 左右不同、顶行与 top 外框不同
        side = Image.new("RGBA", (16, 16), (120, 80, 60, 255))
        sp = side.load()
        for y in range(16):
            sp[0, y] = (10, 10, 10, 255)
            sp[15, y] = (200, 200, 200, 255)
        # top: 外框统一深色，内部砖色
        top = Image.new("RGBA", (16, 16), (120, 80, 60, 255))
        tp = top.load()
        for x in range(16):
            tp[x, 0] = (10, 10, 10, 255)
            tp[x, 15] = (10, 10, 10, 255)
        for y in range(16):
            tp[0, y] = (10, 10, 10, 255)
            tp[15, y] = (10, 10, 10, 255)
        bottom = Image.new("RGBA", (16, 16), (120, 80, 60, 255))

        side.save(d / "side.png")
        top.save(d / "top.png")
        bottom.save(d / "bottom.png")
        result = ct.check_tiling(d / "top.png", d / "side.png", d / "bottom.png")
        check("pre-fix intentionally FAIL", result["status"] == "FAIL", result["status"])

        fixed_top, fixed_side, fixed_bottom = fix_tiling(top, side, bottom)
        fixed_top.save(d / "fix_top.png")
        fixed_side.save(d / "fix_side.png")
        fixed_bottom.save(d / "fix_bottom.png")
        r = ct.check_tiling(d / "fix_top.png", d / "fix_side.png", d / "fix_bottom.png")
        check("post-fix tiling PASS", r["status"] == "PASS", r["status"])

        # JSON 可序列化
        json.dumps(r, ensure_ascii=False)

    print("\n".join(lines))
    print("fix_tiling selftest: %s" % ("PASS" if failures == 0 else "FAIL (%d)" % failures))
    return 0 if failures == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Post-process block_multi top/side/bottom edges so check_tiling passes.",
    )
    parser.add_argument("--top", help="input top PNG")
    parser.add_argument("--side", help="input side PNG")
    parser.add_argument("--bottom", help="input bottom PNG")
    parser.add_argument("--out-dir", default=None, help="write fixed *_top.png/_side.png/_bottom.png into this dir")
    parser.add_argument("--prefix", default="fixed", help="output filename prefix (default: fixed)")
    parser.add_argument("--self-test", action="store_true", help="run synthetic self-test")
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test()

    if not (args.top and args.side and args.bottom):
        parser.error("--top, --side, --bottom required")

    top = Image.open(args.top).convert("RGBA")
    side = Image.open(args.side).convert("RGBA")
    bottom = Image.open(args.bottom).convert("RGBA")
    fixed_top, fixed_side, fixed_bottom = fix_tiling(top, side, bottom)

    out_dir = Path(args.out_dir or ".").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    top_out = out_dir / ("%s_top.png" % args.prefix)
    side_out = out_dir / ("%s_side.png" % args.prefix)
    bottom_out = out_dir / ("%s_bottom.png" % args.prefix)
    fixed_top.save(top_out, "PNG")
    fixed_side.save(side_out, "PNG")
    fixed_bottom.save(bottom_out, "PNG")
    print("Wrote %s" % top_out)
    print("Wrote %s" % side_out)
    print("Wrote %s" % bottom_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
