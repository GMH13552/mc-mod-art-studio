#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_reference_analyzer.py

对 reference_analyzer.py 的结构化提炼与参考块渲染做单元测试。
不需访问原版库：使用内嵌 compact 文本样例。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import reference_analyzer as ra  # noqa: E402

SAMPLE_COMPACT = """## Silhouette (X=opaque, .=transparent)
```
................
.........X......
........XX......
........X.......
.....XXXXXX.....
...XXXXXXXXXX...
..XXXXXXXXXXXX..
..XXXXXXXXXXXX..
..XXXXXXXXXXXX..
..XXXXXXXXXXXX..
..XXXXXXXXXXXX..
...XXXXXXXXXX...
...XXXXXXXXXX...
....XXXXXXXX....
.....XXXXXX.....
................
```
## ASCII color map
Legend: . transparent | # near-black | + dark-gray | = light-gray | @ white | R red | O orange/brown | Y yellow | G green | C cyan | B blue | M magenta | P pink
```
................
.........O......
........OO......
........O.......
.....RROOOO.....
...RRRRORRROO...
..RRRRRRRRRROO..
..RRRRRRRRRRRO..
..RRRRRRRRRRRR..
..ORRRRRRRRRRR..
..ORRRRRRRRRRR..
...ORRRRRRRRR...
...ORRRRRRRRR...
....RRRRRRRR....
.....ROOORR.....
................
```
## Palette (hex)
```
 0: #752802
 1: #7e370e
 2: #542409
 3: #9c1017
 4: #b4131e
 5: #ff969d
 6: #dd1725
 7: #ff1c2b
 8: #ff5e69
 9: #54090e
```
## Index grid (-1 = transparent)
```
-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1 -1 -1  0 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1 -1  1  2 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1 -1  0 -1 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1  3  3  0  2  0  0 -1 -1 -1 -1 -1
-1 -1 -1  3  4  5  4  2  3  6  4  0  0 -1 -1 -1
-1 -1  3  4  7  8  5  5  5  8  7  4  0  0 -1 -1
-1 -1  3  4  7  7  7  7  7  7  6  7  4  0 -1 -1
-1 -1  3  4  6  7  6  7  6  6  6  7  6  9 -1 -1
-1 -1  0  4  4  6  6  4  4  6  4  7  6  9 -1 -1
-1 -1  0  4  4  4  4  4  6  4  4  7  4  9 -1 -1
-1 -1 -1  0  4  4  6  4  4  4  6  4  9 -1 -1 -1
-1 -1 -1  0  3  4  4  4  6  6  4  3  9 -1 -1 -1
-1 -1 -1 -1  9  3  4  3  3  4  3  9 -1 -1 -1 -1
-1 -1 -1 -1 -1  9  0  0  0  9  9 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1
```
"""


class TestReferenceAnalyzer(unittest.TestCase):
    def test_analyze_compact_has_core_fields(self) -> None:
        analysis = ra.analyze_compact(SAMPLE_COMPACT, form="item", name="apple")
        self.assertIn("palette_family", analysis)
        self.assertIn("material_signature", analysis)
        self.assertIn("structure_hints", analysis)
        self.assertIn("uv_regions", analysis)
        self.assertEqual(analysis["palette_family"]["count"], 10)
        self.assertGreater(len(analysis["structure_hints"]["hints"]), 0)

    def test_render_block_contains_borrow_but_no_copy(self) -> None:
        analysis = ra.analyze_compact(SAMPLE_COMPACT, form="item", name="apple")
        block = ra.render_reference_block(
            analysis, compact_text=[("apple", SAMPLE_COMPACT)], include_compact=True
        )
        self.assertIn("借鉴但不照抄", block)
        self.assertIn("禁止逐像素复制", block)
        self.assertIn("参考语法：apple", block)
        self.assertIn("原版参考片段", block)
        self.assertIn("## Palette (hex)", block)

    def test_no_compact_when_include_false(self) -> None:
        analysis = ra.analyze_compact(SAMPLE_COMPACT, form="item", name="apple")
        block = ra.render_reference_block(analysis, include_compact=False)
        self.assertNotIn("原版参考片段", block)
        self.assertIn("参考语法", block)

    def test_decide_reference_include(self) -> None:
        self.assertEqual(ra.decide_reference_include(0.0), (True, 2))
        self.assertEqual(ra.decide_reference_include(0.5), (True, 2))
        self.assertEqual(ra.decide_reference_include(0.7), (True, 1))
        self.assertEqual(ra.decide_reference_include(0.9), (False, 0))


if __name__ == "__main__":
    unittest.main()
