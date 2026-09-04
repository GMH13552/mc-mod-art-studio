#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
asset_to_text.py — 把 Minecraft 资产库中的任意尺寸 PNG 转成逐像素文本。

包装并复用 minecraft_texture_tool/texture_to_text.py 的确定性转换逻辑，
额外提供 `--index library-index.json` 批量入口、分类过滤与 Windows 路径兼容。
物品/方块原版为 16x16；实体为 64x32 / 64x64 UV。本脚本不限制尺寸。

Modes (与 texture_to_text.py 一致):
  compact (default)  palette + index grid + silhouette + ASCII
  all                exact hex grid + silhouette + ASCII
  grid               exact hex grid only (no silhouette / ASCII)
  json               machine-readable JSON (x/y/r/g/b/a/hex)

Usage examples:
  # 任意单张 PNG
  python3 asset_to_text.py mc_asset_library/raw/item/stone_pickaxe.png
  python3 asset_to_text.py "C:\\path\\to\\pig.png" --mode grid --no-header

  # 通过 library-index.json 批量（全部 108 张）
  python3 asset_to_text.py --index mc_asset_library/library-index.json --mode grid --output-dir asset_text/

  # 只转物品或实体
  python3 asset_to_text.py --index mc_asset_library/library-index.json --category item --mode compact --output-dir asset_text/item/
  python3 asset_to_text.py --index mc_asset_library/library-index.json --category entity --mode compact --output-dir asset_text/entity/

  # 半透明纹理（如 creeper.png）需要保留 alpha 时加 --alpha-column
  python3 asset_to_text.py mc_asset_library/raw/entity/creeper/creeper.png --mode grid --alpha-column

  # 自检（16x16 与 64x32 各一张）
  python3 asset_to_text.py --self-test

  # 写日志
  python3 asset_to_text.py --self-test > asset_to_text_selftest.txt 2>&1
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.stderr.write("ERROR: Pillow is required.  Install with:  pip install pillow\n")
    raise

# 复用 texture_to_text.py。如果 script 与 minecraft_texture_tool/ 同级，直接可用；
# 否则把脚本所在目录加入 sys.path。
_THIS_DIR = Path(__file__).resolve().parent
_TOOL_DIR = _THIS_DIR / "minecraft_texture_tool"
if str(_TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOL_DIR))

import texture_to_text as ttt  # noqa: E402


# ---------------------------------------------------------------------------
# 公共函数
# ---------------------------------------------------------------------------

def normalize_path(path: str | Path) -> Path:
    """委托给 texture_to_text 的 Windows/WSL 路径归一化。"""
    return ttt.normalize_path(path)


def build_doc_for_path(path: Path, args: argparse.Namespace) -> str:
    """
    读取一张 PNG 并用 texture_to_text.build_document 生成文档字符串。
    复用了 texture_to_text 的完整输出格式，因此输出与已有工具完全一致。
    """
    with Image.open(path) as image:
        im = image.convert("RGBA")
        if ttt.has_semitransparent(im) and not args.alpha_column:
            raise ValueError(
                "%s contains semi-transparent alpha (0<alpha<255). "
                "Use --alpha-column for an alpha-aware hex grid." % path
            )
        # build_document 只读取这些属性；我们不重复实现格式逻辑。
        doc_args = argparse.Namespace(
            mode=args.mode,
            alpha_threshold=args.alpha_threshold,
            no_header=args.no_header,
            alpha_column=args.alpha_column,
            blocks=getattr(args, "blocks", 0),
            no_silhouette=args.no_silhouette,
            no_ascii=args.no_ascii,
        )
        return ttt.build_document(path, im, doc_args)


def load_index(index_path: Path) -> list[dict]:
    """读取 asset library index JSON 并返回条目列表。"""
    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("index file must contain a JSON array: %s" % index_path)
    return data


def resolve_index_entry(index_dir: Path, entry: dict) -> Path:
    """把 index 中相对路径解析为工作区内的真实 PNG 路径。"""
    raw = str(entry.get("path", ""))
    if not raw:
        raise ValueError("index entry missing 'path': %r" % entry)
    p = normalize_path(raw)
    if not p.is_absolute():
        p = index_dir / p
    return p


def collect_index_paths(args) -> list[tuple[Path, dict]]:
    """按 --index + --category / --name / --limit 收集待转换条目。"""
    index_path = normalize_path(args.index)
    if not index_path.exists():
        raise FileNotFoundError("index file not found: %s" % index_path)
    entries = load_index(index_path)
    index_dir = index_path.resolve().parent

    if args.category:
        cat = args.category.lower().strip()
        entries = [e for e in entries if str(e.get("category", "")).lower() == cat]

    if args.name:
        wanted = {n.lower() for n in args.name}
        def _name_match(e: dict) -> bool:
            name = str(e.get("name", "")).lower()
            stem = Path(name).stem.lower()
            path_name = Path(str(e.get("path", ""))).name.lower()
            path_stem = Path(path_name).stem.lower()
            return (
                name in wanted or stem in wanted
                or path_name in wanted or path_stem in wanted
            )
        entries = [e for e in entries if _name_match(e)]

    if args.limit is not None:
        entries = entries[: args.limit]

    result = []
    for e in entries:
        p = resolve_index_entry(index_dir, e)
        if not p.exists():
            raise FileNotFoundError("entry path not found: %s" % p)
        result.append((p, e))
    return result


# ---------------------------------------------------------------------------
# CLI 主体
# ---------------------------------------------------------------------------

def run_cli(args: argparse.Namespace) -> int:
    docs: list[tuple[Path, str]] = []

    if args.index:
        paths = collect_index_paths(args)
        if not paths:
            sys.stderr.write("ERROR: --index selected no entries\n")
            return 1
        for p, _entry in paths:
            try:
                doc = build_doc_for_path(p, args)
            except Exception as e:
                sys.stderr.write("ERROR: cannot convert %s: %s\n" % (p, e))
                return 1
            if args.stats:
                doc += ttt.render_stats(doc)
            docs.append((p, doc))
    else:
        if not args.paths:
            sys.stderr.write(
                "ERROR: at least one PNG path is required "
                "(or use --index library-index.json); use --self-test for checks\n"
            )
            return 2
        for raw in args.paths:
            p = normalize_path(raw)
            if not p.exists():
                sys.stderr.write("ERROR: file not found: %s\n" % raw)
                return 1
            try:
                doc = build_doc_for_path(p, args)
            except Exception as e:
                sys.stderr.write("ERROR: cannot read %s: %s\n" % (raw, e))
                return 1
            if args.stats:
                doc += ttt.render_stats(doc)
            docs.append((p, doc))

    if args.output_dir:
        out_dir = normalize_path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for p, doc in docs:
            out_path = out_dir / (p.stem + ".txt")
            out_path.write_text(doc + "\n", encoding="utf-8")
            print("saved: %s" % out_path, file=sys.stderr)
        return 0

    if args.output:
        out_path = normalize_path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        merged = args.separator.join(doc for _, doc in docs)
        out_path.write_text(merged + "\n", encoding="utf-8")
        print("saved: %s" % out_path, file=sys.stderr)
        return 0

    sys.stdout.write(args.separator.join(doc for _, doc in docs))
    sys.stdout.write("\n")
    return 0


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------

def _windows_form(path: Path) -> str | None:
    """把 /mnt/c/... 转成 C:/... 以测试 Windows 路径输入。"""
    s = str(path)
    if s.startswith("/mnt/"):
        return s[5].upper() + ":" + s[6:]
    return None


def run_self_test() -> int:
    """
    自检至少覆盖 16x16 与 64x32 两种尺寸：
      - 16x16: mc_asset_library/raw/item/stone_pickaxe.png（物品）
      - 64x32: mc_asset_library/raw/entity/pig/pig.png（实体 UV）
    对每张验证 grid/compact/all/json 四种模式的输出结构与像素一致性。
    核心仓库没有 mc_asset_library/ 时自动生成代码合成 PNG，不依赖原版素材。
    """
    base = _THIS_DIR
    assets = base / "mc_asset_library" / "raw"
    tmp_root: Path | None = None
    if (assets / "item" / "stone_pickaxe.png").exists():
        candidates = [
            ("16x16 item", assets / "item" / "stone_pickaxe.png", (16, 16)),
            ("64x32 entity", assets / "entity" / "pig" / "pig.png", (64, 32)),
        ]
    else:
        tmp_root = Path(tempfile.mkdtemp(prefix="asset_to_text_selftest_"))
        syn16 = tmp_root / "syn_stone_pickaxe.png"
        syn64 = tmp_root / "syn_pig.png"
        for path, size, color in (
            (syn16, (16, 16), (120, 140, 130, 255)),
            (syn64, (64, 32), (220, 160, 150, 255)),
        ):
            img = Image.new("RGBA", size, color)
            for x in range(0, size[0], 2):
                for y in range(0, size[1], 2):
                    img.putpixel((x, y), (0, 0, 0, 0))
            img.save(path, "PNG")
        candidates = [
            ("16x16 item (synthetic)", syn16, (16, 16)),
            ("64x32 entity (synthetic)", syn64, (64, 32)),
        ]

    print("# asset_to_text.py self-test")
    print("Script: %s" % (base / "asset_to_text.py"))
    print("Reused module: %s" % (_TOOL_DIR / "texture_to_text.py"))
    print("")

    passed = 0
    failed = 0

    def report(name: str, ok: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if ok:
            passed += 1
            print("PASS: %s" % name)
        else:
            failed += 1
            print("FAIL: %s%s" % (name, (" :: " + detail) if detail else ""))

    def run_cli(argv: list[str]) -> subprocess.CompletedProcess:
        import subprocess
        return subprocess.run(
            [sys.executable, str(base / "asset_to_text.py")] + argv,
            cwd=str(base),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    for label, path, expected_size in candidates:
        if not path.exists():
            report("%s (%s) found" % (label, path.name), False, "file missing")
            continue

        # 1) Pix dimension assertion.
        with Image.open(path) as im:
            size = im.size
        size_ok = size == expected_size
        report("%s (%s) dimensions are %dx%d" % (label, path.name, *expected_size),
               size_ok, "actual %dx%d" % size)

        # 2) --mode grid --no-header: exact rows/columns + valid hex tokens.
        res_grid = run_cli([str(path), "--mode", "grid", "--no-header"])
        grid_lines = res_grid.stdout.strip().splitlines() if res_grid.stdout.strip() else []
        grid_ok = (
            res_grid.returncode == 0
            and len(grid_lines) == expected_size[1]
            and all(len(line.split(" ")) == expected_size[0] for line in grid_lines)
            and all(
                tok == ttt.TRANSPARENT_HEX or ttt.HEX_RE.match(tok)
                for line in grid_lines for tok in line.split(" ")
            )
        )
        report("%s: --mode grid --no-header outputs bare %dx%d hex grid" % (label, *expected_size),
               grid_ok,
               ("exit=%d lines=%d" % (res_grid.returncode, len(grid_lines))) if not grid_ok else "")

        # 3) --mode all: contains exact grid + silhouette + ASCII.
        res_all = run_cli([str(path), "--mode", "all", "--no-header"])
        all_ok = (
            res_all.returncode == 0
            and "## Hex color grid" in res_all.stdout
            and "## Silhouette" in res_all.stdout
            and "## ASCII color map" in res_all.stdout
        )
        report("%s: --mode all emits hex+silhouette+ASCII" % label, all_ok)

        # 4) --mode compact: palette + index grid + silhouette + ASCII.
        res_compact = run_cli([str(path), "--mode", "compact", "--no-header"])
        compact_ok = (
            res_compact.returncode == 0
            and "## Silhouette" in res_compact.stdout
            and "## ASCII color map" in res_compact.stdout
            and "## Palette (hex)" in res_compact.stdout
            and "## Index grid" in res_compact.stdout
        )
        report("%s: --mode compact emits palette+index+silhouette+ASCII" % label, compact_ok)

        # 5) --mode json: parseable JSON with correct size and pixel depth.
        res_json = run_cli([str(path), "--mode", "json"])
        try:
            data = json.loads(res_json.stdout)
            rows = data.get("pixels", [])
            json_ok = (
                res_json.returncode == 0
                and data.get("size") == [expected_size[0], expected_size[1]]
                and len(rows) == expected_size[1]
                and all(len(r) == expected_size[0] for r in rows)
            )
            if json_ok:
                # Verify every pixel has the required fields.
                json_ok = all(
                    set(p) == {"x", "y", "r", "g", "b", "a", "hex"}
                    for r in rows for p in r
                )
        except Exception as e:
            json_ok = False
            print("    json parse error: %s" % e)
        report("%s: --mode json emits parseable per-pixel JSON" % label, json_ok)

        # 6) If under /mnt/c, test Windows C:/ and C:\ path normalization.
        win = _windows_form(path)
        if win is not None:
            res_win_fwd = run_cli([win, "--mode", "grid", "--no-header"])
            res_win_back = run_cli([win.replace("/", "\\"), "--mode", "grid", "--no-header"])
            win_ok = (
                res_win_fwd.returncode == 0
                and res_win_back.returncode == 0
                and res_win_fwd.stdout == grid_ok_text(res_grid)
                and res_win_back.stdout == grid_ok_text(res_grid)
            )
            report("%s: Windows C:/ and C:\\ paths normalize correctly" % label, win_ok)
        else:
            report("%s: Windows path tests skipped (not under /mnt/c)" % label, True, "SKIP")

    # ---- --index smoke test on a small subset ----
    index_path = base / "mc_asset_library" / "library-index.json"
    if index_path.exists():
        res_index = run_cli([
            "--index", str(index_path),
            "--category", "entity",
            "--name", "pig.png",
            "--mode", "grid",
            "--no-header",
        ])
        index_lines = res_index.stdout.strip().splitlines() if res_index.stdout.strip() else []
        index_ok = (
            res_index.returncode == 0
            and len(index_lines) == 32
            and all(len(line.split(" ")) == 64 for line in index_lines)
        )
        report("--index library-index.json --category entity --name pig.png works", index_ok,
               ("exit=%d" % res_index.returncode) if not index_ok else "")
    else:
        report("--index library-index.json smoke test", True, "SKIP: index missing")

    if tmp_root is not None:
        shutil.rmtree(tmp_root, ignore_errors=True)

    print("")
    if failed:
        print("SELF-TEST: FAIL (%d passed, %d failed)" % (passed, failed))
        return 1
    print("SELF-TEST: PASS (%d passed, 0 failed)" % passed)
    return 0


def grid_ok_text(res) -> str:
    """返回成功 grid 运行的 stdout，供 Windows 一致性比较。"""
    return res.stdout


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Minecraft asset-library PNGs into per-pixel text."
    )
    parser.add_argument("paths", nargs="*", help="PNG texture file(s)")
    parser.add_argument(
        "--index",
        default=None,
        help="Use mc_asset_library/library-index.json to resolve PNG paths",
    )
    parser.add_argument(
        "--category",
        default=None,
        choices=["item", "block", "entity"],
        help="Filter index entries by category (requires --index)",
    )
    parser.add_argument(
        "--name",
        action="append",
        default=None,
        help="Filter index entries by exact basename (repeatable; requires --index)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of index entries to convert",
    )
    parser.add_argument(
        "--mode",
        choices=["all", "grid", "compact", "json"],
        default=ttt.DEFAULT_MODE,
        help="Output mode (default: %s)" % ttt.DEFAULT_MODE,
    )
    parser.add_argument(
        "--alpha-threshold",
        type=int,
        default=ttt.DEFAULT_ALPHA_THRESHOLD,
        help="Alpha values below this are treated as transparent (default: %d)"
        % ttt.DEFAULT_ALPHA_THRESHOLD,
    )
    parser.add_argument(
        "--no-silhouette",
        action="store_true",
        help="Do not print the X/. silhouette block",
    )
    parser.add_argument(
        "--no-ascii",
        action="store_true",
        help="Do not print the coarse ASCII color map",
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="Omit the # Texture / Size / Alpha threshold / Opaque header block",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Append character count and approximate token count (~4 chars/token)",
    )
    parser.add_argument(
        "--alpha-column",
        action="store_true",
        help="Alpha-aware mode: hex grid emits '#RRGGBB a=NN' for opaque pixels",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Write each input PNG's text as DIR/<name>.txt instead of stdout",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write single-file (or merged multi-file) output to FILE instead of stdout",
    )
    parser.add_argument(
        "--blocks",
        type=int,
        default=0,
        help="Also print an NxN downsampled average-color grid (if 0, disabled)",
    )
    parser.add_argument(
        "--separator",
        default="\n" + "=" * 70 + "\n",
        help="Separator between multiple textures",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run integrity checks on 16x16 and 64x32 assets and exit",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    if args.output_dir and args.output:
        sys.stderr.write("ERROR: --output-dir and --output are mutually exclusive\n")
        return 2

    if not args.index and not args.paths:
        parser.error("at least one PNG path or --index is required")

    if (args.category or args.name or args.limit is not None) and not args.index:
        parser.error("--category / --name / --limit require --index")

    try:
        return run_cli(args)
    except Exception as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
