#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_pixel_asset.py — 通用 16x16 像素资产检查器。

该脚本只做“通用几何/颜色/描边/部件分离”的像素级证据量化，不绑定任何物品名或
具体形状。它可作为生成流程的冒烟质检，也可作为独立 CLI 输出 JSON/MD evidence。

检查项
------
1. non-empty       : 不透明像素数 >= ``--opaque-min``（默认 20）。
2. bbox            : 尺寸是否为 16x16；剪影 bbox 四周至少有 ``--min-margin``
                     像素透明（默认 1px，不贴边）。
3. border/描边     : 沿剪影外轮廓（与透明/画布外相邻的不透明像素）中，亮度
                     低于 ``--border-dark-lum`` 的暗色像素占比是否 >=
                     ``--min-border-dark-ratio``（默认 0.15）。同时输出边界与内部
                     平均亮度差作为“外轮廓邻域色差”参考。
4. light/dark 色阶 : 不透明像素按亮度分桶，要求同时有暗色（<80）、亮色（>=160）
                     以及明确的主色（出现次数最多的颜色）。阈值可用参数覆盖。
5. part separation : 4-连通非透明像素连通块数 >= 2 视为“有部件分离”。默认仅
                     报告指标；传入 ``--require-separation`` 时把该项纳入
                     PASS/FAIL 判定。

用法
----
    python3 check_pixel_asset.py examples/skeleton_staff/sprite.png
    python3 check_pixel_asset.py examples/skeleton_staff/sprite.png --out evidence.json
    python3 check_pixel_asset.py examples/skeleton_staff/sprite.png --out evidence.md \
        --require-separation
    python3 check_pixel_asset.py --self-test

依赖：仅 Pillow + Python 标准库。不依赖其它项目的私有模型。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow is required: pip install pillow") from exc

TOOL_NAME = "check_pixel_asset.py"
VERSION = "1.0.0"
DEFAULT_SIZE = (16, 16)
DEFAULT_OPAQUE_MIN = 20
DEFAULT_ALPHA_MIN = 8
DEFAULT_MIN_MARGIN = 1
DEFAULT_BORDER_DARK_LUM = 90
DEFAULT_MIN_BORDER_DARK_RATIO = 0.15
DEFAULT_DARK_LUM = 80
DEFAULT_BRIGHT_LUM = 160
DEFAULT_MIN_BUCKET_PX = 2
DEFAULT_MIN_MAIN_PX = 2
DEFAULT_THIN_RATIO = 0.5
DEFAULT_THIN_MIN_BBOX_PX = 10


def normalize_path(path: str | Path) -> Path:
    """接受 Windows 风格路径（C:\\...）在 WSL 下转换为 /mnt/c/...。"""
    s = str(path)
    if s.startswith("\\\\") and s[2:3].isalpha() and s[3:4] in ("\\", "/"):
        s = s.replace("\\", "/")
    if len(s) >= 3 and s[0].isalpha() and s[1] == ":" and s[2] in ("\\", "/"):
        drive = s[0].lower()
        rest = s[2:].replace("\\", "/")
        return Path("/mnt") / drive / rest
    return Path(s)


def _luminance(r: int, g: int, b: int) -> float:
    """Rec.709 亮度，返回 0..255 的浮点值。"""
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _alpha_mask(px, width: int, height: int, alpha_min: int) -> set[tuple[int, int]]:
    """返回不透明像素坐标集合。alpha 阈值默认 8，与 text_to_texture 一致。"""
    mask = set()
    for y in range(height):
        for x in range(width):
            r, g, b, a = px[x, y]
            if a > alpha_min:
                mask.add((x, y))
    return mask


def _connected_components(mask: set[tuple[int, int]]) -> list[int]:
    """4-连通分量，返回每个分量的像素数量。"""
    if not mask:
        return []
    seen: set[tuple[int, int]] = set()
    sizes: list[int] = []
    for start in mask:
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        size = 0
        while stack:
            x, y = stack.pop()
            size += 1
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (x + dx, y + dy)
                if nxt in mask and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        sizes.append(size)
    return sorted(sizes, reverse=True)


def _outer_boundary(mask: set[tuple[int, int]], width: int, height: int) -> set[tuple[int, int]]:
    """剪影外轮廓：不透明像素中，至少有一个 4-邻域是透明/画布外的像素。"""
    boundary = set()
    for x, y in mask:
        if (
            (x + 1, y) not in mask or (x - 1, y) not in mask
            or (x, y + 1) not in mask or (x, y - 1) not in mask
        ):
            boundary.add((x, y))
    return boundary


def _palette_buckets(mask: set[tuple[int, int]], px, dark_lum: int, bright_lum: int) -> dict:
    """按亮度分桶，并统计主色（出现最多次的 RGBA 颜色）。"""
    from collections import Counter

    lums: list[float] = []
    color_counts: Counter[tuple[int, int, int, int]] = Counter()
    for x, y in mask:
        r, g, b, a = px[x, y]
        lums.append(_luminance(r, g, b))
        color_counts[(r, g, b, a)] += 1

    dark_count = sum(1 for lum in lums if lum < dark_lum)
    mid_count = sum(1 for lum in lums if dark_lum <= lum < bright_lum)
    bright_count = sum(1 for lum in lums if lum >= bright_lum)
    dominant = color_counts.most_common(1)[0] if color_counts else (None, 0)
    dominant_color = list(dominant[0]) if dominant[0] is not None else None
    dominant_count = dominant[1]
    total = len(lums)
    return {
        "total_pixels": total,
        "dark_count": dark_count,
        "mid_count": mid_count,
        "bright_count": bright_count,
        "dark_lum": dark_lum,
        "bright_lum": bright_lum,
        "dominant_color": dominant_color,
        "dominant_color_count": dominant_count,
        "dominant_color_ratio": round(dominant_count / total, 4) if total else 0.0,
    }


def analyze_png(path: str | Path, args: argparse.Namespace) -> dict:
    """分析单张 PNG，返回结构化 evidence。"""
    input_path = normalize_path(path)
    with Image.open(input_path) as im:
        rgba = im.convert("RGBA")
        width, height = rgba.size
        px = rgba.load()

    mask = _alpha_mask(px, width, height, args.alpha_min)
    opaque_count = len(mask)

    # ---- non-empty ----
    non_empty_ok = opaque_count >= args.opaque_min

    # ---- size / bbox ----
    exp_w, exp_h = DEFAULT_SIZE
    if args.expected_size:
        try:
            exp_w, exp_h = (int(v) for v in args.expected_size.lower().split("x", 1))
        except ValueError:
            exp_w, exp_h = DEFAULT_SIZE
    size_ok = (width, height) == (exp_w, exp_h)

    if mask:
        bbox = [
            min(x for x, _ in mask),
            min(y for _, y in mask),
            max(x for x, _ in mask) + 1,
            max(y for _, y in mask) + 1,
        ]
        left, top, right, bottom = bbox
        margins = {
            "left": left,
            "top": top,
            "right": width - right,
            "bottom": height - bottom,
        }
        bbox_ok = all(v >= args.min_margin for v in margins.values())
        bbox_area = (right - left) * (bottom - top)
        opaque_ratio = opaque_count / bbox_area if bbox_area > 0 else 0.0
    else:
        bbox = None
        margins = {"left": 0, "top": 0, "right": 0, "bottom": 0}
        bbox_ok = False
        opaque_ratio = 0.0

    # ---- thin / negative-space（细长部件启发式）----
    thin_min_bbox_px = int(getattr(args, "thin_min_bbox_px", DEFAULT_THIN_MIN_BBOX_PX))
    thin_ratio = float(getattr(args, "thin_ratio", DEFAULT_THIN_RATIO))
    thin_part = False
    if bbox is not None:
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
        # bbox 明显大于 1px 物体，但内部负空间多（opaque_ratio 低）。
        thin_part = max(bw, bh) >= thin_min_bbox_px and opaque_ratio <= thin_ratio
    thin_required = bool(getattr(args, "require_thin_part", False))
    thin_ok = thin_part if thin_required else None

    # ---- border / 描边 ----
    boundary = _outer_boundary(mask, width, height)
    boundary_lums = [_luminance(*px[x, y][:3]) for x, y in boundary]
    if boundary_lums:
        boundary_dark_count = sum(
            1 for lum in boundary_lums if lum <= args.border_dark_lum
        )
        boundary_dark_ratio = boundary_dark_count / len(boundary_lums)
        mean_boundary_lum = sum(boundary_lums) / len(boundary_lums)
    else:
        boundary_dark_count = 0
        boundary_dark_ratio = 0.0
        mean_boundary_lum = 0.0

    all_lums = [_luminance(*px[x, y][:3]) for x, y in mask]
    mean_all_lum = sum(all_lums) / len(all_lums) if all_lums else 0.0
    # 外轮廓邻域色差：边界平均亮度相对全体平均亮度的差异（负数表示边界偏暗）。
    boundary_vs_all_delta = mean_boundary_lum - mean_all_lum
    border_ok = (
        len(boundary) >= args.min_border_px
        and boundary_dark_ratio >= args.min_border_dark_ratio
    )

    # ---- light/dark 色阶 ----
    palette = _palette_buckets(mask, px, args.dark_lum, args.bright_lum)
    palette_ok = (
        palette["dark_count"] >= args.min_bucket_px
        and palette["bright_count"] >= args.min_bucket_px
        and palette["dominant_color_count"] >= args.min_main_px
    )

    # ---- part separation ----
    component_sizes = _connected_components(mask)
    component_count = len(component_sizes)
    part_separation = component_count >= args.min_components
    separation_required = bool(args.require_separation)
    separation_ok = (
        part_separation if separation_required else None
    )

    # ---- verdict ----
    checks = [
        {
            "id": "non_empty",
            "ok": non_empty_ok,
            "summary": "不透明像素数 >= %d" % args.opaque_min,
            "detail": "opaque_pixels=%d threshold=%d" % (opaque_count, args.opaque_min),
        },
        {
            "id": "size",
            "ok": size_ok,
            "summary": "尺寸为 %dx%d" % (exp_w, exp_h),
            "detail": "size=%dx%d" % (width, height),
        },
        {
            "id": "bbox",
            "ok": bbox_ok,
            "summary": "剪影 bbox 四周至少 %dpx 透明" % args.min_margin,
            "detail": "bbox=%s margins=%s" % (bbox, margins),
        },
        {
            "id": "border",
            "ok": border_ok,
            "summary": "外轮廓存在足够暗色描边像素（暗色边界占比 >= %.2f）" % args.min_border_dark_ratio,
            "detail": "boundary_pixels=%d dark_boundary=%d ratio=%.4f"
            % (len(boundary), boundary_dark_count, boundary_dark_ratio),
        },
        {
            "id": "palette",
            "ok": palette_ok,
            "summary": "调色板同时含暗色/亮色/主色",
            "detail": "dark=%d mid=%d bright=%d dominant=%s count=%d"
            % (
                palette["dark_count"],
                palette["mid_count"],
                palette["bright_count"],
                palette["dominant_color"],
                palette["dominant_color_count"],
            ),
        },
        {
            "id": "thin_part",
            "ok": thin_ok,
            "summary": "细长部件/负空间启发式：bbox 较大但 opaque_ratio<=%.2f" % thin_ratio,
            "detail": "bbox=%s opaque_ratio=%.4f thin=%s (min_bbox_px=%d)"
            % (bbox, opaque_ratio, thin_part, thin_min_bbox_px),
        },
    ]
    if separation_required:
        checks.append(
            {
                "id": "part_separation",
                "ok": separation_ok,
                "summary": "要求部件分离（连通块 >= %d）" % args.min_components,
                "detail": "components=%d sizes=%s" % (component_count, component_sizes),
            }
        )
    else:
        checks.append(
            {
                "id": "part_separation",
                "ok": None,
                "summary": "部件分离为启发式报告（未用 --require-separation 纳入判定）",
                "detail": "components=%d sizes=%s" % (component_count, component_sizes),
            }
        )

    overall = "PASS" if all(c["ok"] for c in checks if c["ok"] is not None) else "FAIL"

    return {
        "tool": TOOL_NAME,
        "version": VERSION,
        "input": {
            "path": str(input_path),
            "width": width,
            "height": height,
        },
        "metrics": {
            "opaque_count": opaque_count,
            "opaque_min": args.opaque_min,
            "alpha_min": args.alpha_min,
            "size_ok": size_ok,
            "bbox": bbox,
            "bbox_area": (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) if bbox is not None else 0,
            "opaque_ratio": round(opaque_ratio, 4),
            "margins": margins,
            "min_margin": args.min_margin,
            "bbox_ok": bbox_ok,
            "thin_part": thin_part,
            "thin_ratio": thin_ratio,
            "thin_min_bbox_px": thin_min_bbox_px,
            "thin_required": thin_required,
            "thin_ok": thin_ok,
            "boundary_pixel_count": len(boundary),
            "boundary_dark_pixel_count": boundary_dark_count,
            "boundary_dark_ratio": round(boundary_dark_ratio, 4),
            "boundary_dark_lum": args.border_dark_lum,
            "min_border_dark_ratio": args.min_border_dark_ratio,
            "mean_boundary_luminance": round(mean_boundary_lum, 2),
            "mean_all_luminance": round(mean_all_lum, 2),
            "boundary_vs_all_delta": round(boundary_vs_all_delta, 2),
            "border_ok": border_ok,
            "palette": palette,
            "palette_ok": palette_ok,
            "component_count": component_count,
            "component_sizes": component_sizes,
            "part_separation": part_separation,
            "min_components": args.min_components,
            "separation_required": separation_required,
            "separation_ok": separation_ok,
        },
        "verdict": {
            "overall": overall,
            "checks": checks,
        },
    }


def render_markdown(data: dict) -> str:
    """渲染为 Markdown evidence。"""
    m = data["metrics"]
    v = data["verdict"]
    lines = [
        "# Pixel Asset Check Evidence",
        "",
        "- Tool: `%s` v%s" % (data["tool"], data["version"]),
        "- Input: `%s` (%dx%d)" % (data["input"]["path"], data["input"]["width"], data["input"]["height"]),
        "- Verdict: **%s**" % v["overall"],
        "",
        "## Checks",
        "",
    ]
    for c in v["checks"]:
        ok = c["ok"]
        if ok is True:
            status = "PASS"
        elif ok is False:
            status = "FAIL"
        else:
            status = "INFO"
        lines.append("- **%s** [%s]: %s  " % (c["id"], status, c["summary"]))
        lines.append("  - %s" % c["detail"])

    lines += [
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        "| opaque_count | %d |" % m["opaque_count"],
        "| opaque_min | %d |" % m["opaque_min"],
        "| size | %dx%d |" % (data["input"]["width"], data["input"]["height"]),
        "| bbox | %s |" % m["bbox"],
        "| bbox_area | %d |" % m["bbox_area"],
        "| opaque_ratio | %.4f |" % m["opaque_ratio"],
        "| margins | %s |" % m["margins"],
        "| boundary_pixel_count | %d |" % m["boundary_pixel_count"],
        "| boundary_dark_count | %d |" % m["boundary_dark_pixel_count"],
        "| boundary_dark_ratio | %.4f |" % m["boundary_dark_ratio"],
        "| boundary_vs_all_delta | %.2f |" % m["boundary_vs_all_delta"],
        "| palette | dark=%d mid=%d bright=%d |"
        % (m["palette"]["dark_count"], m["palette"]["mid_count"], m["palette"]["bright_count"]),
        "| dominant_color | %s |" % m["palette"]["dominant_color"],
        "| component_count | %d |" % m["component_count"],
        "| component_sizes | %s |" % m["component_sizes"],
        "| separation_ok | %s |" % m["separation_ok"],
        "| thin_part | %s |" % m["thin_part"],
        "| thin_ratio | %.2f |" % m["thin_ratio"],
        "| thin_min_bbox_px | %d |" % m["thin_min_bbox_px"],
        "",
        "## Notes",
        "",
        "- 本检查为通用像素启发式，不绑定具体物品名或形状。",
        "- `part_separation` 默认仅报告；用 `--require-separation` 才会纳入 verdict。",
        "- `thin_part` 默认仅报告；用 `--require-thin-part` 才会纳入 verdict。",
        "- 阈值可通过 CLI 参数调整，产生可复现的证据文件。",
        "",
    ]
    return "\n".join(lines)


def render_console(data: dict) -> str:
    """渲染为终端可读摘要。"""
    m = data["metrics"]
    v = data["verdict"]
    lines = [
        "[%s] %s (%dx%d) -> %s"
        % (data["tool"], data["input"]["path"], data["input"]["width"], data["input"]["height"], v["overall"]),
        "  opaque=%d/%d bbox=%s bbox_area=%d opaque_ratio=%.4f margins=%s"
        % (m["opaque_count"], m["opaque_min"], m["bbox"], m["bbox_area"], m["opaque_ratio"], m["margins"]),
        "  border: boundary=%d dark=%d ratio=%.4f ok=%s"
        % (
            m["boundary_pixel_count"],
            m["boundary_dark_pixel_count"],
            m["boundary_dark_ratio"],
            m["border_ok"],
        ),
        "  palette: dark=%d mid=%d bright=%d dominant=%s ok=%s"
        % (
            m["palette"]["dark_count"],
            m["palette"]["mid_count"],
            m["palette"]["bright_count"],
            m["palette"]["dominant_color"],
            m["palette_ok"],
        ),
        "  components=%d sizes=%s separation=%s thin=%s ratio=%s"
        % (m["component_count"], m["component_sizes"], m["part_separation"], m["thin_part"], m["opaque_ratio"]),
    ]
    for c in v["checks"]:
        status = "PASS" if c["ok"] is True else ("FAIL" if c["ok"] is False else "INFO")
        lines.append("  [%s] %-24s %s" % (status, c["id"], c["detail"]))
    return "\n".join(lines)


def _self_test() -> int:
    """用合成图片验证脚本主要判定逻辑。"""
    import io

    # 36x? 不，创建 16x16 合成资产：
    #   - 主体：4x4 方块，带深色描边、亮色高光、透明边距
    #   - 一个独立 2x2 小块，构成两个连通分量
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
    px[11, 11] = (40, 40, 60, 255)
    px[12, 11] = (40, 40, 60, 255)
    px[11, 12] = (40, 40, 60, 255)
    px[12, 12] = (40, 40, 60, 255)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "synthetic.png"
        path.write_bytes(buf.getvalue())
        args = argparse.Namespace(
            alpha_min=DEFAULT_ALPHA_MIN,
            opaque_min=DEFAULT_OPAQUE_MIN,
            expected_size="16x16",
            min_margin=DEFAULT_MIN_MARGIN,
            border_dark_lum=DEFAULT_BORDER_DARK_LUM,
            min_border_dark_ratio=DEFAULT_MIN_BORDER_DARK_RATIO,
            min_border_px=2,
            dark_lum=DEFAULT_DARK_LUM,
            bright_lum=DEFAULT_BRIGHT_LUM,
            min_bucket_px=DEFAULT_MIN_BUCKET_PX,
            min_main_px=DEFAULT_MIN_MAIN_PX,
            min_components=2,
            require_separation=True,
            thin_ratio=DEFAULT_THIN_RATIO,
            thin_min_bbox_px=DEFAULT_THIN_MIN_BBOX_PX,
            require_thin_part=False,
        )
        data = analyze_png(path, args)
        assert data["metrics"]["opaque_count"] >= 20
        assert data["metrics"]["size_ok"]
        assert data["metrics"]["bbox_ok"]
        assert data["metrics"]["border_ok"]
        assert data["metrics"]["palette_ok"]
        assert data["metrics"]["component_count"] >= 2
        assert data["metrics"]["part_separation"]
        assert data["verdict"]["overall"] == "PASS"

        # 全透明：validate 会 FAIL，且不应异常。
        empty = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        epath = Path(td) / "empty.png"
        empty.save(epath)
        edata = analyze_png(epath, args)
        assert edata["verdict"]["overall"] == "FAIL"
        assert edata["metrics"]["opaque_count"] == 0
    print("check_pixel_asset self-test: PASS")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="通用 16x16 像素资产检查器（不绑定物品名）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("sprite", nargs="?", type=str, default=None,
                        help="输入 PNG 路径")
    parser.add_argument("--out", type=str, default=None,
                        help="输出 evidence 文件；扩展名 .json 或 .md 决定格式")
    parser.add_argument("--opaque-min", type=int, default=DEFAULT_OPAQUE_MIN,
                        help="不透明像素数下限（默认 20）")
    parser.add_argument("--alpha-min", type=int, default=DEFAULT_ALPHA_MIN,
                        help="判定不透明的 alpha 阈值（默认 8）")
    parser.add_argument("--expected-size", type=str, default="16x16",
                        help="期望尺寸，例如 16x16")
    parser.add_argument("--min-margin", type=int, default=DEFAULT_MIN_MARGIN,
                        help="剪影 bbox 四周至少多少透明像素（默认 1）")
    parser.add_argument("--border-dark-lum", type=int, default=DEFAULT_BORDER_DARK_LUM,
                        help="描边暗色像素的亮度阈值（默认 90）")
    parser.add_argument("--min-border-dark-ratio", type=float, default=DEFAULT_MIN_BORDER_DARK_RATIO,
                        help="外轮廓暗色像素占比下限（默认 0.15）")
    parser.add_argument("--min-border-px", type=int, default=2,
                        help="外轮廓像素数下限（默认 2）")
    parser.add_argument("--dark-lum", type=int, default=DEFAULT_DARK_LUM,
                        help="暗色桶亮度上限（默认 80）")
    parser.add_argument("--bright-lum", type=int, default=DEFAULT_BRIGHT_LUM,
                        help="亮色桶亮度下限（默认 160）")
    parser.add_argument("--min-bucket-px", type=int, default=DEFAULT_MIN_BUCKET_PX,
                        help="暗色/亮色桶最少像素数（默认 2）")
    parser.add_argument("--min-main-px", type=int, default=DEFAULT_MIN_MAIN_PX,
                        help="主色最少像素数（默认 2）")
    parser.add_argument("--require-separation", action="store_true",
                        help="将部件分离（连通块>=2）纳入 PASS/FAIL 判定；默认仅报告")
    parser.add_argument("--min-components", type=int, default=2,
                        help="判定部件分离所需的最少连通块数（默认 2）")
    parser.add_argument("--thin-ratio", type=float, default=DEFAULT_THIN_RATIO,
                        help="细长部件负空间判定：opaque_ratio 上限（默认 0.5）")
    parser.add_argument("--thin-min-bbox-px", type=int, default=DEFAULT_THIN_MIN_BBOX_PX,
                        help="细长部件判定：bbox 长边最少像素数（默认 10）")
    parser.add_argument("--require-thin-part", action="store_true",
                        help="将细长部件/负空间启发式纳入 PASS/FAIL 判定；默认仅报告")
    parser.add_argument("--self-test", action="store_true",
                        help="运行合成图片自测并退出")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    if not args.sprite:
        parser.error("缺少输入 PNG 路径")

    data = analyze_png(args.sprite, args)

    if args.out:
        out_path = normalize_path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        suffix = out_path.suffix.lower()
        if suffix == ".json":
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
        elif suffix == ".md":
            out_path.write_text(render_markdown(data), encoding="utf-8")
        else:
            print(
                "ERROR: --out 扩展名必须为 .json 或 .md，当前为 %r" % suffix,
                file=sys.stderr,
            )
            return 2
        print(render_console(data))
        print("evidence written: %s" % out_path)
    else:
        print(render_console(data))

    # 检查未通过时以非零退出码提示；证据文件仍会正常写出。
    return 1 if data["verdict"]["overall"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
