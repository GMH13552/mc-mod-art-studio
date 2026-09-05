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
import sys
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
    fragment = _crop_silhouette_fragment(rows) if rows else None
    silhouette_candidates = []
    if fragment:
        silhouette_candidates.append({
            "token": "compact:%s" % (name or "compact"),
            "source": name or "compact",
            "kind": "compact_fragment",
            "fragment": fragment,
            "note": "只含 X/. 剪影；整体轮廓基础（非 Palette/Index grid）",
        })
    return {
        "source": name or "compact",
        "form": form,
        "palette_family": _palette_family(colors),
        "material_signature": _material_signature(colors),
        "structure_hints": _structure_hints(rows),
        "uv_regions": _uv_regions(uv_region, form),
        "silhouette": rows or [],
        "silhouette_candidates": silhouette_candidates,
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


# ---------------------------------------------------------------------------
# silhouette bank：把“形状借鉴”变成可挑选、可组合、可大改的候选菜单
# ---------------------------------------------------------------------------

# 中文部件 -> 可能相关的原版锚点英文名
_ZH_SOURCE_MAP: dict[str, tuple[str, ...]] = {
    "牛": ("cow", "mooshroom"),
    "猪": ("pig",),
    "骷髅": ("skeleton",),
    "骨": ("skeleton", "bone"),
    "杖": ("staff", "rod", "wand", "blaze_rod", "stick"),
    "柄": ("handle", "staff", "stick", "rod", "sword"),
    "刀": ("sword", "shears", "knife"),
    "刃": ("sword", "shears", "blade"),
    "皮": ("leather", "hide", "villager"),
    "菌": ("mushroom", "mooshroom"),
    "菇": ("mushroom", "mooshroom"),
    "角": ("cow", "goat", "mooshroom"),
    "耳": ("cow", "mooshroom", "villager"),
    "鼻": ("cow", "mooshroom", "pig"),
}

# 部件中的英文关键词 -> 锚点英文名（用于直接匹配）
_PART_EN_HINTS = (
    "head", "skull", "bone", "horn", "muzzle", "snout", "ear", "leg",
    "blade", "sword", "shears", "handle", "shaft", "staff", "stick",
    "rod", "wand", "hide", "leather", "cap", "mushroom", "eye", "soul",
)

# 部件 -> 2-4 个通用 shape token（不绑定某一张原版）
_SHAPE_TOKEN_HINTS: list[tuple[tuple[str, ...], tuple[tuple[str, str], ...]]] = [
    (("骷髅", "skull", "颅", "骨"), (
        ("skull-round", "圆/方骨白头骨；眼窝+下颌暗部，适合杖顶/头饰"),
        ("skull-flat", "扁平骨白颅骨；适合小幅杖顶"),
    )),
    (("角", "horn"), (
        ("horn-split", "分叉角；顶部向外/向上分叉"),
        ("horn-curved", "弯角；向后/下弯曲"),
        ("horn-short", "短角；适合牛头/恶魔角"),
    )),
    (("鼻", "muzzle", "snout"), (
        ("muzzle-block", "方形鼻口；宽而直的鼻端"),
        ("muzzle-rounded", "圆形鼻口；钝圆鼻端"),
    )),
    (("头", "head"), (
        ("round-head", "圆头轮廓；正面/侧面均可用"),
        ("square-head", "方头轮廓；原版方块式头部"),
    )),
    (("耳", "ear"), (
        ("ear-side", "侧耳；紧贴头两侧"),
        ("ear-pointed", "尖耳；向外/上尖出"),
    )),
    (("腿", "leg"), (
        ("leg-straight", "直立腿柱；四足基础"),
        ("leg-tapered", "下收腿柱；蹄部收窄"),
    )),
    (("刃", "刀", "blade", "sword"), (
        ("curved-blade", "略上翘的短刃；适合小刀/匕首"),
        ("straight-tip", "直背短刃；原版短刀/剑基础"),
        ("hook-tip", "钩形短刃；上翘/钩尖"),
    )),
    (("柄", "杖", "杆", "handle", "shaft", "staff", "stick", "rod"), (
        ("thin-handle", "1-2px 直线细柄；适合杖身/握柄"),
        ("wooden-curve", "微曲木质柄；带自然弧度"),
        ("grip-rounded", "底部加粗握柄；防滑/分段"),
    )),
    (("皮", "hide", "leather"), (
        ("hide-fringe", "皮料/织物边缘；窄条或流苏"),
        ("hide-fold", "折叠皮面；多块皮料拼合"),
    )),
    (("菌", "菇", "mushroom", "cap", "伞"), (
        ("cap-round", "半圆伞盖；蘑菇/菌盖"),
        ("cap-flat", "扁平伞盖；蘑菇块/菌盖"),
    )),
    (("眼", "eye", "魂"), (
        ("soul-eye", "魂火眼点；小面积发光"),
        ("eye-socket", "黑色眼窝；骷髅/恶魔眼"),
    )),
    (("身", "体", "body"), (
        ("body-block", "方形躯干；原版方块式身体"),
        ("body-tapered", "收腰躯干；身体中段略收"),
    )),
    (("尾", "tail"), (
        ("tail-short", "短尾；点状/小段尾"),
        ("tail-long", "长尾；可弯曲尾"),
    )),
]

# 无匹配部件时的通用 fallback，避免把“身体”误判成“骷髅头”。
_DEFAULT_SHAPE_TOKEN_FALLBACK: tuple[tuple[str, str], ...] = (
    ("generic-outline", "原版整体/部件轮廓；保持语义可辨认"),
    ("plain-block", "原版方块/躯干轮廓；适合无特定形状的部件"),
)


def _part_anchor_score(part: str, anchor: dict[str, Any]) -> int:
    """粗略计算“这个部件与该锚点有多相关”。"""
    part_l = str(part).lower()
    name_l = str(anchor.get("name", "") or "").lower()
    path_l = str(anchor.get("path", "") or "").lower()
    hay = name_l + " " + path_l
    score = 0
    for zh, ens in _ZH_SOURCE_MAP.items():
        if zh in part and any(e in hay for e in ens):
            score += 3
    for token in _PART_EN_HINTS:
        if token in part_l and token in hay:
            score += 2
    if anchor.get("category") == "entity" or "/entity/" in path_l or "entity/" in path_l:
        score += 1
    return score


def _select_related_anchors(part: str, anchors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按部件相关度排序，返回最多 3 个最相关锚点；若无匹配返回全部。"""
    ranked = sorted(
        anchors or [],
        key=lambda a: -_part_anchor_score(part, a),
    )
    best = ranked[0] if ranked else None
    if best is None:
        return []
    # 如果最相关分数为 0，仍返回前 3 个默认锚点，保证候选不为空。
    if _part_anchor_score(part, best) <= 0:
        return ranked[:3]
    # 保留所有分数>0 的锚点，最多 3 个；不足 3 个时补默认前 3 个。
    positive = [a for a in ranked if _part_anchor_score(part, a) > 0]
    if len(positive) >= 3:
        return positive[:3]
    merged = list(positive)
    for a in ranked:
        if a not in merged and len(merged) < 3:
            merged.append(a)
    return merged


def _anchor_display_name(anchor: dict[str, Any]) -> str:
    return str(anchor.get("name") or anchor.get("path") or "compact")


def _source_shape_token(part: str, anchor: dict[str, Any]) -> tuple[str, str] | None:
    """从锚点资产名生成一个来源相关的 shape token。"""
    name_l = str(_anchor_display_name(anchor)).lower()
    base = name_l.rsplit(".", 1)[0].replace(" ", "-").replace("_", "-")
    if not base or base in ("compact", "unknown"):
        return None
    part_l = str(part).lower()
    if "skull" in part_l or "骷髅" in part or "骨" in part:
        return ("%s-skull" % base, "来源：%s 头部区域骨白头骨轮廓" % _anchor_display_name(anchor))
    if "horn" in part_l or "角" in part:
        return ("%s-horn" % base, "来源：%s 角/耳区域轮廓" % _anchor_display_name(anchor))
    if "muzzle" in part_l or "鼻" in part or "snout" in part_l:
        return ("%s-muzzle" % base, "来源：%s 鼻口区域轮廓" % _anchor_display_name(anchor))
    if "head" in part_l or "头" in part:
        return ("%s-head" % base, "来源：%s 头部区域轮廓" % _anchor_display_name(anchor))
    if "ear" in part_l or "耳" in part:
        return ("%s-ear" % base, "来源：%s 耳朵区域轮廓" % _anchor_display_name(anchor))
    if "leg" in part_l or "腿" in part:
        return ("%s-leg" % base, "来源：%s 腿部区域轮廓" % _anchor_display_name(anchor))
    if "body" in part_l or "身" in part or "体" in part:
        return ("%s-body" % base, "来源：%s 身体/躯干区域轮廓" % _anchor_display_name(anchor))
    if "tail" in part_l or "尾" in part:
        return ("%s-tail" % base, "来源：%s 尾部区域轮廓" % _anchor_display_name(anchor))
    if "blade" in part_l or "刀" in part or "刃" in part:
        return ("%s-blade" % base, "来源：%s 刃部轮廓" % _anchor_display_name(anchor))
    if "handle" in part_l or "柄" in part or "杖" in part or "staff" in part_l:
        return ("%s-handle" % base, "来源：%s 柄/杖身轮廓" % _anchor_display_name(anchor))
    if "hide" in part_l or "皮" in part:
        return ("%s-hide" % base, "来源：%s 皮料/织物边缘轮廓" % _anchor_display_name(anchor))
    if "cap" in part_l or "菌" in part:
        return ("%s-cap" % base, "来源：%s 菌盖/伞面轮廓" % _anchor_display_name(anchor))
    return ("%s-shape" % base, "来源：%s 整体/部件轮廓" % _anchor_display_name(anchor))


def _generic_shape_tokens(part: str) -> list[tuple[str, str]]:
    for keywords, tokens in _SHAPE_TOKEN_HINTS:
        if any(k in str(part).lower() or k in str(part) for k in keywords):
            return list(tokens)
    return list(_DEFAULT_SHAPE_TOKEN_FALLBACK)


def _crop_silhouette_fragment(
    rows: list[str],
    box: tuple[int, int, int, int] | None = None,
    max_rows: int = 12,
    max_cols: int = 28,
) -> str | None:
    """把 X/. 剪影裁剪成紧凑片段，去掉空白行/列。"""
    if not rows or not rows[0]:
        return None
    if box:
        x1, y1, x2, y2 = (int(v) for v in box)
        x1 = max(0, min(x1, len(rows[0]) if rows else 0))
        y1 = max(0, min(y1, len(rows)))
        x2 = max(x1, min(x2, len(rows[0]) if rows else 0))
        y2 = max(y1, min(y2, len(rows)))
        rows = [row[x1:x2] for row in rows[y1:y2]]

    # 去掉上下全空行
    def _nonempty(r: str) -> bool:
        return any(ch in ("X", "x") for ch in r)

    while rows and not _nonempty(rows[0]):
        rows.pop(0)
    while rows and not _nonempty(rows[-1]):
        rows.pop(-1)
    if not rows:
        return None
    # 去掉左右全空列
    width = len(rows[0]) if rows else 0
    left = width
    right = 0
    for r in rows:
        indices = [i for i, ch in enumerate(r) if ch in ("X", "x")]
        if indices:
            left = min(left, indices[0])
            right = max(right, indices[-1] + 1)
    if left >= right:
        return None
    rows = [r[left:right] for r in rows]

    # 限宽：取中间一段，保留轮廓中部
    if rows and len(rows[0]) > max_cols:
        w = len(rows[0])
        start = max(0, (w - max_cols) // 2)
        rows = [r[start:start + max_cols] for r in rows]

    # 限高：均匀抽样，保留整体比例
    if len(rows) > max_rows:
        indices = [round(i * (len(rows) - 1) / (max_rows - 1)) for i in range(max_rows)]
        rows = [rows[i] for i in indices]

    # 归一化：统一小写 x -> X
    rows = [r.replace("x", "X") for r in rows]
    if not any(any(ch == "X" for ch in r) for r in rows):
        return None
    return "\n".join(rows)


def _fragment_candidate_for_anchor(
    part: str,
    anchor: dict[str, Any],
    form: str = "item",
    entity: str | None = None,
) -> dict[str, Any] | None:
    """从锚点 compact_text 生成一个 X/. 剪影候选。"""
    compact = anchor.get("compact_text") or ""
    rows = _parse_silhouette(compact)
    box = None
    region = None
    if form == "entity_uv" and entity:
        import entity_uv_spec as eu
        regions = eu.regions_for_entity(entity, 64, 32) or {}
        part_l = str(part).lower()
        # 从部件名找对应区域名
        region_names = []
        if "horn" in part_l or "角" in str(part):
            region_names = ["horns", "head"]
        elif "muzzle" in part_l or "鼻" in str(part) or "snout" in part_l:
            region_names = ["muzzle", "head"]
        elif "leg" in part_l or "腿" in str(part):
            region_names = ["legs"]
        elif "head" in part_l or "头" in str(part):
            region_names = ["head"]
        elif "ear" in part_l or "耳" in str(part):
            region_names = ["ears", "head"]
        elif "body" in part_l or "身" in str(part) or "体" in str(part):
            region_names = ["body"]
        elif "tail" in part_l or "尾" in str(part):
            region_names = ["tail", "body"]
        for rn in region_names:
            if rn in regions:
                box = tuple(int(v) for v in regions[rn])
                region = rn
                break
    fragment = _crop_silhouette_fragment(rows, box=box)
    if not fragment:
        return None
    source = _anchor_display_name(anchor)
    token = "compact:%s" % source
    kind = "compact_fragment"
    note = "只含 X/. 剪影；%s 区域/整体轮廓" % (region or source)
    return {
        "token": token,
        "source": source,
        "kind": kind,
        "fragment": fragment,
        "note": note,
        "region": region,
    }


def build_silhouette_bank(
    parts: list[str] | None,
    retrieval_anchors: list[dict[str, Any]] | None,
    form: str = "item",
    width: int = 16,
    height: int = 16,
    entity: str | None = None,
) -> list[dict[str, Any]]:
    """为每个部件生成 2-4 个轮廓基础候选。

    返回 ``silhouette_candidates`` 列表（每个部件一条），包含 shape token 与
    X/. compact fragment。候选是“菜单”不是锁：可选一个/可组合/可大改。
    """
    anchors = list(retrieval_anchors or [])
    part_list = [str(p) for p in (parts or [])] or ["主体"]
    bank: list[dict[str, Any]] = []
    for part in part_list:
        related = _select_related_anchors(part, anchors)
        candidates: list[dict[str, Any]] = []
        seen_tokens: set[str] = set()

        # 1) 来源相关 shape token（优先）
        for a in related:
            src = _source_shape_token(part, a)
            if not src:
                continue
            token, note = src
            if token in seen_tokens:
                continue
            candidates.append({
                "token": token,
                "source": _anchor_display_name(a),
                "kind": "shape_token",
                "note": note,
            })
            seen_tokens.add(token)
            if len(candidates) >= 4:
                break

        # 2) X/. compact fragment（从最相关 1-2 个锚点切，让模型看到可拿捏的轮廓）
        if len(candidates) < 4:
            for a in related[:2]:
                if len(candidates) >= 4:
                    break
                frag = _fragment_candidate_for_anchor(part, a, form=form, entity=entity)
                if frag and frag["token"] not in seen_tokens:
                    candidates.append(frag)
                    seen_tokens.add(frag["token"])

        # 3) 通用 shape token（补足种类）
        for token, note in _generic_shape_tokens(part):
            if token in seen_tokens:
                continue
            candidates.append({
                "token": token,
                "source": "通用原版形状语法",
                "kind": "shape_token",
                "note": note,
            })
            seen_tokens.add(token)
            if len(candidates) >= 4:
                break

        # 4) 兜底：候选不足 2 时补一个来源整体 compact
        if len(candidates) < 2 and related:
            frag = _fragment_candidate_for_anchor(part, related[0], form=form, entity=entity)
            if frag:
                candidates.append(frag)
            else:
                candidates.append({
                    "token": "original-outline",
                    "source": _anchor_display_name(related[0]),
                    "kind": "shape_token",
                    "note": "来源：%s 整体轮廓；仅作轮廓语法参考" % _anchor_display_name(related[0]),
                })

        # 5) 即使没有锚点，也要给出可操作的 2 个通用 token
        if len(candidates) < 2:
            for token, note in _generic_shape_tokens(part):
                if token in seen_tokens:
                    continue
                candidates.append({
                    "token": token,
                    "source": "通用原版形状语法",
                    "kind": "shape_token",
                    "note": note,
                })
                seen_tokens.add(token)
                if len(candidates) >= 2:
                    break

        candidates = candidates[:4]
        bank.append({
            "part": part,
            "candidates": candidates,
        })
    return bank


def render_silhouette_candidates(silhouette_bank: list[dict[str, Any]]) -> str:
    """把 silhouette bank 渲染成 prompt 中的“部件轮廓候选”段。"""
    lines: list[str] = []
    lines.append("### 部件轮廓候选 silhouette_candidates（2-4 个/部件）")
    lines.append("> 形状候选 = 菜单，不是锁。")
    lines.append("> - 可选其中一个；")
    lines.append("> - 可组合多个；")
    lines.append("> - 可大改形状（加长/加粗/弯曲/变形/换比例都允许）；")
    lines.append("> - 禁止把候选当成最终网格/逐像素复制候选剪影。")
    lines.append("")
    for entry in silhouette_bank or []:
        part = entry.get("part", "主体")
        lines.append("- [%s]" % part)
        cands = entry.get("candidates", []) or []
        for i, c in enumerate(cands, 1):
            token = c.get("token", "shape")
            source = c.get("source", "-")
            note = c.get("note", "")
            lines.append("  - 候选 %d：%s（来源：%s）%s" % (
                i, token, source, ("；" + note) if note else ""
            ))
            frag = c.get("fragment")
            if frag and c.get("kind") == "compact_fragment":
                lines.append("    ```")
                lines.append(frag)
                lines.append("    ```")
        lines.append("")
    return "\n".join(lines).strip()


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


def _run_self_test() -> int:
    """简单自测：验证分析、候选生成与渲染入口。"""
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
    assert "palette_family" in analysis
    assert "silhouette_candidates" in analysis
    assert analysis["silhouette_candidates"], "silhouette_candidates should not be empty"

    anchors = [
        {"name": "cow.png", "path": "entity/cow/cow.png", "category": "entity",
         "compact_text": sample},
        {"name": "stick.png", "path": "item/stick.png", "category": "item",
         "compact_text": sample},
    ]
    bank = build_silhouette_bank(["角 horns", "杖身/握柄 handle"], anchors, form="item")
    assert len(bank) == 2
    for entry in bank:
        assert 2 <= len(entry["candidates"]) <= 4, entry
    text = render_silhouette_candidates(bank)
    assert "可选其中一个" in text
    assert "可组合多个" in text
    assert "可大改形状" in text

    print("reference_analyzer self-test: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(_run_self_test())
