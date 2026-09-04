#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
text_to_texture.py — Convert an LLM pixel-text answer into a PNG + preview.

Input contract (LLM output text)
--------------------------------
Line 1 must declare the canvas size:

    W=16 H=16

After the header, either one of two pixel-grid forms may follow:

1. Palette + index grid::

       PALETTE
       0: #494949
       1: #9a9a9a
       2: #898989
       3: #3c3c3c
       4: #5a5a5a
       5: #6c6c6c
       6: #493615
       7: #684e1e
       8: #896727
       9: #281e0b

       0 1 2 2 -1 -1 -1 ...
       ... (each row has exactly W space-separated entries)
       -1 or . means transparent.

2. Direct hex grid::

       #494949 #9a9a9a ...
       ---- ---- ...
       ... (each row has exactly W tokens; `----` is transparent)

Usage
-----
    python3 text_to_texture.py llm_answer.txt --output out.png --preview out_preview.png
    python3 text_to_texture.py --input llm_answer.txt --output out.png
    python3 text_to_texture.py --self-test
    python3 text_to_texture.py --validate <dir_or_file>
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow is required: pip install pillow") from exc

HEADER_RE = re.compile(r"^\s*W\s*=\s*(\d+)\s+H\s*=\s*(\d+)\s*$", re.I)
PALETTE_LINE_RE = re.compile(r"^\s*(\d+)\s*:\s*(#[0-9a-fA-F]{6})(?:\s+a=(\d+))?\s*$")
HEX_TOKEN_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
HEX_LINE_RE = re.compile(r"^#[0-9a-fA-F]{6}(?:\s|$)")
ALPHA_THRESHOLD = 8
SELFTEST_REPORT = "text_to_texture_selftest.txt"
_NOISE_LABELS = {
    "hex color grid",
    "hex grid",
    "hex grid:",
    "index grid",
    "index grid:",
    "index grid (palette index; alpha column active)",
    "palette (hex)",
}
_INDEX_GRID_LABELS = frozenset({"index grid", "index grid:"})


def normalize_path(path: str | Path) -> Path:
    """Accept Windows paths C:\\... and C:/... while running under WSL."""
    s = str(path)
    if s.startswith("\\\\") and s[2:3].isalpha() and s[3:4] in ("\\", "/"):
        s = s.replace("\\", "/")
    # WSL already sees /mnt/c as a normal POSIX path; normal Windows absolute
    # path conversion is only needed for C:\ style strings.
    if len(s) >= 3 and s[0].isalpha() and s[1] == ":" and s[2] in ("\\", "/"):
        drive = s[0].lower()
        rest = s[2:].replace("\\", "/")
        return Path("/mnt") / drive / rest
    return Path(s)


def _parse_declared_size(line: str) -> tuple[int, int] | None:
    m = HEADER_RE.match(line)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _is_comment_or_label(line: str) -> bool:
    """Return True for blank/comment/label lines that should be skipped.

    Important: a direct hex-grid data row such as ``#494949 #9a9a9a`` is NOT a
    comment, even though it begins with ``#``.  A line is only treated as a
    comment when it begins with ``# ``/``##``/another non-hex ``#...`` marker or
    is one of the known section labels emitted by asset_to_text.py.
    ``PALETTE`` is intentionally not treated as a comment because it marks the
    start of a palette/index block.
    """
    stripped = line.strip()
    if not stripped:
        return True
    low = stripped.lower()
    if low.startswith("palette"):
        return False
    if low in _NOISE_LABELS:
        return True
    if stripped.startswith("##"):
        return True
    if stripped.startswith("# ") or stripped.startswith("#\t"):
        return True
    if stripped.startswith("#") and not HEX_LINE_RE.match(stripped):
        return True
    return False


def _is_index_grid_label(line: str) -> bool:
    """Return True for a standalone ``INDEX GRID`` / ``index grid:`` label line."""
    return line.strip().lower() in _INDEX_GRID_LABELS


def _skip_noise(lines: list[str], start: int) -> int:
    """Skip blank/comment/label lines, but never skip hex-grid data rows."""
    i = start
    while i < len(lines):
        if not _is_comment_or_label(lines[i]):
            break
        i += 1
    return i


def _parse_palette_block(lines: list[str], start: int) -> tuple[list[tuple[int, int, int, int]], int]:
    """Parse palette lines starting at `start` (which must be 'PALETTE').

    Returns (palette_rgba, next_index).  Palette entries are ordered and may
    optionally carry `a=NN`; alpha defaults to 255.
    """
    i = start
    if not lines[i].strip().lower().startswith("palette"):
        raise ValueError("expected PALETTE block, got %r" % lines[i])
    i += 1
    palette: list[tuple[int, int, int, int]] = []
    while i < len(lines):
        s = lines[i].strip()
        if not s or s.startswith("#"):
            i += 1
            continue
        m = PALETTE_LINE_RE.match(s)
        if not m:
            break
        idx = int(m.group(1))
        hex_color = m.group(2)
        alpha = int(m.group(3)) if m.group(3) is not None else 255
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        # Enforce contiguous indices; this keeps index-grid lookups simple and
        # catches LLM answers that skip an entry.
        if idx != len(palette):
            raise ValueError(
                "palette index %d is out of order (expected %d)"
                % (idx, len(palette))
            )
        if not (0 <= alpha <= 255):
            raise ValueError("palette alpha out of range: %d" % alpha)
        palette.append((r, g, b, alpha))
        i += 1
    if not palette:
        raise ValueError("PALETTE block contains no color entries")
    return palette, i


def _parse_index_grid(lines: list[str], start: int, w: int, h: int, palette: list[tuple[int, int, int, int]]) -> list[list[tuple[int, int, int, int]]]:
    """Parse the palette-index grid into RGBA rows."""
    rows: list[list[tuple[int, int, int, int]]] = []
    i = start
    palette_n = len(palette)
    while i < len(lines):
        s = lines[i].strip()
        if not s or s.startswith("#") or _is_index_grid_label(s):
            i += 1
            continue
        tokens = s.split()
        # A leading "Index grid ..." label may appear on the same line as the
        # first row in sloppy LLM answers; tolerate it only if the line also
        # has exactly w tokens after removing common words.  Keeping this
        # conservative avoids silently accepting malformed answers.
        if len(tokens) != w:
            raise ValueError(
                "index row %d has %d columns; expected %d (line: %r)"
                % (len(rows) + 1, len(tokens), w, s)
            )
        row: list[tuple[int, int, int, int]] = []
        for tok in tokens:
            if tok in ("-1", "."):
                row.append((0, 0, 0, 0))
                continue
            try:
                idx = int(tok)
            except ValueError:
                raise ValueError("invalid index token %r" % tok) from None
            if idx < -1 or idx >= palette_n:
                raise ValueError(
                    "index %d out of range [0,%d) for palette" % (idx, palette_n)
                )
            if idx == -1:
                row.append((0, 0, 0, 0))
            else:
                row.append(palette[idx])
        rows.append(row)
        i += 1
        if len(rows) == h:
            break
    if len(rows) != h:
        raise ValueError("index grid has %d rows; expected %d" % (len(rows), h))
    # There must not be extra data rows beyond h.  Noise lines (blank lines,
    # comments, section labels) are allowed after the grid.
    while i < len(lines):
        s = lines[i].strip()
        if s and not _is_comment_or_label(s):
            raise ValueError("unexpected extra data after index grid: %r" % s)
        i += 1
    return rows


def _parse_hex_grid(lines: list[str], start: int, w: int, h: int) -> list[list[tuple[int, int, int, int]]]:
    """Parse a direct #RRGGBB / ---- hex grid into RGBA rows."""
    rows: list[list[tuple[int, int, int, int]]] = []
    i = start
    while i < len(lines):
        s = lines[i].strip()
        if _is_comment_or_label(s):
            i += 1
            continue
        tokens = s.split()
        if len(tokens) > w:
            raise ValueError(
                "hex row %d has %d columns; expected %d (line: %r)"
                % (len(rows) + 1, len(tokens), w, s)
            )
        if len(tokens) < w:
            # 容错：模型偶尔少写尾部透明列，自动补 ---- 到 W 列
            tokens = tokens + ["----"] * (w - len(tokens))
        row: list[tuple[int, int, int, int]] = []
        for tok in tokens:
            if tok == "----":
                row.append((0, 0, 0, 0))
                continue
            if not HEX_TOKEN_RE.match(tok):
                raise ValueError("invalid hex token %r" % tok)
            row.append((
                int(tok[1:3], 16),
                int(tok[3:5], 16),
                int(tok[5:7], 16),
                255,
            ))
        rows.append(row)
        i += 1
        if len(rows) == h:
            break
    if len(rows) != h:
        raise ValueError("hex grid has %d rows; expected %d" % (len(rows), h))
    while i < len(lines):
        s = lines[i].strip()
        if _is_comment_or_label(s):
            i += 1
            continue
        raise ValueError("unexpected extra data after hex grid: %r" % s)
    return rows


def parse_text_to_grid(text: str) -> tuple[int, int, list[list[tuple[int, int, int, int]]]]:
    """Parse full LLM text into (width, height, rows of RGBA tuples)."""
    lines = [ln.rstrip("\r\n") for ln in text.splitlines()]

    # Locate the header.  Allow a few leading blank/comment lines.
    header_idx = None
    for idx, ln in enumerate(lines):
        s = ln.strip()
        if _is_comment_or_label(s):
            continue
        if _parse_declared_size(s) is not None:
            header_idx = idx
            break
        raise ValueError("expected W=<w> H=<h> on first data line, got %r" % s)
    if header_idx is None:
        raise ValueError("missing W=<w> H=<h> header")
    w, h = _parse_declared_size(lines[header_idx])
    if w <= 0 or h <= 0:
        raise ValueError("invalid texture dimensions: %dx%d" % (w, h))

    start = _skip_noise(lines, header_idx + 1)
    if start >= len(lines):
        raise ValueError("no pixel data after W/H header")

    # Determine whether this is a palette+index answer or a direct hex grid.
    first = lines[start].strip()
    has_palette = first.lower().startswith("palette")
    if has_palette:
        palette, next_i = _parse_palette_block(lines, start)
        rows = _parse_index_grid(lines, next_i, w, h, palette)
    else:
        # Direct hex grid: validate first token visually.
        if not (HEX_TOKEN_RE.match(first.split()[0]) if first.split() else False) and not first.split()[0] == "----":
            raise ValueError(
                "expected PALETTE block or hex grid, got line %r" % first
            )
        rows = _parse_hex_grid(lines, start, w, h)

    return w, h, rows


def text_to_image(text: str) -> Image.Image:
    """Parse text and return an RGBA PIL image of the declared size."""
    w, h, rows = parse_text_to_grid(text)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, px in enumerate(row):
            img.putpixel((x, y), px)
    return img


def make_preview(img: Image.Image, scale: int | None = None) -> Image.Image:
    """Return a nearest-neighbour upscaled preview."""
    w, h = img.size
    if scale is None:
        scale = 16 if max(w, h) <= 16 else 8 if max(w, h) <= 64 else 4
    scale = max(1, scale)
    return img.resize((w * scale, h * scale), Image.NEAREST)


def validate_text_against_size(text: str, expected_size: tuple[int, int] | None = None) -> dict:
    """Parse and return a summary dict; raises on malformed input."""
    w, h, rows = parse_text_to_grid(text)
    if expected_size is not None and (w, h) != tuple(expected_size):
        raise ValueError(
            "declared size %dx%d does not match requested size %dx%d"
            % (w, h, expected_size[0], expected_size[1])
        )
    opaque = sum(1 for row in rows for px in row if px[3] >= ALPHA_THRESHOLD)
    return {
        "width": w,
        "height": h,
        "opaque_pixels": opaque,
        "total_pixels": w * h,
        "opaque_ratio": round(opaque / (w * h), 6),
    }


def _write_png(img: Image.Image, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    img.save(output, "PNG")


def _run_convert(args) -> int:
    input_path = normalize_path(args.input or args.text or "")
    if not input_path.exists():
        print("ERROR: input not found: %s" % input_path)
        return 1
    try:
        text = input_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        print("ERROR: input is not UTF-8 text: %s (%s)" % (input_path, e))
        return 1
    try:
        img = text_to_image(text)
    except Exception as e:
        print("ERROR: failed to parse %s: %s" % (input_path, e))
        return 1

    if args.size:
        try:
            sw, sh = args.size.lower().split("x", 1)
            expected = (int(sw), int(sh))
            if img.size != expected:
                print(
                    "ERROR: output size %dx%d does not match --size %dx%d"
                    % (img.size[0], img.size[1], expected[0], expected[1])
                )
                return 1
        except Exception as e:
            print("ERROR: invalid --size %r: %s" % (args.size, e))
            return 1

    output = normalize_path(args.output or (input_path.parent / (input_path.stem + ".png")))
    preview = normalize_path(args.preview or (output.parent / (output.stem + "_preview.png")))
    _write_png(img, output)
    preview_img = make_preview(img, args.preview_scale)
    _write_png(preview_img, preview)

    stats = validate_text_against_size(text)
    print("OK: %s -> %s (%dx%d)" % (input_path, output, img.size[0], img.size[1]))
    print("OK: preview -> %s (%dx%d)" % (preview, preview_img.size[0], preview_img.size[1]))
    print("OK: opaque_pixels=%d/%d" % (stats["opaque_pixels"], stats["total_pixels"]))
    print("OUTPUT=%s" % output)
    print("PREVIEW=%s" % preview)
    return 0


def _run_validate(args) -> int:
    target = normalize_path(args.validate)
    files: list[Path] = []
    if target.is_dir():
        files = sorted(target.rglob("*.txt"))
    elif target.is_file():
        files = [target]
    else:
        print("ERROR: --validate path not found: %s" % target)
        return 1

    failures = 0
    total = 0
    for fn in files:
        total += 1
        try:
            text = fn.read_text(encoding="utf-8")
            stats = validate_text_against_size(text)
            print("PASS %s (%dx%d, opaque=%d)" % (
                fn, stats["width"], stats["height"], stats["opaque_pixels"]
            ))
        except Exception as e:
            failures += 1
            print("FAIL %s: %s" % (fn, e))
    print("VALIDATE: %d/%d files parsed" % (total - failures, total))
    return 1 if failures else 0


# ---------------------------------------------------------------------------
# Self-test helpers
# ---------------------------------------------------------------------------


def _synth_16x16_palette_text() -> str:
    palette = [
        "#808080", "#a0a0a0", "#7070e0", "#6464f0", "#aaaaaa",
        "#505050", "#c8c8c8", "#9090d0", "#b0b0b0",
    ]
    rows = [
        [-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1],
        [-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1],
        [-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1],
        [-1, -1, -1, -1,  1,  0,  0,  1, -1, -1, -1, -1, -1, -1, -1, -1],
        [-1, -1, -1,  1,  0,  4,  4,  0,  1, -1, -1, -1, -1, -1, -1, -1],
        [-1, -1, -1,  0,  4,  7,  7,  4,  0, -1, -1, -1, -1, -1, -1, -1],
        [-1, -1, -1,  1,  0,  4,  4,  0,  1, -1, -1, -1, -1, -1, -1, -1],
        [-1, -1, -1, -1,  1,  0,  0,  1, -1, -1, -1, -1, -1, -1, -1, -1],
        [-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1],
        [-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1],
        [-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1],
        [-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1],
        [-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1],
        [-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1],
        [-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1],
        [-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1],
    ]
    lines = ["W=16 H=16", "", "PALETTE"]
    for idx, c in enumerate(palette):
        lines.append("%d: %s" % (idx, c))
    lines.append("")
    for row in rows:
        lines.append(" ".join("-1" if v == -1 else str(v) for v in row))
    return "\n".join(lines) + "\n"


def _synth_16x16_noisy_palette_text() -> str:
    """16x16 palette+index answer with INDEX GRID and ``#`` comments."""
    palette = ["#b03030", "#30b030", "#3030b0"]
    lines = [
        "W=16 H=16",
        "# top comment after header",
        "",
        "PALETTE",
        "# palette comment",
        "0: #b03030",
        "1: #30b030",
        "2: #3030b0",
        "",
        "# comment before the index grid label",
        "INDEX GRID",
        "# comment right after INDEX GRID",
    ]
    for y in range(16):
        row = [(x + y) % 3 for x in range(16)]
        lines.append(" ".join(str(v) for v in row))
    return "\n".join(lines) + "\n"


def _synth_multi_face_noisy_raw() -> str:
    """Two-face raw answer; every face uses INDEX GRID and ``#`` comments."""
    lines: list[str] = []

    def append_face(face_id: str, png_path: str, color: str) -> None:
        lines.append("=== face: %s ===" % face_id)
        lines.append("FILE: %s" % png_path)
        lines.append("# face %s header comment" % face_id)
        lines.append("W=16 H=16")
        lines.append("")
        lines.append("PALETTE")
        lines.append("# face %s palette comment" % face_id)
        lines.append("0: %s" % color)
        lines.append("")
        lines.append("INDEX GRID" if face_id == "front" else "index grid:")
        lines.append("# face %s grid comment" % face_id)
        for _ in range(16):
            lines.append("0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0")
        lines.append("")

    append_face("front", "assets/demo/textures/block/custom_front.png", "#ff5050")
    append_face("back", "assets/demo/textures/block/custom_back.png", "#5050ff")
    return "\n".join(lines) + "\n"


def _synth_64x32_hex_text() -> str:
    """64x32 direct-hex grid with opaque first-column rows (covers the bug)."""
    w, h = 64, 32
    lines = ["W=64 H=32", ""]
    for y in range(h):
        row = []
        for x in range(w):
            if y < 4 or y >= h - 4:
                row.append("----")
            else:
                # No left/right border: rows 4..27 start with an opaque #RRGGBB,
                # so the parser must not treat them as comments.
                row.append("#5a7d2a" if (x + y) % 4 == 0 else "#7ca63a")
        lines.append(" ".join(row))
    return "\n".join(lines) + "\n"


def _synth_16x16_stone_sword_hex_text() -> str:
    """Exact 16x16 hex grid for stone_sword.

    Generated with:
        python3 asset_to_text.py mc_asset_library/raw/item/stone_sword.png \\
            --mode grid --no-header
    Rows 13-15 start with an opaque #RRGGBB, so this is the regression case
    reported in the mc2-convert review.
    """
    rows = [
        "---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- #494949 #494949 #494949",
        "---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- #494949 #95918d #b3b1af #212121",
        "---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- #494949 #95918d #b3b1af #95918d #212121",
        "---- ---- ---- ---- ---- ---- ---- ---- ---- ---- #494949 #95918d #b3b1af #95918d #212121 ----",
        "---- ---- ---- ---- ---- ---- ---- ---- ---- #494949 #95918d #b3b1af #95918d #212121 ---- ----",
        "---- ---- ---- ---- ---- ---- ---- ---- #494949 #95918d #b3b1af #95918d #212121 ---- ---- ----",
        "---- ---- #494949 #494949 ---- ---- ---- #494949 #787777 #b3b1af #95918d #212121 ---- ---- ---- ----",
        "---- ---- #494949 #5a5a5a #494949 ---- #494949 #787777 #b3b1af #787777 #212121 ---- ---- ---- ---- ----",
        "---- ---- ---- #494949 #787777 #212121 #787777 #95918d #787777 #212121 ---- ---- ---- ---- ---- ----",
        "---- ---- ---- #494949 #787777 #787777 #5a5a5a #787777 #212121 ---- ---- ---- ---- ---- ---- ----",
        "---- ---- ---- ---- #494949 #5a5a5a #494949 #212121 ---- ---- ---- ---- ---- ---- ---- ----",
        "---- ---- ---- #493615 #684e1e #212121 #494949 #494949 #212121 ---- ---- ---- ---- ---- ---- ----",
        "---- ---- #493615 #896727 #281e0b ---- #212121 #212121 #494949 #212121 ---- ---- ---- ---- ---- ----",
        "#494949 #494949 #684e1e #281e0b ---- ---- ---- ---- #212121 #212121 ---- ---- ---- ---- ---- ----",
        "#494949 #5a5a5a #212121 ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ----",
        "#212121 #212121 #212121 ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ----",
    ]
    return "\n".join(["W=16 H=16", ""] + rows) + "\n"


def _run_self_test(args) -> int:
    report_lines: list[str] = []
    failures = 0
    tmp = Path("text_to_texture_selftest_assets")
    tmp.mkdir(parents=True, exist_ok=True)

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        status = "PASS" if cond else "FAIL"
        report_lines.append("[%s] %s%s" % (status, name, (" — " + detail) if detail else ""))
        if not cond:
            failures += 1

    try:
        # 1. 16x16 palette+index
        t16 = _synth_16x16_palette_text()
        img16 = text_to_image(t16)
        check("16x16 palette+index parse", img16.size == (16, 16), "size=%s" % (img16.size,))
        stats16 = validate_text_against_size(t16)
        check("16x16 opaque count > 0", stats16["opaque_pixels"] > 0,
              "opaque=%d" % stats16["opaque_pixels"])
        out16 = tmp / "synth_16x16.png"
        prev16 = tmp / "synth_16x16_preview.png"
        img16.save(out16, "PNG")
        make_preview(img16, 16).save(prev16, "PNG")
        check("16x16 output file written", out16.exists() and out16.stat().st_size > 0)
        check("16x16 preview written", prev16.exists() and prev16.stat().st_size > 0)
        report_lines.append("PATH_16=%s" % out16)
        report_lines.append("PATH_PREVIEW_16=%s" % prev16)

        # 2. 64x32 hex grid
        t64 = _synth_64x32_hex_text()
        img64 = text_to_image(t64)
        check("64x32 hex grid parse", img64.size == (64, 32), "size=%s" % (img64.size,))
        stats64 = validate_text_against_size(t64)
        check("64x32 opaque count > 0", stats64["opaque_pixels"] > 0,
              "opaque=%d" % stats64["opaque_pixels"])
        out64 = tmp / "synth_64x32.png"
        prev64 = tmp / "synth_64x32_preview.png"
        img64.save(out64, "PNG")
        make_preview(img64, 8).save(prev64, "PNG")
        check("64x32 output file written", out64.exists() and out64.stat().st_size > 0)
        check("64x32 preview written", prev64.exists() and prev64.stat().st_size > 0)
        report_lines.append("PATH_64=%s" % out64)
        report_lines.append("PATH_PREVIEW_64=%s" % prev64)

        # 2b. 16x16 stone_sword direct hex grid (leading #RRGGBB rows)
        t_stone = _synth_16x16_stone_sword_hex_text()
        img_stone = text_to_image(t_stone)
        check("16x16 stone_sword hex grid parse", img_stone.size == (16, 16),
              "size=%s" % (img_stone.size,))
        stats_stone = validate_text_against_size(t_stone)
        check("16x16 stone_sword hex grid opaque > 0",
              stats_stone["opaque_pixels"] > 0, "opaque=%d" % stats_stone["opaque_pixels"])
        out_stone = tmp / "stone_sword_hex_16x16.png"
        img_stone.save(out_stone, "PNG")
        check("16x16 stone_sword hex output written",
              out_stone.exists() and out_stone.stat().st_size > 0)
        report_lines.append("PATH_STONE_16=%s" % out_stone)

        # 2c. 16x16 palette+index with INDEX GRID label and # comments
        t_noisy16 = _synth_16x16_noisy_palette_text()
        img_noisy16 = text_to_image(t_noisy16)
        check("16x16 noisy palette+index grid parse", img_noisy16.size == (16, 16),
              "size=%s" % (img_noisy16.size,))
        stats_noisy16 = validate_text_against_size(t_noisy16)
        check("16x16 noisy opaque count > 0", stats_noisy16["opaque_pixels"] > 0,
              "opaque=%d" % stats_noisy16["opaque_pixels"])
        out_noisy16 = tmp / "synth_16x16_noisy.png"
        img_noisy16.save(out_noisy16, "PNG")
        check("16x16 noisy output written", out_noisy16.exists() and out_noisy16.stat().st_size > 0)
        report_lines.append("PATH_NOISY_16=%s" % out_noisy16)

        # 2d. Multi-face raw with INDEX GRID labels and # comments
        t_multi = _synth_multi_face_noisy_raw()
        # Local import: package_asset imports text_to_texture, which is safe
        # once this module is already being executed/imported.
        import package_asset as _pa
        face_blocks = _pa.split_face_blocks(t_multi)
        check("multi-face noisy raw has 2 faces", len(face_blocks) == 2,
              "faces=%d" % len(face_blocks))
        for fid, block in face_blocks:
            cleaned = _pa._clean_face_text(block)
            img_face = text_to_image(cleaned)
            check("multi-face noisy %s parse" % fid, img_face.size == (16, 16),
                  "size=%s" % (img_face.size,))
            check("multi-face noisy %s opaque > 0" % fid,
                  validate_text_against_size(cleaned)["opaque_pixels"] > 0)
            face_out = tmp / ("synth_multi_face_%s.png" % fid)
            img_face.save(face_out, "PNG")
            check("multi-face noisy %s output written" % fid,
                  face_out.exists() and face_out.stat().st_size > 0)
            report_lines.append("PATH_MULTI_%s=%s" % (fid.upper(), face_out))

        # 3. Format rejection: wrong dims
        bad = "W=16 H=8\n" + " ".join(["----"] * 16) + "\n"
        try:
            parse_text_to_grid(bad)
            check("reject wrong row count", False)
        except ValueError:
            check("reject wrong row count", True)

        # 4. Format rejection: out-of-range index
        bad_idx = "W=4 H=1\nPALETTE\n0: #ff0000\n1 9 0 -1\n"
        try:
            parse_text_to_grid(bad_idx)
            check("reject out-of-range index", False)
        except ValueError:
            check("reject out-of-range index", True)

        # 5. Alpha/transparency check
        w, h, rows = parse_text_to_grid(t16)
        transparent_pixels = sum(1 for row in rows for px in row if px[3] == 0)
        check("transparent alpha==0 exists", transparent_pixels > 0,
              "transparent=%d" % transparent_pixels)

        report_lines.append("RESULT: %s" % ("PASS" if failures == 0 else "FAIL (%d)" % failures))
        (Path(SELFTEST_REPORT)).write_text("\n".join(report_lines) + "\n", encoding="utf-8")
        print("\n".join(report_lines))
        print("selftest report: %s" % Path(SELFTEST_REPORT).resolve())
        return 0 if failures == 0 else 1
    finally:
        # Keep temp assets; they are small and useful as evidence.
        pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert LLM pixel-text answers to PNG and preview."
    )
    parser.add_argument("text", nargs="?", help="Input LLM text file (or use --input)")
    parser.add_argument("--input", dest="input", help="Input LLM text file")
    parser.add_argument("--output", help="Output PNG path")
    parser.add_argument("--preview", help="Output preview PNG path")
    parser.add_argument("--preview-scale", type=int, default=None,
                        help="Nearest-neighbour preview scale (default auto)")
    parser.add_argument("--size", help="Expected WxH size, enforced if given")
    parser.add_argument("--validate", help="Validate a .txt file or directory of .txt files")
    parser.add_argument("--self-test", action="store_true",
                        help="Synthesize 16x16 and 64x32 inputs and validate the parser")
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test(args)
    if args.validate:
        return _run_validate(args)
    if not args.text and not args.input:
        parser.error("provide an input text file or use --self-test/--validate")
    return _run_convert(args)


if __name__ == "__main__":
    sys.exit(main())
