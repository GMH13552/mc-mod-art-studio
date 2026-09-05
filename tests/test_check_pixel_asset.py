#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_check_pixel_asset.py

对 check_pixel_asset.py 的通用像素检查逻辑做单元测试。
运行:
    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

import check_pixel_asset as cpa  # noqa: E402


def _args(**overrides) -> argparse.Namespace:
    base = dict(
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
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def _synthetic_two_part_image() -> Image.Image:
    """16x16 合成资产：主体带深色描边、亮色高光、主色；另有独立小块。"""
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    px = img.load()
    # 主体 (3,3)-(8,8)
    for y in range(3, 9):
        for x in range(3, 9):
            if x in (3, 8) or y in (3, 8):
                px[x, y] = (20, 20, 20, 255)
            elif x in (4, 7) and y in (4, 7):
                px[x, y] = (240, 240, 200, 255)
            else:
                px[x, y] = (120, 80, 60, 255)
    # 独立小块 (11,11)-(12,12)
    for y in (11, 12):
        for x in (11, 12):
            px[x, y] = (40, 40, 60, 255)
    return img


class TestCheckPixelAsset(unittest.TestCase):
    def test_synthetic_good_asset(self) -> None:
        img = _synthetic_two_part_image()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "good.png"
            img.save(path)
            data = cpa.analyze_png(path, _args(require_separation=True))
        self.assertGreaterEqual(data["metrics"]["opaque_count"], 20)
        self.assertTrue(data["metrics"]["size_ok"])
        self.assertTrue(data["metrics"]["bbox_ok"])
        self.assertTrue(data["metrics"]["border_ok"])
        self.assertTrue(data["metrics"]["palette_ok"])
        self.assertEqual(data["metrics"]["component_count"], 2)
        self.assertTrue(data["metrics"]["part_separation"])
        self.assertGreater(data["metrics"]["opaque_ratio"], 0.0)
        self.assertLess(data["metrics"]["opaque_ratio"], 1.0)
        self.assertEqual(data["verdict"]["overall"], "PASS")

    def test_require_separation_off_reports_only(self) -> None:
        img = _synthetic_two_part_image()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "part.png"
            img.save(path)
            data = cpa.analyze_png(path, _args(require_separation=False))
        self.assertIsNone(data["metrics"]["separation_ok"])
        self.assertTrue(data["metrics"]["part_separation"])
        self.assertEqual(data["verdict"]["overall"], "PASS")

    def test_empty_image_fails(self) -> None:
        img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "empty.png"
            img.save(path)
            data = cpa.analyze_png(path, _args(require_separation=True))
        self.assertEqual(data["metrics"]["opaque_count"], 0)
        self.assertEqual(data["metrics"]["opaque_ratio"], 0.0)
        self.assertEqual(data["verdict"]["overall"], "FAIL")

    def test_bbox_touching_edge_fails(self) -> None:
        img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        px = img.load()
        for x in range(2, 14):
            px[x, 0] = (100, 100, 100, 255)  # 顶部 touches edge
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "touching.png"
            img.save(path)
            data = cpa.analyze_png(path, _args(require_separation=False))
        self.assertFalse(data["metrics"]["bbox_ok"])
        self.assertEqual(data["verdict"]["overall"], "FAIL")

    def test_remove_separation_requirement_fails(self) -> None:
        img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        px = img.load()
        # 单连通、非贴边、有暗色/亮色/主色的方块
        for y in range(4, 12):
            for x in range(4, 12):
                if x in (4, 11) or y in (4, 11):
                    px[x, y] = (20, 20, 20, 255)
                elif x in (6, 9) and y in (6, 9):
                    px[x, y] = (230, 230, 200, 255)
                else:
                    px[x, y] = (120, 80, 60, 255)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "single.png"
            img.save(path)
            data = cpa.analyze_png(path, _args(require_separation=True, min_components=2))
        self.assertEqual(data["metrics"]["component_count"], 1)
        self.assertFalse(data["metrics"]["part_separation"])
        self.assertEqual(data["verdict"]["overall"], "FAIL")

    def test_md_and_json_renderers(self) -> None:
        img = _synthetic_two_part_image()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "good.png"
            img.save(path)
            data = cpa.analyze_png(path, _args(require_separation=True))
        self.assertIn("Pixel Asset Check Evidence", cpa.render_markdown(data))
        self.assertIn("PASS", cpa.render_console(data))
        # JSON serializable
        import json
        json.dumps(data, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
