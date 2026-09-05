#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_tiling.py — 检查 block_multi 方块贴图能否拼成完整方块（edge/tile check）。

检查项
------
- ``side_wrap``    : side 贴图左右边是否一致（四个侧面共用同一张 side 时，
  绕方块一圈需要 side.left == side.right，即左右可无缝平铺）。
- ``top_side``     : side 顶部边缘与 top 贴图四边是否颜色连续（若有透明像素也算 FAIL，
  因为 block_multi 的 alpha 契约是 False）。
- ``bottom_side``  : side 底部边缘与 bottom 贴图四边是否颜色连续。

用法
----
    python3 check_tiling.py --top a_top.png --side a_side.png --bottom a_bottom.png \\
        --name bricks --out-dir evidence/tiling
    python3 check_tiling.py --self-test

输出
----
默认打印人类可读结果；指定 ``--out-json`` / ``--out-md`` 写 JSON/Markdown。
指定 ``--out-dir`` 时按 ``<name>_tiling.json`` / ``<name>_tiling.md`` 写入。

阈值
----
``--threshold`` 为 RGB 三个通道的最大允许差值（0-255，默认 32）。
默认要求边缘完全不透明（内部开关 ``require_opaque=True``）：只要边缘像素 alpha<128
就视为 FAIL。对真正可用的 block_multi 方块，顶/侧/底三张 16x16 贴图边缘必须完全不透明；
``--allow-transparent`` 可关闭该检查，只比较颜色。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow is required: pip install pillow") from exc

DEFAULT_THRESHOLD = 32
ALPHA_VISIBLE = 128
DEFAULT_SIDE_ORDER = ("north", "east", "south", "west")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _color_distance(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    """RGB 最大通道差，用于“颜色/图案不突变”。"""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2]))


def _is_visible(c: tuple[int, int, int, int]) -> bool:
    return c[3] >= ALPHA_VISIBLE


def _edge_metric(
    pairs: list[tuple[tuple[int, int], tuple[int, int]]],
    img_a: Image.Image,
    img_b: Image.Image,
    threshold: int,
    require_opaque: bool,
) -> dict:
    """计算一条共享边的颜色/alpha 指标。"""
    diffs: list[int] = []
    transparent_pairs = 0
    for ca, cb in pairs:
        pa = img_a.getpixel(ca)
        pb = img_b.getpixel(cb)
        d = _color_distance(pa, pb)
        diffs.append(d)
        if require_opaque and (not _is_visible(pa) or not _is_visible(pb)):
            transparent_pairs += 1

    max_diff = max(diffs) if diffs else 0
    avg_diff = sum(diffs) / len(diffs) if diffs else 0.0
    status = (
        "PASS"
        if (not require_opaque or transparent_pairs == 0) and max_diff <= threshold
        else "FAIL"
    )
    return {
        "status": status,
        "max_diff": max_diff,
        "avg_diff": round(avg_diff, 2),
        "transparent_pairs": transparent_pairs,
        "total_pairs": len(diffs),
        "threshold": threshold,
    }


def _best_orientation_metric(
    side_coords: list[tuple[int, int]],
    target_coords: list[tuple[int, int]],
    side_img: Image.Image,
    target_img: Image.Image,
    threshold: int,
    require_opaque: bool,
) -> tuple[dict, bool]:
    """在正向/反向两种 UV 方向中选择较小差值的映射。

    返回 (metric, reversed)。“best”意味着 Minecraft 允许的某个方向；若两个方向都
    超出阈值或都含透明，则仍会 FAIL。
    """
    if len(side_coords) != len(target_coords):
        raise ValueError(
            "edge length mismatch: side=%d target=%d" % (len(side_coords), len(target_coords))
        )
    candidates: list[tuple[dict, bool]] = []
    for rev in (False, True):
        tcoords = list(reversed(target_coords)) if rev else target_coords
        pairs = list(zip(side_coords, tcoords))
        metric = _edge_metric(pairs, side_img, target_img, threshold, require_opaque)
        candidates.append((metric, rev))
    # 透明像素数优先，其次颜色差；两者都相同时可选正向（保持输出稳定）。
    best = min(
        candidates,
        key=lambda c: (c[0]["transparent_pairs"], c[0]["max_diff"], c[1]),
    )
    return best


# ---------------------------------------------------------------------------
# Core check
# ---------------------------------------------------------------------------

def _edge_coords(edge_name: str, width: int, height: int) -> list[tuple[int, int]]:
    if edge_name == "top":
        return [(x, 0) for x in range(width)]
    if edge_name == "bottom":
        return [(x, height - 1) for x in range(width)]
    if edge_name == "left":
        return [(0, y) for y in range(height)]
    if edge_name == "right":
        return [(width - 1, y) for y in range(height)]
    raise ValueError("unknown edge: %r" % edge_name)


def check_tiling(
    top_path: str | Path,
    side_path: str | Path,
    bottom_path: str | Path,
    name: str | None = None,
    threshold: int = DEFAULT_THRESHOLD,
    require_opaque: bool = True,
    side_order: tuple[str, ...] | list[str] | None = None,
) -> dict:
    """执行贴图拼贴检查，返回可 JSON 序列化的结果字典。"""
    top_path = Path(top_path)
    side_path = Path(side_path)
    bottom_path = Path(bottom_path)
    if not top_path.exists():
        raise FileNotFoundError("top texture not found: %s" % top_path)
    if not side_path.exists():
        raise FileNotFoundError("side texture not found: %s" % side_path)
    if not bottom_path.exists():
        raise FileNotFoundError("bottom texture not found: %s" % bottom_path)

    top = Image.open(top_path).convert("RGBA")
    side = Image.open(side_path).convert("RGBA")
    bottom = Image.open(bottom_path).convert("RGBA")

    if top.size != side.size or top.size != bottom.size:
        raise ValueError(
            "top/side/bottom must have the same size; got top=%s side=%s bottom=%s"
            % (top.size, side.size, bottom.size)
        )
    width, height = top.size
    if width != height:
        # 非正方形贴图也能做左右 wrap；但当前 Minecraft block 纹理通常 16x16。
        print(
            "[warn] non-square block textures (%dx%d) may not follow Minecraft 16x16 cube convention"
            % (width, height),
            file=sys.stderr,
        )

    # 1. side wrap-around
    side_left = [(0, y) for y in range(height)]
    side_right = [(width - 1, y) for y in range(height)]
    side_wrap_metric = _edge_metric(
        list(zip(side_left, side_right)), side, side, threshold, require_opaque
    )

    # 2. top/side: side 顶部边缘 vs top 四边（每个边取最佳方向）
    side_top_coords = [(x, 0) for x in range(width)]
    top_edges: dict[str, dict] = {}
    top_metrics: list[dict] = []
    for edge_name in ("top", "bottom", "left", "right"):
        target_coords = _edge_coords(edge_name, width, height)
        metric, rev = _best_orientation_metric(
            side_top_coords, target_coords, side, top, threshold, require_opaque
        )
        escaped = metric.copy()
        escaped["edge"] = edge_name
        escaped["orientation"] = "reversed" if rev else "forward"
        top_edges[edge_name] = escaped
        top_metrics.append(escaped)

    # 3. bottom/side: side 底部边缘 vs bottom 四边
    side_bottom_coords = [(x, height - 1) for x in range(width)]
    bottom_edges: dict[str, dict] = {}
    bottom_metrics: list[dict] = []
    for edge_name in ("top", "bottom", "left", "right"):
        target_coords = _edge_coords(edge_name, width, height)
        metric, rev = _best_orientation_metric(
            side_bottom_coords, target_coords, side, bottom, threshold, require_opaque
        )
        escaped = metric.copy()
        escaped["edge"] = edge_name
        escaped["orientation"] = "reversed" if rev else "forward"
        bottom_edges[edge_name] = escaped
        bottom_metrics.append(escaped)

    checks = {
        "side_wrap": {
            "status": side_wrap_metric["status"],
            "gate": "left==right (per-row)",
            "metric": side_wrap_metric,
        },
        "top_side": {
            "status": "PASS" if all(m["status"] == "PASS" for m in top_metrics) else "FAIL",
            "gate": "side.top vs top.{top,bottom,left,right}",
            "edges": top_edges,
        },
        "bottom_side": {
            "status": "PASS" if all(m["status"] == "PASS" for m in bottom_metrics) else "FAIL",
            "gate": "side.bottom vs bottom.{top,bottom,left,right}",
            "edges": bottom_edges,
        },
    }
    overall = "PASS" if all(c["status"] == "PASS" for c in checks.values()) else "FAIL"

    # 简洁的失败原因
    failed: list[str] = []
    if checks["side_wrap"]["status"] == "FAIL":
        m = checks["side_wrap"]["metric"]
        failed.append(
            "side_wrap: max_diff=%d/%d transparent_pairs=%d/%d"
            % (m["max_diff"], threshold, m["transparent_pairs"], m["total_pairs"])
        )
    for check_name in ("top_side", "bottom_side"):
        if checks[check_name]["status"] == "FAIL":
            for edge in ("top", "bottom", "left", "right"):
                m = checks[check_name]["edges"][edge]
                if m["status"] == "FAIL":
                    failed.append(
                        "%s.%s: max_diff=%d/%d transparent_pairs=%d/%d"
                        % (
                            check_name,
                            edge,
                            m["max_diff"],
                            threshold,
                            m["transparent_pairs"],
                            m["total_pairs"],
                        )
                    )

    side_order = tuple(side_order) if side_order is not None else DEFAULT_SIDE_ORDER
    if len(side_order) != 4 or len(set(side_order)) != 4:
        raise ValueError("side_order must contain exactly 4 unique side names, got %r" % (side_order,))

    return {
        "tool": "check_tiling.py",
        "asset": name or Path(top_path).stem,
        "side_order": list(side_order),
        "images": {
            "top": str(top_path),
            "side": str(side_path),
            "bottom": str(bottom_path),
            "size": "%dx%d" % (width, height),
        },
        "threshold": threshold,
        "require_opaque": require_opaque,
        "status": overall,
        "checks": checks,
        "failed_checks": failed,
        "message": (
            "PASS: block_multi textures tile into a cube (edge continuity OK)."
            if overall == "PASS"
            else "FAIL: edge continuity or opaque-edge requirement not satisfied. " + "; ".join(failed)
        ),
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _dump_json(result: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _render_markdown(result: dict) -> str:
    lines = [
        "# Tiling Check: %s" % result["asset"],
        "",
        "- Tool: `%s`" % result["tool"],
        "- Images: top=`%s`, side=`%s`, bottom=`%s`"
        % (
            result["images"]["top"],
            result["images"]["side"],
            result["images"]["bottom"],
        ),
        "- Size: `%s`" % result["images"]["size"],
        "- Threshold: %d (RGB max channel diff)" % result["threshold"],
        "- Require opaque edges: %s" % ("yes" if result["require_opaque"] else "no"),
        "- Side order: `%s`" % ",".join(result.get("side_order", ["north", "east", "south", "west"])),
        "- **Overall: `%s`**" % result["status"],
        "",
        "| Check | Edge | Status | MaxDiff | AvgDiff | TransparentPairs | Detail |",
        "|---|---|---|---|---|---|---|",
    ]
    def add(check_name: str, edge: str | None, metric: dict) -> None:
        status = metric["status"]
        edge_display = edge if edge is not None else "-"
        lines.append(
            "| %s | %s | %s | %d | %.2f | %d/%d | %s |"
            % (
                check_name,
                edge_display,
                status,
                metric["max_diff"],
                metric["avg_diff"],
                metric["transparent_pairs"],
                metric["total_pairs"],
                metric.get("orientation", "-"),
            )
        )

    wrap = result["checks"]["side_wrap"]
    add("side_wrap", None, wrap["metric"])
    for edge_name, metric in result["checks"]["top_side"]["edges"].items():
        add("top_side", edge_name, metric)
    for edge_name, metric in result["checks"]["bottom_side"]["edges"].items():
        add("bottom_side", edge_name, metric)

    lines.append("")
    if result["status"] == "FAIL":
        lines.append("## 失败原因 / 修复建议")
        lines.append("")
        for reason in result["failed_checks"]:
            lines.append("- " + reason)
        lines.append("")
        lines.append(
            "修复建议：block_multi 的顶/侧/底贴图边缘必须完全不透明，且 side 的左右边一致；"
            "若颜色差超阈值，应让同一材质的跨面边缘使用相同的边缘像素（可用 1px 描边/接缝统一）。"
        )
    else:
        lines.append("## 结论")
        lines.append("")
        lines.append("边缘连续：通过。")
    return "\n".join(lines) + "\n"


def _dump_markdown(result: dict, path: Path | None) -> str:
    md = _render_markdown(result)
    if path is not None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(md, encoding="utf-8")
    return md


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _make_solid_rgba(color: tuple[int, int, int, int], size: int = 16) -> Image.Image:
    img = Image.new("RGBA", (size, size), color)
    return img


def _run_self_test() -> int:
    import tempfile

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
        # PASS: 三张纯色贴图，边缘全部连续/不透明。
        top = _make_solid_rgba((100, 120, 140, 255))
        side = _make_solid_rgba((100, 120, 140, 255))
        bottom = _make_solid_rgba((100, 120, 140, 255))
        top.save(d / "pass_top.png")
        side.save(d / "pass_side.png")
        bottom.save(d / "pass_bottom.png")
        r = check_tiling(d / "pass_top.png", d / "pass_side.png", d / "pass_bottom.png")
        check("solid pass overall", r["status"] == "PASS", r["status"])

        # FAIL: side 左右边缘颜色突变。
        side_fail = _make_solid_rgba((10, 10, 10, 255))
        side_fail.putpixel((0, 0), (255, 0, 0, 255))
        side_fail.putpixel((15, 0), (0, 255, 0, 255))
        side_fail.save(d / "fail_side.png")
        r2 = check_tiling(d / "pass_top.png", d / "fail_side.png", d / "pass_bottom.png")
        check("side color mismatch fail", r2["status"] == "FAIL", ",".join(r2["failed_checks"]))

        # FAIL: 透明边缘（block_multi 应完全不透明）。
        side_trans = _make_solid_rgba((100, 120, 140, 255))
        side_trans.putpixel((0, 0), (100, 120, 140, 0))
        side_trans.save(d / "fail_trans.png")
        r3 = check_tiling(d / "pass_top.png", d / "fail_trans.png", d / "pass_bottom.png")
        check(
            "transparent edge fail with require_opaque",
            r3["status"] == "FAIL" and any("transparent_pairs" in x for x in r3["failed_checks"]),
            ",".join(r3["failed_checks"]),
        )
        r4 = check_tiling(d / "pass_top.png", d / "fail_trans.png", d / "pass_bottom.png", require_opaque=False)
        check(
            "transparent edge can pass with --allow-transparent",
            r4["status"] == "PASS",
            r4["status"],
        )

        # FAIL: bottom 与 side 底边颜色突变（bottom_side 断言）。
        bottom_fail = _make_solid_rgba((100, 120, 140, 255))
        bottom_fail.putpixel((0, 0), (255, 0, 0, 255))
        bottom_fail.save(d / "fail_bottom.png")
        r5 = check_tiling(d / "pass_top.png", d / "pass_side.png", d / "fail_bottom.png")
        check(
            "bottom color mismatch fail",
            r5["status"] == "FAIL" and any(x.startswith("bottom_side.") for x in r5["failed_checks"]),
            ",".join(r5["failed_checks"]),
        )

    print("\n".join(lines))
    print("check_tiling selftest: %s" % ("PASS" if failures == 0 else "FAIL (%d)" % failures))
    return 0 if failures == 0 else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="检查 block_multi 方块顶/侧/底贴图的边缘连续性与可拼贴性。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--top", help="top face PNG")
    parser.add_argument("--side", help="side face PNG (重复用于四个侧面)")
    parser.add_argument("--bottom", help="bottom face PNG")
    parser.add_argument("--name", default=None, help="资产名/输出文件名（默认取自 top 文件名）")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help="RGB 最大通道差阈值（默认 %d）" % DEFAULT_THRESHOLD)
    parser.add_argument("--allow-transparent", action="store_true",
                        help="忽略 alpha 透明，只比较 RGB 颜色（默认要求边缘不透明）")
    parser.add_argument("--side-order", default=None,
                        help="4 个侧面的顺序，逗号分隔（默认 north,east,south,west）")
    parser.add_argument("--out-json", default=None, help="输出 JSON 路径")
    parser.add_argument("--out-md", default=None, help="输出 Markdown 路径")
    parser.add_argument("--out-dir", default=None,
                        help="输出目录；写入 <name>_tiling.json / <name>_tiling.md")
    parser.add_argument("--self-test", action="store_true", help="运行内置自测")
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test()

    if not args.top or not args.side or not args.bottom:
        parser.error("--top, --side, --bottom are required (use --self-test for a synthetic check)")

    try:
        side_order = None
        if args.side_order:
            side_order = tuple(x.strip() for x in args.side_order.split(","))
        result = check_tiling(
            args.top,
            args.side,
            args.bottom,
            name=args.name,
            threshold=args.threshold,
            require_opaque=not args.allow_transparent,
            side_order=side_order,
        )
    except Exception as exc:  # noqa: BLE001
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1

    print("Asset: %s  Status: %s" % (result["asset"], result["status"]))
    for reason in result["failed_checks"]:
        print("  FAIL: %s" % reason)

    if args.out_dir:
        d = Path(args.out_dir)
        result["output_files"] = []
        json_path = d / ("%s_tiling.json" % result["asset"])
        md_path = d / ("%s_tiling.md" % result["asset"])
        _dump_json(result, json_path)
        _dump_markdown(result, md_path)
        result["output_files"] = [str(json_path), str(md_path)]
        # 重新写 JSON 以便包含 output_files 列表
        _dump_json(result, json_path)
        print("JSON -> %s" % json_path)
        print("MD   -> %s" % md_path)
    else:
        if args.out_json:
            _dump_json(result, Path(args.out_json))
            print("JSON -> %s" % args.out_json)
        if args.out_md:
            _dump_markdown(result, Path(args.out_md))
            print("MD   -> %s" % args.out_md)

    if result["status"] == "PASS":
        print("PASS: edge continuity OK.")
    else:
        print("FAIL: edge continuity or opaque-edge requirement not satisfied.")
        print("修复建议：请确保 block_multi 三张贴图均为 16x16 不透明方块图；"
              "side 左右边一致；side 顶/底边与 top/bottom 对应边缘颜色连续。")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
