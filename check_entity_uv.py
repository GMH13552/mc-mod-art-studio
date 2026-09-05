#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_entity_uv.py — 检查 entity_uv 输出是否遵循 Vanilla 实体纹理布局。

标准模型可加载的核心语义：
- 尺寸必须符合目标实体的 Vanilla 纹理尺寸。
- 目标实体硬编码模型采样的关键 UV 区域必须有内容（不是空白/单个居中侧视图）。
- 画布边距：atlas 左右至少 1px 透明；顶部/底部边距作为说明项记录。

用法：:

    python3 check_entity_uv.py --self-test
    python3 check_entity_uv.py tests/runs/v2/pig/sprite.png --entity pig
    python3 check_entity_uv.py generated/pig/sprite.png --entity pig --json evidence.json --md evidence.md
    python3 check_entity_uv.py --help

输出：stdout 打印 PASS/FAIL 摘要；--json/--md 写结构化证据。
退出码：PASS=0，FAIL=1。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow is required: pip install pillow") from exc

try:
    import entity_uv_spec as eu
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import entity_uv_spec as eu

ALPHA_THRESHOLD = 8
MIN_MARGIN = 1
SUPPORTED_ENTITIES = ("pig", "creeper", "cow", "red_mooshroom", "player")


def _canvas_margins(img: Image.Image) -> dict[str, int]:
    """返回不透明内容到画布四边的透明边距（像素数）。

    使用 bbox（left, top, right, bottom 半开区间）；空图为全 0。
    注意：atlas 场景中左右边距作为硬性检查，顶部/底部作为说明项。
    """
    img = img.convert("RGBA")
    width, height = img.size
    bbox = img.getchannel("A").getbbox()
    if not bbox:
        return {"left": 0, "top": 0, "right": 0, "bottom": 0}
    left, top, right, bottom = bbox
    return {
        "left": left,
        "top": top,
        "right": width - right,
        "bottom": height - bottom,
    }


def _alpha_opaque_count(img: Image.Image, box: tuple[int, int, int, int] | None = None) -> int:
    """统计区域内 alpha >= ALPHA_THRESHOLD 的像素数。"""
    if box:
        crop = img.convert("RGBA").getchannel("A").crop(box)
    else:
        crop = img.convert("RGBA").getchannel("A")
    return sum(1 for v in crop.tobytes() if v >= ALPHA_THRESHOLD)


def _expected_size(entity: str, width: int, height: int) -> tuple[tuple[int, int] | None, str]:
    """返回 (预期尺寸集合，说明文字)。None 表示不限定。"""
    if entity == "player":
        return ((64, 32), (64, 64)), "player skin 允许 64x32 (legacy) 或 64x64 (modern)"
    if entity in eu.MOB_ENTITY_REGIONS:
        return ((64, 32),), "%s 原版纹理是 64x32" % entity
    return None, "%s 无内置尺寸约束（按实体自定义）" % entity


def _check_image_obj(img: Image.Image, entity: str, label: str = "<memory>") -> dict:
    """对已加载的 RGBA 图片执行全部检查，返回结构化结果。"""
    result: dict = {
        "png": label,
        "entity": entity,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "FAIL",
        "checks": [],
        "regions": {},
        "summary": "",
    }
    img = img.convert("RGBA")
    width, height = img.size
    result["size"] = "%dx%d" % (width, height)
    result["opaque_pixels"] = _alpha_opaque_count(img)
    result["bbox"] = img.getchannel("A").getbbox()
    result["margins"] = _canvas_margins(img)

    expected, expected_note = _expected_size(entity, width, height)
    dimension_ok = expected is None or (width, height) in expected
    result["checks"].append({
        "id": "dimension",
        "name": "尺寸",
        "ok": dimension_ok,
        "detail": "%s 实际=%dx%d，期望=%s" % (
            expected_note, width, height,
            " 或 ".join("%dx%d" % s for s in expected) if expected else "不限定"),
    })

    nonempty_ok = result["opaque_pixels"] > 0
    result["checks"].append({
        "id": "nonempty",
        "name": "非空",
        "ok": nonempty_ok,
        "detail": "opaque_pixels=%d" % result["opaque_pixels"],
    })

    # 画布边距（atlas：左右为硬性，顶/底为说明项）
    margins = result["margins"]
    margin_ok = margins["left"] >= MIN_MARGIN and margins["right"] >= MIN_MARGIN
    margin_detail = "margins=%s (atlas 左右至少 %dpx；顶/底为说明项)" % (margins, MIN_MARGIN)
    if margins["top"] < MIN_MARGIN or margins["bottom"] < MIN_MARGIN:
        weak = [side for side in ("top", "bottom") if margins[side] < MIN_MARGIN]
        margin_detail += "；%s 边距不足 %dpx（说明：atlas 不强制，仅在证据中标注）" % ("/".join(weak), MIN_MARGIN)
    result["checks"].append({
        "id": "canvas_margin",
        "name": "画布边距",
        "ok": margin_ok,
        "detail": margin_detail,
    })

    # 区域占位
    regions = eu.regions_for_entity(entity, width, height) or {}
    region_ok = True
    for name, box in regions.items():
        count = _alpha_opaque_count(img, box)
        ok = count > 0
        if not ok:
            region_ok = False
        result["regions"][name] = {
            "expected": "%d,%d -> %d,%d" % box,
            "opaque": count,
            "ok": ok,
        }
        result["checks"].append({
            "id": "region_" + name,
            "name": "区域 " + name,
            "ok": ok,
            "detail": "期望 %s，opaque=%d" % (result["regions"][name]["expected"], count),
        })

    all_ok = dimension_ok and nonempty_ok and region_ok and margin_ok
    result["status"] = "PASS" if all_ok else "FAIL"
    weak_margins = [side for side in ("left", "right", "top", "bottom") if margins[side] < MIN_MARGIN]
    margin_note = "" if not weak_margins else " margins_lt_1=%s" % "/".join(weak_margins)
    result["summary"] = "%s: %s (entity=%s, size=%s, opaque=%d, regions=%d, margins=%s%s)" % (
        "PASS" if all_ok else "FAIL",
        "符合标准实体 UV 布局" if all_ok else "不满足标准实体 UV 布局",
        entity,
        result.get("size", "?"),
        result["opaque_pixels"],
        len(regions),
        margins,
        margin_note,
    )
    return result


def _check_image(path: Path, entity: str) -> dict:
    """打开 PNG 后执行全部检查，返回结构化结果。"""
    try:
        with Image.open(path) as im:
            img = im.convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        result: dict = {
            "png": str(path),
            "entity": entity,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "status": "FAIL",
            "checks": [],
            "regions": {},
            "summary": "",
        }
        result["summary"] = "无法打开 PNG: %s" % exc
        result["checks"].append({
            "id": "open",
            "name": "打开 PNG",
            "ok": False,
            "detail": str(exc),
        })
        return result
    return _check_image_obj(img, entity, str(path))


def _synthetic_entity_image(entity: str) -> Image.Image:
    """用 entity_uv_spec.MOB_ENTITY_REGIONS 在内存生成 64x32 合成正例。

    每个标准区域都填充不透明像素；不依赖任何原版素材。
    """
    img = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
    px = img.load()
    regions = eu.regions_for_entity(entity, 64, 32) or {}
    if not regions:
        raise ValueError("unsupported synthetic entity: %r" % entity)
    # 每个区域至少填充一点；用不同颜色便于人工辨认，不影响 alpha 判定。
    palette = [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
        (255, 255, 0, 255),
        (255, 0, 255, 255),
        (0, 255, 255, 255),
    ]
    for i, (name, box) in enumerate(regions.items()):
        x1, y1, x2, y2 = box
        color = palette[i % len(palette)]
        # 只填充区域内部（避开画布最外一圈），既保证各区域非空，也满足 1px 画布边距。
        x_start = max(x1 + 1, x1)
        y_start = max(y1 + 1, y1)
        x_end = max(x2 - 1, x2)
        y_end = max(y2 - 1, y2)
        step_x = max(1, (x_end - x_start) // 4)
        step_y = max(1, (y_end - y_start) // 4)
        for y in range(y_start, y_end, step_y):
            for x in range(x_start, x_end, step_x):
                px[x, y] = color
    return img


def _run_self_test() -> int:
    """用内存合成的 64x32 区域图自测，不依赖原版素材。"""
    failures = 0
    lines: list[str] = []

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        status = "PASS" if cond else "FAIL"
        lines.append("[%s] %s%s" % (status, label, (" — " + detail) if detail else ""))
        if not cond:
            failures += 1

    for entity in sorted(eu.MOB_ENTITY_REGIONS):
        img = _synthetic_entity_image(entity)
        result = _check_image_obj(img, entity, "<self-test:%s>" % entity)
        check("%s synthetic region positive" % entity, result["status"] == "PASS",
              "status=%s opaque=%d" % (result["status"], result["opaque_pixels"]))
        for name, region in result["regions"].items():
            check("%s region %s nonempty" % (entity, name), region["opaque"] > 0,
                  "opaque=%d" % region["opaque"])

    # 负例：全透明 64x32 应 FAIL，且每个区域为空。
    empty = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
    empty_result = _check_image_obj(empty, "pig", "<self-test:empty>")
    check("empty synthetic negative fails", empty_result["status"] == "FAIL",
          "status=%s opaque=%d" % (empty_result["status"], empty_result["opaque_pixels"]))

    print("\n".join(lines))
    print("check_entity_uv self-test: %s" % ("PASS" if failures == 0 else "FAIL (%d)" % failures))
    return 0 if failures == 0 else 1


def _write_json(result: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _write_md(result: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# entity_uv check: %s" % result["entity"],
        "",
        "```",
        result["summary"],
        "```",
        "",
        "| 项 | 结果 | 说明 |",
        "|---|---|---|",
    ]
    for c in result["checks"]:
        lines.append("| %s | %s | %s |" % (
            c["name"], "PASS" if c["ok"] else "FAIL", c["detail"]))
    lines.append("")
    lines.append("## 画布边距")
    lines.append("")
    lines.append("| 边 | 边距(px) | 要求 |")
    lines.append("|---|---|---|")
    margins = result.get("margins", {})
    notes = {
        "left": "atlas 硬性 >= %d" % MIN_MARGIN,
        "right": "atlas 硬性 >= %d" % MIN_MARGIN,
        "top": "说明项",
        "bottom": "说明项",
    }
    for side in ("left", "top", "right", "bottom"):
        lines.append("| %s | %d | %s |" % (side, margins.get(side, 0), notes[side]))
    lines.append("")
    lines.append("## 区域占位")
    lines.append("")
    lines.append("| 区域 | 期望坐标 | opaque | 结果 |")
    lines.append("|---|---|---|---|")
    for name, r in result["regions"].items():
        lines.append("| %s | %s | %d | %s |" % (
            name, r["expected"], r["opaque"], "PASS" if r["ok"] else "FAIL"))
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check entity_uv output against Vanilla entity texture layout.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 check_entity_uv.py --self-test
  python3 check_entity_uv.py tests/runs/v2/pig/sprite.png --entity pig
  python3 check_entity_uv.py generated/pig/sprite.png --entity pig --json evidence.json --md evidence.md
""",
    )
    parser.add_argument("png", nargs="?", default=None, help="待检查的 PNG 路径")
    parser.add_argument("--entity", default="auto",
                        choices=list(SUPPORTED_ENTITIES) + ["auto"],
                        help="实体类型；auto 从文件名/路径中猜测")
    parser.add_argument("--json", default=None, help="可选：写结构化 JSON 证据")
    parser.add_argument("--md", default=None, help="可选：写 Markdown 证据")
    parser.add_argument("--quiet", action="store_true", help="只输出状态行")
    parser.add_argument("--self-test", action="store_true",
                        help="运行内存合成图片自测并退出")
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test()

    if not args.png:
        parser.error("PNG path is required (or use --self-test)")

    png = Path(args.png)
    if not png.exists():
        print("ERROR: PNG not found: %s" % png, file=sys.stderr)
        return 2

    entity = args.entity
    if entity == "auto":
        entity = eu.detect_entity(png.stem) or "player"
    if entity not in SUPPORTED_ENTITIES:
        print("ERROR: unsupported entity %r (use one of %s)" % (entity, "/".join(SUPPORTED_ENTITIES)), file=sys.stderr)
        return 2

    result = _check_image(png, entity)

    if args.json:
        _write_json(result, Path(args.json))
    if args.md:
        _write_md(result, Path(args.md))

    if args.quiet:
        print(result["summary"])
    else:
        print(result["summary"])
        for c in result["checks"]:
            print("  [%s] %s: %s" % ("PASS" if c["ok"] else "FAIL", c["name"], c["detail"]))
        for name, r in result.get("regions", {}).items():
            print("  region %s: %s opaque=%d" % (name, r["expected"], r["opaque"]))
        print("  margins: %s" % result.get("margins", {}))

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
