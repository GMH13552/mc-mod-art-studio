#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a local absolute-path index containing only the vanilla assets needed for s3-rebuild demos.

The resulting JSON is an old-format array (compatible with retrieve_assets.load_index_with_base),
but paths are absolute so it can live anywhere in the repo without needing the library dirs.
"""
from __future__ import annotations

import json
from pathlib import Path

FULL = Path("/mnt/c/Users/GMH13/Documents/deepseek_harness_workspace/mc_asset_library_full")
OUT = Path(__file__).resolve().parent / "rebuild-index.json"

NAMES = [
    # entity refs
    "cow.png", "red_mooshroom.png", "skeleton.png", "villager.png",
    # item refs
    "iron_sword.png", "stone_sword.png", "wooden_sword.png", "shears.png",
    "leather.png", "rabbit_hide.png", "stick.png", "carrot_on_a_stick.png",
    # block refs
    "oak_planks.png", "bone_block_side.png", "bone_block_top.png",
    "soul_fire_0.png", "soul_fire_1.png",
    # extra cow region-related
    "brown_mooshroom.png",
]


def main() -> None:
    entries: list[dict] = []
    seen: set[str] = set()
    for cat_dir in ("entity", "item", "block"):
        texture_dir = FULL / "textures" / cat_dir
        for name in NAMES:
            # entity files are nested one level deeper in some cases (entity/cow/cow.png)
            if not (texture_dir / name).exists():
                # search two levels deep under the category dir
                for p in texture_dir.rglob(name):
                    if p.is_file() and p.name == name:
                        break
                else:
                    continue
            else:
                p = texture_dir / name
            if not p.exists():
                continue
            rel = p.resolve().relative_to(FULL.resolve())
            category = "entity" if cat_dir == "entity" else "item" if cat_dir == "item" else "block"
            key = str(p.resolve())
            if key in seen:
                continue
            seen.add(key)
            entries.append({
                "path": str(p.resolve()),
                "name": name,
                "category": category,
                "md5": "",  # filled by full-index lookup below
                "palette_count": 0,
                "opaque_pixel_count": 0,
            })

    # Fill md5 from full-index.json
    idx = json.loads((FULL / "full-index.json").read_text(encoding="utf-8"))
    md5_by_name: dict[str, str] = {}
    for e in idx.get("textures", []):
        md5_by_name.setdefault(e["name"] + ".png", e.get("md5", ""))
    for e in entries:
        e["md5"] = md5_by_name.get(e["name"], "")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote %s with %d entries" % (OUT, len(entries)))


if __name__ == "__main__":
    main()
