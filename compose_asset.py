#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compose_asset.py — v4-compose: 形状模板/概念 mask + 重新上色/纹样组合器。

核心思想
--------
- ``template`` 模式：形状必须来自原版模板，LLM 只负责颜色/花纹。本脚本以原版
  PNG 的 alpha 作为形状 mask，输出新 PNG 时**逐像素复制基础图的 alpha**，
  因此形状/alpha 与 base 完全一致；LLM 的 palette/pattern 只在 mask 内部
  生效，mask 外保持透明。
- ``concept`` / ``content`` 模式：形状从概念卡/内置规则生成（当前目标是蘑菇
  幼苗的“菌盖+菌柄”小蘑菇剪影），不再锁 birch_sapling 这类树苗形状；内容
  （配色/纹样）可以来自指定内容贴图（red_mushroom / brown_mushroom）或
  palette/pattern。

支持两种组合模式（与 shape-source 正交）
----------------------------------------
- ``mask-recolor``：以形状 mask 作为 mask，将 mask 内像素颜色按 HSV/亮度
  映射到新调色板；alpha/形状完全不变。
- ``pattern-overlay``：同样锁 shape mask，LLM/外部 pattern 网格只在 mask 内
  生效；mask 外保持透明。alpha 仍复制自 shape mask，因此 shape IoU 恒为 1.0。

用法
----
    python3 compose_asset.py \
        --base mc_asset_library/raw/item/stone_axe.png \
        --palette "#c32826,#be2321,#494949,#3c3c3c,#ffbfbf" \
        --mode mask-recolor --output mushroom_axe.png

    python3 compose_asset.py \
        --multi base1.png;base2.png \
        --palette "#c32826,#be2321" \
        --mode mask-recolor --output out_dir/

    python3 compose_asset.py \
        --base mc_asset_library/raw/block/birch_sapling.png \
        --raw generated_assets_v3/mushroom_sapling/raw_answer.txt \
        --mode pattern-overlay --output mushroom_sapling_v4.png

    # 蘑菇幼苗：cross 是形式，内容为蘑菇（不锁树苗）
    python3 compose_asset.py \
        --shape-source content \
        --multi "mc_asset_library_full/textures/block/red_mushroom.png;\
mc_asset_library_full/textures/block/brown_mushroom.png" \
        --concept concept_examples/mushroom_sprout.json \
        --output generated_assets_v4b/mushroom_sprout/cross.png

    python3 compose_asset.py --self-test

依赖/复用的现有实现
-------------------
- ``text_to_texture``：解析 LLM raw_answer 的 W/H + PALETTE + index grid 或
  直接 hex grid 文本为 RGBA 图像。
- ``package_asset.split_face_blocks``：拆分多 face raw_answer 的
  ``=== face: <id> ===`` / ``FILE:`` 块。
- ``mc_asset_library_full/textures/block/red_mushroom.png`` 与
  ``brown_mushroom.png``：蘑菇内容贴图（配色/纹样参考）。
"""

from __future__ import annotations

import argparse
import colorsys
import json
import math
import re
import sys
import time
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow is required: pip install pillow") from exc

# 复用现有实现
import text_to_texture as t2t
from package_asset import split_face_blocks

LOG_PATH = "v4-compose-log.txt"
SELFTEST_REPORT = "v4_compose_selftest.txt"
SELFTEST_ASSETS_DIR = Path("v4_compose_selftest_assets")

DEFAULT_PALETTE = [
    (195, 40, 38),   # #c32826
    (190, 35, 33),   # #be2321
    (73, 73, 73),    # #494949
    (60, 60, 60),    # #3c3c3c
    (255, 191, 191), # #ffbfbf
]

HEX6_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def normalize_path(path: str | Path) -> Path:
    """接受 Windows 风格路径（C:\\...）与 POSIX /mnt/c/...。"""
    s = str(path)
    if s.startswith("\\\\") and s[2:3].isalpha() and s[3:4] in ("\\", "/"):
        s = s.replace("\\", "/")
    if len(s) >= 3 and s[0].isalpha() and s[1] == ":" and s[2] in ("\\", "/"):
        drive = s[0].lower()
        rest = s[2:].replace("\\", "/")
        return Path("/mnt") / drive / rest
    return Path(s)


def log_message(message: str, path: str | Path = LOG_PATH) -> None:
    """追加带时间戳的消息到日志文件。"""
    p = normalize_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(p, "a", encoding="utf-8") as f:
        f.write("[%s] %s\n" % (ts, message))


# ---------------------------------------------------------------------------
# 颜色 / palette
# ---------------------------------------------------------------------------

def hex_to_rgb(token: str) -> tuple[int, int, int]:
    token = token.strip().strip('"').strip("'").strip("#")
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    if len(token) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", token):
        raise ValueError("invalid hex color: %r" % token)
    return int(token[0:2], 16), int(token[2:4], 16), int(token[4:6], 16)


def parse_palette_string(s: str) -> list[tuple[int, int, int]]:
    """解析 ``#c32826,#be2321,...`` / 空格 / 分号分隔的调色板字符串。"""
    if not s:
        raise ValueError("empty palette string")
    s = s.strip()
    # 容错用户复制了尖括号占位符
    if s.startswith("<") and s.endswith(">"):
        s = s[1:-1]
    tokens = [tok for tok in re.split(r"[,\s;]+", s.strip()) if tok]
    palette = []
    for tok in tokens:
        palette.append(hex_to_rgb(tok))
    if not palette:
        raise ValueError("no palette colors parsed from %r" % s)
    return palette


def palette_from_pattern_image(img: Image.Image) -> list[tuple[int, int, int]]:
    """从 RGBA 图的不透明像素提取唯一颜色（保持出现顺序）。"""
    seen: list[tuple[int, int, int]] = []
    seen_set: set[tuple[int, int, int]] = set()
    for r, g, b, a in img.convert("RGBA").getdata():
        if a > 0 and (r, g, b) not in seen_set:
            seen_set.add((r, g, b))
            seen.append((r, g, b))
    return seen


# ---------------------------------------------------------------------------
# 概念形状 mask / 蘑菇内容组合
# ---------------------------------------------------------------------------

# 16x16 小蘑菇剪影：菌盖半圆 + 菌柄。用 'X' 表示不透明，'.' 表示透明。
MUSHROOM_MASK_ROWS = [
    "................",
    "................",
    "................",
    "................",
    ".......XXXX.....",
    ".....XXXXXXXX...",
    "....XXXXXXXXXX..",
    "...XXXXXXXXXXXX.",
    "...XXXXXXXXXXXX.",
    "....XXXXXXXXXX..",
    ".......XXXX.....",
    ".......XXXX.....",
    ".......XXXX.....",
    ".......XXXX.....",
    "................",
    "................",
]

# 默认菌褶/菌柄参考色（来自 red_mushroom / brown_mushroom 的常见色）。
DEFAULT_CAP_PALETTE = [
    (226, 18, 18),   # #e21212 red_mushroom
    (254, 42, 42),   # #fe2a2a
    (196, 29, 38),   # #c41d26
    (169, 18, 26),   # #a9121a
]
DEFAULT_STEM_PALETTE = [
    (204, 153, 120), # #cc9978 brown_mushroom
    (181, 148, 125), # #b5947d
    (145, 109, 85),  # #916d55
    (114, 86, 67),   # #725643
    (106, 78, 59),   # #6a4e3b
    (76, 61, 51),    # #4c3d33
]
DEFAULT_GILL_PALETTE = [
    (237, 232, 202), # #ede8ca red_mushroom 菌褶亮部
    (227, 221, 186), # #e3ddba
    (207, 196, 127), # #cfc47f
    (214, 208, 172), # #d6d0ac
]


def render_mask_rows(rows: list[str], size: tuple[int, int] = (16, 16)) -> Image.Image:
    """把 ``X`` / ``.`` 行渲染为 RGBA mask；不透明像素用白色填充。"""
    h = size[1]
    w = size[0]
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        if y >= h:
            break
        for x, ch in enumerate(row):
            if x >= w:
                break
            if ch in ("X", "#", "*"):
                img.putpixel((x, y), (255, 255, 255, 255))
    return img


def build_mushroom_mask(size: tuple[int, int] = (16, 16)) -> Image.Image:
    """生成 16x16 小蘑菇剪影（菌盖半圆 + 菌柄），用于 cross 形式的概念 shape mask。"""
    if tuple(size) != (16, 16):
        # 通用尺寸：按 16x16 版缩放，保持近邻像素风格。
        base = build_mushroom_mask((16, 16))
        return base.resize(tuple(size), Image.NEAREST)
    return render_mask_rows(MUSHROOM_MASK_ROWS, size)


def _is_mushroom_concept(concept: dict | None) -> bool:
    if not concept:
        return True
    text = " ".join(str(v) for v in concept.values())
    keys = ("蘑菇", "mushroom", "sprout", "sapling")
    return any(k in text.lower() for k in keys)


def build_concept_mask(concept_path: str | Path | None = None,
                       size: tuple[int, int] = (16, 16)) -> Image.Image:
    """从概念卡（JSON）生成小蘑菇 shape mask；无卡/非蘑菇时回退默认小蘑菇。

    目前内置规则只覆盖蘑菇幼苗场景：16x16 菌盖半圆 + 菌柄。后续如需其他
    concept shape，可在此扩展为按 ``parts`` / ``face_regions`` 生成 mask。
    """
    concept: dict | None = None
    p = normalize_path(concept_path) if concept_path else None
    if p is not None and p.is_file():
        try:
            concept = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            concept = None
    if _is_mushroom_concept(concept):
        return build_mushroom_mask(size)
    # 非蘑菇概念：先统一用默认小蘑菇 mask（本版本以蘑菇幼苗为目标，
    # 显式说明这是内置 fallback）。
    return build_mushroom_mask(size)


def _classify_content_palettes(paths: list[Path]) -> tuple[list[tuple[int, int, int]],
                                                           list[tuple[int, int, int]],
                                                           list[tuple[int, int, int]]]:
    """从内容贴图路径返回 cap(红/主色)、stem(褐/副色)、gill(菌褶) 参考调色板。

    规则：文件名含 ``red`` → cap；含 ``brown`` → stem；其余路径按顺序进入
    main/alt。菌褶色从输入图里低饱和亮色中挑选；找不到则用默认值。
    """
    cap_palette: list[tuple[int, int, int]] = []
    stem_palette: list[tuple[int, int, int]] = []
    gill_palette: list[tuple[int, int, int]] = []
    for path in paths:
        if not path.is_file():
            continue
        img = Image.open(path)
        colors = palette_from_pattern_image(img)
        low = str(path).lower()
        if "red" in low:
            # 红蘑菇：只取红色主体（R 明显高于 G/B），避免把菌褶/灰白边混入菌盖。
            cap_palette.extend(c for c in colors if c[0] >= c[1] + 30 and c[0] >= c[2] + 30)
            if not cap_palette:
                cap_palette.extend(colors)
        elif "brown" in low:
            stem_palette.extend(colors)
        else:
            stem_palette.extend(colors)
        # 从该图提取低饱和/亮色作为菌褶候选
        for r, g, b in colors:
            h, s, v = _rgb_to_hsv01((r, g, b))
            if s < 0.45 and v > 0.6:
                gill_palette.append((r, g, b))
    if not cap_palette:
        cap_palette = list(DEFAULT_CAP_PALETTE)
    if not stem_palette:
        stem_palette = list(DEFAULT_STEM_PALETTE)
    if not gill_palette:
        gill_palette = list(DEFAULT_GILL_PALETTE)
    return cap_palette, stem_palette, gill_palette


def _pattern_color(palette: list[tuple[int, int, int]],
                   x: int, y: int, seed: int = 0) -> tuple[int, int, int]:
    """用空间位置产生可复现的像素级明暗变化。"""
    v = (x * 7 + y * 13 + seed * 31) % 256
    return map_color_brightness((v, v, v), palette)


def compose_content_mushroom(mask_img: Image.Image,
                             content_paths: list[Path]) -> Image.Image:
    """在概念蘑菇 mask 内填入 red/brown 内容贴图的配色/纹样。

    - 菌盖区域 → red_mushroom 系调色板（红）。
    - 菌盖下沿 → 菌褶调色板（白/米）。
    - 菌柄区域 → brown_mushroom 系调色板（浅褐/褐）。
    alpha 完全来自传入的 concept mask，因此 shape IoU = 1.0。
    """
    cap_palette, stem_palette, gill_palette = _classify_content_palettes(content_paths)
    mask = mask_img.convert("RGBA")
    w, h = mask.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mp = mask.load()
    op = out.load()

    # 按 mask 每行不透明像素数自动判断“菌盖底”位置。
    # 小蘑菇的菌盖应明显宽于菌柄；阈值 8 可避免把 4px 菌柄误判为菌盖。
    row_widths = []
    for y in range(h):
        row_widths.append(sum(1 for x in range(w) if mp[x, y][3] > 0))
    cap_bottom = 0
    for y in range(h):
        if row_widths[y] >= 8:
            cap_bottom = y
    stem_start = cap_bottom + 1

    for y in range(h):
        for x in range(w):
            if mp[x, y][3] <= 0:
                op[x, y] = (0, 0, 0, 0)
                continue
            alpha = mp[x, y][3]
            if y == cap_bottom:
                rgb = _pattern_color(gill_palette, x, y, seed=2)
            elif y <= cap_bottom:
                rgb = _pattern_color(cap_palette, x, y, seed=0)
            else:
                rgb = _pattern_color(stem_palette, x, y, seed=1)
            op[x, y] = rgb + (alpha,)
    return out


def compose_concept_asset(mask_img: Image.Image,
                          palette: list[tuple[int, int, int]],
                          pattern_img: Image.Image | None = None,
                          content_paths: list[Path] | None = None,
                          map_mode: str = "nearest") -> Image.Image:
    """概念模式的统一组合：mask 负责形状，palette/pattern/content 负责配色。

    优先级：外部 pattern > content 内容贴图配色 > palette 重上色。
    """
    if pattern_img is not None:
        return compose_pattern_overlay(mask_img, pattern_img)
    if content_paths:
        return compose_content_mushroom(mask_img, content_paths)
    if palette:
        return compose_mask_recolor(mask_img, palette, map_mode)
    return compose_content_mushroom(mask_img, [])  # 用默认红/褐 palette


def parse_palette_from_text(text: str) -> list[tuple[int, int, int]]:
    """从 raw 文本解析 palette。

    优先解析 ``PALETTE`` 块；若没有 palette 块，则渲染 pattern 并取不透明
    像素的唯一颜色。这样 ``--raw`` 既可用于 mask-recolor（取 palette）也可用于
    pattern-overlay（取 pattern）。
    """
    palette: list[tuple[int, int, int]] = []
    # 先按 "PALETTE" 块逐行收集连续编号颜色。
    lines = text.splitlines()
    in_palette = False
    for line in lines:
        low = line.strip().lower()
        if low.startswith("palette"):
            in_palette = True
            continue
        if in_palette:
            m = re.match(r"^\s*(\d+)\s*:\s*(#?[0-9a-fA-F]{6})", line)
            if m:
                palette.append(hex_to_rgb(m.group(2)))
                continue
            # 遇到非 palette 行（空行/INDEX GRID/编号索引）停止收集
            if low in ("index grid", "index grid:", "hex color grid"):
                break
            if line.strip() and not line.strip().startswith(("#", "-1", ".")):
                # 可能是 index grid 第一行；停止
                break
    if palette:
        return palette

    # 没有 palette 块：尝试渲染文本，再从渲染结果提取唯一色。
    try:
        img = render_pattern_from_text(text, None)
    except Exception:
        return []
    return palette_from_pattern_image(img)


def _clean_llm_text(text: str) -> str:
    """去掉多 face raw 中的 FILE:/FORM=/FACES= 等非像素契约行。"""
    kept = []
    for ln in text.splitlines():
        s = ln.strip()
        if re.match(r"^(FILE\s*:|FORM\s*=|FACES\s*=)", s, re.I):
            continue
        if s.startswith("```") or s.startswith("~~~"):
            continue
        if re.match(r"^=+\s*face\s*:", s, re.I):
            continue
        kept.append(ln)
    return "\n".join(kept)


def _lines_to_pattern_image(rows: list[list[tuple[int, int, int, int]]]) -> Image.Image:
    if not rows or not rows[0]:
        raise ValueError("empty pattern grid")
    h = len(rows)
    w = max(len(row) for row in rows)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, px in enumerate(row):
            if x < w:
                img.putpixel((x, y), px)
    return img


def parse_direct_hex_grid(text: str) -> Image.Image:
    """解析无 W/H 头部的直接 hex 网格。

    每行可为 ``#c32826 #494949 ...`` 或逗号分隔；透明可用 ``----`` / ``.`` /
    ``-1``。
    """
    rows: list[list[tuple[int, int, int, int]]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        # 去掉非数据注释；但不要去掉 “#c32826” 本身
        if s.startswith("#") and not re.match(r"^#[0-9a-fA-F]{6}", s):
            continue
        if s.lower().startswith(("palette", "index grid")):
            continue
        tokens = [tok for tok in re.split(r"[\s,;]+", s) if tok]
        if not tokens:
            continue
        row = []
        for tok in tokens:
            if tok in ("----", ".", "-1"):
                row.append((0, 0, 0, 0))
            elif HEX6_RE.match(tok):
                r, g, b = hex_to_rgb(tok)
                row.append((r, g, b, 255))
            else:
                raise ValueError("invalid hex grid token %r" % tok)
        rows.append(row)
    if not rows:
        raise ValueError("empty direct hex pattern")
    return _lines_to_pattern_image(rows)


def render_pattern_from_text(text: str, size: tuple[int, int] | None) -> Image.Image:
    """把 raw/pattern 文本渲染为 RGBA 图像。

    优先使用 text_to_texture 解析 W/H + PALETTE/index grid 或直接 hex grid；
    若没有 W/H 头，则回退到本脚本的纯 hex 网格解析。
    """
    clean = _clean_llm_text(text)
    if not clean.strip():
        raise ValueError("empty pattern text")
    # JSON pattern 支持
    if clean.lstrip().startswith("{"):
        data = json.loads(clean)
        if isinstance(data, dict) and "pattern" in data:
            return parse_pattern_value(data["pattern"])
    # t2t 格式（W= H= 或 PALETTE 开头）
    if re.search(r"(?im)^W\s*=\s*\d+\s+H\s*=\s*\d+", clean) or re.search(r"(?im)^PALETTE", clean):
        img = t2t.text_to_image(clean)
        if size is not None and img.size != tuple(size):
            img = img.resize(tuple(size), Image.NEAREST)
        return img
    img = parse_direct_hex_grid(clean)
    if size is not None and img.size != tuple(size):
        img = img.resize(tuple(size), Image.NEAREST)
    return img


def parse_pattern_value(value) -> Image.Image:
    """解析 JSON pattern 字段为 RGBA Image。

    支持：
    - list[list[str]]: hex 字符串矩阵
    - list[list[int]]: RGB 值矩阵（3 长度）或 RGBA（4 长度）
    - list[str]: 每行一个逗号/空格分隔的 hex 串
    """
    if isinstance(value, str):
        return render_pattern_from_text(value, None)
    if isinstance(value, list):
        if value and isinstance(value[0], list):
            rows = []
            for row in value:
                rrow = []
                for cell in row:
                    if isinstance(cell, str):
                        c = hex_to_rgb(cell)
                        rrow.append((c[0], c[1], c[2], 255))
                    elif isinstance(cell, (list, tuple)):
                        if len(cell) == 3:
                            rrow.append((int(cell[0]), int(cell[1]), int(cell[2]), 255))
                        elif len(cell) == 4:
                            rrow.append((int(cell[0]), int(cell[1]), int(cell[2]), int(cell[3])))
                        else:
                            raise ValueError("pattern cell must have 3 or 4 channels")
                    else:
                        raise ValueError("invalid pattern cell %r" % (cell,))
                rows.append(rrow)
            return _lines_to_pattern_image(rows)
        if value and all(isinstance(v, str) for v in value):
            return render_pattern_from_text("\n".join(value), None)
    raise ValueError("unsupported JSON pattern value")


def load_pattern_arg(pattern_arg: str | None) -> Image.Image | None:
    """加载 --pattern 参数（文件路径或内联文本）。"""
    if pattern_arg is None:
        return None
    p = normalize_path(pattern_arg)
    if p.is_file():
        return render_pattern_from_text(p.read_text(encoding="utf-8"), None)
    return render_pattern_from_text(pattern_arg, None)


# ---------------------------------------------------------------------------
# compose 核心
# ---------------------------------------------------------------------------

def _rgb_to_hsv01(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = (v / 255.0 for v in rgb)
    return colorsys.rgb_to_hsv(r, g, b)


def _luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = (v / 255.0 for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _hue_distance(h1: float, h2: float) -> float:
    d = abs(h1 - h2)
    return d if d <= 0.5 else 1.0 - d


def map_color_nearest(base_rgb: tuple[int, int, int],
                      palette: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    """加权 HSV 最近邻：hue 权重最高，其次饱和度/明度。"""
    base_h = _rgb_to_hsv01(base_rgb)
    best = palette[0]
    best_d = math.inf
    for cand_rgb in palette:
        cand_h = _rgb_to_hsv01(cand_rgb)
        dh = _hue_distance(base_h[0], cand_h[0])
        ds = base_h[1] - cand_h[1]
        dv = base_h[2] - cand_h[2]
        # hue 0..1，sat/value 也是 0..1，权重 2/1/1
        d = math.sqrt(2.0 * dh * dh + ds * ds + dv * dv)
        if d < best_d:
            best_d = d
            best = cand_rgb
    return best


def map_color_brightness(base_rgb: tuple[int, int, int],
                         palette: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    """亮度分层：按感知亮度排序 palette，再把 base 亮度量化到层。"""
    if not palette:
        return (0, 0, 0)
    if len(palette) == 1:
        return palette[0]
    sorted_palette = sorted(palette, key=_luminance)
    lum = _luminance(base_rgb)
    idx = int(round(lum * (len(sorted_palette) - 1)))
    idx = max(0, min(len(sorted_palette) - 1, idx))
    return sorted_palette[idx]


def map_color(base_rgb: tuple[int, int, int],
              palette: list[tuple[int, int, int]],
              mode: str = "nearest") -> tuple[int, int, int]:
    if mode == "nearest":
        return map_color_nearest(base_rgb, palette)
    if mode == "brightness":
        return map_color_brightness(base_rgb, palette)
    if mode == "auto":
        # palette 颜色饱和度都很低或都在同色相时，亮度分层更稳；
        # 否则用最近邻保留局部色相/细节。
        hsvs = [_rgb_to_hsv01(c) for c in palette]
        sats = [h[1] for h in hsvs]
        hues = [h[0] for h in hsvs]
        low_sat = sum(1 for s in sats if s < 0.15) >= len(palette) * 0.4
        max_hue_diff = max(_hue_distance(hues[0], hue) for hue in hues)
        if low_sat or max_hue_diff < 0.05:
            return map_color_brightness(base_rgb, palette)
        return map_color_nearest(base_rgb, palette)
    raise ValueError("unknown map mode: %r" % mode)


def compose_mask_recolor(base_img: Image.Image,
                         palette: list[tuple[int, int, int]],
                         map_mode: str = "nearest") -> Image.Image:
    """以 base alpha 为形状 mask，重新着色但完全保留 alpha/形状。"""
    if not palette:
        raise ValueError("mask-recolor requires a non-empty palette")
    base = base_img.convert("RGBA")
    out = Image.new("RGBA", base.size, (0, 0, 0, 0))
    bp = base.load()
    op = out.load()
    w, h = base.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = bp[x, y]
            if a <= 0:
                op[x, y] = (0, 0, 0, 0)
            else:
                nr, ng, nb = map_color((r, g, b), palette, map_mode)
                op[x, y] = (nr, ng, nb, a)
    return out


def compose_pattern_overlay(base_img: Image.Image,
                            pattern_img: Image.Image | None) -> Image.Image:
    """在 base 的形状 mask 内叠加 pattern；alpha/形状从 base 复制。"""
    if pattern_img is None:
        # 没有外部 pattern 时，把 base 自身作为 pattern，只做恒等叠加（形状验证用）
        pattern = base_img.convert("RGBA")
    else:
        pattern = pattern_img.convert("RGBA")
        if pattern.size != base_img.size:
            pattern = pattern.resize(base_img.size, Image.NEAREST)
    base = base_img.convert("RGBA")
    out = Image.new("RGBA", base.size, (0, 0, 0, 0))
    bp = base.load()
    pp = pattern.load()
    op = out.load()
    w, h = base.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = bp[x, y]
            if a <= 0:
                op[x, y] = (0, 0, 0, 0)
                continue
            pr, pg, pb, pa = pp[x, y]
            if pa > 0:
                op[x, y] = (pr, pg, pb, a)
            else:
                # pattern 内部透明时保留 base 颜色，避免 mask 内部出现空洞
                op[x, y] = (r, g, b, a)
    return out


# ---------------------------------------------------------------------------
# Raw answer 解析
# ---------------------------------------------------------------------------

def parse_raw_answer(raw_text: str) -> list[dict]:
    """把 LLM raw answer 解析为每 face 的 palette/pattern。

    返回 list[dict]，每个 dict 含 ``id``、``palette``、``pattern``（Image|None）。
    多 face 按 ``=== face: ... ===`` / ``FILE:`` 分隔；若只有单块则返回一项。
    """
    raw_text = raw_text.strip()
    if not raw_text:
        raise ValueError("empty raw answer")

    # JSON 对象：palette/pattern 直接可用
    if raw_text.lstrip().startswith("{"):
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            palette = []
            if "palette" in data:
                pv = data["palette"]
                if isinstance(pv, str):
                    palette = parse_palette_string(pv)
                elif isinstance(pv, list):
                    palette = [hex_to_rgb(str(x)) for x in pv]
            pattern = render_pattern_from_text(raw_text, None) if "pattern" in data else None
            return [{"id": "", "palette": palette, "pattern": pattern}]

    blocks = split_face_blocks(raw_text)
    results: list[dict] = []
    for face_id, block in blocks:
        block = block.strip()
        if not block:
            continue
        palette = []
        pattern = None
        try:
            palette = parse_palette_from_text(block)
        except Exception:
            palette = []
        try:
            pattern = render_pattern_from_text(block, None)
        except Exception:
            pattern = None
        results.append({"id": face_id, "palette": palette, "pattern": pattern})
    if not results:
        raise ValueError("raw answer has no parseable face blocks")
    return results


def read_text_or_inline(arg: str) -> str:
    p = normalize_path(arg)
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return arg


# ---------------------------------------------------------------------------
# 输出路径 / self-test
# ---------------------------------------------------------------------------

def resolve_output_paths(output_arg: str | None, n: int, base_stems: list[str]) -> list[Path]:
    """确定多 face / 单 base 的输出文件列表。

    - 单 face：--output 直接作为输出文件（默认 composed.png）。
    - 多 face：若 --output 是 .png 路径，生成 ``stem_1.png``/``stem_2.png``；
      若 --output 指向目录（存在目录或以分隔符结尾），生成目录内的
      ``<base_stem>_composed.png``。
    """
    if n == 1:
        if output_arg:
            return [normalize_path(output_arg)]
        return [Path("composed.png")]
    if not output_arg:
        return [Path("composed_%d.png" % (i + 1)) for i in range(n)]
    out = normalize_path(output_arg)
    ext = out.suffix.lower()
    is_dir = out.exists() and out.is_dir()
    if is_dir or (ext == ""):
        out.mkdir(parents=True, exist_ok=True)
        return [out / ("%s_composed.png" % base_stems[i]) for i in range(n)]
    # 以 .png 结尾：在扩展名前加 _1/_2...
    parent = out.parent
    parent.mkdir(parents=True, exist_ok=True)
    stem = out.stem
    return [parent / ("%s_%d.png" % (stem, i + 1)) for i in range(n)]


def alpha_mask(img: Image.Image):
    return [px[3] > 0 for px in img.convert("RGBA").getdata()]


def shape_iou(img_a: Image.Image, img_b: Image.Image) -> float:
    ma = img_a.convert("RGBA")
    mb = img_b.convert("RGBA")
    if ma.size != mb.size:
        raise ValueError("size mismatch for IoU: %s vs %s" % (ma.size, mb.size))
    inter = 0
    union = 0
    pa = ma.load()
    pb = mb.load()
    w, h = ma.size
    for y in range(h):
        for x in range(w):
            a = pa[x, y][3] > 0
            b = pb[x, y][3] > 0
            if a and b:
                inter += 1
            if a or b:
                union += 1
    return inter / union if union else 1.0


def alpha_exact(img_a: Image.Image, img_b: Image.Image) -> bool:
    ma = img_a.convert("RGBA")
    mb = img_b.convert("RGBA")
    if ma.size != mb.size:
        return False
    pa = ma.load()
    pb = mb.load()
    w, h = ma.size
    for y in range(h):
        for x in range(w):
            if pa[x, y][3] != pb[x, y][3]:
                return False
    return True


def _synth_pattern_text(w: int = 16, h: int = 16) -> str:
    """生成一个自包含的 palette + index grid 测试 pattern。"""
    palette = ["#c32826", "#be2321", "#494949", "#3c3c3c", "#ffbfbf"]
    lines = ["W=%d H=%d" % (w, h), "PALETTE"]
    for i, c in enumerate(palette):
        lines.append("%d: %s" % (i, c))
    lines.append("")
    lines.append("INDEX GRID")
    for y in range(h):
        row = []
        for x in range(w):
            # 简单斜纹：内部大部分用红/灰交替，边缘留一些透明
            if (x + y) % 7 == 0:
                row.append("-1")
            elif (x + y) % 3 == 0:
                row.append("2")
            elif (x + y) % 3 == 1:
                row.append("1")
            else:
                row.append("0")
        lines.append(" ".join(row))
    return "\n".join(lines) + "\n"


def _synthetic_selftest_base(name: str, rel: str) -> Path:
    """如果原版 base 不存在，生成一张合成 16x16 图作为自测 base（不属于任何原版素材）。"""
    orig = normalize_path(rel)
    if orig.exists():
        return orig
    selftest_dir = normalize_path(SELFTEST_ASSETS_DIR)
    selftest_dir.mkdir(parents=True, exist_ok=True)
    out = selftest_dir / ("synthetic_%s.png" % name)
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    # 简单圆形/团块 alpha，足以验证 mask-recolor / pattern-overlay 的形状保持
    for y in range(16):
        for x in range(16):
            dx, dy = x - 8, y - 8
            if dx * dx + dy * dy <= 30:
                img.putpixel((x, y), (160, 160, 160, 255))
    img.save(out, "PNG")
    return out


def run_self_test() -> int:
    bases = [
        ("stone_axe", "mc_asset_library/raw/item/stone_axe.png"),
        ("birch_sapling", "mc_asset_library/raw/block/birch_sapling.png"),
        ("anvil_body", "mc_asset_library_full/textures/block/anvil.png"),
        ("anvil_top", "mc_asset_library_full/textures/block/anvil_top.png"),
    ]
    palette = parse_palette_string("#c32826,#be2321,#494949,#3c3c3c,#ffbfbf")
    pattern_text = _synth_pattern_text()
    pattern_img = render_pattern_from_text(pattern_text, None)
    selftest_dir = normalize_path(SELFTEST_ASSETS_DIR)
    selftest_dir.mkdir(parents=True, exist_ok=True)

    lines = ["# v4-compose self-test", "date: %s" % time.strftime("%Y-%m-%d %H:%M:%S")]
    failures = []
    for name, rel in bases:
        base_path = _synthetic_selftest_base(name, rel)
        if not base_path.exists():
            failures.append("%s: base not found %s" % (name, rel))
            lines.append("FAIL %s: base not found %s" % (name, rel))
            continue
        base_img = Image.open(base_path)
        for mode in ("mask-recolor", "pattern-overlay"):
            if mode == "mask-recolor":
                out_img = compose_mask_recolor(base_img, palette, "nearest")
                suffix = "mask_recolor"
            else:
                out_img = compose_pattern_overlay(base_img, pattern_img)
                suffix = "pattern_overlay"
            out_path = selftest_dir / ("%s_%s.png" % (name, suffix))
            out_img.convert("RGBA").save(out_path)
            iou = shape_iou(base_img, out_img)
            exact = alpha_exact(base_img, out_img)
            ok = iou >= 0.95
            lines.append("%-16s %-15s shape_iou=%.6f alpha_exact=%s saved=%s" % (name, mode, iou, exact, out_path))
            if not ok:
                failures.append("%s %s shape_iou=%.6f" % (name, mode, iou))

    # 额外验证 concept / content shape-source（蘑菇幼苗修复）
    try:
        mask_img = build_mushroom_mask()
        mask_path = selftest_dir / "concept_mushroom_mask.png"
        mask_img.convert("RGBA").save(mask_path)
        content_paths = [
            normalize_path("mc_asset_library_full/textures/block/red_mushroom.png"),
            normalize_path("mc_asset_library_full/textures/block/brown_mushroom.png"),
        ]
        content_paths = [p for p in content_paths if p.exists()]
        content_img = compose_concept_asset(mask_img, palette, None, content_paths or None, "nearest")
        content_path = selftest_dir / "content_mushroom_cross.png"
        content_img.convert("RGBA").save(content_path)
        iou = shape_iou(mask_img, content_img)
        exact = alpha_exact(mask_img, content_img)
        ok = mask_img.size == (16, 16) and mask_img.getbbox() is not None and iou >= 0.95 and exact
        lines.append("concept-mask                      ok=%s size=%s bbox=%s saved=%s" % (
            ok, mask_img.size, mask_img.getbbox(), mask_path))
        lines.append("content-mushroom                  ok=%s shape_iou=%.6f alpha_exact=%s saved=%s" % (
            iou >= 0.95 and exact, iou, exact, content_path))
        if not ok:
            failures.append("concept-mask")
        if iou < 0.95 or not exact:
            failures.append("content-mushroom shape_iou=%.4f alpha_exact=%s" % (iou, exact))
    except Exception as e:  # noqa: BLE001
        failures.append("concept/content selftest: %s" % e)
        lines.append("FAIL concept/content selftest: %s" % e)

    # 额外验证 raw 解析（复用现有 v3 mushroom_sapling raw，若存在）
    raw_candidate = normalize_path("generated_assets_v3/mushroom_sapling/raw_answer.txt")
    if raw_candidate.exists():
        raw_data = parse_raw_answer(raw_candidate.read_text(encoding="utf-8"))
        raw_ok = len(raw_data) == 1 and raw_data[0]["palette"] and raw_data[0]["pattern"] is not None
        lines.append("raw-parse                        ok=%s palette=%d pattern=%s" % (
            raw_ok, len(raw_data[0]["palette"]), raw_data[0]["pattern"] is not None))
        if not raw_ok:
            failures.append("raw parse")
    else:
        lines.append("raw-parse                        skipped (no v3 raw sample)")

    report_path = normalize_path(SELFTEST_REPORT)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    summary = "PASS" if not failures else "FAIL: " + "; ".join(failures)
    lines.append("summary: %s" % summary)
    # 重新写入包含 summary 的完整报告
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    log_message("self-test %s -> %s" % (summary, report_path))
    print("\n".join(lines))
    return 0 if not failures else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="v4-compose: 形状模板/概念 mask + LLM/内容贴图重新上色组合器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python3 compose_asset.py --base mc_asset_library/raw/item/stone_axe.png "
            "--palette '#c32826,#be2321' --mode mask-recolor --output out.png\n"
            "  python3 compose_asset.py --multi a.png;b.png --pattern pattern.txt "
            "--mode pattern-overlay --output out.png\n"
            "  python3 compose_asset.py --base birch_sapling.png --raw generated_assets_v3/"
            "mushroom_sapling/raw_answer.txt --mode pattern-overlay --output out.png\n"
            "  python3 compose_asset.py --shape-source content "
            "--multi 'mc_asset_library_full/textures/block/red_mushroom.png;"
            "mc_asset_library_full/textures/block/brown_mushroom.png' "
            "--concept concept_examples/mushroom_sprout.json "
            "--output generated_assets_v4b/mushroom_sprout/cross.png\n"
        ),
    )
    parser.add_argument("--shape-source", choices=["concept", "content", "template"],
                        default="template",
                        help="形状来源：template=锁定原版 base alpha；"
                             "content=用内容贴图配色+概念蘑菇 mask；"
                             "concept=由概念卡生成小蘑菇 mask")
    parser.add_argument("--concept", help="概念卡 JSON 路径（shape-source=concept/content 时用于生成蘑菇 mask）")
    parser.add_argument("--base", help="原版 PNG 路径；在 content 模式下是内容贴图路径")
    parser.add_argument("--multi", help="多 face / 多内容贴图：分号分隔的 PNG 路径列表")
    parser.add_argument("--palette", help="palette，如 '#c32826,#be2321,...'")
    parser.add_argument("--pattern", help="LLM pattern 网格（文件路径或内联文本）")
    parser.add_argument("--raw", help="LLM raw_answer 文件路径（或内联文本），提供 palette/pattern")
    parser.add_argument("--mode", choices=["mask-recolor", "pattern-overlay"],
                        default="mask-recolor", help="组合模式")
    parser.add_argument("--map", choices=["nearest", "brightness", "auto"],
                        default="nearest", help="mask-recolor 的颜色映射策略")
    parser.add_argument("--output", help="输出 PNG 路径（多 face 时自动编号或写入目录）")
    parser.add_argument("--self-test", action="store_true",
                        help="运行形状保真自测并写 v4_compose_selftest.txt")
    return parser.parse_args(argv)


def run_compose(args: argparse.Namespace) -> int:
    # 解析 base/multi。content 模式允许多张内容贴图共同提供配色；
    # concept 模式可以没有 base（概念 mask 就是形状）。
    if args.multi:
        base_strs = [s.strip() for s in args.multi.split(";") if s.strip()]
    elif args.base:
        base_strs = [args.base]
    else:
        base_strs = []

    if not base_strs and args.shape_source == "template":
        raise ValueError("--base or --multi is required for --shape-source template unless --self-test")
    if args.shape_source == "content" and not base_strs:
        raise ValueError("--shape-source content requires at least one content texture via --base/--multi")

    base_paths = [normalize_path(s) for s in base_strs]
    for p in base_paths:
        if not p.exists():
            raise FileNotFoundError("base/content PNG not found: %s" % p)

    # 解析 raw（若提供）
    raw_data = None
    if args.raw:
        raw_text = read_text_or_inline(args.raw)
        raw_data = parse_raw_answer(raw_text)

    # 全局 palette/pattern（CLI 显式 > raw 单块 > 默认）
    global_palette = None
    if args.palette:
        global_palette = parse_palette_string(args.palette)
    elif raw_data and len(raw_data) == 1 and raw_data[0]["palette"]:
        global_palette = raw_data[0]["palette"]

    global_pattern = None
    if args.pattern:
        global_pattern = load_pattern_arg(args.pattern)
    elif raw_data and len(raw_data) == 1 and raw_data[0]["pattern"] is not None:
        global_pattern = raw_data[0]["pattern"]

    if args.shape_source in ("concept", "content"):
        # 概念/内容模式：单张输出（通常是一个 cross 贴图），多个 base 只作为
        # 内容贴图/颜色参考。
        out_paths = [normalize_path(args.output)] if args.output else [Path("composed.png")]
        source_label = args.shape_source
        if not args.concept and args.shape_source in ("content", "concept"):
            # 不强制要求 --concept：内置蘑菇概念卡可离线 fallback。
            pass
        concept_path = normalize_path(args.concept) if args.concept else None
        mask_img = build_concept_mask(concept_path)
        pattern = global_pattern
        palette = global_palette or DEFAULT_PALETTE
        if args.shape_source == "content":
            out_img = compose_concept_asset(mask_img, palette, pattern, base_paths, args.map)
        else:
            out_img = compose_concept_asset(mask_img, palette, pattern, None, args.map)
        out_path = out_paths[0]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_img.convert("RGBA").save(out_path)
        iou = shape_iou(mask_img, out_img)
        log_message(
            "compose shape_source=%s concept=%s base=%s mode=%s palette=%d pattern=%s "
            "output=%s shape_iou=%.4f"
            % (source_label, concept_path, ";".join(str(p) for p in base_paths),
               args.mode, len(palette) if palette else 0,
               "yes" if pattern is not None else "no", out_path, iou)
        )
        print("OK shape_source=%s -> %s shape_iou=%.4f" % (source_label, out_path, iou))
        return 0

    # template 模式：保留原有多 face / 单 face 行为。
    base_stems = [p.stem for p in base_paths]
    out_paths = resolve_output_paths(args.output, len(base_paths), base_stems)

    for i, (base_path, out_path) in enumerate(zip(base_paths, out_paths)):
        base_img = Image.open(base_path)

        # 每个 face 优先取对应 raw 块，否则用全局单块
        raw_item = None
        if raw_data:
            if i < len(raw_data):
                raw_item = raw_data[i]
            elif len(raw_data) == 1:
                raw_item = raw_data[0]

        palette = global_palette
        if palette is None and raw_item and raw_item["palette"]:
            palette = raw_item["palette"]
        if palette is None:
            palette = DEFAULT_PALETTE

        pattern = global_pattern
        if pattern is None and raw_item and raw_item["pattern"] is not None:
            pattern = raw_item["pattern"]

        if args.mode == "mask-recolor":
            out_img = compose_mask_recolor(base_img, palette, args.map)
        elif args.mode == "pattern-overlay":
            if pattern is None:
                raise ValueError("pattern-overlay requires --pattern or a pattern in --raw")
            out_img = compose_pattern_overlay(base_img, pattern)
        else:
            raise ValueError("unknown mode: %s" % args.mode)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_img.convert("RGBA").save(out_path)
        iou = shape_iou(base_img, out_img)
        log_message(
            "compose base=%s mode=%s palette=%d pattern=%s output=%s shape_iou=%.4f"
            % (base_path, args.mode, len(palette), "yes" if pattern is not None else "no",
               out_path, iou)
        )
        print("OK base=%s mode=%s -> %s shape_iou=%.4f" % (base_path, args.mode, out_path, iou))

    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.self_test:
            return run_self_test()
        return run_compose(args)
    except Exception as exc:  # noqa: BLE001
        log_message("ERROR: %s" % exc)
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
