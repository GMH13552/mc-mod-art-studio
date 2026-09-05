#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit smoke tests for check_entity_uv.py.

Run from repo root:
    python3 -m pytest tests/test_check_entity_uv.py -q
    # or
    python3 tests/test_check_entity_uv.py

Synthetic positive tests are generated from entity_uv_spec.MOB_ENTITY_REGIONS
in memory, so they pass even when the vanilla_entity_ref/ original textures
have been removed.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

try:
    import pytest
except ImportError:  # pragma: no cover
    pytest = None

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import check_entity_uv as ck  # noqa: E402
import entity_uv_spec as eu  # noqa: E402


class _Skipped(Exception):
    """Fallback for running the file directly without pytest installed."""


def _skip(reason: str) -> None:
    if pytest is not None:
        pytest.skip(reason)
    raise _Skipped(reason)


_SKIP_EXCEPTIONS: tuple[type[BaseException], ...] = (_Skipped,)
if pytest is not None:
    _SKIP_EXCEPTIONS = _SKIP_EXCEPTIONS + (pytest.skip.Exception,)


def _status(png: Path, entity: str) -> str:
    return ck._check_image(png, entity)["status"]


def _skip_if_missing(path: Path, label: str) -> None:
    if not path.exists():
        _skip("%s missing: %s" % (label, path))


def test_synthetic_mob_regions_pass_without_vanilla() -> None:
    """用 MOB_ENTITY_REGIONS 内存生成 64x32 合成正例，每个区域必须有像素。"""
    for entity in sorted(eu.MOB_ENTITY_REGIONS):
        img = ck._synthetic_entity_image(entity)
        result = ck._check_image_obj(img, entity, "<synthetic:%s>" % entity)
        assert result["status"] == "PASS", "%s: %s" % (entity, result["summary"])
        assert result["size"] == "64x32"
        assert result["opaque_pixels"] > 0
        for name, region in result["regions"].items():
            assert region["opaque"] > 0, "%s region %s is empty" % (entity, name)


def test_canvas_margin_left_touch_fails() -> None:
    """atlas 画布边距：不透明像素贴到左边缘时必须 FAIL。"""
    img = Image.new("RGBA", (64, 32), (0, 0, 0, 0))
    img.putpixel((0, 1), (255, 0, 0, 255))
    result = ck._check_image_obj(img, "pig", "<synthetic:left-touch>")
    assert result["status"] == "FAIL"
    assert result["margins"]["left"] == 0
    margin_check = next(c for c in result["checks"] if c["id"] == "canvas_margin")
    assert margin_check["ok"] is False


def test_vanilla_pig_passes() -> None:
    png = ROOT / "vanilla_entity_ref" / "pig.png"
    _skip_if_missing(png, "vanilla_entity_ref/pig.png")
    assert _status(png, "pig") == "PASS"


def test_vanilla_creeper_passes() -> None:
    png = ROOT / "vanilla_entity_ref" / "creeper.png"
    _skip_if_missing(png, "vanilla_entity_ref/creeper.png")
    assert _status(png, "creeper") == "PASS"


def test_v2_pig_fails_region() -> None:
    png = ROOT / "tests" / "runs" / "v2" / "pig" / "sprite.png"
    _skip_if_missing(png, "tests/runs/v2/pig/sprite.png")
    result = ck._check_image(png, "pig")
    assert result["status"] == "FAIL"
    assert result["regions"]["legs"]["opaque"] == 0


def test_v2_creeper_fails_region() -> None:
    png = ROOT / "tests" / "runs" / "v2" / "creeper" / "sprite.png"
    _skip_if_missing(png, "tests/runs/v2/creeper/sprite.png")
    result = ck._check_image(png, "creeper")
    assert result["status"] == "FAIL"
    assert result["regions"]["body"]["opaque"] == 0
    assert result["regions"]["legs"]["opaque"] == 0


def _run_all() -> int:
    tests = [test_synthetic_mob_regions_pass_without_vanilla,
             test_canvas_margin_left_touch_fails,
             test_vanilla_pig_passes, test_vanilla_creeper_passes,
             test_v2_pig_fails_region, test_v2_creeper_fails_region]
    failures = 0
    for fn in tests:
        try:
            fn()
            print("PASS %s" % fn.__name__)
        except _SKIP_EXCEPTIONS as exc:  # type: ignore[arg-type]
            print("SKIP %s: %s" % (fn.__name__, exc))
        except AssertionError as exc:
            failures += 1
            print("FAIL %s: %s" % (fn.__name__, exc))
    print("RESULT: %s (%d failures)" % ("PASS" if failures == 0 else "FAIL", failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_all())
