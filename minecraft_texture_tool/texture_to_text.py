#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
texture_to_text.py — Convert Minecraft texture PNGs into LLM-readable text.

The output describes every opaque pixel with its exact RGB hex color and also
gives a shape silhouette + a coarse ASCII color map, so a text-only LLM can
reconstruct the item's outline and approximate colors.

Modes:
  compact (default)  palette + index grid + silhouette + ASCII
  all                exact hex grid + silhouette + ASCII
  grid               exact hex grid only (no silhouette / ASCII)
  json               machine-readable JSON (x/y/r/g/b/a/hex)

Usage examples:
    python3 texture_to_text.py textures/stone_sword.png
    python3 texture_to_text.py textures/*.png --mode grid --no-header --no-silhouette --no-ascii
    python3 texture_to_text.py textures/stone_sword.png --mode compact --stats
    python3 texture_to_text.py textures/stone_sword.png --mode json
    python3 texture_to_text.py textures/*.png --mode all --output-dir samples/
    python3 texture_to_text.py --self-test
"""

from __future__ import annotations

import argparse
import colorsys
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.stderr.write("ERROR: Pillow is required.  Install with:  pip install pillow\n")
    raise

DEFAULT_ALPHA_THRESHOLD = 8
DEFAULT_MODE = "compact"
TRANSPARENT_HEX = "----"
TRANSPARENT_CHAR = "."
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


# ---------------------------------------------------------------------------
# Path / small helpers
# ---------------------------------------------------------------------------

def normalize_path(path: str) -> Path:
    """Accept Windows paths C:\\... and C:/... while running under WSL."""
    s = str(path)
    if os.name == "nt":
        return Path(s)
    m = re.match(r"^([a-zA-Z]):[\\/](.*)$", s)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2).replace("\\", "/")
        return Path("/mnt") / drive / rest
    return Path(s)


def rgb_hex(rgb) -> str:
    r, g, b = rgb[:3]
    return f"#{r:02x}{g:02x}{b:02x}"


def opacity_char(alpha: int, threshold: int) -> str:
    return "X" if alpha >= threshold else "."


def ascii_color_char(r: int, g: int, b: int) -> str:
    """
    Map an opaque RGB pixel to a single perceptible character.

    The mapping is coarse but intuitive:
      .  transparent
      #  near-black      (all channels < 48)
      +  dark gray       (low saturation, max < 120)
      =  light gray      (low saturation, max < 220)
      @  white / near-white (low saturation, max >= 220)
      R  red
      O  orange / brown
      Y  yellow
      G  green
      C  cyan
      B  blue
      M  magenta / purple
      P  pink
    """
    mx = max(r, g, b)
    mn = min(r, g, b)
    sat = mx - mn

    if sat < 18:  # neutral / gray
        if mx < 48:
            return "#"
        if mx < 120:
            return "+"
        if mx < 220:
            return "="
        return "@"

    h, _s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    h_deg = h * 360

    if v < 0.22:
        return "#"
    if h_deg < 15 or h_deg >= 345:
        return "R"
    if h_deg < 42:
        return "O"
    if h_deg < 70:
        return "Y"
    if h_deg < 160:
        return "G"
    if h_deg < 205:
        return "C"
    if h_deg < 260:
        return "B"
    if h_deg < 300:
        return "M"
    if h_deg < 345:
        return "P"
    return "R"


def has_semitransparent(im) -> bool:
    """Return True if any pixel has alpha strictly between 0 and 255."""
    w, h = im.size
    for y in range(h):
        for x in range(w):
            a = im.getpixel((x, y))[3]
            if 0 < a < 255:
                return True
    return False


# ---------------------------------------------------------------------------
# Independent PNG pixel reader (zlib only)
#
# This is deliberately kept separate from Pillow. It parses the PNG container,
# inflates the IDAT stream with the standard-library zlib module, and applies
# the unfiltering rules from the PNG specification. It is therefore a second,
# Pillow-independent oracle for the pixel data used by the conversion scripts.
# ---------------------------------------------------------------------------

def _paeth_predictor(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def read_png_rgba(path) -> list[list[tuple[int, int, int, int]]]:
    """
    Decode an 8-bit non-interlaced PNG (gray, RGB, or RGBA) into RGBA pixel
    rows using only the Python standard library (struct + zlib).
    """
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG file: %s" % path)

    width = height = None
    bit_depth = None
    color_type = None
    interlace = None
    idat = bytearray()
    pos = 8
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError("truncated PNG chunk header")
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        chunk_type = data[pos + 4:pos + 8]
        chunk_data = data[pos + 8:pos + 8 + length]
        if len(chunk_data) != length:
            raise ValueError("truncated PNG chunk: %s" % chunk_type)
        if chunk_type == b"IHDR":
            (width, height, bit_depth, color_type,
             _compression, _filter_method, interlace) = struct.unpack(
                ">IIBBBBB", chunk_data
            )
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
        pos += 12 + length

    if width is None or height is None:
        raise ValueError("missing IHDR in %s" % path)
    if bit_depth != 8:
        raise NotImplementedError(
            "independent PNG reader supports only 8-bit PNG (got bit depth %d)" % bit_depth
        )
    if color_type not in (0, 2, 6):
        raise NotImplementedError(
            "independent PNG reader supports gray/RGB/RGBA "
            "(color type %d)" % color_type
        )
    if interlace != 0:
        raise NotImplementedError("independent PNG reader does not support interlaced PNG")

    channels = {0: 1, 2: 3, 6: 4}[color_type]
    # Each scanline has one filter byte followed by width*channels bytes.
    stride = width * channels
    if len(idat) == 0:
        raise ValueError("PNG has no IDAT chunks")
    raw = zlib.decompress(bytes(idat))
    if len(raw) != height * (stride + 1):
        raise ValueError(
            "PNG raw size mismatch: expected %d bytes, got %d"
            % (height * (stride + 1), len(raw))
        )

    bpp = channels
    previous = bytearray(stride)
    rows = []
    pos = 0
    for _y in range(height):
        filter_type = raw[pos]
        pos += 1
        scan = bytearray(raw[pos:pos + stride])
        pos += stride

        # Undo PNG per-scanline filtering in place.
        if filter_type == 0:
            pass  # None
        elif filter_type == 1:  # Sub
            for i in range(bpp, stride):
                scan[i] = (scan[i] + scan[i - bpp]) & 0xFF
        elif filter_type == 2:  # Up
            for i in range(stride):
                scan[i] = (scan[i] + previous[i]) & 0xFF
        elif filter_type == 3:  # Average
            for i in range(stride):
                left = scan[i - bpp] if i >= bpp else 0
                up = previous[i]
                scan[i] = (scan[i] + ((left + up) >> 1)) & 0xFF
        elif filter_type == 4:  # Paeth
            for i in range(stride):
                left = scan[i - bpp] if i >= bpp else 0
                up = previous[i]
                upper_left = previous[i - bpp] if i >= bpp else 0
                scan[i] = (scan[i] + _paeth_predictor(left, up, upper_left)) & 0xFF
        else:
            raise ValueError("unknown PNG filter type: %d" % filter_type)

        row = []
        for x in range(width):
            base_idx = x * channels
            if color_type == 0:
                v = scan[base_idx]
                row.append((v, v, v, 255))
            elif color_type == 2:
                row.append((scan[base_idx], scan[base_idx + 1],
                            scan[base_idx + 2], 255))
            else:
                row.append((scan[base_idx], scan[base_idx + 1],
                            scan[base_idx + 2], scan[base_idx + 3]))
        rows.append(row)
        previous = scan
    return rows


def hex_lines_from_rgba(rows, threshold: int, alpha_column: bool = False) -> list[str]:
    """Render the same hex-grid format as `render_hex_lines`, but from raw rows."""
    lines = []
    for row in rows:
        tokens = []
        for r, g, b, a in row:
            if alpha_column:
                tokens.append("%s a=%d" % (rgb_hex((r, g, b)), a))
            elif a < threshold:
                tokens.append(TRANSPARENT_HEX)
            else:
                tokens.append(rgb_hex((r, g, b)))
        lines.append(" ".join(tokens))
    return lines


def quantize_palette(image, threshold: int, alpha_column: bool = False, flat: bool = False):
    """
    Return (unique_colors, palette_indices).

    When `alpha_column` is False the palette key is RGB; alpha is binary
    (opaque/transparent).  When True the palette key includes alpha so that a
    semi-transparent source can be reconstructed exactly.
    """
    im = image.convert("RGBA")
    w, h = im.size
    colors = []
    index_of = {}
    grid = []
    for y in range(h):
        row_idx = []
        for x in range(w):
            px = im.getpixel((x, y))
            if alpha_column:
                # Alpha-aware mode: palette keys include alpha, and even fully
                # transparent pixels are indexed so nothing is discarded.
                key = px
                if key not in index_of:
                    index_of[key] = len(colors)
                    colors.append(key)
                row_idx.append(index_of[key])
            elif px[3] < threshold:
                row_idx.append(-1)  # transparent
            else:
                key = px[:3]
                if key not in index_of:
                    index_of[key] = len(colors)
                    colors.append(key)
                row_idx.append(index_of[key])
        grid.append(row_idx)
    if flat:
        return colors, [idx for row in grid for idx in row]
    return colors, grid


def render_stats(doc: str) -> str:
    """Append character count and approximate token count."""
    chars = len(doc)
    # ~4 chars/token is the conventional rough English/text estimate used here.
    tokens = max(1, round(chars / 4))
    return (
        "\n\n## Stats\n"
        "chars: %d\n"
        "tokens (~4 chars/token): %d\n" % (chars, tokens)
    )


# ---------------------------------------------------------------------------
# Output building blocks
# ---------------------------------------------------------------------------

def render_hex_lines(im, threshold: int, alpha_column: bool = False) -> list[str]:
    """Return the exact hex-grid lines. Each row is 16 space-separated tokens."""
    w, h = im.size
    lines = []
    for y in range(h):
        row = []
        for x in range(w):
            r, g, b, a = im.getpixel((x, y))
            if alpha_column:
                # Alpha-aware mode: every pixel carries its exact alpha value,
                # so even 0<alpha<255 pixels are not silently binarized.
                row.append(f"{rgb_hex((r, g, b))} a={a}")
            elif a < threshold:
                row.append(TRANSPARENT_HEX)
            else:
                row.append(rgb_hex((r, g, b)))
        lines.append(" ".join(row))
    return lines


def render_silhouette_lines(im, threshold: int) -> list[str]:
    w, h = im.size
    return ["".join(opacity_char(im.getpixel((x, y))[3], threshold) for x in range(w)) for y in range(h)]


def render_ascii_lines(im, threshold: int) -> list[str]:
    w, h = im.size
    lines = []
    for y in range(h):
        row = []
        for x in range(w):
            r, g, b, a = im.getpixel((x, y))
            row.append(ascii_color_char(r, g, b) if a >= threshold else TRANSPARENT_CHAR)
        lines.append("".join(row))
    return lines


def render_compact_blocks(im, threshold: int, alpha_column: bool = False):
    """Return (palette_lines, index_lines)."""
    colors, grid = quantize_palette(im, threshold, alpha_column=alpha_column)
    palette_lines = []
    for i, key in enumerate(colors):
        if alpha_column:
            r, g, b, a = key
            palette_lines.append(f"{i:2d}: {rgb_hex((r, g, b))} a={a}")
        else:
            palette_lines.append(f"{i:2d}: {rgb_hex(key)}")
    index_lines = [" ".join("%2s" % str(v) for v in row) for row in grid]
    return palette_lines, index_lines


# ---------------------------------------------------------------------------
# Document builder
# ---------------------------------------------------------------------------

def build_document(path: Path, image, args) -> str:
    im = image.convert("RGBA")
    w, h = im.size
    threshold = args.alpha_threshold
    name = path.name if path else "<texture>"
    alpha_column = getattr(args, "alpha_column", False)

    if args.mode == "json":
        return render_json(path, im, threshold)

    lines: list[str] = []
    if not args.no_header:
        lines.append("# Texture: %s" % name)
        lines.append("")
        lines.append("Size: %dx%d" % (w, h))
        lines.append("Alpha threshold: %d (alpha < %d -> transparent)" % (threshold, threshold))
        if alpha_column:
            lines.append("Alpha column: exact #RRGGBB a=NN; silhouette/ASCII still use the binary threshold")
        opaque = sum(
            1
            for y in range(h)
            for x in range(w)
            if im.getpixel((x, y))[3] >= threshold
        )
        lines.append("Opaque pixels: %d / %d" % (opaque, w * h))
        lines.append("")

    # --- compact: palette + index grid + silhouette + ASCII ---
    if args.mode == "compact":
        palette_lines, index_lines = render_compact_blocks(im, threshold, alpha_column)
        if not args.no_silhouette:
            lines.append("## Silhouette (X=opaque, .=transparent)")
            lines.append("```")
            lines.extend(render_silhouette_lines(im, threshold))
            lines.append("```")
            lines.append("")
        if not args.no_ascii:
            lines.append("## ASCII color map")
            lines.append("Legend: . transparent | # near-black | + dark-gray | = light-gray | @ white | R red | O orange/brown | Y yellow | G green | C cyan | B blue | M magenta | P pink")
            lines.append("```")
            lines.extend(render_ascii_lines(im, threshold))
            lines.append("```")
            lines.append("")
        if alpha_column:
            lines.append("## Palette (hex + alpha)")
        else:
            lines.append("## Palette (hex)")
        lines.append("```")
        lines.extend(palette_lines)
        lines.append("```")
        lines.append("")
        if alpha_column:
            lines.append("## Index grid (palette index; alpha column active)")
        else:
            lines.append("## Index grid (-1 = transparent)")
        lines.append("```")
        lines.extend(index_lines)
        lines.append("```")

    # --- all: exact hex grid + silhouette + ASCII ---
    elif args.mode == "all":
        lines.append("## Hex color grid (row 0 is top; `----` = transparent)")
        lines.append("```")
        lines.extend(render_hex_lines(im, threshold, alpha_column))
        lines.append("```")
        lines.append("")
        if not args.no_silhouette:
            lines.append("## Silhouette (X=opaque, .=transparent)")
            lines.append("```")
            lines.extend(render_silhouette_lines(im, threshold))
            lines.append("```")
            lines.append("")
        if not args.no_ascii:
            lines.append("## ASCII color map")
            lines.append("Legend: . transparent | # near-black | + dark-gray | = light-gray | @ white | R red | O orange/brown | Y yellow | G green | C cyan | B blue | M magenta | P pink")
            lines.append("```")
            lines.extend(render_ascii_lines(im, threshold))
            lines.append("```")
            lines.append("")

    # --- grid: exact hex grid only ---
    elif args.mode == "grid":
        if args.no_header:
            # Bare 16-line grid: no fences, no section heading, no metadata.
            lines.extend(render_hex_lines(im, threshold, alpha_column))
        else:
            lines.append("## Hex color grid (row 0 is top; `----` = transparent)")
            lines.append("```")
            lines.extend(render_hex_lines(im, threshold, alpha_column))
            lines.append("```")

    # --- optional downsampled average-color grid (kept from original) ---
    if args.blocks > 1:
        lines.append("")
        lines.append("## Downsampled average-color grid (%dx%d blocks)" % (args.blocks, args.blocks))
        lines.append("```")
        bw = w // args.blocks
        bh = h // args.blocks
        for by in range(args.blocks):
            row = []
            for bx in range(args.blocks):
                total = [0, 0, 0, 0]
                count = 0
                for y in range(by * bh, (by + 1) * bh):
                    for x in range(bx * bw, (bx + 1) * bw):
                        px = im.getpixel((x, y))
                        if px[3] >= threshold:
                            total[0] += px[0]
                            total[1] += px[1]
                            total[2] += px[2]
                            count += 1
                if count == 0:
                    row.append("----")
                else:
                    row.append(rgb_hex((total[0] // count, total[1] // count, total[2] // count)))
            lines.append(" ".join(row))
        lines.append("```")

    return "\n".join(lines)


def render_json(path: Path, im, threshold: int) -> str:
    w, h = im.size
    pixels = []
    for y in range(h):
        row = []
        for x in range(w):
            r, g, b, a = im.getpixel((x, y))
            row.append(
                {
                    "x": x,
                    "y": y,
                    "r": r,
                    "g": g,
                    "b": b,
                    "a": a,
                    "hex": rgb_hex((r, g, b)) if a >= threshold else None,
                }
            )
        pixels.append(row)
    data = {
        "texture": path.name,
        "size": [w, h],
        "alpha_threshold": threshold,
        "pixels": pixels,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def run_self_test() -> int:
    base = Path(__file__).resolve().parent
    texture_dir = base / "textures"
    pngs = sorted(texture_dir.glob("*.png"))
    if not pngs:
        sys.stderr.write("FAIL: no PNG files found under %s\n" % texture_dir)
        return 1

    (base / "tmp").mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve()
    threshold = DEFAULT_ALPHA_THRESHOLD
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

    def run_cli(args, cwd=None):
        return subprocess.run(
            [sys.executable, str(script)] + args,
            cwd=cwd or str(base),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def windows_form(path: Path):
        """Convert /mnt/c/... to C:/... for WSL path-normalization tests."""
        s = str(path)
        if s.startswith("/mnt/"):
            return s[5].upper() + ":" + s[6:]
        return None

    print("# texture_to_text.py self-test")
    print("Texture dir: %s" % texture_dir)
    print("Alpha threshold: %d" % threshold)
    print("")

    # ------------------------------------------------------------------
    # 1) Built-in 8 textures: Pillow conversion + independent zlib oracle.
    # ------------------------------------------------------------------
    for p in pngs:
        try:
            with Image.open(p) as image:
                im = image.convert("RGBA")
                w, h = im.size
                if (w, h) != (16, 16):
                    raise AssertionError("size is %dx%d, expected 16x16" % (w, h))
                if has_semitransparent(im):
                    raise AssertionError(
                        "contains semi-transparent alpha; the shipped textures are 0/255"
                    )

                indep_rows = read_png_rgba(p)
                if len(indep_rows) != h or any(len(r) != w for r in indep_rows):
                    raise AssertionError("independent PNG reader returned wrong dimensions")

                # Cross-check Pillow's decoded pixels against the zlib-only reader.
                for y in range(h):
                    for x in range(w):
                        pil_px = tuple(im.getpixel((x, y)))
                        zlib_px = tuple(indep_rows[y][x])
                        if pil_px != zlib_px:
                            raise AssertionError(
                                "Pillow/zlib pixel mismatch at (%d,%d): %s vs %s"
                                % (x, y, pil_px, zlib_px)
                            )

                # Hex-grid content must match what an independent reader would render.
                hex_lines = render_hex_lines(im, threshold)
                expected_indep = hex_lines_from_rgba(indep_rows, threshold)
                if hex_lines != expected_indep:
                    raise AssertionError("hex grid differs between Pillow and zlib reader")

                if len(hex_lines) != 16:
                    raise AssertionError("hex grid has %d rows, expected 16" % len(hex_lines))
                for y, line in enumerate(hex_lines):
                    tokens = line.split(" ")
                    if len(tokens) != 16:
                        raise AssertionError(
                            "hex row %d has %d tokens, expected 16" % (y, len(tokens))
                        )
                    for x, tok in enumerate(tokens):
                        if tok != TRANSPARENT_HEX and not HEX_RE.match(tok):
                            raise AssertionError(
                                "invalid grid token at (%d,%d): %r" % (x, y, tok)
                            )

                # Compact reversibility: palette + index reconstruct RGB exactly.
                colors, grid = quantize_palette(im, threshold, alpha_column=False)
                for y in range(h):
                    for x in range(w):
                        idx = grid[y][x]
                        r, g, b, a = im.getpixel((x, y))
                        if a < threshold:
                            if idx != -1:
                                raise AssertionError(
                                    "compact transparent index at (%d,%d) != -1" % (x, y)
                                )
                        else:
                            if idx == -1:
                                raise AssertionError(
                                    "compact opaque index at (%d,%d) is -1" % (x, y)
                                )
                            if colors[idx] != (r, g, b):
                                raise AssertionError(
                                    "compact RGB mismatch at (%d,%d): palette=%s pixel=%s"
                                    % (x, y, colors[idx], (r, g, b))
                                )

                report("%s (16x16, hex grid exact, compact reversible, PIL==zlib)" % p.name, True)
        except Exception as e:
            report("%s" % p.name, False, str(e))

    texture = texture_dir / "stone_sword.png"
    if not texture.exists() and pngs:
        texture = pngs[0]

    # ------------------------------------------------------------------
    # 2) CLI semantics: --mode grid --no-header must be bare 16-line hex.
    # ------------------------------------------------------------------
    res_grid = run_cli([str(texture), "--mode", "grid", "--no-header"])
    grid_ok = res_grid.returncode == 0
    grid_lines = res_grid.stdout.strip().splitlines() if res_grid.stdout.strip() else []
    grid_ok = grid_ok and len(grid_lines) == 16 and all(
        len(line.split(" ")) == 16 for line in grid_lines
    )
    grid_ok = grid_ok and "##" not in res_grid.stdout
    grid_ok = grid_ok and "```" not in res_grid.stdout
    grid_ok = grid_ok and "Silhouette" not in res_grid.stdout
    grid_ok = grid_ok and "ASCII color" not in res_grid.stdout
    grid_ok = grid_ok and "# Texture" not in res_grid.stdout
    expected_grid_hex = "\n".join(hex_lines_from_rgba(read_png_rgba(texture), threshold))
    grid_ok = grid_ok and res_grid.stdout.rstrip("\n") == expected_grid_hex
    report("--mode grid --no-header outputs bare 16-line hex", grid_ok,
           ("exit=%d" % res_grid.returncode) if not grid_ok else "")

    # ------------------------------------------------------------------
    # 3) Default mode must be compact.
    # ------------------------------------------------------------------
    res_default = run_cli([str(texture)])
    default_ok = res_default.returncode == 0
    default_ok = default_ok and "## Silhouette" in res_default.stdout
    default_ok = default_ok and "## ASCII color map" in res_default.stdout
    default_ok = default_ok and "## Palette (hex)" in res_default.stdout
    default_ok = default_ok and "## Index grid" in res_default.stdout
    default_ok = default_ok and "## Hex color grid" not in res_default.stdout
    report("default mode is compact", default_ok,
           ("exit=%d" % res_default.returncode) if not default_ok else "")

    # ------------------------------------------------------------------
    # 4) Semi-transparent: --alpha-column works; no-alpha-column fails.
    # ------------------------------------------------------------------
    with tempfile.TemporaryDirectory(prefix="self-test-alpha-", dir=base / "tmp") as td:
        semi_path = Path(td) / "semi_alpha.png"
        img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        for y in range(16):
            for x in range(16):
                if x < 4:
                    img.putpixel((x, y), (255, 0, 0, 0))
                elif x < 8:
                    img.putpixel((x, y), (0, 255, 0, 128))
                elif x < 12:
                    img.putpixel((x, y), (0, 0, 255, 200))
                else:
                    img.putpixel((x, y), (255, 255, 255, 255))
        img.save(semi_path)

        with Image.open(semi_path) as image:
            im = image.convert("RGBA")
            indep_semi = read_png_rgba(semi_path)
            semi_ok = has_semitransparent(im)
            for y in range(16):
                for x in range(16):
                    if tuple(im.getpixel((x, y))) != tuple(indep_semi[y][x]):
                        semi_ok = False
            report("semi-transparent PNG passes independent zlib oracle", semi_ok)

        res_alpha = run_cli([str(semi_path), "--alpha-column", "--mode", "grid", "--no-header"])
        alpha_ok = res_alpha.returncode == 0
        alpha_lines = res_alpha.stdout.strip().splitlines() if res_alpha.stdout.strip() else []
        alpha_ok = alpha_ok and len(alpha_lines) == 16
        alpha_ok = alpha_ok and all(" a=" in line for line in alpha_lines)
        expected_alpha = "\n".join(hex_lines_from_rgba(indep_semi, threshold, alpha_column=True))
        alpha_ok = alpha_ok and res_alpha.stdout.rstrip("\n") == expected_alpha
        report("--alpha-column emits alpha-aware #RRGGBB a=NN lines", alpha_ok,
               ("exit=%d" % res_alpha.returncode) if not alpha_ok else "")

        res_noalpha = run_cli([str(semi_path)])
        noalpha_ok = res_noalpha.returncode != 0
        noalpha_ok = noalpha_ok and "semi-transparent alpha" in res_noalpha.stderr
        report("semi-transparent without --alpha-column exits non-zero", noalpha_ok,
               ("exit=%d" % res_noalpha.returncode) if not noalpha_ok else "")

    # ------------------------------------------------------------------
    # 5) Windows C:/ and C:\ input-path normalization (WSL only).
    # ------------------------------------------------------------------
    win_texture = windows_form(texture)
    if win_texture is not None:
        res_win = run_cli([win_texture, "--mode", "grid", "--no-header"])
        res_win_bs = run_cli([win_texture.replace("/", "\\"), "--mode", "grid", "--no-header"])
        res_posix = run_cli([str(texture), "--mode", "grid", "--no-header"])
        win_input_ok = (
            res_win.returncode == 0
            and res_win_bs.returncode == 0
            and res_win.stdout.rstrip("\n") == res_posix.stdout.rstrip("\n")
            and res_win_bs.stdout.rstrip("\n") == res_posix.stdout.rstrip("\n")
        )
        report("Windows C:/ and C:\\ input paths normalize to /mnt/c/...", win_input_ok)

        # --output-dir with a Windows path must write under /mnt/c/... not C:.
        with tempfile.TemporaryDirectory(prefix="self-test-winout-", dir=base / "tmp") as td:
            out_dir = Path(td)
            win_out_dir = windows_form(out_dir)
            res_outdir = run_cli([str(texture), "--output-dir", win_out_dir])
            out_file = out_dir / (texture.stem + ".txt")
            outdir_ok = (
                res_outdir.returncode == 0
                and out_file.exists()
                and out_file.stat().st_size > 0
            )
            report("--output-dir with Windows C:/ path writes under /mnt/c/...", outdir_ok,
                   ("exit=%d" % res_outdir.returncode) if not outdir_ok else "")

        # --output with a Windows path must also map correctly.
        with tempfile.TemporaryDirectory(prefix="self-test-winout-", dir=base / "tmp") as td:
            out_file = Path(td) / "merged.txt"
            win_out_file = windows_form(out_file)
            res_output = run_cli([str(texture), "--output", win_out_file])
            output_ok = (
                res_output.returncode == 0
                and out_file.exists()
                and out_file.stat().st_size > 0
            )
            report("--output with Windows C:/ path writes under /mnt/c/...", output_ok,
                   ("exit=%d" % res_output.returncode) if not output_ok else "")

        # --manifest is also a user-supplied path; Windows style must normalize.
        default_jar = (
            "/path/to/user/.minecraft/versions/"
            "1.12.2-Forge_14.23.5.2864/1.12.2-Forge_14.23.5.2864.jar"
        )
        if Path(default_jar).exists():
            with tempfile.TemporaryDirectory(prefix="self-test-winmanifest-",
                                             dir=base / "tmp") as td:
                manifest_posix = Path(td) / "manifest.json"
                result_posix = Path(td) / "manifest-result.txt"
                manifest_data = {
                    "jar": default_jar,
                    "outdir": windows_form(texture.parent),
                    "result": windows_form(result_posix),
                    "entries": [
                        {"entry": "assets/minecraft/textures/items/stone_sword.png",
                         "local": str(texture)}
                    ],
                }
                manifest_posix.write_text(
                    json.dumps(manifest_data), encoding="utf-8"
                )
                win_manifest = windows_form(manifest_posix)
                res_manifest = subprocess.run(
                    [sys.executable, str(base / "verify_from_jar.py"),
                     "--manifest", win_manifest],
                    cwd=str(base), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True,
                )
                manifest_ok = (
                    res_manifest.returncode == 0
                    and "match" in res_manifest.stdout
                    and result_posix.exists()
                )
                report("verify_from_jar.py --manifest with Windows C:/ path works",
                       manifest_ok,
                       ("exit=%d" % res_manifest.returncode) if not manifest_ok else "")
        else:
            report("verify_from_jar.py --manifest with Windows C:/ path works (default jar "
                   "unavailable)", True, "SKIP: default 1.12.2 jar not found")
    else:
        report("Windows C:/ input/output path tests (only meaningful under WSL)", True,
               "SKIP: current filesystem is not /mnt/c")

    # ------------------------------------------------------------------
    # 6) Error paths: missing input file and bad / missing jar entry.
    # ------------------------------------------------------------------
    res_missing = run_cli([str(base / "definitely-not-here.png")])
    missing_ok = res_missing.returncode != 0 and "ERROR: file not found" in res_missing.stderr
    report("missing PNG input exits non-zero", missing_ok,
           ("exit=%d" % res_missing.returncode) if not missing_ok else "")

    verify_script = base / "verify_from_jar.py"
    res_bad_jar = subprocess.run(
        [sys.executable, str(verify_script), "--jar", str(base / "no-such.jar"),
         "--entry", "assets/x.png", "--outdir", str(base / "tmp")],
        cwd=str(base), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    bad_jar_ok = res_bad_jar.returncode != 0 and "ERROR: jar not found" in res_bad_jar.stderr
    report("bad jar exits non-zero", bad_jar_ok,
           ("exit=%d" % res_bad_jar.returncode) if not bad_jar_ok else "")

    # Missing jar entry (using the real default jar when available).
    default_jar = (
        "/path/to/user/.minecraft/versions/"
        "1.12.2-Forge_14.23.5.2864/1.12.2-Forge_14.23.5.2864.jar"
    )
    if Path(default_jar).exists():
        with tempfile.TemporaryDirectory(prefix="self-test-badentry-", dir=base / "tmp") as td:
            res_bad_entry = subprocess.run(
                [sys.executable, str(verify_script), "--jar", default_jar,
                 "--entry", "assets/do-not-exist.png", "--outdir", td],
                cwd=str(base), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            bad_entry_ok = res_bad_entry.returncode != 0 and "MISMATCH" in res_bad_entry.stdout
            report("missing jar entry exits non-zero", bad_entry_ok,
                   ("exit=%d" % res_bad_entry.returncode) if not bad_entry_ok else "")
    else:
        report("missing jar entry exits non-zero (default jar unavailable)", True,
               "SKIP: default 1.12.2 jar not found")

    print("")
    if failed:
        print("SELF-TEST: FAIL (%d passed, %d failed)" % (passed, failed))
        return 1
    print("SELF-TEST: PASS (%d passed, 0 failed)" % passed)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert Minecraft texture PNGs into LLM-readable color text."
    )
    parser.add_argument("paths", nargs="*", help="PNG texture file(s)")
    parser.add_argument(
        "--mode",
        choices=["all", "grid", "compact", "json"],
        default=DEFAULT_MODE,
        help="Output mode (default: %s)" % DEFAULT_MODE,
    )
    parser.add_argument(
        "--alpha-threshold",
        type=int,
        default=DEFAULT_ALPHA_THRESHOLD,
        help="Alpha values below this are treated as transparent (default: %d)"
        % DEFAULT_ALPHA_THRESHOLD,
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
        help="Alpha-aware mode: hex grid emits '#RRGGBB a=NN' for opaque pixels; "
             "required when the PNG has semi-transparent alpha",
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
        help="Run integrity checks on textures/*.png and exit",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    if args.output_dir and args.output:
        sys.stderr.write("ERROR: --output-dir and --output are mutually exclusive\n")
        return 2

    if not args.paths:
        parser.error("at least one PNG path is required (use --self-test for integrity checks)")

    docs = []
    for raw in args.paths:
        p = normalize_path(raw)
        if not p.exists():
            sys.stderr.write("ERROR: file not found: %s\n" % raw)
            return 1
        try:
            with Image.open(p) as image:
                im = image.convert("RGBA")
                if has_semitransparent(im) and not args.alpha_column:
                    sys.stderr.write(
                        "ERROR: %s contains semi-transparent alpha (0<alpha<255). "
                        "Use --alpha-column for an alpha-aware hex grid, or the script will not "
                        "silently treat it as binary alpha.\n" % raw
                    )
                    return 1
                doc = build_document(p, im, args)
                if args.stats:
                    doc += render_stats(doc)
                docs.append((p, doc))
        except Exception as e:
            sys.stderr.write("ERROR: cannot read %s: %s\n" % (raw, e))
            return 1

    if args.output_dir:
        # Windows-style paths (C:/... or C:\...) must be normalized exactly like
        # input paths, otherwise WSL writes a literal `C:` directory in cwd.
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


if __name__ == "__main__":
    sys.exit(main())
