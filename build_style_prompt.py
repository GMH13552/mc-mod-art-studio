#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_style_prompt.py — 生成 mc2-prompt 提示包 (prompt_packs/<name>.json)。

功能
----
1. 接收物品/方块/实体提示包参数：--name, --type, --size, --anchor primary/secondary,
   --fusion, --out。
2. 自动从 mc_asset_library/ 提取锚点 compact 文本（复用 asset_to_text.py
   `--mode compact --no-header`）。
3. 自动从 style_cards/*.md 抽取调色板/明暗/描边/噪点规则。
4. 构造与 text_to_texture.py 兼容的 `output_contract`：
   - v1 保留可解析的完整示例（W=.. H=.. + `PALETTE` + 索引 grid，含 -1）。
   - v2/v3 只给**格式骨架**：W=.. H=.. 模板、`PALETTE` 占位说明、
     `index grid` 行列规则；**不嵌入完整原版锚点的 PALETTE + index grid**。
5. 嵌入至少一个同类原版 compact few-shot：
   item -> stone_pickaxe；block -> red_mushroom_block；entity -> pig。
6. 可选 `--prebuild` 生成任务列出的全部提示包；`--self-test` 校验 4+ 个包。
7. v2-form：支持 `--query`/`--retrieval` 自动取 retrieval anchors/features，
   `--form auto|item|block_multi|cross|entity_uv` 生成 form-aware 提示包
   （含 file_contract / features / output_contract），并 `--prebuild-v2`
   生成 `prompt_packs_v2/` 下 3 个示例。
8. v4-concept：v2/v4 提示包自动调用 concept_grounder.py 生成概念卡
   （item_name/description/parts/face_regions/visual_goals/minecraft_reference/avoid），
   并在 prompt 中加入“先理解再生成”的输出顺序要求。

用法示例
--------
    python3 build_style_prompt.py \\
        --name mushroom_axe --type item --size 16x16 \\
        --anchor primary mc_asset_library/raw/item/stone_axe.png \\
        --anchor secondary mc_asset_library/raw/block/red_mushroom_block.png \\
        --fusion "palette overlay on shape" \\
        --out prompt_packs/mushroom_axe.json

    python3 build_style_prompt.py --prebuild
    python3 build_style_prompt.py --prebuild-v2
    python3 build_style_prompt.py --self-test > build_style_prompt_selftest.txt 2>&1
    python3 build_style_prompt.py --name alien_crystal_wand --query "异形水晶法杖" --out prompt_packs_v2/alien_crystal_wand.json
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.stderr.write("ERROR: Pillow is required.  Install with:  pip install pillow\n")
    raise

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import entity_uv_spec as eu  # noqa: E402
import reference_analyzer as refa  # noqa: E402

_ASSET_SCRIPT = _THIS_DIR / "asset_to_text.py"
_INDEX_PATH = _THIS_DIR / "mc_asset_library" / "library-index.json"
_STYLE_CARDS_DIR = _THIS_DIR / "style_cards"
_SNIPPET_DIR = _STYLE_CARDS_DIR / "snippets"
_PROMPT_PACKS_DIR = _THIS_DIR / "prompt_packs"
_PROMPT_PACKS_V2_DIR = _THIS_DIR / "prompt_packs_v2"
_RETRIEVAL_DIR = _THIS_DIR / "retrieval_examples"
_V2_LOG_PATH = _THIS_DIR / "build_style_prompt_v2_log.txt"

# v2 合法形式
_VALID_FORMS = ("item", "block_multi", "cross", "entity_uv")

# form -> 传统 type / 默认尺寸 / 输出 face 清单
_FORM_SPECS = {
    "item": {
        "type": "item",
        "default_size": (16, 16),
        "faces": [{"id": "sprite", "suffix": "", "width": 16, "height": 16}],
    },
    "block_multi": {
        "type": "block",
        "default_size": (16, 16),
        "faces": [
            {"id": "top", "suffix": "_top", "width": 16, "height": 16},
            {"id": "side", "suffix": "_side", "width": 16, "height": 16},
            {"id": "bottom", "suffix": "_bottom", "width": 16, "height": 16},
        ],
    },
    "cross": {
        "type": "block",
        "default_size": (16, 16),
        "faces": [{"id": "cross", "suffix": "", "width": 16, "height": 16}],
    },
    "entity_uv": {
        "type": "entity",
        "default_size": (64, 32),
        "faces": [{"id": "uv", "suffix": "", "width": 64, "height": 32}],
    },
}

# few-shot：v2 form -> (snippet, asset)
_FEW_SHOT_BY_FORM = {
    "item": ("item_stone_pickaxe.txt", "stone_pickaxe.png", "item"),
    "block_multi": ("block_red_mushroom_block.txt", "red_mushroom_block.png", "block"),
    "cross": ("block_red_mushroom_block.txt", "red_mushroom_block.png", "block"),
    "entity_uv": ("entity_pig.txt", "pig.png", "entity"),
}

# 任务要求的 3 个 v2 提示包。query+retrieval 二选一；retrieval 缺失时按 query 自动生成。
V2_PREBUILDS = [
    {
        "name": "alien_crystal_wand",
        "query": "异形水晶法杖",
        "retrieval": "retrieval_examples/alien_crystal_wand.json",
        "form": "item",
    },
    {
        "name": "glowstone_mushroom_block",
        "query": "荧石蘑菇方块",
        "retrieval": "retrieval_examples/glowstone_mushroom_block.json",
        "form": "block_multi",
    },
    {
        "name": "mushroom_sapling",
        "query": "蘑菇树苗",
        "retrieval": "retrieval_examples/mushroom_sapling.json",
        "form": "cross",
    },
]

# 核心仓库没有 style_cards/ 时的内置极简风格兜底（非原版素材，仅格式/规则示意）。
_FALLBACK_FEW_SHOT_TEXT = """## Silhouette (X=opaque, .=transparent)
```
................
.......X........
.......X........
.......X........
```
## ASCII color map
Legend: . transparent | # near-black | + dark-gray | = light-gray | @ white | R red | O orange | Y yellow | G green | C cyan | B blue | M magenta | P pink
```
................
.......O........
.......O........
.......O........
```
## Palette (hex)
```
 0: #888888
```
## Index grid (-1 = transparent)
```
-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1  0 -1 -1 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1  0 -1 -1 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1  0 -1 -1 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1
-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1
```

> 内置极简 few-shot：仅示意格式，不包含任何原版贴图；实际生成必须使用新形状/图案。
"""

_FALLBACK_STYLE_RULES = {
    "palette": [
        "- 调色板数量 6-11；避免高饱和荧光色，保留少量亮/暗阶。",
    ],
    "light_dark": [
        "- 左上偏亮、右下偏暗；局部使用 1px 色阶表现体积。",
        "- 每个部件至少 base/light/dark 三档色阶；亮部高光沿形状走向，暗部在背光侧。",
    ],
    "outline": [
        "- 外轮廓使用 1px 深色/暗色自然描边，不做均匀黑框。",
        "- 部件接缝用暗色分隔；不同材质（金属/木/石/发光/软质）按语义使用不同高光强度与纹理提示，不给死例子。",
    ],
    "noise": [
        "- 使用少量 1px 噪点/抖动，避免大面积平涂和模糊渐变。",
        "- 材质纹理（木纹/石裂纹/金属划痕/发光颗粒等）贴合形状；若原版有参考就参考其质感，没有就自行推理合理材质。",
    ],
}

# 风格卡 sections -> 内部键
_STYLE_SECTIONS = {
    "palette": "调色板",
    "light_dark": "明暗规则",
    "outline": "描边规则",
    "noise": "噪点 / 材质规则",
}

# 风格卡文件名：build_style_cards.py 生成复数文件（items/blocks/entities.md）
_CARD_FILE_BY_TYPE = {
    "item": "items",
    "block": "blocks",
    "entity": "entities",
}

# 同类 few-shot 的默认原版资产（来自 style_cards/snippets/）
_FEW_SHOT_BY_TYPE = {
    "item": ("item_stone_pickaxe.txt", "stone_pickaxe.png"),
    "block": ("block_red_mushroom_block.txt", "red_mushroom_block.png"),
    "entity": ("entity_pig.txt", "pig.png"),
}

# 任务列出的预生成包。若库中缺少任务指定的资产，使用最接近的现有锚点并记录 fallback_note。
PREBUILDS = [
    {
        "name": "mushroom_axe",
        "type": "item",
        "size": "16x16",
        "primary": "stone_axe.png",
        "secondary": "red_mushroom_block.png",
        "fusion": "palette overlay on shape",
    },
    {
        "name": "villager_armor_helmet",
        "type": "item",
        "size": "16x16",
        "primary": "iron_helmet.png",
        "secondary": "villager.png",
        "fusion": "palette overlay on shape",
    },
    {
        "name": "villager_armor_chestplate",
        "type": "item",
        "size": "16x16",
        "primary": "iron_chestplate.png",
        "secondary": "villager.png",
        "fusion": "palette overlay on shape",
    },
    {
        "name": "villager_armor_leggings",
        "type": "item",
        "size": "16x16",
        "primary": "iron_leggings.png",
        "secondary": "villager.png",
        "fusion": "palette overlay on shape",
    },
    {
        "name": "villager_armor_boots",
        "type": "item",
        "size": "16x16",
        "primary": "iron_boots.png",
        "secondary": "villager.png",
        "fusion": "palette overlay on shape",
    },
    {
        "name": "hybrid_block",
        "type": "block",
        "size": "16x16",
        "primary": "red_mushroom_block.png",
        "secondary": "glowstone.png",
        "fusion": "palette overlay on shape",
    },
    {
        "name": "hybrid_entity",
        "type": "entity",
        "size": "64x32",
        "primary": "pig.png",
        "secondary": "red_mooshroom.png",
        "fusion": "palette overlay on shape",
    },
]


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _normalize_path(path: str | Path) -> Path:
    """委托给 asset_to_text 的 Windows/WSL path 归一化。"""
    import asset_to_text as att
    return att.normalize_path(path)


def _parse_size(size: str) -> tuple[int, int]:
    m = re.match(r"^\s*(\d+)\s*[xX]\s*(\d+)\s*$", size)
    if not m:
        raise ValueError("--size must be WxH, got %r" % size)
    w, h = int(m.group(1)), int(m.group(2))
    if w <= 0 or h <= 0:
        raise ValueError("--size must have positive W/H")
    return w, h


def _load_index_entries() -> list[dict]:
    if not _INDEX_PATH.exists():
        return []
    with open(_INDEX_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _resolve_anchor(path_arg: str, category: str) -> tuple[Path, dict | None]:
    """
    解析锚点 PNG：
      1) 如果给出的是真实路径，直接使用；
      2) 否则按 category + 文件名在 library-index.json 中查找。
    返回 (path, index_entry_or_None)。
    """
    p = _normalize_path(path_arg)
    if p.exists():
        return p, None

    wanted_stem = Path(path_arg).stem.lower()
    wanted_name = Path(path_arg).name.lower()
    entries = _load_index_entries()
    for e in entries:
        if str(e.get("category", "")).lower() != category.lower():
            continue
        entry_name = str(e.get("name", "")).lower()
        entry_stem = Path(entry_name).stem.lower()
        path_name = Path(str(e.get("path", ""))).name.lower()
        path_stem = Path(path_name).stem.lower()
        if (
            wanted_name in (entry_name, path_name)
            or wanted_stem in (entry_stem, path_stem)
        ):
            raw = _normalize_path(e["path"])
            if not raw.is_absolute():
                raw = _INDEX_PATH.parent / raw
            return raw.resolve(), e
    raise FileNotFoundError(
        "anchor not found: %r (category=%s); searched mc_asset_library/library-index.json"
        % (path_arg, category)
    )


def _infer_category_from_path(path: Path) -> str | None:
    """从 mc_asset_library/raw/<category>/... 路径推断 category。"""
    try:
        rel = path.resolve().relative_to(_THIS_DIR / "mc_asset_library" / "raw")
    except ValueError:
        return None
    if len(rel.parts) >= 1 and rel.parts[0] in ("item", "block", "entity"):
        return rel.parts[0]
    return None


def _image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as im:
        return im.size


def _has_semitransparent_alpha(path: Path) -> bool:
    """检查 PNG 是否含半透明像素（0<alpha<255）。"""
    with Image.open(path) as im:
        rgba = im.convert("RGBA")
        return any(0 < a < 255 for _, _, _, a in rgba.getdata())


def _run_asset_to_text(path: Path) -> str:
    """调用 asset_to_text.py --mode compact --no-header，返回完整 compact 文本。

    对含半透明 alpha 的原版实体纹理（如 creeper）自动加 --alpha-column，
    避免 asset_to_text 因 alpha 校验失败。
    """
    cmd = [
        sys.executable,
        str(_ASSET_SCRIPT),
        str(path),
        "--mode", "compact",
        "--no-header",
    ]
    if _has_semitransparent_alpha(path):
        cmd.append("--alpha-column")
    proc = subprocess.run(
        cmd,
        cwd=str(_THIS_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "asset_to_text failed for %s: %s" % (path, proc.stderr.strip())
        )
    return proc.stdout.strip()


def _extract_palette_and_index(compact_text: str) -> tuple[list[str], list[str]]:
    """
    从 asset_to_text 的 compact 输出中提取 palette 行与 index grid 行。
    只保留 code-fence 内的数据行，过滤标题/```。
    """
    palette_lines: list[str] = []
    index_lines: list[str] = []
    section = None
    in_fence = False

    for line in compact_text.splitlines():
        if line.startswith("## Palette (hex"):
            section = "palette"
            in_fence = False
            continue
        if line.startswith("## Index grid"):
            section = "index"
            in_fence = False
            continue
        if section and line.strip() == "```":
            # 进入或离开 code fence
            in_fence = not in_fence
            continue
        if not section or not in_fence:
            continue
        if section == "palette" and line.strip():
            palette_lines.append(line)
        elif section == "index" and line.strip():
            index_lines.append(line)

    if not palette_lines:
        raise ValueError("compact text did not contain a palette block")
    if not index_lines:
        raise ValueError("compact text did not contain an index grid")
    return palette_lines, index_lines


def _build_output_contract(w: int, h: int, palette_lines: list[str], index_lines: list[str]) -> str:
    """
    生成 text_to_texture.py 可解析的最小程序契约：
      第 1 行 W=.. H=..
      随后 PALETTE + palette + index grid。
    不包含解释性叙述。
    """
    return "W=%d H=%d\nPALETTE\n%s\n%s" % (
        w, h,
        "\n".join(palette_lines),
        "\n".join(index_lines),
    )


def _grid_rows_from_contract(contract: str) -> list[str]:
    """从 W/H + PALETTE 契约中提取索引 grid 的裸数据行。"""
    lines = contract.splitlines()
    palette_offset = None
    for idx, ln in enumerate(lines):
        if ln.strip().lower().startswith("palette"):
            palette_offset = idx
            break
    if palette_offset is None:
        raise ValueError("output_contract missing PALETTE marker")
    start = palette_offset + 1
    while start < len(lines):
        s = lines[start].strip()
        if re.match(r"^\s*\d+\s*:\s*#[0-9a-fA-F]{6}", s):
            start += 1
        else:
            break
    grid = [
        ln.strip() for ln in lines[start:]
        if ln.strip() and not ln.strip().startswith("#")
        and not ln.strip().lower().startswith("palette")
    ]
    return grid


def _extract_style_rules(cards: list[Path]) -> dict:
    """从 style_cards/*.md 抽取指定 section 的 bullet 规则。"""
    result = {k: [] for k in _STYLE_SECTIONS}
    for card in cards:
        if not card.exists():
            continue
        current = None
        for line in card.read_text(encoding="utf-8").splitlines():
            if line.startswith("### "):
                heading = line[4:].strip()
                current = None
                for key, label in _STYLE_SECTIONS.items():
                    if heading.startswith(label) or label in heading:
                        current = key
                        break
                continue
            if current and line.startswith("- "):
                result[current].append(line.strip())
    return result


def _few_shot_for_type(type_: str) -> dict:
    snippet_rel, asset_name = _FEW_SHOT_BY_TYPE[type_]
    snippet_path = _SNIPPET_DIR / snippet_rel
    if not snippet_path.exists():
        raise FileNotFoundError(
            "few-shot snippet not found: %s (expected for type %s)" % (snippet_path, type_)
        )
    return {
        "asset": asset_name,
        "type": type_,
        "path": str(snippet_path.relative_to(_THIS_DIR)),
        "compact_text": snippet_path.read_text(encoding="utf-8").strip(),
    }


def _rel_or_abs(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_THIS_DIR))
    except ValueError:
        return str(path.resolve())


# ---------------------------------------------------------------------------
# v2-form：自动检索 + form-aware 提示包
# ---------------------------------------------------------------------------

def _v2_log(message: str) -> None:
    """把一条 v2-form 事件追加到 build_style_prompt_v2_log.txt。"""
    _V2_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(_V2_LOG_PATH, "a", encoding="utf-8") as f:
        f.write("[%s] %s\n" % (ts, message))


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("JSON must be an object: %s" % path)
    return data


def _load_retrieval(path: Path | None, query: str | None, top: int = 3) -> dict:
    """读取 retrieval JSON；若未提供路径则由 --query 调用 retrieve_assets.retrieve。"""
    import retrieve_assets as ra

    if path is not None:
        p = _normalize_path(path)
        if not p.is_absolute():
            p = _THIS_DIR / p
        if not p.exists():
            raise FileNotFoundError("--retrieval not found: %s" % p)
        return _load_json(p)

    if query:
        # 复用已有离线检索器，保持 method=rule、可复现。
        return ra.retrieve(query, top=top, form=None)
    raise ValueError("either --retrieval or --query is required")


def _ensure_retrieval_file(spec: dict) -> Path:
    """若 spec 指定的 retrieval 文件不存在，用 spec['query'] 自动生成并保存。"""
    import retrieve_assets as ra

    rel = spec["retrieval"]
    path = _normalize_path(rel)
    if not path.is_absolute():
        path = _THIS_DIR / path
    path = path.resolve()
    if path.exists():
        return path
    if not spec.get("query"):
        raise FileNotFoundError("retrieval file missing and no query to generate: %s" % path)
    # retrieval 文件保持 auto 判定，build_prompt_pack_v2 再用 spec['form'] 强制目标形式
    result = ra.retrieve(spec["query"], top=3, form="auto")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    _v2_log("generated retrieval example: %s (query=%r form=%s)" % (
        _rel_or_abs(path), spec["query"], result["form"]
    ))
    return path


def _resolve_retrieval_anchor_path(anchor: dict) -> Path:
    """把 retrieval anchor 的 'path'（相对 mc_asset_library/）解析为真实 PNG。"""
    p = _normalize_path(anchor["path"])
    if p.exists():
        return p.resolve()
    candidate = _THIS_DIR / "mc_asset_library" / anchor["path"]
    if candidate.exists():
        return candidate.resolve()
    raise FileNotFoundError(
        "retrieval anchor image not found: %s (searched %s)" % (anchor.get("path"), candidate)
    )


def _extract_feature_per_anchor(anchor: dict) -> dict:
    """给 retrieval anchor 补上 compact_text 与 seed palette/index。"""
    image_path = _resolve_retrieval_anchor_path(anchor)
    compact = _run_asset_to_text(image_path)
    palette_lines, index_lines = _extract_palette_and_index(compact)
    return {
        "path": str(image_path.relative_to(_THIS_DIR / "mc_asset_library")) if image_path.exists() and image_path.is_relative_to(_THIS_DIR / "mc_asset_library") else _rel_or_abs(image_path),
        "name": anchor.get("name", image_path.name),
        "category": anchor.get("category", ""),
        "role": anchor.get("role", "shape"),
        "features": dict(anchor.get("features", {})),
        "score": anchor.get("score"),
        "matched_terms": anchor.get("matched_terms", []),
        "palette_count": anchor.get("palette_count"),
        "size": "%dx%d" % _image_size(image_path),
        "compact_text": compact,
        "seed_palette": palette_lines,
        "seed_index": index_lines,
    }


def _aggregate_features(anchors: list[dict]) -> dict:
    """从 retrieval anchors 聚合 shape/pattern/colors/parts/attraction。"""
    buckets: dict[str, list[str]] = {
        "shape": [], "pattern": [], "colors": [], "parts": [], "attraction": []
    }
    sources: dict[str, list[str]] = {
        "shape": [], "pattern": [], "colors": [], "parts": [], "attraction": []
    }

    def _add(field: str, value: str, source_name: str) -> None:
        if not value or value in buckets[field]:
            return
        buckets[field].append(value)
        sources[field].append(source_name)

    for a in anchors:
        feats = a.get("features", {})
        name = a.get("name", "?")
        _add("shape", feats.get("shape", ""), name)
        _add("pattern", feats.get("pattern", ""), name)
        for c in feats.get("colors", []) or []:
            if c not in buckets["colors"]:
                buckets["colors"].append(c)
                sources["colors"].append(name)
        for p in feats.get("parts", []) or []:
            if p not in buckets["parts"]:
                buckets["parts"].append(p)
                sources["parts"].append(name)
        for x in feats.get("attraction", []) or []:
            if x not in buckets["attraction"]:
                buckets["attraction"].append(x)
                sources["attraction"].append(name)

    summary_parts = []
    summary_parts.append("形状：" + "；".join(buckets["shape"]) if buckets["shape"] else "形状：-")
    summary_parts.append("图案：" + "；".join(buckets["pattern"]) if buckets["pattern"] else "图案：-")
    summary_parts.append("颜色：" + " ".join(buckets["colors"]) if buckets["colors"] else "颜色：-")
    summary_parts.append("部位：" + "；".join(buckets["parts"]) if buckets["parts"] else "部位：-")
    summary_parts.append("吸引点：" + "；".join(buckets["attraction"]) if buckets["attraction"] else "吸引点：-")

    return {
        "summary": "\n".join(summary_parts),
        "shape": buckets["shape"],
        "pattern": buckets["pattern"],
        "colors": buckets["colors"],
        "parts": buckets["parts"],
        "attraction": buckets["attraction"],
        "sources": sources,
        "anchor_count": len(anchors),
    }


def _reference_block_for_anchors(
    anchors: list[dict],
    form: str,
    width: int,
    height: int,
    entity: str | None,
    novelty: float,
    no_original_ref: bool,
) -> tuple[str | None, bool, int]:
    """为检索锚点生成“参考语法 + 可选 compact 片段”的 prompt 文本段。

    返回 (reference_block, include_compact, compact_limit)。
    ``no_original_ref=True`` 时返回 ``(None, False, 0)``。
    """
    analyses: list[dict] = []
    for a in anchors:
        uv_region = None
        if form == "entity_uv":
            uv_region = eu.regions_for_entity(entity, width, height)
        analysis = refa.analyze_compact(
            a.get("compact_text", ""), form=form, uv_region=uv_region,
            name=a.get("name", "?") or "?",
        )
        analysis.update({
            "path": a.get("path", ""),
            "category": a.get("category", ""),
            "role": a.get("role", ""),
            "size": a.get("size", ""),
        })
        a["reference_analysis"] = analysis
        analyses.append(analysis)

    if no_original_ref:
        return None, False, 0

    include_compact, compact_limit = refa.decide_reference_include(novelty)
    # “最相关”取 score 最高的锚点；没有 score 时保持原始顺序。
    ranked = sorted(
        anchors,
        key=lambda a: -(
            a.get("score") if a.get("score") is not None else 0
        ),
    )
    compact_items = [
        (a.get("name", "compact") or "compact", a.get("compact_text", ""))
        for a in ranked[:compact_limit]
        if a.get("compact_text")
    ]
    reference_block = refa.render_reference_block(
        analyses,
        compact_text=compact_items,
        include_compact=include_compact,
        max_compact=compact_limit,
    )
    return reference_block, include_compact, compact_limit


def _form_file_contract(form: str, name: str, width: int, height: int) -> dict:
    """按 form 生成所需文件清单与空白/示例 JSON 模板。"""
    modid = "mcmod"
    texture_dir = "assets/%s/textures" % modid
    model_dir = "assets/%s/models" % modid
    blockstate_dir = "assets/%s/blockstates" % modid

    if form == "item":
        files = [
            {
                "path": "%s/item/%s.png" % (texture_dir, name),
                "kind": "texture",
                "width": width,
                "height": height,
                "alpha": True,
                "face": "sprite",
                "note": "单张 16x16 透明背景物品贴图",
            },
            {
                "path": "%s/item/%s.json" % (model_dir, name),
                "kind": "model",
                "format": "item/generated",
                "face": None,
                "note": "item model，texture 指向 layer0",
            },
        ]
        templates = {
            "%s/item/%s.json" % (model_dir, name): {
                "parent": "minecraft:item/generated",
                "textures": {"layer0": "%s:item/%s" % (modid, name)},
            }
        }

    elif form == "block_multi":
        files = [
            {
                "path": "%s/block/%s_top.png" % (texture_dir, name),
                "kind": "texture", "width": width, "height": height,
                "alpha": False, "face": "top",
            },
            {
                "path": "%s/block/%s_side.png" % (texture_dir, name),
                "kind": "texture", "width": width, "height": height,
                "alpha": False, "face": "side",
            },
            {
                "path": "%s/block/%s_bottom.png" % (texture_dir, name),
                "kind": "texture", "width": width, "height": height,
                "alpha": False, "face": "bottom",
            },
            {
                "path": "%s/block/%s.json" % (model_dir, name),
                "kind": "model", "format": "block/cube_bottom_top",
                "face": None,
            },
            {
                "path": "%s/%s.json" % (blockstate_dir, name),
                "kind": "blockstate", "format": "variants",
                "face": None,
            },
        ]
        templates = {
            "%s/block/%s.json" % (model_dir, name): {
                "parent": "minecraft:block/cube_bottom_top",
                "textures": {
                    "particle": "%s:block/%s_side" % (modid, name),
                    "top": "%s:block/%s_top" % (modid, name),
                    "bottom": "%s:block/%s_bottom" % (modid, name),
                    "side": "%s:block/%s_side" % (modid, name),
                },
            },
            "%s/%s.json" % (blockstate_dir, name): {
                "variants": {"": {"model": "%s:block/%s" % (modid, name)}},
            },
        }

    elif form == "cross":
        files = [
            {
                "path": "%s/block/%s.png" % (texture_dir, name),
                "kind": "texture", "width": width, "height": height,
                "alpha": True, "face": "cross",
                "note": "十字交叉贴图（透明背景）",
            },
            {
                "path": "%s/block/%s.json" % (model_dir, name),
                "kind": "model", "format": "block/cross",
                "face": None,
            },
            {
                "path": "%s/%s.json" % (blockstate_dir, name),
                "kind": "blockstate", "format": "variants",
                "face": None,
            },
        ]
        templates = {
            "%s/block/%s.json" % (model_dir, name): {
                "parent": "minecraft:block/cross",
                "textures": {"cross": "%s:block/%s" % (modid, name)},
            },
            "%s/%s.json" % (blockstate_dir, name): {
                "variants": {"": {"model": "%s:block/%s" % (modid, name)}},
            },
        }

    elif form == "entity_uv":
        files = [
            {
                "path": "%s/entity/%s.png" % (texture_dir, name),
                "kind": "texture", "width": width, "height": height,
                "alpha": True, "face": "uv",
                "note": "实体 UV 贴图（64x32 或 64x64）",
            },
        ]
        templates = {}

    else:
        raise ValueError("unsupported form: %r" % form)

    return {
        "form": form,
        "modid": modid,
        "files": files,
        "templates": templates,
        "note": "文件路径按 Minecraft 资源包约定；templates 为空白/示例 JSON。",
    }


def _build_v2_file_path(form: str, name: str, face: dict) -> str:
    """生成 face 对应的 texture file path（与 file_contract 一致）。"""
    modid = "mcmod"
    suffix = face.get("suffix", "")
    if form == "block_multi":
        return "assets/%s/textures/block/%s%s.png" % (modid, name, suffix)
    if form == "cross":
        return "assets/%s/textures/block/%s.png" % (modid, name)
    if form == "entity_uv":
        return "assets/%s/textures/entity/%s.png" % (modid, name)
    # item
    return "assets/%s/textures/item/%s.png" % (modid, name)


def _build_v2_output_contract(form: str, name: str, width: int, height: int,
                              anchors: list[dict], entity: str | None = None) -> dict:
    """生成 output_contract：按 form 声明每个 face 需要输出的像素块。

    v3-prompt-fix：这是**格式骨架**，不是答案示例。
    - 保留 W/H 模板、PALETTE 占位说明、index grid 行列规则。
    - 不嵌入任何完整原版锚点的 PALETTE + index grid。
    - 如需格式示例，只给明显无关的 2x2 占位并注明不得复制参考贴图。
    """
    spec = _FORM_SPECS[form]
    faces_out = []
    text_lines = ["FORM=%s" % form, "FACES=%d" % len(spec["faces"]), ""]
    for i, face in enumerate(spec["faces"]):
        fw, fh = face.get("width", width), face.get("height", height)
        file_path = _build_v2_file_path(form, name, face)
        # anchors 参数保留用于调用兼容；此处绝不把锚点 palette/index 写入契约。
        faces_out.append({
            "face": face["id"],
            "file": file_path,
            "width": fw,
            "height": fh,
            "palette_placeholder": "#RRGGBB",
            "grid_format": "共 %d 行，每行 %d 个整数；-1 表示透明，非负整数引用 PALETTE 索引。" % (fh, fw),
            "seed_contract": None,
            "seed_note": "格式骨架：不嵌入完整锚点 grid；输出必须由 LLM 新生成，不得复制参考贴图。",
        })
        text_lines.append("=== face: %s ===" % face["id"])
        text_lines.append("FILE: %s" % file_path)
        text_lines.append("W=%d H=%d" % (fw, fh))
        text_lines.append("")
        text_lines.append("PALETTE")
        text_lines.append("# 占位说明：在此列出 LLM 自己生成的调色板，每行一个索引与 #RRGGBB")
        text_lines.append("# 例如：0: #AABBCC（仅格式示意，禁止复制参考贴图）")
        text_lines.append("")
        text_lines.append("INDEX GRID")
        text_lines.append("# 共 %d 行，每行 %d 个整数；-1 表示透明，非负整数引用上面 PALETTE 的索引。" % (fh, fw))
        text_lines.append("# 非 -1 像素数量要求：16x16 至少 40 个；禁止输出全 -1 的空图。")
        if fw == 16 and fh == 16:
            text_lines.append("# 以下是 16x16 真实生成样本的 INDEX GRID（蘑菇幼苗），仅用于展示“如何用索引填色/哪些位置用哪个颜色”；禁止复制它的形状与配色：")
            text_lines += [
                "-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1",
                "-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1",
                "-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1",
                "-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1",
                "-1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1 -1",
                "-1 -1 -1 -1 -1 -1  2  0  0  2 -1 -1 -1 -1 -1 -1",
                "-1 -1 -1 -1 -1  2  0  0  1  0  2 -1 -1 -1 -1 -1",
                "-1 -1 -1 -1  2  0  0  1  0  0  1  2 -1 -1 -1 -1",
                "-1 -1 -1 -1  2  0  1  0  0  1  0  2 -1 -1 -1 -1",
                "-1 -1 -1 -1  2  0  0  1  0  0  1  2 -1 -1 -1 -1",
                "-1 -1 -1 -1  3  3  4  3  3  3  4  3 -1 -1 -1 -1",
                "-1 -1 -1 -1 -1 -1 -1  5  6 -1 -1 -1 -1 -1 -1 -1",
                "-1 -1 -1 -1 -1 -1 -1  5  6 -1 -1 -1 -1 -1 -1 -1",
                "-1 -1 -1 -1 -1 -1  7  5  6  7 -1 -1 -1 -1 -1 -1",
                "-1 -1 -1 -1 -1 -1 -1  5  6 -1 -1 -1 -1 -1 -1 -1",
                "-1 -1 -1 -1 -1 -1 -1  5  6 -1 -1 -1 -1 -1 -1 -1",
            ]
            text_lines.append("# 注意：该样本的 PALETTE 有 0~7 共 8 个颜色索引；你的输出调色板也必须更丰富（至少 5~8 色：主色/亮部/暗部/强调色/描边色/中间色），并用这些索引填充细节。样本只是格式示范，不代表你只能用这几色。")
        else:
            text_lines.append("# 示例：至少填一部分非 -1 像素，并用 0/1/2 等索引表示颜色。")
        text_lines.append("")

    # entity_uv 额外输出 Vanilla 标准 UV 语义，避免 LLM 画成单个居中侧视图。
    if form == "entity_uv":
        text_lines.append("")
        text_lines.append(eu.contract_text(width, height, entity=entity))
        text_lines.append("")

    return {
        "form": form,
        "faces": faces_out,
        "text": "\n".join(text_lines).strip(),
        "note": "声明每个 face 需要输出的像素块文本的格式骨架（W/H 模板 + PALETTE 占位 + index grid 行列规则）；"
                "不提供任何完整锚点 grid，实际像素内容必须由 LLM 新生成。",
    }


def _v2_few_shot(form: str) -> dict:
    snippet_rel, asset_name, type_ = _FEW_SHOT_BY_FORM[form]
    snippet_path = _SNIPPET_DIR / snippet_rel
    if snippet_path.exists():
        return {
            "asset": asset_name,
            "type": type_,
            "form": form,
            "path": str(snippet_path.relative_to(_THIS_DIR)),
            "compact_text": snippet_path.read_text(encoding="utf-8").strip(),
        }
    # 核心仓库没有 style_cards/snippets 时，用内置极简格式兜底。
    return {
        "asset": asset_name,
        "type": type_,
        "form": form,
        "path": "builtin_fallback",
        "compact_text": _FALLBACK_FEW_SHOT_TEXT,
        "fallback_note": "style_cards/snippets 不存在，使用内置极简 few-shot（非原版素材）。",
    }


def _v2_style_rules(type_: str) -> dict:
    card_name = _CARD_FILE_BY_TYPE[type_]
    cards = [_STYLE_CARDS_DIR / ("%s.md" % card_name)]
    rules = _extract_style_rules(cards)
    if any(rules.values()):
        return rules
    # 核心仓库没有 style_cards 时，返回内置极简规则兜底。
    return dict(_FALLBACK_STYLE_RULES)


def build_prompt_pack_v2(args: argparse.Namespace) -> dict:
    """v2：基于 retrieval/query 生成 form-aware 提示包。"""
    retrieval_data = getattr(args, "retrieval_data", None)
    if retrieval_data is not None:
        retrieval = retrieval_data
    else:
        retrieval = _load_retrieval(args.retrieval, args.query, getattr(args, "top", 3) or 3)

    form = args.form
    if form in (None, "", "auto"):
        form = retrieval.get("form", "auto")
    if form not in _VALID_FORMS:
        # auto 且无 retrieval.form 时按 query 关键词再判一次
        if form == "auto" and args.query:
            import retrieve_assets as ra
            form = ra._query_form(args.query, retrieval.get("anchors", []), None)["form"]
        else:
            raise ValueError("unsupported form: %r (must be one of %s)" % (form, "/".join(_VALID_FORMS)))
    if form not in _VALID_FORMS:
        raise ValueError("unsupported form: %r" % form)

    spec = _FORM_SPECS[form]
    type_ = spec["type"]
    if args.size:
        width, height = _parse_size(args.size)
    else:
        width, height = spec["default_size"]
    if form == "entity_uv" and (width, height) not in ((64, 32), (64, 64)):
        raise ValueError("entity_uv size must be 64x32 or 64x64, got %dx%d" % (width, height))
    if form != "entity_uv" and (width, height) != (16, 16):
        raise ValueError("%s requires 16x16 textures, got %dx%d" % (form, width, height))

    raw_anchors = retrieval.get("anchors", [])
    if not raw_anchors:
        raise ValueError("retrieval returned no anchors; cannot build prompt pack")
    anchors = [_extract_feature_per_anchor(a) for a in raw_anchors]

    novelty = getattr(args, "novelty", 0.5)
    if novelty is None:
        novelty = 0.5
    novelty = max(0.0, min(1.0, float(novelty)))
    no_original_ref = bool(getattr(args, "no_original_ref", False))

    features = _aggregate_features(anchors)
    style_rules = _v2_style_rules(type_)
    few_shot = _v2_few_shot(form)
    file_contract = _form_file_contract(form, args.name, width, height)
    entity = eu.detect_entity(args.query or args.name) if form == "entity_uv" else None
    output_contract = _build_v2_output_contract(form, args.name, width, height, anchors, entity=entity)

    reference_block, include_compact, compact_limit = _reference_block_for_anchors(
        anchors, form, width, height, entity, novelty, no_original_ref,
    )

    # v4-concept：生成概念卡并作为“先理解再生成”的前置上下文。
    concept_card = None
    try:
        import concept_grounder as cg
        concept_card = cg.build_concept_card(
            query=(args.query or retrieval.get("query") or args.name),
            retrieval_data=retrieval,
            form=form,
        )
        _v2_log("v4-concept: generated card for %s (form=%s, face_regions=%d, goals=%d)" % (
            args.name, form, len(concept_card.get("face_regions", {})),
            len(concept_card.get("visual_goals", []))
        ))
    except Exception as exc:  # noqa: BLE001
        # 不因概念卡失败阻断提示包生成；记录原因以便追踪。
        _v2_log("v4-concept: FAILED for %s: %s" % (args.name, exc))

    # s2-shape：为每个部件生成 2-4 个轮廓基础候选（silhouette bank）。
    silhouette_parts = []
    if concept_card:
        silhouette_parts = concept_card.get("parts", [])
        sp = concept_card.get("shape_pattern") or {}
        if isinstance(sp, dict):
            silhouette_parts = sp.get("parts") or silhouette_parts
    if not silhouette_parts:
        silhouette_parts = features.get("parts", []) or ["主体"]
    if no_original_ref:
        # --no-original-ref 连原版轮廓候选也一并关闭。
        silhouette_bank = []
    else:
        silhouette_bank = refa.build_silhouette_bank(
            parts=silhouette_parts,
            retrieval_anchors=anchors,
            form=form,
            width=width,
            height=height,
            entity=entity,
        )
    if concept_card is not None:
        concept_card = dict(concept_card)
        sp = concept_card.get("shape_pattern")
        if isinstance(sp, dict):
            sp = dict(sp)
            sp["silhouette_candidates"] = silhouette_bank
            concept_card["shape_pattern"] = sp

    prompt_text = _build_v2_prompt_text(
        args.name, retrieval, form, width, height, anchors, features,
        style_rules, few_shot, file_contract, output_contract,
        concept_card=concept_card,
        reference_block=reference_block,
        silhouette_bank=silhouette_bank,
    )

    pack = {
        "name": args.name,
        "query": retrieval.get("query", args.query or ""),
        "form": form,
        "form_note": retrieval.get("form_note", ""),
        "form_source": retrieval.get("form_source", "query_rule"),
        "type": type_,
        "size": "%dx%d" % (width, height),
        "width": width,
        "height": height,
        "fusion": args.fusion or "retrieval features fusion",
        "retrieval_method": retrieval.get("method", "rule"),
        "retrieval_method_note": retrieval.get("method_note", ""),
        "anchors": anchors,
        "features": features,
        "style_rules": style_rules,
        "few_shot": few_shot,
        "file_contract": file_contract,
        "output_contract": output_contract,
        "output_contract_note": (
            "按 form 声明的像素块输出清单；实际 LLM 应逐 face 输出可被 text_to_texture.py 解析的文本块。"
        ),
        "concept_card": concept_card,
        "silhouette_bank": silhouette_bank or None,
        "novelty": novelty,
        "no_original_ref": no_original_ref,
        "reference_block": reference_block or "",
        "reference_block_meta": {
            "include_compact": include_compact,
            "compact_limit": compact_limit,
        },
        "prompt": prompt_text,
    }
    if args.retrieval:
        rp = _normalize_path(args.retrieval)
        if not rp.is_absolute():
            rp = _THIS_DIR / rp
        pack["retrieval_path"] = _rel_or_abs(rp.resolve())
    return pack


def _form_specific_constraints_text(form: str, width: int, height: int) -> list[str]:
    """返回 form-specific 的结构化输出硬约束（参考完整资源，不做单张图/剪影）。"""
    lines: list[str] = []
    if form == "block_multi":
        lines.append("# 形式硬约束（block_multi：完整方块，不是物品剪影）")
        lines.append("- 三面 top/side/bottom 都是 16x16 全不透明方块面，边缘必须连续；禁止沿用透明物品剪影或棋盘格。")
        lines.append("- side 左右边可环绕平铺（四个侧面共用同一张 side，左右 wrap 一致）；side 顶/底边与 top/bottom 边缘颜色连续。")
        lines.append("- 参考完整资源：不是只看单张参考图；必须同时理解方块三面 + 原版 blockstate/model（cube_bottom_top）契约，按结构化 face 输出。")
    elif form == "entity_uv":
        lines.append("# 形式硬约束（entity_uv：标准 UV 图集/皮肤，不是单个侧视图）")
        lines.append("- 这不是单个侧视图，是标准 %dx%d atlas；每个区域按语义填，禁止把整张图画成一个居中侧视剪影。" % (width, height))
        lines.append("- 按 entity_uv_spec 注入的区域坐标逐区域展开（头/身/腿/手臂等）；Java 资源包只能替换原版实体贴图路径，原版模型硬编码。")
        lines.append("- 参考完整资源：原版实体 texture atlas + 标准模型采样坐标，不是只看单张截图。")
    elif form == "cross":
        lines.append("# 形式硬约束（cross：植物/十字透明贴图）")
        lines.append("- 这是 16x16 透明背景的十字交叉贴图；主体居中、四周保留至少 1px 透明边距，禁止铺满到边缘。")
    else:  # item
        lines.append("# 形式硬约束（item：16x16 透明物品贴图）")
        lines.append("- 这是 16x16 透明背景物品贴图；主体居中、四周保留至少 1px 透明边距，禁止铺满到边缘。")
    return lines


def _build_v2_prompt_text(
    name: str, retrieval: dict, form: str, width: int, height: int,
    anchors: list[dict], features: dict, style_rules: dict,
    few_shot: dict, file_contract: dict, output_contract: dict,
    concept_card: dict | None = None,
    reference_block: str | None = None,
    silhouette_bank: list[dict] | None = None,
) -> str:
    """把 v2/v4 提示包渲染为可直接给 LLM 的中文提示文本。"""
    lines = []
    lines.append("# 任务说明")
    lines.append("请生成一个新的 Minecraft 像素资源，遵守 Minecraft 原版像素风格。")
    lines.append("")
    lines.append("- 资源名：%s" % name)
    lines.append("- 描述：%s" % (retrieval.get("query", name) or name))
    lines.append("- 形式：%s" % form)
    lines.append("- 尺寸：%dx%d" % (width, height))
    lines.append("")
    lines.append("# 本体硬约束（最重要）")
    lines.append("- 必须生成「%s」这个物体本身；参考节点不能改变主体类别、形状或语义。" % (retrieval.get("query", name) or name))
    lines.append("- 参考节点只允许借用配色、材质、明暗、尺度与局部图案；若参考节点与 %s 语义冲突，请忽略其形状与语义。" % (retrieval.get("query", name) or name))
    lines.append("")
    lines.extend(_form_specific_constraints_text(form, width, height))
    lines.append("")

    if concept_card:
        lines.append("")
        lines.append("# 概念理解卡片（先理解，再生成）")
        lines.append("")
        lines.append("- 名称：%s" % concept_card.get("item_name", ""))
        lines.append("- 描述：%s" % concept_card.get("description", ""))
        lines.append("- 部件：%s" % "；".join(concept_card.get("parts", [])))
        lines.append("- 各 face 画什么：")
        for face, desc in concept_card.get("face_regions", {}).items():
            lines.append("  - %s：%s" % (face, desc))
        lines.append("- 视觉目标：")
        for g in concept_card.get("visual_goals", []):
            lines.append("  - %s" % g)
        lines.append("- 原版参考：%s" % concept_card.get("minecraft_reference", ""))
        lines.append("- 避免：%s" % "；".join(
            str(x).strip().rstrip("；;。., ") for x in concept_card.get("avoid", [])
        ))
        lines.append("")
        lines.append("> 输出顺序要求：你必须先用自己的话描述你理解的这个物体"
                     "（至少包含它是什么、由哪些部件组成、每个 face 画什么），"
                     "再输出下面的各 face 纹理。禁止跳过理解直接画纹理。")
        lines.append("")

        # v5 设计流程升级：先理解语义 → 再定配色方案 → 再定形状图样 → 参考节点仅作设计参考。
        lines.append("")
        lines.append("# 设计方案（先理解 → 配色 → 形状）")
        lines.append("")
        lines.append("> 参考素材只是设计参考节点，不是硬性指标，更不是必须锁形状。")
        lines.append("> 不要复制参考贴图的逐像素内容；优先保证“这个东西是什么”的语义可辨认。")
        lines.append("> 允许 3~8 个参考节点，不要求只参考 2 个；每个节点的作用可以是 shape/color/pattern/border/material。")
        lines.append("> 形状-纹样一体：先用形状确定结构，再让纹样贴合形状的走向/边缘/明暗面；纹样不得脱离形状独立存在。")
        lines.append("")
        ps = concept_card.get("palette_scheme", {}) if isinstance(concept_card.get("palette_scheme"), dict) else {}
        if ps:
            lines.append("### 配色方案 palette_scheme")
            lines.append("- 主色 base：%s" % ps.get("base", ""))
            lines.append("- 亮部 light：%s" % ps.get("light", ""))
            lines.append("- 暗部 dark：%s" % ps.get("dark", ""))
            lines.append("- 强调色 accent：%s" % ps.get("accent", ""))
            lines.append("- 描边色 outline：%s" % ps.get("outline", ""))
            lines.append("- 自然边框说明：%s" % ps.get("border_note", ""))
            lines.append("- 饱和度说明：%s" % ps.get("saturation_note", ""))
            lines.append("")
        sp = concept_card.get("shape_pattern", {}) if isinstance(concept_card.get("shape_pattern"), dict) else {}
        if sp:
            lines.append("### 形状图样 shape_pattern")
            lines.append("- 剪影 silhouette：%s" % sp.get("silhouette", ""))
            lines.append("- 部件 parts：%s" % "；".join(sp.get("parts", [])))
            lines.append("- 描边 border：%s" % sp.get("border", ""))
            lines.append("- 明暗 shading：%s" % sp.get("shading", ""))
            lines.append("- 细节图案 detail_pattern：%s" % sp.get("detail_pattern", ""))
            lines.append("- 是否锁形状 shape_lock_optional：%s" % sp.get("shape_lock_optional", True))
            ori = sp.get("orientation")
            if isinstance(ori, dict):
                lines.append("- 方位/构图 orientation：")
                for k, v in ori.items():
                    lines.append("  - %s：%s" % (k, v))
            lines.append("- 形状-纹样联动 part_pattern_flow：")
            for ppf in sp.get("part_pattern_flow", []):
                lines.append("  - [%s] 形状：%s | 纹样：%s | 走向：%s" % (
                    ppf.get("part", ""), ppf.get("shape", ""),
                    ppf.get("pattern", ""), ppf.get("flow", ""),
                ))
            lines.append("- 联动说明 integration_note：%s" % sp.get("integration_note", ""))
            bank_for_prompt = sp.get("silhouette_candidates") or (silhouette_bank or [])
            if bank_for_prompt:
                candidate_block = refa.render_silhouette_candidates(bank_for_prompt)
                if candidate_block:
                    lines.append(candidate_block)
                    lines.append("")
        refs = concept_card.get("reference_nodes", [])
        if refs:
            lines.append("### 参考节点 reference_nodes（3~8 个）")
            for i, node in enumerate(refs, 1):
                lines.append("- [%d] %s | role=%s | %s" % (
                    i, node.get("asset", ""), node.get("role", ""), node.get("reason", "")
                ))
            lines.append("")
        checklist = concept_card.get("design_checklist", [])
        if checklist:
            lines.append("### 设计自检清单（输出像素前必须逐项自查）")
            for c in checklist:
                lines.append("- [ ] %s：%s" % (c.get("item", ""), c.get("must", "")))
                lines.append("    自查：%s" % c.get("self_check", ""))
            lines.append("")

    lines.append("")
    lines.append("# 检索特征摘要")
    lines.append("")
    lines.append("从原版锚点检索到以下特征，必须体现在生成结果中：")
    lines.append("")
    lines.append(features["summary"])

    lines.append("")
    if reference_block:
        lines.append(reference_block)
        lines.append("")
    else:
        # 兼容回退：没有新 reference block 时保留旧的“仅语义摘要”锚点段。
        lines.append("# 锚点参考（语义摘要，仅供风格参考，不得复制像素）")
        lines.append("")
        for a in anchors:
            lines.append("## %s (%s)" % (a.get("name", "?"), a.get("role", "?")))
            lines.append("- 路径：%s" % a.get("path", ""))
            lines.append("- 类别：%s" % a.get("category", ""))
            lines.append("- 尺寸：%s" % a.get("size", ""))
            for k, label in (("shape", "形状"), ("pattern", "图案"), ("parts", "部位"), ("attraction", "吸引点")):
                v = (a.get("features", {}).get(k) or [])
                if isinstance(v, list):
                    v = "；".join(v)
                if v:
                    lines.append("- %s：%s" % (label, v))
            cols = a.get("features", {}).get("colors", [])
            if cols:
                lines.append("- 颜色：%s" % " ".join(cols))
            lines.append("")

        lines.append("> 参考素材只是语义/风格参考，不提供可复制的像素网格；必须自行设计新形状与配色。")
        lines.append("")

    lines.append("# 风格规则")
    lines.append("")
    for key, label in (("palette", "调色板"), ("light_dark", "明暗规则"),
                       ("outline", "描边规则"), ("noise", "噪点 / 材质规则")):
        rules = style_rules.get(key, [])
        if rules:
            lines.append("## %s" % label)
            lines.extend(rules)
            lines.append("")

    lines.append("# 通用设计原则（每个物体都适用）")
    lines.append("")
    try:
        import concept_grounder as cg
        generic_principles = getattr(cg, "GENERIC_DESIGN_PRINCIPLES", []) or []
    except Exception:  # noqa: BLE001
        generic_principles = []
    for rule in generic_principles:
        lines.append("- %s" % rule)
    lines.append("")

    lines.append("# 通用像素细节（每个物体都适用，不绑定具体物品）")
    lines.append("")
    try:
        import concept_grounder as cg
        generic_rules = getattr(cg, "GENERIC_PIXEL_DETAIL_RULES", []) or []
    except Exception:  # noqa: BLE001
        generic_rules = []
    if not generic_rules:
        generic_rules = [
            "边框/描边：外轮廓用 1px 深色描边；部件接缝用暗色分隔；不做均匀黑框。",
            "材质高光：亮部高光沿形状走向，暗部在背光侧；金属/木/石/发光/软质等不同材质按语义推理使用不同高光强度与纹理提示，不给死例子。",
            "纹理：材质纹理（木纹/石裂纹/金属划痕/发光颗粒等）贴合形状；若原版有参考就参考其质感，没有就自行推理合理材质。",
            "明暗分层：每个部件至少 base/light/dark 三档色阶；用 1px 明暗过渡表现体积，避免平涂。",
            "方向/连接：整体方向一致，部件连接自然、不悬空。",
        ]
    for rule in generic_rules:
        lines.append("- %s" % rule)
    lines.append("")

    lines.append("# Few-shot：同类原版 compact 片段")
    lines.append("")
    fs = few_shot
    lines.append("- 示例资产：%s" % fs.get("asset", ""))
    lines.append("- 类型：%s" % fs.get("type", ""))
    lines.append("- 来源：%s" % fs.get("path", ""))
    lines.append("")
    lines.append("> few-shot 仅作格式/风格示意；不得复制参考贴图，必须生成新形状/图案。")
    lines.append("")

    lines.append("# 输出文件清单")
    lines.append("")
    for f in file_contract.get("files", []):
        lines.append("- %s" % f["path"])
    lines.append("")
    lines.append("空白/示例 JSON 模板：")
    for path, tmpl in file_contract.get("templates", {}).items():
        lines.append("```json")
        lines.append(json.dumps(tmpl, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    lines.append("# 输出契约")
    lines.append("")
    lines.append(output_contract["text"])
    lines.append("")

    lines.append("# 严格输出要求")
    lines.append("")
    lines.append("- 每个 face 只输出一个可被 text_to_texture.py 解析的文本块（W/H + PALETTE + index grid）。")
    lines.append("- 多 face 时按 output_contract 的 face 顺序逐一输出，禁止混在一个块里。")
    lines.append("- 透明像素必须使用 -1。")
    lines.append("- 禁止输出全 -1 的空图：16x16 的 INDEX GRID 中非 -1 像素必须 ≥ 40（64x32 实体按面积比例 ≥ 30%）。")
    lines.append("- 禁止输出解释性文字、Markdown 代码围栏、JSON 或额外标题。")
    lines.append("- 必须生成新的形状/图案/调色板：不得复制任何参考贴图（包括锚点 compact 文本与 few-shot 的 index grid）。")
    return "\n".join(lines).strip() + "\n"


def write_v2_prompt_pack(pack: dict, out_path: Path) -> Path:
    out_path = _normalize_path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return out_path


def prebuild_v2_packs(verbose: bool = True) -> list[Path]:
    """生成任务列出的 3 个 v2 提示包到 prompt_packs_v2/。"""
    out_files = []
    for preset in V2_PREBUILDS:
        retrieval_path = _ensure_retrieval_file(preset)
        out_path = _PROMPT_PACKS_V2_DIR / ("%s.json" % preset["name"])
        ns = argparse.Namespace(
            name=preset["name"],
            query=preset.get("query"),
            retrieval=str(retrieval_path),
            form=preset["form"],
            size=None,
            fusion=None,
            out=str(out_path),
            novelty=0.5,
            no_original_ref=False,
        )
        pack = build_prompt_pack_v2(ns)
        write_v2_prompt_pack(pack, out_path)
        out_files.append(out_path)
        _v2_log("wrote v2 pack: %s (form=%s, query=%r)" % (
            _rel_or_abs(out_path), pack["form"], pack["query"]
        ))
        if verbose:
            print("wrote: %s (%s, %s, %s)" % (
                out_path, pack["form"], pack["type"], pack["size"]
            ), file=sys.stderr)
    return out_files


# ---------------------------------------------------------------------------
# 主生成函数
# ---------------------------------------------------------------------------

def build_prompt_pack(args: argparse.Namespace) -> dict:
    w, h = _parse_size(args.size)
    category = args.type.lower().strip()
    if category not in ("item", "block", "entity"):
        raise ValueError("--type must be item|block|entity")

    primary_path, primary_index = _resolve_anchor(args.anchor_primary, category)
    primary_w, primary_h = _image_size(primary_path)
    primary_compact = _run_asset_to_text(primary_path)

    primary_category = primary_index.get("category", category) if primary_index else (_infer_category_from_path(primary_path) or category)
    anchors = {
        "primary": {
            "role": "primary",
            "name": primary_path.name,
            "path": _rel_or_abs(primary_path),
            "category": primary_category,
            "size": "%dx%d" % (primary_w, primary_h),
            "compact_text": primary_compact,
        }
    }

    if args.anchor_secondary:
        # 杂交：secondary 可能来自其他 category，按指定 category 之外的库索引兜底。
        secondary_path = _normalize_path(args.anchor_secondary)
        if not secondary_path.exists():
            # 尝试在全集索引中按文件名查找
            entries = _load_index_entries()
            wanted_stem = Path(args.anchor_secondary).stem.lower()
            wanted_name = Path(args.anchor_secondary).name.lower()
            for e in entries:
                entry_name = str(e.get("name", "")).lower()
                path_name = Path(str(e.get("path", ""))).name.lower()
                if (
                    wanted_name in (entry_name, path_name)
                    or wanted_stem in (Path(entry_name).stem.lower(), Path(path_name).stem.lower())
                ):
                    raw = _normalize_path(e["path"])
                    if not raw.is_absolute():
                        raw = _INDEX_PATH.parent / raw
                    secondary_path = raw
                    secondary_index = e
                    break
            else:
                raise FileNotFoundError(
                    "secondary anchor not found: %r" % args.anchor_secondary
                )
        else:
            secondary_index = None
        secondary_w, secondary_h = _image_size(secondary_path)
        secondary_compact = _run_asset_to_text(secondary_path)
        # 从 index 或路径推断 category
        secondary_category = (
            secondary_index.get("category") if secondary_index
            else _infer_category_from_path(secondary_path)
        )
        anchors["secondary"] = {
            "role": "secondary",
            "name": secondary_path.name,
            "path": _rel_or_abs(secondary_path),
            "category": secondary_category,
            "size": "%dx%d" % (secondary_w, secondary_h),
            "compact_text": secondary_compact,
        }
    elif args.fusion:
        raise ValueError("hybrid prompt requires --anchor secondary <png>")

    # 风格卡：主类型必选；若存在 secondary 且其 category 不同，追加对应卡。
    # 文件名使用 build_style_cards.py 生成的复数风格卡（items/blocks/entities.md）。
    card_names = [_CARD_FILE_BY_TYPE[category]]
    if "secondary" in anchors and anchors["secondary"]["category"]:
        sec_cat = anchors["secondary"]["category"]
        sec_card = _CARD_FILE_BY_TYPE.get(sec_cat)
        if sec_card and sec_card not in card_names:
            card_names.append(sec_card)
    cards = [_STYLE_CARDS_DIR / ("%s.md" % cn) for cn in card_names]
    style_rules = _extract_style_rules(cards)
    # 至少保留一个非空 section，否则视为失败
    if not any(style_rules.values()):
        raise ValueError("no style rules extracted from %s" % ", ".join(map(str, cards)))

    # 输出契约
    primary_palette, primary_index_grid = _extract_palette_and_index(primary_compact)
    output_contract = _build_output_contract(w, h, primary_palette, primary_index_grid)

    # 校验输出契约行列数与声明一致
    contract_lines = output_contract.splitlines()
    header_match = re.match(r"^W=(\d+) H=(\d+)$", contract_lines[0])
    if not header_match:
        raise ValueError("internal bug: output_contract first line not W/H")
    cw, ch = int(header_match.group(1)), int(header_match.group(2))
    grid_rows = _grid_rows_from_contract(output_contract)
    if len(grid_rows) != ch:
        raise ValueError(
            "output_contract grid rows %d != H %d" % (len(grid_rows), ch)
        )
    if any(len(ln.split()) != cw for ln in grid_rows):
        raise ValueError("output_contract grid row width mismatch")

    pack = {
        "name": args.name,
        "type": category,
        "size": "%dx%d" % (w, h),
        "width": w,
        "height": h,
        "fusion": args.fusion,
        "anchors": anchors,
        "style_rules": style_rules,
        "style_cards": [str(c.relative_to(_THIS_DIR)) if c.exists() else str(c) for c in cards],
        "few_shot": _few_shot_for_type(category),
        "output_contract": output_contract,
        "output_contract_note": (
            "格式契约示例（palette+index 来自 primary 锚点）；"
            "实际 LLM 输出应替换为本次融合后的 palette+index grid。"
        ),
    }
    if getattr(args, "fallback_note", None):
        pack["fallback_note"] = args.fallback_note
    return pack


def write_prompt_pack(pack: dict, out_path: Path) -> Path:
    out_path = _normalize_path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return out_path


# ---------------------------------------------------------------------------
# prebuild
# ---------------------------------------------------------------------------

def prebuild_packs(verbose: bool = True) -> list[Path]:
    out_files: list[Path] = []
    for preset in PREBUILDS:
        args = argparse.Namespace(
            name=preset["name"],
            type=preset["type"],
            size=preset["size"],
            anchor_primary=preset["primary"],
            anchor_secondary=preset["secondary"],
            fusion=preset["fusion"],
            out=str(_PROMPT_PACKS_DIR / ("%s.json" % preset["name"])),
            fallback_note=preset.get("fallback_note"),
        )
        pack = build_prompt_pack(args)
        out_path = write_prompt_pack(pack, Path(args.out))
        out_files.append(out_path)
        if verbose:
            print("wrote: %s (%s, %s, fusion=%s)" % (
                out_path, pack["type"], pack["size"], pack["fusion"]
            ), file=sys.stderr)
    return out_files


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------

def _validate_prompt_pack(path: Path) -> list[str]:
    """返回该 prompt pack 的 PASS 项；失败抛 ValueError。"""
    ok: list[str] = []
    data = json.loads(path.read_text(encoding="utf-8"))

    required_top = ["name", "type", "size", "anchors", "fusion", "style_rules", "few_shot", "output_contract"]
    missing = [k for k in required_top if k not in data]
    if missing:
        raise ValueError("missing top-level fields: %s" % ", ".join(missing))
    ok.append("top-level fields are complete")

    if data["type"] not in ("item", "block", "entity"):
        raise ValueError("invalid type %r" % data["type"])
    ok.append("type is valid (item/block/entity)")

    m = re.match(r"^(\d+)x(\d+)$", data["size"])
    if not m:
        raise ValueError("invalid size %r" % data["size"])
    w, h = int(m.group(1)), int(m.group(2))
    if w <= 0 or h <= 0:
        raise ValueError("non-positive size")
    if data.get("width") != w or data.get("height") != h:
        raise ValueError("width/height fields do not match size")
    ok.append("size matches W/H fields")

    for role in ("primary", "secondary"):
        if role not in data["anchors"]:
            raise ValueError("missing anchor %s" % role)
        anchor = data["anchors"][role]
        for field in ("role", "name", "path", "category", "size", "compact_text"):
            if not anchor.get(field):
                raise ValueError("anchor %s missing field %r" % (role, field))
        if "compact_text" not in anchor or not anchor["compact_text"].strip():
            raise ValueError("anchor %s has no compact_text" % role)
        if "## Palette (hex)" not in anchor["compact_text"] or "## Index grid" not in anchor["compact_text"]:
            raise ValueError("anchor %s compact_text is not compact asset_to_text output" % role)
    ok.append("primary and secondary anchors are complete")

    if not data["fusion"]:
        raise ValueError("fusion is empty")
    ok.append("fusion is present")

    if not isinstance(data["style_rules"], dict) or not any(data["style_rules"].values()):
        raise ValueError("style_rules is empty")
    for rule_key in ("palette", "light_dark", "outline", "noise"):
        if rule_key not in data["style_rules"]:
            raise ValueError("style_rules missing section %r" % rule_key)
    ok.append("style_rules has all four sections")

    fs = data["few_shot"]
    if "compact_text" not in fs or not fs["compact_text"].strip():
        raise ValueError("few_shot has no compact_text")
    ok.append("few_shot is present")

    contract = data["output_contract"]
    lines = contract.splitlines()
    if not lines or not re.match(r"^W=%d H=%d$" % (w, h), lines[0].strip()):
        raise ValueError("output_contract does not start with W=%d H=%d" % (w, h))
    if not any(ln.strip().lower().startswith("palette") for ln in lines):
        raise ValueError("output_contract missing PALETTE block marker")
    ok.append("output_contract starts with correct W/H and has PALETTE")

    # 从契约中解析 grid 行（首行 W/H -> PALETTE -> palette entries -> grid）
    start = None
    palette_offset = None
    for idx, ln in enumerate(lines):
        if ln.strip().lower().startswith("palette"):
            palette_offset = idx
            break
    if palette_offset is None:
        raise ValueError("no PALETTE marker")
    start = palette_offset + 1
    while start < len(lines):
        s = lines[start].strip()
        pal_line = re.match(r"^\s*\d+\s*:\s*#[0-9a-fA-F]{6}", s)
        if pal_line:
            start += 1
        else:
            break
    grid_lines = [ln.strip() for ln in lines[start:] if ln.strip() and not ln.strip().startswith("#") and not ln.strip().lower().startswith("palette")]
    if len(grid_lines) != h:
        raise ValueError("output_contract grid rows %d != H %d" % (len(grid_lines), h))
    if any(len(ln.split()) != w for ln in grid_lines):
        raise ValueError("output_contract grid columns mismatch")
    ok.append("output_contract grid dimensions match size")

    return ok


def _expected_file_count(form: str) -> int:
    return {
        "item": 2,
        "block_multi": 5,
        "cross": 3,
        "entity_uv": 1,
    }[form]


def _output_contract_text_has_full_grid(text: str, widths: list[int]) -> bool:
    """检测 output_contract.text 是否包含完整的 W 列 index grid 行。"""
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        # 即使是注释也不放过：完整 W 列数字行在任何位置都视为嵌入 grid。
        for n in widths:
            if re.match(r"^-?\d+(\s+-?\d+){%d}$" % (n - 1), s.lstrip("# ")):
                return True
    return False


def _output_contract_text_has_palette_entries(text: str) -> bool:
    """检测 output_contract.text 是否包含实际的 PALETTE 索引行（非注释占位）。"""
    return any(
        re.match(r"^\s*\d+\s*:\s*#[0-9a-fA-F]{6}\s*$", line)
        for line in text.splitlines()
    )


def _validate_v2_prompt_pack(path: Path) -> list[str]:
    """返回 v2 prompt pack 的 PASS 项；失败抛 ValueError。"""
    ok: list[str] = []
    data = json.loads(path.read_text(encoding="utf-8"))

    required_top = [
        "name", "query", "form", "type", "size", "width", "height",
        "anchors", "features", "style_rules", "few_shot",
        "file_contract", "output_contract", "prompt",
    ]
    missing = [k for k in required_top if k not in data]
    if missing:
        raise ValueError("missing v2 top-level fields: %s" % ", ".join(missing))
    ok.append("v2 top-level fields are complete")

    form = data["form"]
    if form not in _VALID_FORMS:
        raise ValueError("invalid v2 form: %r" % form)
    ok.append("form is valid (%s)" % form)

    if data["type"] not in ("item", "block", "entity"):
        raise ValueError("invalid v2 type %r" % data["type"])
    ok.append("v2 type is valid (item/block/entity)")

    m = re.match(r"^(\d+)x(\d+)$", data["size"])
    if not m:
        raise ValueError("invalid v2 size %r" % data["size"])
    w, h = int(m.group(1)), int(m.group(2))
    if data.get("width") != w or data.get("height") != h:
        raise ValueError("v2 width/height does not match size")
    ok.append("v2 size matches W/H fields")

    spec = _FORM_SPECS[form]
    if (w, h) != tuple(spec["default_size"]) and not (form == "entity_uv" and (w, h) in ((64, 32), (64, 64))):
        raise ValueError("v2 size %dx%d does not match form spec %s" % (w, h, form))
    ok.append("v2 size matches form spec")

    anchors = data["anchors"]
    if not isinstance(anchors, list) or len(anchors) < 1:
        raise ValueError("v2 anchors must be a non-empty list")
    for i, a in enumerate(anchors, 1):
        for field in ("path", "name", "role", "category", "size", "compact_text", "features"):
            if not a.get(field):
                raise ValueError("v2 anchor %d missing %s" % (i, field))
        feats = a["features"]
        for key in ("shape", "pattern", "colors", "parts", "attraction"):
            if key not in feats:
                raise ValueError("v2 anchor %d missing feature %s" % (i, key))
        if "## Palette (hex)" not in a["compact_text"] or "## Index grid" not in a["compact_text"]:
            raise ValueError("v2 anchor %d compact_text is not compact asset_to_text output" % i)
    ok.append("v2 anchors are complete (%d anchors)" % len(anchors))

    feats_all = data["features"]
    for key in ("shape", "pattern", "colors", "parts", "attraction", "summary", "anchor_count"):
        if key not in feats_all:
            raise ValueError("v2 features missing %s" % key)
    if feats_all.get("anchor_count") != len(anchors):
        raise ValueError("v2 features.anchor_count does not match anchors")
    ok.append("v2 features aggregate all five dimensions")

    if not isinstance(data["style_rules"], dict) or not any(data["style_rules"].values()):
        raise ValueError("v2 style_rules is empty")
    for key in ("palette", "light_dark", "outline", "noise"):
        if key not in data["style_rules"]:
            raise ValueError("v2 style_rules missing %s" % key)
    ok.append("v2 style_rules has four sections")

    fs = data["few_shot"]
    if "compact_text" not in fs or not fs["compact_text"].strip():
        raise ValueError("v2 few_shot has no compact_text")
    ok.append("v2 few_shot is present")

    # v4-concept：若 prompt pack 携带 concept_card，则校验字段非空。
    if data.get("concept_card") is not None:
        cc = data["concept_card"]
        for field in ("item_name", "description", "parts", "face_regions",
                      "visual_goals", "minecraft_reference", "avoid"):
            if not cc.get(field):
                raise ValueError("v2 concept_card missing %s" % field)
        if not isinstance(cc["face_regions"], dict) or not cc["face_regions"]:
            raise ValueError("v2 concept_card face_regions must be non-empty dict")
        if len(cc["visual_goals"]) < 1:
            raise ValueError("v2 concept_card visual_goals must be non-empty")
        # v5 设计升级：palette_scheme / shape_pattern / reference_nodes
        ps = cc.get("palette_scheme")
        if not isinstance(ps, dict) or not all(
            ps.get(k) for k in ("base", "light", "dark", "accent", "outline", "border_note", "saturation_note")
        ):
            raise ValueError("v2 concept_card palette_scheme missing required fields")
        sp = cc.get("shape_pattern")
        if not isinstance(sp, dict) or not sp.get("silhouette") or not sp.get("parts") or not sp.get("border"):
            raise ValueError("v2 concept_card shape_pattern missing required fields")
        ppf = sp.get("part_pattern_flow")
        if not isinstance(ppf, list) or len(ppf) < 1 or not sp.get("integration_note"):
            raise ValueError("v2 concept_card shape_pattern missing part_pattern_flow/integration_note")
        for item in ppf:
            if not item.get("part") or not item.get("shape") or not item.get("pattern") or not item.get("flow"):
                raise ValueError("v2 concept_card shape_pattern.part_pattern_flow entry invalid")
        refs = cc.get("reference_nodes")
        if not isinstance(refs, list) or not (3 <= len(refs) <= 8):
            raise ValueError("v2 concept_card reference_nodes must contain 3..8 entries")
        for node in refs:
            if not node.get("asset") or node.get("role") not in ("shape", "color", "pattern", "border", "material") or not node.get("reason"):
                raise ValueError("v2 concept_card reference_nodes entry invalid")
        chk = cc.get("design_checklist")
        if not isinstance(chk, list) or len(chk) != 9:
            raise ValueError(
                "v2 concept_card design_checklist must contain 9 items (got %d)"
                % (len(chk) if isinstance(chk, list) else 0)
            )
        for c in chk:
            if not isinstance(c, dict) or not c.get("item") or not c.get("must") or not c.get("self_check"):
                raise ValueError("v2 concept_card design_checklist entry invalid")
        checklist_ids = {c.get("id") for c in chk}
        required_ids = ("segment_border", "material_highlight", "material_texture")
        missing_ids = [rid for rid in required_ids if rid not in checklist_ids]
        if missing_ids:
            raise ValueError(
                "v2 concept_card design_checklist missing border/highlight/texture entry: %s"
                % ", ".join(missing_ids)
            )
        checklist_items = "\n".join(c.get("item", "") for c in chk)
        required_labels = ("描边", "高光", "纹理")
        missing_labels = [label for label in required_labels if label not in checklist_items]
        if missing_labels:
            raise ValueError(
                "v2 concept_card design_checklist entries missing required concepts: %s"
                % ", ".join(missing_labels)
            )
        ok.append("v2 concept_card is present and non-empty")
        ok.append("v2 concept_card has palette_scheme/shape_pattern/reference_nodes (v5 design)")
        ok.append("v2 concept_card shape_pattern is shape-pattern integrated (part_pattern_flow)")
        ok.append("v2 concept_card has design_checklist (orientation/connection/border/highlight/texture/palette/pattern/frame, 9 items)")

    # s2-shape：新生成的 prompt pack 应携带 silhouette bank，并渲染出候选菜单。
    sb = data.get("silhouette_bank")
    if sb is not None:
        if not isinstance(sb, list) or not sb:
            raise ValueError("v2 silhouette_bank must be a non-empty list")
        for entry in sb:
            if not isinstance(entry, dict) or not entry.get("part") or not isinstance(entry.get("candidates"), list):
                raise ValueError("v2 silhouette_bank entry invalid: %r" % entry)
            if not (2 <= len(entry["candidates"]) <= 4):
                raise ValueError(
                    "v2 silhouette_bank part %r must have 2..4 candidates, got %d"
                    % (entry.get("part"), len(entry["candidates"]))
                )
            for cand in entry["candidates"]:
                if cand.get("kind") not in ("shape_token", "compact_fragment"):
                    raise ValueError("v2 silhouette_bank candidate kind invalid: %r" % cand)
                if not cand.get("token") or not cand.get("source"):
                    raise ValueError("v2 silhouette_bank candidate missing token/source: %r" % cand)
        prompt_text = data.get("prompt", "")
        if "部件轮廓候选 silhouette_candidates" not in prompt_text:
            raise ValueError("v2 prompt missing silhouette_candidates section")
        for marker in ("可选其中一个", "可组合多个", "可大改形状", "禁止把候选当成最终网格"):
            if marker not in prompt_text:
                raise ValueError("v2 prompt missing silhouette-bank instruction: %r" % marker)
        ok.append("v2 silhouette_bank present with 2..4 candidates per part and rendered in prompt")

    prompt_text = data.get("prompt", "")
    design_flow_markers = (
        "设计要点（先理解，再直接输出）",
        "设计方案（先理解 → 配色 → 形状）",
    )
    if "HEX GRID" in prompt_text:
        markers = ("走向/轴线设计", "HEX GRID",
                   "参考节点（仅语义参考，禁止复制像素）",
                   "非 ---- 像素必须 >= 40")
    elif "INDEX GRID" in prompt_text:
        # INDEX GRID 可能来自“原版参考片段”（新参考块），也可能来自输出契约。
        # 因此 common 设计流程标题只要求二者之一。
        markers = ("通用设计原则", "INDEX GRID", "非 -1 像素必须 >= 40")
    else:
        markers = (
            "参考素材只是设计参考节点，不是硬性指标",
            "不要复制参考贴图",
            "允许 3~8 个参考节点",
            "形状-纹样一体：先用形状确定结构，再让纹样贴合形状的走向/边缘/明暗面；纹样不得脱离形状独立存在。",
            "设计自检清单（输出像素前必须逐项自查）",
        )
    for marker in markers:
        if marker not in prompt_text:
            raise ValueError("v2 prompt missing design-flow marker: %r" % marker)
    if not any(m in prompt_text for m in design_flow_markers):
        raise ValueError("v2 prompt missing design-flow heading (understand -> palette -> shape)")
    ok.append("v2 prompt contains design-flow paragraph (understand -> palette -> shape)")
    ok.append("v2 prompt contains shape-pattern integration requirement")
    if "HEX GRID" in prompt_text:
        ok.append("v2 prompt uses compact HEX GRID format (hex pixels + axis design)")

    fc = data["file_contract"]
    if fc.get("form") != form:
        raise ValueError("file_contract form mismatch: %r != %r" % (fc.get("form"), form))
    if len(fc.get("files", [])) != _expected_file_count(form):
        raise ValueError(
            "file_contract file count %d != expected %d for form %s"
            % (len(fc.get("files", [])), _expected_file_count(form), form)
        )
    ok.append("file_contract lists required files for %s" % form)

    oc = data["output_contract"]
    if oc.get("form") != form:
        raise ValueError("output_contract form mismatch: %r != %r" % (oc.get("form"), form))
    faces = oc.get("faces", [])
    if len(faces) != len(spec["faces"]):
        raise ValueError(
            "output_contract face count %d != expected %d for form %s"
            % (len(faces), len(spec["faces"]), form)
        )
    for i, face in enumerate(faces):
        expected = spec["faces"][i]
        if face.get("face") != expected["id"]:
            raise ValueError("output_contract face %d id mismatch: %r" % (i + 1, face.get("face")))
        if (face.get("width"), face.get("height")) != (expected["width"], expected["height"]):
            raise ValueError("output_contract face %d size mismatch" % (i + 1,))
    ok.append("output_contract declares one block per face for %s" % form)

    oc_text = oc.get("text", "")
    if "FORM=%s" % form not in oc_text:
        raise ValueError("output_contract.text missing FORM marker")
    if "FACES=%d" % len(spec["faces"]) not in oc_text:
        raise ValueError("output_contract.text missing FACES count")
    ok.append("output_contract.text has FORM/FACES header")

    # v3-prompt-fix：output_contract 只允许格式骨架，不得嵌入完整锚点 seed_contract。
    for face in faces:
        if face.get("seed_contract"):
            raise ValueError(
                "output_contract face %s still embeds a seed_contract; must use format skeleton only"
                % face["face"]
            )
    ok.append("v2 output_contract has no seed_contract full anchor grid")

    # 文本中不允许出现实际 palette 条目（非注释）和完整 W 列 index grid 行。
    if _output_contract_text_has_palette_entries(oc_text):
        raise ValueError("v2 output_contract.text has actual PALETTE entries; use placeholder only")
    face_widths = [f["width"] for f in faces]
    if _output_contract_text_has_full_grid(oc_text, face_widths):
        raise ValueError("v2 output_contract.text has a complete index grid; use format skeleton only")
    ok.append("v2 output_contract.text is a format skeleton (no full palette/index grid)")

    if "HEX GRID" in data["prompt"]:
        if "输出格式（HEX GRID" not in data["prompt"] or "参考节点" not in data["prompt"]:
            raise ValueError("v2 prompt missing features/output contract sections (compact HEX mode)")
        ok.append("v2 prompt embeds reference nodes and HEX output contract")
    elif "INDEX GRID" in data["prompt"]:
        if "通用设计原则" not in data["prompt"] or "INDEX GRID" not in data["prompt"]:
            raise ValueError("v2 prompt missing features/output contract sections (compact INDEX mode)")
        ok.append("v2 prompt embeds reference nodes and INDEX output contract")
    else:
        if "检索特征摘要" not in data["prompt"] or "输出契约" not in data["prompt"]:
            raise ValueError("v2 prompt missing features/output contract sections")
        ok.append("v2 prompt embeds features and output contract")

    if ("不得复制" not in data["prompt"]) and ("禁止复制" not in data["prompt"]):
        raise ValueError("v2 prompt missing no-copy notice")
    ok.append("v2 prompt forbids copying reference textures")

    return ok


def _run_self_test_body() -> int:
    print("# build_style_prompt.py self-test")
    print("Script: %s" % (_THIS_DIR / "build_style_prompt.py"))
    print("Prompt packs directory: %s" % _PROMPT_PACKS_DIR)
    print("Minimum required packs: 4")
    print("")

    # 旧 v1 prompt packs：仅在目录存在时校验；核心仓库没有该目录时跳过。
    passed_checks = 0
    passed_packs = 0
    failed_packs = 0
    if _PROMPT_PACKS_DIR.exists():
        pack_paths = sorted(_PROMPT_PACKS_DIR.glob("*.json"))
        print("Found old v1 prompt packs: %d" % len(pack_paths))
        for path in pack_paths:
            print("- %s" % path.name)
            try:
                ok_list = _validate_prompt_pack(path)
                passed_packs += 1
                passed_checks += len(ok_list)
                for item in ok_list:
                    print("  PASS: %s" % item)
            except Exception as e:
                failed_packs += 1
                print("  FAIL: %s" % e)
    else:
        print("SKIP: prompt_packs/ not present in this minimal core; validating v2 examples instead.")

    # v2 prompt packs：优先用 prompt_packs_v2/，否则用 examples/*/prompt_pack.json。
    # 核心仓库没有 style_cards/ 等旧依赖，因此不自动重新生成，而是校验已随仓库提供的示例包。
    v2_paths: list[Path] = []
    if _PROMPT_PACKS_V2_DIR.exists():
        v2_paths = sorted(_PROMPT_PACKS_V2_DIR.glob("*.json"))
        v2_dir_label = str(_PROMPT_PACKS_V2_DIR)
    else:
        examples_root = _THIS_DIR / "examples"
        v2_paths = sorted(examples_root.glob("*/prompt_pack.json"))
        v2_dir_label = str(examples_root / "*/prompt_pack.json")
    print("")
    print("# v2 prompt packs source: %s" % v2_dir_label)
    print("Minimum required v2 packs: %d" % min(2, len(v2_paths) or 1))
    print("")
    if len(v2_paths) < 2:
        print("FAIL: found %d v2 prompt packs, expected >=2" % len(v2_paths))
        for p in v2_paths:
            print("  found: %s" % p)
        print("SELF-TEST: FAIL")
        return 1

    v2_passed_checks = 0
    v2_passed_packs = 0
    v2_failed_packs = 0
    for path in v2_paths:
        print("- %s" % path.name)
        try:
            ok_list = _validate_v2_prompt_pack(path)
            v2_passed_packs += 1
            v2_passed_checks += len(ok_list)
            for item in ok_list:
                print("  PASS: %s" % item)
        except Exception as e:
            v2_failed_packs += 1
            print("  FAIL: %s" % e)

    print("")
    if failed_packs or v2_failed_packs:
        print("SELF-TEST: FAIL (%d old packs passed, %d old failed; %d v2 packs passed, %d v2 failed)"
              % (passed_packs, failed_packs, v2_passed_packs, v2_failed_packs))
        return 1
    total_packs = passed_packs + v2_passed_packs
    total_checks = passed_checks + v2_passed_checks
    print("SELF-TEST: PASS (%d packs, %d checks passed)" % (total_packs, total_checks))
    return 0


def run_self_test() -> int:
    """运行自检并把完整报告写入 build_style_prompt_selftest.txt，同时打印到 stdout。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = _run_self_test_body()
    report = buf.getvalue()
    out_path = _THIS_DIR / "build_style_prompt_selftest.txt"
    out_path.write_text(report, encoding="utf-8")
    sys.stdout.write(report)
    _v2_log("SELF-TEST: %s" % ("PASS" if rc == 0 else "FAIL"))
    return rc


def packed_count(paths: list[Path]) -> int:
    return len(paths)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_anchors_arg(groups: list[list[str]] | None) -> tuple[str, str | None]:
    """解析 --anchor / --anchors 手动锚点，返回 (primary, secondary)。"""
    primary = None
    secondary = None
    for group in groups or []:
        # 支持 --anchors primary p1 secondary p2 的成对形式
        if len(group) >= 2 and group[0] in ("primary", "secondary"):
            i = 0
            while i + 1 < len(group):
                role = group[i]
                png = group[i + 1]
                if role not in ("primary", "secondary"):
                    parser_error = SystemExit("--anchors role must be 'primary' or 'secondary'")
                    raise parser_error
                if role == "primary":
                    if primary is not None:
                        raise SystemExit("duplicate primary anchor")
                    primary = png
                else:
                    if secondary is not None:
                        raise SystemExit("duplicate secondary anchor")
                    secondary = png
                i += 2
        else:
            # 支持旧 plan 里的 --anchors primary.png secondary.png
            for item in group:
                if primary is None:
                    primary = item
                elif secondary is None:
                    secondary = item
                else:
                    raise SystemExit("--anchors accepts at most primary and secondary (got extra %r)" % item)
    return primary, secondary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate mc2-prompt JSON pack from mc_asset_library + style_cards (v1/v2)."
    )
    parser.add_argument("--name", help="Prompt pack name, e.g. mushroom_axe")
    parser.add_argument("--type", choices=["item", "block", "entity"], help="Resource type (manual mode)")
    parser.add_argument("--size", help="Canvas size, WxH, e.g. 16x16 or 64x32")
    parser.add_argument("--anchor", action="append", nargs=2, metavar=("ROLE", "PNG"),
                        help="Manual anchor PNG; use --anchor primary <png> --anchor secondary <png>. "
                             "Hybrid prompts require primary+'secondary'.")
    parser.add_argument("--anchors", action="append", nargs="+", metavar="PNG",
                        help="Manual anchors as --anchors primary.png secondary.png "
                             "or --anchors primary p1 secondary p2.")
    parser.add_argument("--query", default=None,
                        help="v2: 中文/英文想法，例如 ‘异形水晶法杖’")
    parser.add_argument("--retrieval", default=None,
                        help="v2: 读取已有 retrieval JSON，例如 retrieval_examples/xxx.json")
    parser.add_argument("--form", choices=["auto"] + list(_VALID_FORMS), default="auto",
                        help="v2 form: auto|item|block_multi|cross|entity_uv")
    parser.add_argument("--top", type=int, default=3, choices=list(range(1, 9)),
                        help="v2 query 未给 retrieval 时检索锚点数（默认 3，支持 1-8）")
    parser.add_argument("--novelty", type=float, default=0.5,
                        help="参考自由度 0..1；默认 0.5。越高越少附原版 compact 片段，越低越贴原版。")
    parser.add_argument("--no-original-ref", action="store_true",
                        help="关闭原版参考块（不注入 compact 片段与参考语法）")
    parser.add_argument("--fusion", default=None,
                        help='Fusion method, e.g. "palette overlay on shape" or custom')
    parser.add_argument("--out", default=None,
                        help="Output JSON path (default: prompt_packs/<name>.json or prompt_packs_v2/<name>.json)")
    parser.add_argument("--prebuild", action="store_true",
                        help="Generate all v1 prompt packs listed in Mission Brief (7 packs)")
    parser.add_argument("--prebuild-v2", action="store_true",
                        help="Generate 3 v2 form-aware prompt packs to prompt_packs_v2/")
    parser.add_argument("--self-test", action="store_true",
                        help="Validate old + v2 prompt packs and write build_style_prompt_selftest.txt")
    args = parser.parse_args(argv)

    if args.prebuild:
        paths = prebuild_packs()
        print("prebuild wrote %d prompt packs:" % len(paths))
        for p in paths:
            print("  %s" % p)
        return 0

    if args.prebuild_v2:
        paths = prebuild_v2_packs()
        print("prebuild-v2 wrote %d prompt packs:" % len(paths))
        for p in paths:
            print("  %s" % p)
        return 0

    if args.self_test:
        return run_self_test()

    # v2：自动检索/已有 retrieval 路径
    if args.query or args.retrieval:
        if not args.name:
            # 允许省略 --name，从 query 推断稳定 slug（例如“异形水晶法杖” -> alien_crystal_wand）。
            if args.query:
                import concept_grounder as cg
                args.name = cg.slugify(args.query)
            else:
                parser.error("--name is required when using --retrieval without --query")
        if args.type:
            # v2 从 form 推导 type；显式 --type 会误导，直接忽略但提示
            print("INFO: --type is inferred from --form in v2 mode; ignoring --type=%s" % args.type,
                  file=sys.stderr)
        if args.anchor or args.anchors:
            print("INFO: manual --anchor/--anchors ignored in v2 query/retrieval mode",
                  file=sys.stderr)
        out = args.out or str(_PROMPT_PACKS_V2_DIR / ("%s.json" % args.name))
        ns = argparse.Namespace(
            name=args.name,
            query=args.query,
            retrieval=args.retrieval,
            form=args.form,
            size=args.size,
            fusion=args.fusion,
            out=out,
            novelty=args.novelty,
            no_original_ref=args.no_original_ref,
        )
        pack = build_prompt_pack_v2(ns)
        out_path = write_v2_prompt_pack(pack, Path(out))
        _v2_log("wrote v2 pack: %s (form=%s, query=%r)" % (
            _rel_or_abs(out_path), pack["form"], pack["query"]
        ))
        print("wrote: %s" % out_path)
        return 0

    # 旧手动模式
    if not args.name or not args.type or not args.size:
        parser.error("--name, --type, --size are required for manual mode "
                     "(or use --prebuild/--prebuild-v2/--self-test)")
    primary, secondary = _parse_anchors_arg(args.anchor or args.anchors)
    if primary is None:
        parser.error("--anchor primary <png> is required (or use --anchors primary.png [...] )")
    if args.fusion and secondary is None:
        parser.error("hybrid prompt requires --anchor secondary <png>")

    out = args.out or str(_PROMPT_PACKS_DIR / ("%s.json" % args.name))
    ns = argparse.Namespace(
        name=args.name,
        type=args.type,
        size=args.size,
        anchor_primary=primary,
        anchor_secondary=secondary,
        fusion=args.fusion,
        out=out,
        fallback_note=None,
    )
    pack = build_prompt_pack(ns)
    out_path = write_prompt_pack(pack, Path(out))
    print("wrote: %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
