#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan_mc_assets.py — 扫描用户本机 Minecraft / 资源包 / 模组目录中的美术资产名。

CLI
---
    python3 scan_mc_assets.py --mc-path ~/.minecraft --out my_asset_index.json
    python3 scan_mc_assets.py --mc-path ~/.minecraft --with-palette --out my_asset_index.json
    python3 scan_mc_assets.py --self-test

扫描行为
--------
* 如果 ``<path>/assets`` 存在，把该目录当作一个资产根（游戏目录或资源包本身）。
* 如果 ``<path>/resourcepacks`` 存在，递归扫描其中每个包含 ``assets`` 的资源包。
* 如果 ``<path>`` 本身是资源包（即 ``<path>/assets`` 存在）也支持。
* 扫描 ``assets/<modid>/textures/**/*.png``：记录绝对路径、名称、modid、分类、尺寸，
  可选统计不透明像素去重颜色数（``--with-palette``）。
* 扫描 ``assets/<modid>/models/**/*.json`` 与 ``assets/<modid>/blockstates/**/*.json``。

生成的索引 JSON 不包含任何原版 PNG，也不包含密钥；只包含本机资产路径与元数据。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.stderr.write("ERROR: Pillow is required.  Install with:  pip install pillow\n")
    raise

try:
    from text_to_texture import normalize_path
except ImportError:  # pragma: no cover
    normalize_path = Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _palette_count(image_path: Path) -> int:
    """统计不透明像素（alpha>128）的去重 RGB 颜色数。"""
    with Image.open(image_path) as im:
        im = im.convert("RGBA")
        colors: set[tuple[int, int, int]] = set()
        for r, g, b, a in im.getdata():
            if a > 128:
                colors.add((r, g, b))
    return len(colors)


def _scan_textures(assets_dir: Path, modid_dir: Path, with_palette: bool) -> list[dict]:
    entries: list[dict] = []
    textures_dir = modid_dir / "textures"
    if not textures_dir.is_dir():
        return entries
    for path in sorted(textures_dir.rglob("*.png")):
        rel = path.relative_to(modid_dir)
        # rel 形如 textures/block/foo.png；第一段必须是 textures。
        parts = rel.parts
        sub = parts[1] if len(parts) > 1 else ""
        if sub == "entity":
            category = "entity"
        elif sub == "item":
            category = "item"
        elif sub == "block":
            category = "block"
        else:
            category = "texture"
        try:
            with Image.open(path) as im:
                width, height = im.size
        except Exception as e:  # noqa: BLE001
            sys.stderr.write("WARN: cannot read PNG size %s: %s\n" % (path, e))
            continue
        entry = {
            "path": str(path.resolve()),
            "name": path.stem,
            "modid": modid_dir.name,
            "category": category,
            "width": width,
            "height": height,
            "file_type": "png",
        }
        if with_palette:
            entry["palette_count"] = _palette_count(path)
        entries.append(entry)
    return entries


def _scan_models(assets_dir: Path, modid_dir: Path) -> list[dict]:
    entries: list[dict] = []
    models_dir = modid_dir / "models"
    if not models_dir.is_dir():
        return entries
    for path in sorted(models_dir.rglob("*.json")):
        rel = path.relative_to(modid_dir)
        # rel 形如 models/block/foo.json 或 models/item/foo.json
        parts = rel.parts
        sub = parts[1] if len(parts) > 1 else ""
        if sub == "item" or (len(parts) > 2 and parts[2] == "item"):
            category = "model_item"
        else:
            category = "model_block"
        entries.append({
            "path": str(path.resolve()),
            "name": path.stem,
            "modid": modid_dir.name,
            "category": category,
            "file_type": "json",
        })
    return entries


def _scan_blockstates(assets_dir: Path, modid_dir: Path) -> list[dict]:
    entries: list[dict] = []
    blockstates_dir = modid_dir / "blockstates"
    if not blockstates_dir.is_dir():
        return entries
    for path in sorted(blockstates_dir.rglob("*.json")):
        entries.append({
            "path": str(path.resolve()),
            "name": path.stem,
            "modid": modid_dir.name,
            "category": "blockstate",
            "file_type": "json",
        })
    return entries


def _scan_asset_root(root: Path, with_palette: bool) -> list[dict]:
    """扫描一个包含 assets/ 的目录（游戏目录或资源包根）。"""
    assets_dir = root / "assets"
    if not assets_dir.is_dir():
        return []
    entries: list[dict] = []
    for modid_dir in sorted(assets_dir.iterdir()):
        if not modid_dir.is_dir():
            continue
        entries.extend(_scan_textures(assets_dir, modid_dir, with_palette))
        entries.extend(_scan_models(assets_dir, modid_dir))
        entries.extend(_scan_blockstates(assets_dir, modid_dir))
    return entries


def _collect_asset_roots(mc_path: Path) -> list[Path]:
    """返回应扫描的资产根目录列表（可能来自游戏目录或 resourcepacks）。"""
    p = normalize_path(mc_path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError("path does not exist: %s" % p)
    roots: list[Path] = []
    if (p / "assets").is_dir():
        roots.append(p)
    resourcepacks = p / "resourcepacks"
    if resourcepacks.is_dir():
        for child in sorted(resourcepacks.iterdir()):
            if child.is_dir() and (child / "assets").is_dir():
                roots.append(child)
    if not roots:
        raise ValueError(
            "no assets directory found. Pass a Minecraft directory (with resourcepacks/), "
            "or a resource pack / mod directory that itself contains assets/: %s" % p
        )
    # 去重（同一 resolved 路径可能被多个入口找到）
    unique: list[Path] = []
    seen: set[Path] = set()
    for r in roots:
        rr = r.resolve()
        if rr not in seen:
            seen.add(rr)
            unique.append(rr)
    return unique


def build_index(
    mc_path: str | Path,
    out_path: str | Path | None = None,
    with_palette: bool = False,
) -> dict:
    """扫描 ``mc_path`` 并返回新格式索引 dict；可选写出到 ``out_path``。"""
    p = normalize_path(mc_path).expanduser().resolve()
    roots = _collect_asset_roots(p)
    entries: list[dict] = []
    for root in roots:
        entries.extend(_scan_asset_root(root, with_palette))

    index = {
        "source_dir": str(p),
        "scanned_at": _now_iso(),
        "base_dir": str(p),
        "count_textures": sum(1 for e in entries if e.get("file_type") == "png"),
        "count_models": sum(1 for e in entries if e.get("category") in ("model_block", "model_item")),
        "count_blockstates": sum(1 for e in entries if e.get("category") == "blockstate"),
        "entries": entries,
    }
    if out_path is not None:
        out = normalize_path(out_path).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
            f.write("\n")
    return index


def _write_test_png(path: Path, color: tuple[int, int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (16, 16), color)
    # 留几个透明像素，方便验证 palette 只统计不透明颜色
    for x in range(0, 16, 2):
        for y in range(0, 16, 2):
            img.putpixel((x, y), (0, 0, 0, 0))
    img.save(path, "PNG")


def run_self_test() -> int:
    """在临时目录创建迷你资源包并断言扫描计数/字段，不依赖任何原版素材。"""
    with tempfile.TemporaryDirectory(prefix="scan_mc_assets_selftest_") as td:
        root = Path(td) / "mini_resourcepack"
        modid = "demomod"
        assets = root / "assets" / modid
        _write_test_png(assets / "textures" / "block" / "red_mushroom.png", (220, 40, 40, 255))
        _write_test_png(assets / "textures" / "item" / "blue_crystal.png", (40, 80, 220, 255))
        _write_test_png(assets / "textures" / "entity" / "pig" / "pig.png", (240, 180, 160, 255))
        (assets / "models" / "block" / "red_mushroom_block.json").parent.mkdir(parents=True, exist_ok=True)
        (assets / "models" / "block" / "red_mushroom_block.json").write_text(
            json.dumps({
                "parent": "minecraft:block/cube_all",
                "textures": {"all": "demomod:block/red_mushroom"},
            }, indent=2),
            encoding="utf-8",
        )
        (assets / "blockstates").mkdir(parents=True, exist_ok=True)
        (assets / "blockstates" / "red_mushroom_block.json").write_text(
            json.dumps({"variants": {"": {"model": "demomod:block/red_mushroom_block"}}}, indent=2),
            encoding="utf-8",
        )

        index = build_index(root, with_palette=True)
        entries = index["entries"]
        failures: list[str] = []

        def check(cond: bool, msg: str) -> None:
            if cond:
                print("  PASS: %s" % msg)
            else:
                failures.append(msg)
                print("  FAIL: %s" % msg)

        check(index["count_textures"] == 3, "count_textures == 3")
        check(index["count_models"] == 1, "count_models == 1")
        check(index["count_blockstates"] == 1, "count_blockstates == 1")
        check(len(entries) == 5, "entries length == 5")

        textures = [e for e in entries if e.get("file_type") == "png"]
        check(len(textures) == 3, "texture entries == 3")
        check(all(e["width"] == 16 and e["height"] == 16 for e in textures), "all textures 16x16")
        check(all(Path(e["path"]).is_absolute() for e in entries), "all entry paths are absolute")
        check(all(e["modid"] == modid for e in entries), "modid == demomod")

        cats = {e["name"]: e["category"] for e in textures}
        check(cats.get("red_mushroom") == "block", "red_mushroom category == block")
        check(cats.get("blue_crystal") == "item", "blue_crystal category == item")
        check(cats.get("pig") == "entity", "pig category == entity")
        check(all(e["palette_count"] >= 1 for e in textures), "palette_count present and >= 1")

        model_names = {e["name"] for e in entries if e.get("category") == "model_block"}
        check("red_mushroom_block" in model_names, "model_block entry found")
        bs_names = {e["name"] for e in entries if e.get("category") == "blockstate"}
        check("red_mushroom_block" in bs_names, "blockstate entry found")

        if failures:
            print("SELF-TEST: FAIL (%d)" % len(failures), file=sys.stderr)
            return 1
        print("SELF-TEST: PASS")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="扫描 Minecraft/资源包路径下的美术资产名，生成可被 retrieve_assets.py 使用的索引 JSON。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mc-path", help="Minecraft 目录 / 资源包目录 / 模组目录（包含 assets/ 或 resourcepacks/）")
    parser.add_argument("--out", help="输出索引 JSON 路径（默认不写文件）")
    parser.add_argument("--with-palette", action="store_true", help="统计每张 PNG 不透明像素去重颜色数（较慢）")
    parser.add_argument("--self-test", action="store_true", help="在临时目录创建迷你资源包并自测，不依赖原版素材")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()
    if not args.mc_path:
        parser.error("--mc-path is required (or use --self-test)")
    out_path = Path(args.out) if args.out else None
    try:
        index = build_index(args.mc_path, out_path=out_path, with_palette=args.with_palette)
    except Exception as e:  # noqa: BLE001
        print("ERROR: %s" % e, file=sys.stderr)
        return 1

    print("source_dir: %s" % index["source_dir"])
    print("base_dir: %s" % index["base_dir"])
    print("count_textures: %d" % index["count_textures"])
    print("count_models: %d" % index["count_models"])
    print("count_blockstates: %d" % index["count_blockstates"])
    print("entries: %d" % len(index["entries"]))
    if out_path is not None:
        print("out: %s" % Path(out_path).resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
