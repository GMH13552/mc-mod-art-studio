#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reference_analyzer.py — 原版参考“语法化”分析器。

把 asset_to_text.py --mode compact --no-header 的原版 compact 文本，
提炼成可借鉴、不可逐像素复制的结构化语法特征：

- `palette_family`：主/亮/暗/描边 的均值与范围（不是具体格子）
- `material_signature`：木质/石/金属/发光/软质 等材质 token
- `structure_hints`：细长/弧形/对称/部件数 等结构提示
- `uv_regions`：实体 UV 区域坐标（供 entity_uv 使用）

并生成带有“借鉴但不照抄：形状/纹理/配色可按需要修改”标注的 prompt 文本段。
"""

from __future__ import annotations

import re
import statistics
from typing import Any, Iterable

# 彩色 hex -> RGB
_HEX_RE = re.compile(r"^\s*(\d+)\s*:\s*(#[0-9a-fA-F]{6})")

# 材质启发式阈值
_BROWN_HUES = (15.0, 55.0)
_GRAY_SAT_MAX = 0.22
_WOOD_LUM_RANGE = (0.10, 0.65)
_METAL_LUM_MIN = 0.55
_GLOW_LUM_MIN = 0.82
_GLOW_SAT_MIN = 0.75
_SOFT_LUM_MIN = 0.75
_SOFT_SAT_MAX = 0.35


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _rgb_to_hsl(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = (v / 255.0 for v in rgb)
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2.0
    if mx == mn:
        return 0.0, 0.0, l
    d = mx - mn
    s = d / (2.0 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = ((g - b) / d + (6.0 if g < b else 0.0)) % 6.0
    elif mx == g:
        h = ((b - r) / d + 2.0) / 6.0
    else:
        h = ((r - g) / d + 4.0) / 6.0
    return h * 360.0, s, l


def _luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = (v / 255.0 for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _parse_palette(compact_text: str) -> list[dict[str, Any]]:
    """解析 ``## Palette (hex)`` 块，返回 [{hex, rgb, lum, sat}...]。"""
    colors: list[dict[str, Any]] = []
    in_fence = False
    section = False
    for line in compact_text.splitlines():
        if line.startswith("## Palette (hex"):
            section = True
            continue
        if section and line.strip() == "```":
            in_fence = not in_fence
            continue
        if not section or not in_fence:
            continue
        m = _HEX_RE.match(line)
        if m:
            hex_str = m.group(2).upper()
            rgb = _hex_to_rgb(hex_str)
            colors.append({
                "hex": hex_str,
                "rgb": rgb,
                "lum": _luminance(rgb),
                "sat": _rgb_to_hsl(rgb)[1],
            })
    return colors


def _parse_silhouette(compact_text: str) -> list[str] | None:
    """解析 ``## Silhouette`` 的 X/. 网格行。"""
    rows: list[str] = []
    in_fence = False
    section = False
    for line in compact_text.splitlines():
        if line.startswith("## Silhouette"):
            section = True
            continue
        if section and line.strip() == "```":
            in_fence = not in_fence
            continue
        if not section or not in_fence:
            continue
        s = line.strip()
        if s and set(s) <= {"X", ".", "x"}:
            rows.append(s)
    return rows or None


def _palette_family(colors: list[dict[str, Any]]) -> dict[str, Any]:
    """统计主/亮/暗/描边与整体明度/饱和度范围。"""
    if not colors:
        return {
            "count": 0,
            "main": None,
            "light": None,
            "dark": None,
            "outline": None,
            "mean": {"luminance": 0.0, "saturation": 0.0},
            "range": {"luminance": [0.0, 0.0], "saturation": [0.0, 0.0]},
            "summary": "（无调色板）",
        }

    by_lum = sorted(colors, key=lambda c: c["lum"])
    dark = by_lum[0]
    light = by_lum[-1]
    # “主色”取明度中位数附近的颜色；若数量少，取中间调。
    median_lum = statistics.median([c["lum"] for c in colors])
    main = min(colors, key=lambda c: abs(c["lum"] - median_lum))
    # “描边色”取最暗 / 接近最暗且饱和度不高的颜色。
    outline = min(by_lum[: max(1, len(by_lum) // 3)], key=lambda c: c["lum"] + (0.15 * c["sat"]))
    lums = [c["lum"] for c in colors]
    sats = [c["sat"] for c in colors]

    def _fmt(c: dict[str, Any] | None) -> str:
        if not c:
            return "-"
        return "%s (L=%.2f)" % (c["hex"], c["lum"])

    summary = "主色=%s；亮色=%s；暗色=%s；描边=%s；明度均值=%.2f 范围=%.2f~%.2f；饱和度均值=%.2f 范围=%.2f~%.2f" % (
        _fmt(main), _fmt(light), _fmt(dark), _fmt(outline),
        sum(lums) / len(lums), min(lums), max(lums),
        sum(sats) / len(sats), min(sats), max(sats),
    )
    return {
        "count": len(colors),
        "main": main,
        "light": light,
        "dark": dark,
        "outline": outline,
        "mean": {
            "luminance": sum(lums) / len(lums),
            "saturation": sum(sats) / len(sats),
        },
        "range": {
            "luminance": [min(lums), max(lums)],
            "saturation": [min(sats), max(sats)],
        },
        "summary": summary,
    }


def _material_signature(colors: list[dict[str, Any]]) -> dict[str, Any]:
    """根据调色板统计推断 木质/石/金属/发光/软质 材质 token。"""
    if not colors:
        return {"tokens": [], "summary": "（无调色板，无法推断材质）"}

    def _is_brown(c: dict[str, Any]) -> bool:
        h = _rgb_to_hsl(c["rgb"])[0]
        l = c["lum"]
        s = c["sat"]
        return _BROWN_HUES[0] <= h <= _BROWN_HUES[1] and s > 0.25 and _WOOD_LUM_RANGE[0] <= l <= _WOOD_LUM_RANGE[1]

    def _is_gray(c: dict[str, Any]) -> bool:
        return c["sat"] < _GRAY_SAT_MAX

    brown_count = sum(1 for c in colors if _is_brown(c))
    gray_count = sum(1 for c in colors if _is_gray(c))
    max_lum = max(c["lum"] for c in colors)
    max_sat = max(c["sat"] for c in colors)
    bright_count = sum(1 for c in colors if c["lum"] > _GLOW_LUM_MIN)
    soft_count = sum(1 for c in colors if c["lum"] > _SOFT_LUM_MIN and c["sat"] < _SOFT_SAT_MAX)

    tokens: list[str] = []
    if brown_count >= max(2, len(colors) // 4):
        tokens.append("木质")
    if gray_count >= max(2, len(colors) // 4):
        if max_lum >= _METAL_LUM_MIN:
            tokens.append("金属")
        tokens.append("石")
    if bright_count >= 1 or (max_lum > _GLOW_LUM_MIN and max_sat > _GLOW_SAT_MIN):
        tokens.append("发光")
    if soft_count >= max(1, len(colors) // 3):
        tokens.append("软质")
    if not tokens:
        tokens.append("中性")

    return {
        "tokens": tokens,
        "summary": "、".join(tokens),
    }


def _connected_components(rows: list[str]) -> int:
    """计算 silhouette 的 4-连通部件数量。"""
    if not rows:
        return 0
    h, w = len(rows), len(rows[0]) if rows else 0
    if h == 0 or w == 0:
        return 0
    visited = [[False] * w for _ in range(h)]
    count = 0
    for y in range(h):
        for x in range(w):
            if rows[y][x] in ("X", "x") and not visited[y][x]:
                count += 1
                stack = [(y, x)]
                visited[y][x] = True
                while stack:
                    cy, cx = stack.pop()
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and rows[ny][nx] in ("X", "x") and not visited[ny][nx]:
                            visited[ny][nx] = True
                            stack.append((ny, nx))
    return count


def _structure_hints(rows: list[str] | None) -> dict[str, Any]:
    """从 silhouette 提取 细长/弧形/对称/部件数 结构提示。"""
    if not rows or not rows[0]:
        return {
            "hints": [],
            "part_count": 0,
            "aspect_ratio": 0.0,
            "symmetric": False,
            "summary": "（无剪影，无法推断结构）",
        }

    h, w = len(rows), len(rows[0])
    coords = [(x, y) for y, row in enumerate(rows) for x, ch in enumerate(row) if ch in ("X", "x")]
    if not coords:
        return {
            "hints": [],
            "part_count": 0,
            "aspect_ratio": 0.0,
            "symmetric": False,
            "summary": "（空剪影）",
        }

    min_x = min(x for x, _ in coords)
    max_x = max(x for x, _ in coords)
    min_y = min(y for _, y in coords)
    max_y = max(y for _, y in coords)
    bbox_w = max(1, max_x - min_x + 1)
    bbox_h = max(1, max_y - min_y + 1)
    aspect = bbox_w / bbox_h

    # 水平对称：比较每行与反转行（允许错位 1 像素）
    total = 0
    match = 0
    for row in rows:
        rev = row[::-1]
        for a, b in zip(row, rev):
            if a in ("X", "x") or b in ("X", "x"):
                total += 1
                if a == b:
                    match += 1
    sym_score = (match / total) if total else 1.0

    parts = _connected_components(rows)
    hints: list[str] = []
    if aspect >= 1.6:
        hints.append("细长")
    elif aspect <= 0.6:
        hints.append("竖向细长")

    # 非矩形且 bbox 有多个宽度变化 -> 弧形/曲线
    row_widths = []
    for row in rows:
        xs = [i for i, ch in enumerate(row) if ch in ("X", "x")]
        row_widths.append((max(xs) - min(xs) + 1) if xs else 0)
    nonempty_widths = [v for v in row_widths if v > 0]
    if nonempty_widths and (max(nonempty_widths) - min(nonempty_widths)) > max(1, min(nonempty_widths) * 0.35):
        hints.append("弧形/曲线")

    if sym_score >= 0.85:
        hints.append("对称")

    if parts >= 2:
        hints.append("多部件(%d)" % parts)
    else:
        hints.append("单件")

    return {
        "hints": hints,
        "part_count": parts,
        "aspect_ratio": round(aspect, 2),
        "symmetric": sym_score >= 0.85,
        "summary": "；".join(hints),
    }


def _uv_regions(uv_region: dict[str, Any] | None, form: str) -> dict[str, Any]:
    """把实体 UV 区域规范化为提示结构。"""
    if not uv_region or form != "entity_uv":
        return {"regions": {}, "summary": "（非实体 UV 形式，无区域）"}
    regions = {k: [int(v) for v in box] for k, box in uv_region.items() if isinstance(box, (tuple, list)) and len(box) == 4}
    summary = "；".join("%s=%s" % (k, ",".join(map(str, v))) for k, v in regions.items())
    return {"regions": regions, "summary": summary or "（无区域）"}


def analyze_compact(
    compact_text: str,
    form: str = "item",
    uv_region: dict[str, Any] | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """把一份原版 compact 文本提炼成结构化语法 dict。"""
    colors = _parse_palette(compact_text)
    rows = _parse_silhouette(compact_text)
    return {
        "source": name or "compact",
        "form": form,
        "palette_family": _palette_family(colors),
        "material_signature": _material_signature(colors),
        "structure_hints": _structure_hints(rows),
        "uv_regions": _uv_regions(uv_region, form),
    }


def _render_analysis(analysis: dict[str, Any]) -> list[str]:
    """把单个 analysis 渲染成几行紧凑的“参考语法”。"""
    lines: list[str] = []
    name = analysis.get("source") or "参考锚点"
    lines.append("### 参考语法：%s" % name)
    if analysis.get("category") or analysis.get("role") or analysis.get("size"):
        details = []
        if analysis.get("category"):
            details.append("类别=%s" % analysis["category"])
        if analysis.get("role"):
            details.append("role=%s" % analysis["role"])
        if analysis.get("size"):
            details.append("尺寸=%s" % analysis["size"])
        lines.append("- 来源信息：%s" % "；".join(details))
    if analysis.get("path"):
        lines.append("- 原版路径：%s" % analysis["path"])
    pf = analysis.get("palette_family") or {}
    lines.append("- 配色家族：%s" % pf.get("summary", "-"))
    ms = analysis.get("material_signature") or {}
    lines.append("- 材质签名：%s" % ms.get("summary", "-"))
    sh = analysis.get("structure_hints") or {}
    lines.append("- 结构提示：%s" % sh.get("summary", "-"))
    uv = analysis.get("uv_regions") or {}
    lines.append("- UV 区域：%s" % uv.get("summary", "-"))
    lines.append("")
    return lines


def _normalize_compact_items(compact_text: Any) -> list[tuple[str, str]]:
    """把 compact_text 参数规范为 [(name, text), ...]，最多保留前 2 个由调用方控制。"""
    if compact_text is None:
        return []
    if isinstance(compact_text, str):
        return [("compact", compact_text)]
    if isinstance(compact_text, dict):
        # 支持 {name: text}
        return [(str(k), str(v)) for k, v in compact_text.items()]
    items: list[tuple[str, str]] = []
    for item in compact_text:
        if isinstance(item, (tuple, list)) and len(item) == 2:
            items.append((str(item[0]), str(item[1])))
        elif isinstance(item, dict) and "compact_text" in item:
            items.append((str(item.get("name", "compact")), str(item["compact_text"])))
        else:
            items.append(("compact", str(item)))
    return items


def render_reference_block(
    analysis: dict[str, Any] | list[dict[str, Any]],
    compact_text: str | list[Any] | dict[str, str] | None = None,
    include_compact: bool = False,
    max_compact: int = 2,
) -> str:
    """生成 prompt 中的“原版参考”文本段。

    第一段是结构化“参考语法”摘要；
    当 ``include_compact=True`` 时，附上最多 ``max_compact`` 个 compact 片段，
    并标注“仅供质感参考，禁止逐像素复制；形状/纹理/配色可按需要修改”。
    """
    if isinstance(analysis, dict):
        analyses = [analysis]
    else:
        analyses = list(analysis or [])

    lines: list[str] = []
    lines.append("## 原版参考（结构化语法 + 少量片段）")
    lines.append("> 借鉴但不照抄：形状/纹理/配色可按需要修改。")
    lines.append("> 禁止逐像素复制；只学习以下配色家族/材质签名/结构hint/UV 区域等“参考语法”。")
    lines.append("")
    for a in analyses:
        lines.extend(_render_analysis(a))

    if include_compact and max_compact > 0:
        snippets = _normalize_compact_items(compact_text)
        snippets = snippets[:max_compact]
        if snippets:
            lines.append("### 原版参考片段（仅供质感参考，禁止逐像素复制；形状/纹理/配色可按需要修改）")
            lines.append("> 下面是 1-%d 个原版 compact 片段，不是输出样例；只用于感知材质节奏/区域占位，禁止逐像素复制。" % max_compact)
            lines.append("")
            for i, (name, text) in enumerate(snippets, 1):
                lines.append("**片段 %d：%s**" % (i, name))
                lines.append("~~~")
                lines.append(text)
                lines.append("~~~")
                lines.append("")
    return "\n".join(lines).strip()


def decide_reference_include(novelty: float) -> tuple[bool, int]:
    """根据 novelty 决定是否附带 compact 片段以及最多几个。

    - novelty < 0.6：附 2 个（最贴近原版）
    - 0.6 <= novelty < 0.85：附 1 个（中等自由）
    - novelty >= 0.85：不附片段，只保留结构化语法
    """
    n = max(0.0, min(1.0, float(novelty)))
    if n >= 0.85:
        return False, 0
    if n >= 0.6:
        return True, 1
    return True, 2


if __name__ == "__main__":
    # 简易自测：构造一段合成 compact，验证基本输出。
    sample = """## Silhouette (X=opaque, .=transparent)
```
................
.........X......
........XX......
.........X......
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
    analysis = analyze_compact(sample, form="item", name="apple")
    print(analysis["palette_family"]["summary"])
    print(analysis["material_signature"]["summary"])
    print(analysis["structure_hints"]["summary"])
    print(render_reference_block(analysis, include_compact=True)[:400])
