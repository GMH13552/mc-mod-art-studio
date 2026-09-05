#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel-demo generator: 4 original Minecraft assets with part-level reference mapping.

Each asset:
  - writes prompt.txt (built from a hand-written concept card + part-level reference table)
  - calls llm_client.py via subprocess (reads key from /tmp/mc_llm.env)
  - parses the LLM answer with text_to_texture.text_to_image
  - saves sprite.png / concept.json / raw_answer.txt / README.md / hashes.json

Run from repo root:
  set -a; source /tmp/mc_llm.env; set +a
  python3 examples/novel-demo/demo_generate.py

The script is intentionally kept in examples/novel-demo/ so all raw/prompt/PNG
artifacts remain reproducible.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import text_to_texture as t2t  # noqa: E402
import concept_grounder as cg  # noqa: E402

FULL_INDEX = Path("/mnt/c/Users/GMH13/Documents/deepseek_harness_workspace/mc_asset_library_full/full-index.json")
SMALL_INDEX = Path("/mnt/c/Users/GMH13/Documents/deepseek_harness_workspace/mc_asset_library/library-index.json")
DEMO_DIR = ROOT / "examples" / "novel-demo"
LLM_CMD = "python3 llm_client.py --prompt-file {prompt_file}"
MAX_ATTEMPTS = 3  # first try + up to 2 retries
SIMILARITY_THRESHOLD = 0.80  # >= means "highly overlapping with an original index grid"


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


_FULL_LIBRARY: dict[str, dict] | None = None


def _full_library_entries() -> dict[str, dict]:
    """Return {asset_name_without_extension: entry} from full-index.json.

    Full-index names are stored without ``.png`` (e.g. ``iron_sword``), while
    the small library and prompt tables usually use ``iron_sword.png``.
    """
    global _FULL_LIBRARY
    if _FULL_LIBRARY is None:
        _FULL_LIBRARY = {}
        if FULL_INDEX.exists():
            data = json.loads(FULL_INDEX.read_text(encoding="utf-8"))
            for e in data.get("textures", []):
                if e.get("name"):
                    _FULL_LIBRARY[e["name"]] = e
    return _FULL_LIBRARY


def load_md5_map() -> dict[str, str]:
    """Return {asset_name_without_extension: md5} from the full library."""
    return {
        name: e["md5"]
        for name, e in _full_library_entries().items()
        if e.get("md5")
    }


def full_texture_path(name: str) -> Path | None:
    """Resolve a prompt-table basename to the full library PNG on disk."""
    base = name[:-4] if name.endswith(".png") else name
    entry = _full_library_entries().get(base)
    if not entry:
        return None
    path = FULL_INDEX.parent / entry["path"]
    if not path.exists():
        return None
    return path


MD5 = load_md5_map()


def rgba_similarity(a: Image.Image, b: Image.Image) -> float:
    """Exact-cell similarity between two same-size RGBA images.

    Transparent cells must both be transparent; opaque cells must have the same
    RGB.  This is the lightweight "index grid" check: an exact or near-exact
    copy of a 16x16 original item texture will score very high, while a new
    item that merely borrows a palette stays comfortably below the threshold.
    """
    if a.size != b.size:
        raise ValueError("rgba_similarity requires same-size images (%s vs %s)" % (a.size, b.size))
    total = a.width * a.height
    if total == 0:
        return 0.0
    matches = 0
    for pa, pb in zip(a.getdata(), b.getdata()):
        if (pa[3] < 128) == (pb[3] < 128):
            if pa[3] < 128:
                matches += 1
            elif pa[:3] == pb[:3]:
                matches += 1
    return matches / total


def max_reference_similarity(img: Image.Image, reference_names: list[str]) -> tuple[float, str | None]:
    """Return (best_score, best_reference) against full-library reference PNGs.

    Same-size textures are compared directly.  For larger atlases/entity
    textures, slide a same-size window over the reference and also try a
    nearest-neighbour resize; the highest of these is used.  Missing/unreadable
    references are skipped rather than failing generation.
    """
    best_score = 0.0
    best_name: str | None = None
    for name in reference_names:
        path = full_texture_path(name)
        if path is None:
            continue
        try:
            with Image.open(path) as raw:
                ref = raw.convert("RGBA")
        except Exception:  # noqa: BLE001 - a missing/corrupt reference should not block generation
            continue
        score = 0.0
        if ref.size == img.size:
            score = rgba_similarity(img, ref)
        else:
            if ref.width >= img.width and ref.height >= img.height:
                for y in range(ref.height - img.height + 1):
                    for x in range(ref.width - img.width + 1):
                        crop = ref.crop((x, y, x + img.width, y + img.height))
                        score = max(score, rgba_similarity(img, crop))
            scaled = ref.resize(img.size, Image.Resampling.NEAREST)
            score = max(score, rgba_similarity(img, scaled))
        if score > best_score:
            best_score = score
            best_name = name
    return best_score, best_name


def reference_names(asset: dict) -> list[str]:
    """Collect unique full-library basenames (without .png) from a source table."""
    names: list[str] = []
    for rec in asset["source_table"]:
        for token in rec["reference"].replace(" + ", " / ").replace("+", " / ").replace("/", " / ").split(" / "):
            token = token.strip()
            if not token:
                continue
            base = token.rsplit(".", 1)[0].split(" ")[-1].strip("()")
            if base and base not in names:
                names.append(base)
    return names


def ref_label(name: str | None) -> str:
    """Human-readable reference name, adding .png when it was stripped."""
    if not name:
        return "无"
    return name if name.endswith(".png") else name + ".png"


def asset_ref(name: str) -> dict:
    """A convenience reference descriptor used in prompts and READMEs."""
    return {
        "name": name,
        "path": f"assets/minecraft/textures/{name.rsplit('.', 1)[0].replace('_', '/')}.png",
        "md5": MD5.get(name, "?"),
    }


# ---------------------------------------------------------------------------
# Hand-written concept cards / part-level reference tables
# ---------------------------------------------------------------------------

ASSETS = [
    {
        "slug": "villager_hide",
        "name": "村民皮 (Villager Hide)",
        "query": "村民皮：新物品，不是原版 villager 皮肤，也不是 leather 复制品",
        "form": "item",
        "size": (16, 16),
        "description": (
            "一张被剥下并鞣制的村民皮/兽皮，作为自定义采集材料和掉落物；"
            "主体是一块折叠/铺开的皮革，带折痕、颗粒、接缝，边缘露出灰褐色村民长袍织物带与缝线。"
        ),
        "parts": ["皮面主体 leather hide", "折痕/接缝 seams", "织物内衬 village cloth trim", "挂环/标签 hanger tag"],
                "source_table": [
            {"part": "皮面主体", "reference": "leather.png", "borrowed_texture": "皮革颗粒、折痕高光、不规则剥制边缘", "borrowed_palette": {"base": "#C65C35", "light": "#D76B43", "dark": "#542716", "accent": "#9E492A", "outline": "#3D1C10", "note": "皮革棕：主色暖橙棕，亮部偏橙，暗部深红棕，边缘用深褐描边。"}, "borrowed_structure": "16x16 中央皮面主体、边缘包边、自然折痕", "not_borrow": "不借 leather.png 的物品外形/具体排布"},
            {"part": "织物内衬", "reference": "villager.png", "borrowed_texture": "村民长袍布料层叠、缝线针脚质感", "borrowed_palette": {"base": "#6F6D6A", "light": "#817D79", "dark": "#545353", "accent": "#636260", "outline": "#3D2D29", "note": "村民袍灰：低饱和暖灰，亮部稍浅，暗部深灰；缝线用更暗灰绿/深棕分隔。"}, "borrowed_structure": "皮面下缘/内侧的窄条织物与 1px 缝线", "not_borrow": "不借村民头部/脸/身体/手臂形状，不把整张图画成村民皮肤"},
            {"part": "挂环/标签", "reference": "stick.png / iron_sword.png", "borrowed_texture": "深色小环/木质小节颗粒", "borrowed_palette": {"base": "#493615", "light": "#896727", "dark": "#281E0B", "accent": "#684E1E", "outline": "#281E0B", "note": "挂环用暗棕木色：主色深棕，亮部木褐，暗部近黑；避免与皮面主色混同。"}, "borrowed_structure": "上缘 2-3px 小环或木牌", "not_borrow": "不借棍/剑形状"},
        ],
        "palette": {
            "base": "#C65C35", "light": "#D76B43", "dark": "#542716",
            "accent": "#6F6D6A", "outline": "#3D1C10",
            "border_note": "外轮廓 1px 深褐；皮革与织物内衬用暗色缝隙分隔，不做均匀黑框。",
            "saturation_note": "整体保持中低饱和，皮革棕不荧光；灰褐织物作为次色。",
        },
        "shape": {
            "silhouette": "16x16 透明 item：一块折叠/铺开的方形皮革，中央有 1-2px 纵向或斜向折痕/褶皱高光，边缘有深色皮革包边；下缘/内侧露出窄条灰褐织物与 1px 缝线，上方有小挂环；整体居中，四边至少 1px 透明。",
            "orientation": "主方向为纵向（皮革主体在中央，织物内衬在下/侧），挂环朝上；所有部件沿同一中轴。",
            "part_pattern_flow": [
                {"part": "皮面主体", "shape": "折叠方形皮革（不是脸/面具）", "pattern": "皮革颗粒 + 1-2px 折痕高光 + 边缘深色包边", "flow": "折痕与高光沿皮面自然起伏走，不形成眼睛/鼻子/嘴巴；边缘用 1px 深褐描边。"},
                {"part": "织物内衬", "shape": "皮面下缘/内侧的窄条织物", "pattern": "灰褐色布料 + 1px 缝线/针脚", "flow": "缝线沿织物条边缘走；布料与皮革之间留暗色接缝，不用黑色粗框。"},
                {"part": "挂环/标签", "shape": "上缘 2-3px 小环或木牌", "pattern": "深色小节 + 1px 高光", "flow": "挂环与皮面连接自然，不悬空；单独看仍能识别为掉落物。",},
            ],
        },
        "avoid": [
            "不要复制原版 leather.png 或 villager.png 的逐像素图案；",
            "不要画成 villager 的头/身体/手臂，也不要画成原版 leather 物品；",
            "不要出现眼睛/鼻孔/嘴等脸部五官；这不是面具，是皮料/皮革；",
            "主体必须能看出是一张皮/皮革，而不是普通棕色方块；",
            "保持 16x16 透明背景、四边至少 1px 透明边距。",
        ],
    },

    {
        "slug": "skinning_knife",
        "name": "剥皮小刀 (Skinning Knife)",
        "query": "剥皮小刀：新物品，不是原版 iron_sword 的复制品，也不是木棍/皮革靴",
        "form": "item",
        "size": (16, 16),
        "description": (
            "一把短柄剥皮/狩猎小刀：刀身短小、刀尖略微上翘，刀柄用皮革缠绕并露出木质芯；"
            "整体是新物品，不是原版 sword。"
        ),
        "parts": ["刀刃 blade", "护手/颈 guard", "刀柄 handle (leather wrap + wood core)"],
                "source_table": [
            {"part": "刀刃", "reference": "iron_sword.png", "borrowed_texture": "金属划痕、刃口高光、冷灰明暗体积", "borrowed_palette": {"base": "#BEBEBE", "light": "#FFFFFF", "dark": "#444444", "accent": "#D8D8D8", "outline": "#181818", "note": "钢铁灰：清冷灰阶，白高光只沿刃口/棱线出现，暗部用深灰；不使用棕色。"}, "borrowed_structure": "短小弯曲刀片（非长剑）、刃口高光沿刃线", "not_borrow": "不借 iron_sword 的斜向满画布剑形、不借整把剑的精确索引"},
            {"part": "护手/颈", "reference": "iron_sword.png / leather.png", "borrowed_texture": "深灰/深褐自然分隔", "borrowed_palette": {"base": "#444444", "light": "#6B6B6B", "dark": "#181818", "accent": "#3D1C10", "outline": "#181818", "note": "护手用深灰为主，局部深褐过渡到柄；不参与刀刃高光。"}, "borrowed_structure": "刀刃与刀柄之间的 1-2px 横向窄条", "not_borrow": "不借剑护手完整形状/原版剑柄"},
            {"part": "刀柄", "reference": "leather.png + stick.png / oak_planks.png", "borrowed_texture": "皮革缠绳 + 木芯颗粒", "borrowed_palette": {"base": "#9E492A", "light": "#C65C35", "dark": "#542716", "accent": "#896727", "outline": "#281E0B", "note": "刀柄皮革棕：主色中棕，亮部橙棕，暗部深红棕；木芯用深褐/木纹黄棕点缀。"}, "borrowed_structure": "1-2px 宽短柄、缠绳横向、木纹纵向", "not_borrow": "不借 leather/stick 单独物品形状，不复制皮革/木棍像素"},
        ],
        "palette": {
            "base": "#BEBEBE", "light": "#FFFFFF", "dark": "#444444",
            "accent": "#896727", "outline": "#181818",
            "border_note": "刀刃外轮廓 1px 深灰；刀柄用深褐描边；刃与柄之间用暗色护手分隔。",
            "saturation_note": "金属保持冷灰，刀柄为暖棕；两种材质用明度/色相自然区分，不做荧光。",
        },
        "shape": {
            "silhouette": "16x16 透明 item：短刀居中，刀尖朝上/右上，刀刃占上 2/3，护手 1-2px，刀柄占下 1/3；四周至少 1px 透明边距，禁止贴边。",
            "orientation": "主方向为竖直/略斜的一条轴线；刀尖、刀刃、护手、刀柄沿同一轴线，连接点对齐，禁止手柄斜、刀刃正。",
            "part_pattern_flow": [
                {"part": "刀刃", "shape": "短小弯曲刀片（非长剑）", "pattern": "金属灰阶 + 1px 刃口高光 + 少量划痕", "flow": "高光沿刀刃弧度/刃线走；背光侧用深灰暗部；不出现原版剑的斜向满画布轮廓。"},
                {"part": "护手/颈", "shape": "刀刃与刀柄之间的 1-2px 窄条", "pattern": "深灰/深褐分隔", "flow": "护手沿横向包住柄根，连接处与主轴对齐。"},
                {"part": "刀柄", "shape": "1-2px 宽短柄", "pattern": "皮革缠绳 + 木芯颗粒", "flow": "缠绳线沿柄的横向环绕，木纹沿柄的纵向；左亮右暗表现圆柱体积。",},
            ],
        },
        "avoid": [
            "不要复制原版 iron_sword.png 的逐像素图案/斜向满画布构图；",
            "不要画成长剑/大剑：必须是小刀（刀刃长度约 6-9px，柄约 4-6px）；",
            "不要画成木棍/皮革靴；刀柄必须有皮革+木的复合感；",
            "保持透明边距，至少 1px，不贴边。",
        ],
    },
    {
        "slug": "skeleton_staff",
        "name": "骷髅法杖 (Skeleton Staff)",
        "query": "骷髅法杖：新物品，不是原版 skeleton，也不是 wand/blaze_rod 的复制品",
        "form": "item",
        "size": (16, 16),
        "description": (
            "一根顶端镶着骷髅头的新法杖/权杖：上方是骨白色、带深色眼窝的骷髅头，"
            "下方是木质杖身/握柄；整体是“法杖”而不是骷髅怪物。"
        ),
        "parts": ["骷髅头 skull top", "眼窝/裂纹 eye sockets + cracks", "杖身/握柄 wooden shaft"],
                "source_table": [
            {"part": "骷髅头/眼窝", "reference": "skeleton.png (head region) + bone_block_side.png", "borrowed_texture": "骨白底、深色眼窝、骨裂纹/凹槽质感", "borrowed_palette": {"base": "#E9E6D4", "light": "#FFFFFD", "dark": "#CBC6A5", "accent": "#DBD8C6", "outline": "#2E2E2E", "note": "骨白/骨灰：米白底，亮部近纯白，暗部暖灰；眼窝用深灰/黑灰，不出现彩度。"}, "borrowed_structure": "杖顶骨白头骨、眼窝位于中上部、左右对称", "not_borrow": "不借 skeleton 全身/动画/武器，不复制骨架纹理；只取头部语义"},
            {"part": "连接插座", "reference": "bone_block_side.png / stick.png", "borrowed_texture": "暗色小口/环、骨质接缝", "borrowed_palette": {"base": "#7B7E6B", "light": "#CBC6A5", "dark": "#494949", "accent": "#493615", "outline": "#2E2E2E", "note": "连接口用骨灰/深灰绿过渡，少量深褐木色，避免与骷髅头同色糊在一起。"}, "borrowed_structure": "骷髅头下的 1-2px 暗色小口/环", "not_borrow": "不借方块/骨头物品外形"},
            {"part": "杖身/握柄", "reference": "stick.png / oak_planks.png", "borrowed_texture": "木纹纵向、少量磨损颗粒", "borrowed_palette": {"base": "#493615", "light": "#896727", "dark": "#281E0B", "accent": "#684E1E", "outline": "#281E0B", "note": "木柄棕：主色深棕，亮部木褐，暗部近黑；亮木纹沿纵向走，不与骨白混用。"}, "borrowed_structure": "1-2px 宽木杖、底部可加粗握柄", "not_borrow": "不借木棍单独物品、不借剑/火炬形状"},
        ],
        "palette": {
            "base": "#E9E6D4", "light": "#FFFFFD", "dark": "#CBC6A5",
            "accent": "#896727", "outline": "#2E2E2E",
            "border_note": "骷髅外轮廓 1px 深灰 #2E2E2E；杖身用深褐描边；头与杖连接处用暗色插座分隔。",
            "saturation_note": "骨白保持低饱和、偏暖；木柄为暗棕；避免荧光白/荧光青。",
        },
        "shape": {
            "silhouette": "16x16 透明 item：竖直法杖，顶部约 4-7px 为骷髅头（有眼窝/下颌暗示），中间为 1-2px 宽木杖，底部为握柄/尾端；整体居中，四边至少 1px 透明。",
            "orientation": "主方向为竖直（可略带 1-2px 斜度：顶部在右上、底部在左下），沿一条连续轴线；骷髅头锚定在杖顶端，不可偏心。",
            "part_pattern_flow": [
                {"part": "骷髅头", "shape": "圆/方形骨白头骨，眼窝深色、鼻洞/裂纹", "pattern": "骨白底 + 深色眼窝 + 1px 裂纹", "flow": "眼窝位于头骨中上部，左右对称但允许 1px 不对称；裂纹沿骨面自然走，不画成完整骨架。"},
                {"part": "连接插座", "shape": "骷髅头下的 1-2px 暗色小口/环", "pattern": "深灰/深褐", "flow": "插座包住杖顶端，与头骨底边对齐。"},
                {"part": "杖身/握柄", "shape": "1-2px 宽木杖，底部可加粗", "pattern": "木纹纵向 + 少量磨损", "flow": "木纹沿杖身纵向；底端为握柄加粗段，与主轴对齐。",},
            ],
        },
        "avoid": [
            "不要复制原版 skeleton.png / bone_block_side.png / stick.png 的逐像素图案；",
            "不要画成完整骷髅或骷髅骑士；",
            "不要画成普通木棍/火把：顶部必须有明显骷髅头；",
            "保持 16x16 透明背景、四边至少 1px 透明边距。",
        ],
    },
    {
        "slug": "demon_cow",
        "name": "恶魔牛 (Demon Cow)",
        "query": "恶魔牛：新物品图标，不是原版 cow/red_mooshroom 的复制品",
        "form": "item",
        "size": (16, 16),
        "description": (
            "一个恶魔化牛头/牛图标：正面牛头，红色恶魔皮肤，黑色角/眼窝，"
            "眼睛和角尖带青色魂火；保留牛/红魔菌牛的剪影语义，但整体是新物品图标。"
        ),
        "parts": ["牛头 head", "双角 horns", "耳朵 ears", "魂火眼睛/角尖 soul-fire accents", "鼻口 muzzle/neck"],
                "source_table": [
            {"part": "牛头", "reference": "cow.png / red_mooshroom.png", "borrowed_texture": "红黑皮肤、鼻梁高光、脸颊暗部", "borrowed_palette": {"base": "#A00F10", "light": "#E04A45", "dark": "#3A0708", "accent": "#940E0F", "outline": "#171414", "note": "恶魔牛红：主体暗红，亮部红棕高光，暗部黑红；不使用原版普通棕色牛配色。"}, "borrowed_structure": "正面牛头剪影、鼻梁纵向、脸颊两侧暗面", "not_borrow": "不借整张 64x32 牛皮肤、不复制原版牛头像素"},
            {"part": "双角/耳朵", "reference": "cow.png / red_mooshroom.png", "borrowed_texture": "黑色角/深红耳、角尖可发魂火", "borrowed_palette": {"base": "#2B0505", "light": "#5A0A0B", "dark": "#171414", "accent": "#A00F10", "outline": "#171414", "note": "角/耳深黑红：比身体更暗，仅用暗红/黑红；不加入青色主色。"}, "borrowed_structure": "顶部双角、两侧耳朵", "not_borrow": "不借原版角/耳具体像素"},
            {"part": "眼睛/鼻口", "reference": "red_mooshroom.png + soul_fire_0.png", "borrowed_texture": "黑色眼窝 + 青色魂火 + 暗红鼻口", "borrowed_palette": {"base": "#01A7AC", "light": "#FFFFFF", "dark": "#018488", "accent": "#00D5DA", "outline": "#171414", "note": "魂火青：眼窝内青色发光，亮部白色核心，暗部青蓝；鼻口仍用暗红/黑红，不整体变青。"}, "borrowed_structure": "两眼左右对称、鼻口在下方", "not_borrow": "不复制整张 soul_fire 火焰贴图"},
        ],
        "palette": {
            "base": "#A00F10", "light": "#E04A45", "dark": "#3A0708",
            "accent": "#01A7AC", "outline": "#171414",
            "border_note": "外轮廓 1px 深黑红 #171414；角/眼窝用更深 #2B0505；魂火用青色高光与白色核心。",
            "saturation_note": "红色保持暗红色相，不荧光；青色只作局部魂火，占比小。",
        },
        "shape": {
            "silhouette": "16x16 透明 item：正面牛头剪影居中，双角向上/两侧，耳朵在两侧，眼睛为青色发光点，鼻口在下方；整体居中，四边至少 1px 透明。",
            "orientation": "主方向为竖直对称中轴；双角、耳朵、眼睛、鼻口沿中轴左右对称（允许 1px 不对称），连接点自然。",
            "part_pattern_flow": [
                {"part": "牛头", "shape": "正面牛头/脸", "pattern": "暗红底 + 中央鼻梁高光 + 两侧暗部", "flow": "高光沿鼻梁纵向，暗部在脸颊两侧；不画成整张侧视牛。"},
                {"part": "双角/耳朵", "shape": "顶部双角 + 两侧耳朵", "pattern": "黑色/深黑红角 + 耳朵暗红", "flow": "角尖可带 1px 青色魂火；耳朵与头连接自然，不悬空。"},
                {"part": "眼睛/鼻口", "shape": "两个青色发光眼 + 下方鼻口", "pattern": "青色魂火眼 + 黑色眼窝 + 暗红鼻口", "flow": "眼睛位于脸部中上部，左右对称；鼻口在下方，有暗色鼻孔。",},
            ],
        },
        "avoid": [
            "不要复制原版 cow.png / red_mooshroom.png / soul_fire_0.png 的逐像素图案；",
            "不要画成完整牛身体/侧视图：这是正面牛头图标；",
            "不要画成普通红牛：必须有黑色角/眼窝与青色魂火点缀；",
            "保持 16x16 透明背景、四边至少 1px 透明边距。",
        ],
    }

]


def _palette_summary(p: dict) -> str:
    return "base=%s light=%s dark=%s accent=%s outline=%s" % (
        p.get("base", "?"), p.get("light", "?"), p.get("dark", "?"),
        p.get("accent", "?"), p.get("outline", "?"))


def format_source_table(asset: dict) -> str:
    lines = ["### 部件级参考映射（借语法、不借整件）", ""]
    lines.append("| 部件 | 参考原版资产 | borrowed_texture | borrowed_palette | borrowed_structure | 不借什么 |")
    lines.append("|---|---|---|---|---|---|")
    for rec in asset["source_table"]:
        lines.append(
            "| %s | %s | %s | %s | %s | %s |" % (
                rec["part"], rec["reference"], rec["borrowed_texture"],
                _palette_summary(rec["borrowed_palette"]), rec["borrowed_structure"],
                rec["not_borrow"],
            )
        )
    lines.append("")
    lines.append("### 部件配色卡（palette 按部件拆，不能全图用一个全局调色板）")
    lines.append("")
    for rec in asset["source_table"]:
        p = rec["borrowed_palette"]
        lines.append("- %s：%s" % (rec["part"], _palette_summary(p)))
        if p.get("note"):
            lines.append("  - 说明：%s" % p["note"])
    lines.append("")
    lines.append("> 每个部件只借用参考资产的“这部分语法”（配色/材质/结构/明暗），整体是新物品，不是任何一件原版资产。")
    lines.append("> 禁止逐像素复制任何原版贴图，尤其避免复制索引网格。")
    return "\n".join(lines)


def build_prompt(asset: dict) -> str:
    name = asset["name"]
    form = asset["form"]
    w, h = asset["size"]
    lines: list[str] = []
    lines.append("# 任务说明")
    lines.append(f"请生成一个全新的 Minecraft 像素资源：{name}")
    lines.append(f"- 形式：{form}")
    lines.append(f"- 尺寸：{w}x{h}")
    lines.append("")
    lines.append("# 本体硬约束（最重要）")
    lines.append(f"- 必须生成「{asset['query']}」这个物体本身；参考节点不能改变主体类别、形状或语义。")
    lines.append("- 参考节点只允许借用配色、材质、明暗、尺度与局部图案；与语义冲突时忽略其形状与语义。")
    lines.append("")
    if form == "item":
        lines.append("# 形式硬约束（item：16x16 透明物品贴图）")
        lines.append("- 这是 16x16 透明背景物品贴图；主体居中、四周保留至少 1px 透明边距，禁止铺满到边缘。")
    elif form == "entity_uv":
        lines.append("# 形式硬约束（entity_uv：标准 64x32 atlas，不是单个侧视图）")
        lines.append("- 这不是单个侧视图，也不是一张自由构图画布；必须按牛/红魔菌牛的 64x32 atlas 区域坐标逐块展开像素（头/身/腿），左侧由渲染器镜像。")
        lines.append("- 每个区域按语义填：头/身/腿等各画自己的内容；区域外可为透明/底色，区域内不能留空。")
        lines.append("- Java 资源包只能替换原版实体贴图路径，原版模型硬编码；请输出可被 64x32 实体模型采样的 atlas。")
    lines.append("")
    lines.append(f"# 设计描述（先理解，再生成）")
    lines.append(f"- 名称：{name}")
    lines.append(f"- 描述：{asset['description']}")
    lines.append(f"- 部件：{'；'.join(asset['parts'])}")
    lines.append("")
    lines.append(format_source_table(asset))
    lines.append("")
    lines.append("### 全局参考色（仅作为整体风格兜底，不是最终调色板）")
    lines.append("> 重要：配色必须按部件拆。每个部件的配色以“## 部件配色卡 / borrowed_palette”为准，不能把下面这个全局色当成整图统一调色板。")
    ps = asset["palette"]
    lines.append(f"- 全局参考：base: {ps['base']}  light: {ps['light']}  dark: {ps['dark']}  accent: {ps['accent']}  outline: {ps['outline']}")
    lines.append(f"- 自然边框说明：{ps['border_note']}")
    lines.append(f"- 饱和度说明：{ps['saturation_note']}")
    lines.append("")
    sp = asset["shape"]
    lines.append("### 形状/构图")
    lines.append(f"- 剪影：{sp['silhouette']}")
    lines.append(f"- 方位/构图：{sp['orientation']}")
    lines.append("- 形状-纹样一体：")
    for ppf in sp["part_pattern_flow"]:
        lines.append(f"  - [{ppf['part']}] 形状：{ppf['shape']} | 纹样：{ppf['pattern']} | 走向：{ppf['flow']}")
    lines.append("")
    lines.append("### 避免")
    for a in asset["avoid"]:
        lines.append(f"- {a}")
    lines.append("")
    lines.append("# 通用设计原则（每个物体都适用）")
    for rule in cg.GENERIC_DESIGN_PRINCIPLES:
        lines.append(f"- {rule}")
    lines.append("")
    lines.append("# 通用像素细节（每个物体都适用）")
    for rule in cg.GENERIC_PIXEL_DETAIL_RULES:
        lines.append(f"- {rule}")
    lines.append("")
    lines.append("# 输出格式（PALETTE + INDEX GRID，-1 表示透明）")
    lines.append("- 设计分析（可省略）必须用 `# ` 开头；正式数据的第一行必须是 `W={w} H={h}`。")
    lines.append("- 然后输出 PALETTE 块与完整的 INDEX GRID。")
    lines.append("- INDEX GRID 共 %d 行，每行 %d 个整数；-1=透明，非负整数引用 PALETTE；非 -1 像素必须 >= %d。禁止全 -1 空图。" % (
        h, w, h if form == "entity_uv" else 40))
    lines.append("- 禁止输出解释性文字、Markdown 代码围栏、JSON 或额外的 face 标题/`=== face:` 标记。")
    lines.append("- 必须生成新的形状/图案/调色板：不得复制任何参考贴图（特别是原版 compact 索引网格）。")
    lines.append("")
    lines.append("```")
    lines.append(f"W={w} H={h}")
    lines.append("PALETTE")
    lines.append("0: #000000")
    lines.append("...")
    lines.append("INDEX GRID")
    lines.append("-1 -1 ... (H lines, each with W integers)")
    lines.append("```")
    return "\n".join(lines)


def write_concept_json(asset: dict, out: Path) -> None:
    refs = []
    for rec in asset["source_table"]:
        refs.append({
            "part": rec["part"],
            "reference": rec["reference"],
            "borrowed_texture": rec["borrowed_texture"],
            "borrowed_palette": rec["borrowed_palette"],
            "borrowed_structure": rec["borrowed_structure"],
            "not_borrow": rec["not_borrow"],
        })
    concept = {
        "item_name": asset["name"],
        "query": asset["query"],
        "form": asset["form"],
        "size": "%dx%d" % asset["size"],
        "description": asset["description"],
        "parts": asset["parts"],
        "source_table": refs,
        "palette_scheme": asset["palette"],
        "shape_pattern": asset["shape"],
        "method": "manual_part_level_concept_card + llm_client + text_to_texture",
        "novelty": 0.75,
        "avoid": asset["avoid"],
    }
    # Build a simple mapping from clean asset basename to md5.
    hash_map = {}
    for rec in asset["source_table"]:
        for token in rec["reference"].replace(" + ", " / ").replace("+", " / ").replace("/", " / ").split(" / "):
            token = token.strip()
            if not token:
                continue
            base = token.rsplit(".", 1)[0].split(" ")[-1].strip("()")
            if base in MD5:
                hash_map[base] = MD5[base]
    concept["reference_hashes"] = hash_map
    out.write_text(json.dumps(concept, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_llm_raw(text: str) -> str:
    """Remove Markdown code fences and turn pre-W/H design prose into comments
    so text_to_texture can find the W/H header reliably."""
    import re as _re
    lines = text.splitlines()
    # Remove code-fence lines (```, ```text, ```json, ...)
    lines = [ln for ln in lines if not ln.strip().startswith("```")]
    # Locate the first real W/H header.
    header_idx = None
    for i, ln in enumerate(lines):
        if _re.match(r"^\s*W\s*=\s*\d+\s+H\s*=\s*\d+\s*$", ln.strip()):
            header_idx = i
            break
    if header_idx is not None:
        for i in range(header_idx):
            stripped = lines[i].strip()
            if stripped and not stripped.startswith("#"):
                lines[i] = "# " + stripped
    return "\n".join(lines).strip()


def ensure_item_margin(img, min_margin: int = 1):
    """Minimal postprocess for 16x16 item sprites: clear an edge row/column
    when the generated bbox touches the canvas, so the item keeps >=1px
    transparent margin on all sides.  This is structural cleanup, not content
    redrawing."""
    if img.size != (16, 16):
        return img
    px = img.load()
    for _ in range(8):
        bbox = img.getbbox()
        if bbox is None:
            return img
        left, top, right, bottom = bbox
        changed = False
        if top < min_margin:
            for x in range(img.width):
                px[x, top] = (0, 0, 0, 0)
            changed = True
        if left < min_margin:
            for y in range(img.height):
                px[left, y] = (0, 0, 0, 0)
            changed = True
        if right > img.width - min_margin:
            for y in range(img.height):
                px[right - 1, y] = (0, 0, 0, 0)
            changed = True
        if bottom > img.height - min_margin:
            for x in range(img.width):
                px[x, bottom - 1] = (0, 0, 0, 0)
            changed = True
        if not changed:
            break
    return img


def call_llm(prompt_path: Path) -> str:
    cmd = LLM_CMD.replace("{prompt_file}", str(prompt_path))
    proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError("LLM command failed (exit %d): %s" % (proc.returncode, proc.stderr.strip()[:500]))
    return proc.stdout.strip()


def run_asset(asset: dict) -> Path:
    slug = asset["slug"]
    out = DEMO_DIR / slug
    out.mkdir(parents=True, exist_ok=True)
    prompt = build_prompt(asset)
    prompt_path = out / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    print(f"[{slug}] prompt written ({len(prompt)} chars)", flush=True)

    raw_text = ""
    attempts = 0
    last_error = ""
    refs = reference_names(asset)
    sim_records: list[dict] = []
    high_sim_retries = 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        attempts = attempt
        try:
            raw_text = call_llm(prompt_path)
            if not raw_text:
                raise RuntimeError("LLM returned empty answer")
            raw_text = clean_llm_raw(raw_text)
            img = t2t.text_to_image(raw_text)
            if img.size != tuple(asset["size"]):
                raise RuntimeError("parsed %dx%d, expected %dx%d" % (img.size[0], img.size[1], *asset["size"]))
            opaque = sum(1 for px in img.getdata() if px[3] >= t2t.ALPHA_THRESHOLD)
            if opaque == 0:
                raise RuntimeError("parsed image has 0 opaque pixels")

            # Lightweight original-index-grid similarity check.  Compare the
            # freshly parsed grid (before item-margin postprocessing) against
            # every full-library reference named in the concept card.
            sim_score, sim_ref = max_reference_similarity(img, refs)
            sim_records.append({
                "attempt": attempt,
                "similarity": round(sim_score, 4),
                "reference": sim_ref,
            })
            if sim_score >= SIMILARITY_THRESHOLD:
                high_sim_retries += 1
                raise RuntimeError(
                    "index grid similarity too high with `%s` (%.1f%% >= %.0f%%)"
                    % (sim_ref or "unknown", sim_score * 100, SIMILARITY_THRESHOLD * 100))

            # Save raw answer before writing PNG.
            (out / "raw_answer.txt").write_text(raw_text, encoding="utf-8")
            if asset["form"] == "item":
                img = ensure_item_margin(img)
            img.save(out / "sprite.png", "PNG")
            if asset["form"] == "entity_uv":
                preview = t2t.make_preview(img, 4)
                preview.save(out / "sprite_preview.png", "PNG")
            # Save audit hashes.
            hashes = {
                "prompt_sha256": sha256_text(prompt),
                "answer_sha256": sha256_text(raw_text),
                "png_sha256": hashlib.sha256((out / "sprite.png").read_bytes()).hexdigest(),
                "attempts": attempts,
                "novelty": 0.75,
                "postprocess": "item_margin_min_1" if asset["form"] == "item" else "none",
                "index_similarity": {
                    "threshold": SIMILARITY_THRESHOLD,
                    "max_score": round(sim_score, 4),
                    "max_reference": sim_ref,
                    "high_similarity_retries": high_sim_retries,
                    "checks": sim_records,
                },
            }
            (out / "hashes.json").write_text(json.dumps(hashes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            write_concept_json(asset, out / "concept.json")
            print(f"    -> saved sprite.png ({img.size[0]}x{img.size[1]}, opaque={opaque}, attempts={attempts})", flush=True)
            return out / "sprite.png"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            print(f"    -> attempt {attempt} failed: {last_error[:300]}", flush=True)
            if attempt < MAX_ATTEMPTS:
                # Keep prompt, retry the answer.
                continue
    raise RuntimeError(f"{slug} failed after {attempts} attempts: {last_error}")


def ref_md5_line(asset: dict) -> list[str]:
    lines = []
    for _, ref, borrow, no in asset["source_table"]:
        # Show the first (and second) referenced asset basenames with md5.
        parts = []
        for token in ref.split(" / "):
            base = token.strip().rsplit(".", 1)[0].split(" ")[-1].strip("()")
            md5 = MD5.get(base, "?")
            parts.append(f"`{base}.png` (md5 {md5})")
        lines.append(f"| {ref} | {parts[0] if parts else ref} | {borrow} | {no} |")
    return lines


def write_asset_readme(asset: dict, png_path: Path) -> Path:
    slug = asset["slug"]
    out = DEMO_DIR / slug
    lines = []
    lines.append(f"# {asset['name']}")
    lines.append("")
    lines.append(f"- 形式：`{asset['form']}`")
    lines.append(f"- 尺寸：`{asset['size'][0]}x{asset['size'][1]}`")
    lines.append(f"- 输出：`{png_path.name}`")
    lines.append(f"- novelty：`0.75`（部件级参考映射，禁逐像素复制）")
    lines.append("")
    lines.append("## 说明")
    lines.append(asset["description"])
    lines.append("")
    lines.append("## 部件级参考来源表")
    lines.append("")
    lines.append("| 部件 | 参考原版资产 | 原版参考 hash (md5) | borrowed_texture | borrowed_palette | borrowed_structure | 不借什么 |")
    lines.append("|---|---|---|---|---|---|---|")
    for rec in asset["source_table"]:
        ref = rec["reference"]
        md5s = []
        for token in ref.replace(" + ", " / ").replace("+", " / ").replace("/", " / ").split(" / "):
            token = token.strip()
            if not token:
                continue
            base = token.rsplit(".", 1)[0].split(" ")[-1].strip("()")
            md5 = MD5.get(base, "?")
            md5s.append(f"{base}.png={md5}")
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s |" % (
                rec["part"], ref, '<br>'.join(md5s), rec["borrowed_texture"],
                _palette_summary(rec["borrowed_palette"]), rec["borrowed_structure"],
                rec["not_borrow"],
            )
        )
    lines.append("")
    lines.append("> 参考来源均为本机 1.18.2 Java 完整库（full-index.json），原版 PNG 未复制进本仓库。")
    lines.append("")
    lines.append("## 部件配色卡（palette 按部件拆）")
    lines.append("")
    lines.append("| 部件 | 配色卡 | 说明 |")
    lines.append("|---|---|---|")
    for rec in asset["source_table"]:
        p = rec["borrowed_palette"]
        lines.append("| %s | %s | %s |" % (rec["part"], _palette_summary(p), p.get("note", "")))
    lines.append("")
    lines.append("## 生成命令")
    lines.append("```bash")
    lines.append("# 从仓库根目录运行；LLM key 从 /tmp/mc_llm.env 读取，不写入仓库。")
    lines.append("set -a; source /tmp/mc_llm.env; set +a")
    lines.append(f"python3 examples/novel-demo/demo_generate.py")
    lines.append("```")
    lines.append("")
    lines.append("## Hash")
    h = json.loads((out / "hashes.json").read_text(encoding="utf-8"))
    lines.append(f"- prompt sha256：`{h['prompt_sha256']}`")
    lines.append(f"- answer sha256：`{h['answer_sha256']}`")
    lines.append(f"- png sha256：`{h['png_sha256']}`")
    lines.append("")
    sim = h.get("index_similarity", {})
    lines.append("## 索引相似度检测")
    lines.append(f"- 阈值：`{sim.get('threshold', SIMILARITY_THRESHOLD)}`")
    lines.append(f"- 最高相似参考：`{ref_label(sim.get('max_reference'))}`（score `{sim.get('max_score', '?')}`）")
    lines.append(f"- 因高相似度重试次数：`{sim.get('high_similarity_retries', 0)}`")
    lines.append(f"- 检查记录：`{json.dumps(sim.get('checks', []), ensure_ascii=False)}`")
    check_path = out / "check_pixel_asset.json"
    if check_path.exists():
        check = json.loads(check_path.read_text(encoding="utf-8"))
        lines.append("")
        lines.append("## 像素自检（check_pixel_asset.py）")
        lines.append(f"- 结论：`{check.get('verdict', {}).get('overall', '?')}`")
        if check.get("verdict", {}).get("overall") == "FAIL":
            palette = check.get("metrics", {}).get("palette", {})
            lines.append(f"- 未通过项：`{palette.get('bright_count')}` 个亮色像素（`bright_count=0` 会判 FAIL），详见 `check_pixel_asset.json`。")
    lines.append("")
    out_readme = out / "README.md"
    out_readme.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_readme


def write_top_readme(results: list[tuple[dict, Path]]) -> Path:
    lines = [
        "# novel-demo：原版没有的新资产（部件级参考）",
        "",
        "本目录生成 4 个 Minecraft 原版没有的新资产演示。",
        "所有资产都使用“部件级参考映射”：每个部件只从指定原版资产借配色/材质/结构/明暗语法，",
        "不把任何一件原版资产当作整件答案。生成的 PNG 均为新资产，原版 PNG 未复制进本仓库。",
        "",
        "| 资产 | form | PNG | 参考摘要 |",
        "|---|---|---|---|",
    ]
    for asset, png in results:
        refs = "；".join(rec["reference"] for rec in asset["source_table"])
        lines.append(f"| {asset['name']} | `{asset['form']}` | `{png.relative_to(DEMO_DIR)}` | {refs} |")
    lines.append("")
    lines.append("## 防复制说明")
    lines.append("- 生成 prompt 不包含任何原版 compact 索引网格，仅含文字化源表、配色、部件结构和通用像素规则。")
    lines.append("- 每个部件参考卡包含三样：`borrowed_texture` / `borrowed_palette` / `borrowed_structure`；配色严格按部件拆分，不作为整图全局调色板。")
    lines.append("- novelty 固定 0.75；生成后会做轻量“原版索引网格相似度”检测（同尺寸逐格比对；大图用滑动窗口/最近邻缩放取最高分），超过阈值自动重试并记录在 `hashes.json` 的 `index_similarity`，脚本最多重试 2 次。")
    lines.append("- 原版参考 hash 在每个资产 README.md 中记录（full-index.json md5）。")
    lines.append("")
    lines.append("## 来源说明")
    lines.append("- 参考来源使用本机 `mc_asset_library_full/full-index.json`（1.18.2 Java 完整纹理库）的 md5。")
    lines.append("- `skeleton.png`/`villager.png` 在 115 小库内；`leather.png`、`soul_fire_0/1.png`、`bone_block_side.png` 等不在 115 小库内，已从 full 库检索补充并记录来源。")
    lines.append("- 原版 PNG 不复制进本仓库，README/JSON 只记录路径与 md5。")
    lines.append("")
    lines.append("## 复现命令")
    lines.append("```bash")
    lines.append("set -a; source /tmp/mc_llm.env; set +a")
    lines.append("python3 examples/novel-demo/demo_generate.py")
    lines.append("```")
    lines.append("")
    lines.append("## 像素自检（check_pixel_asset.py）")
    lines.append("")
    lines.append("| 资产 | 结论 | 说明 |")
    lines.append("|---|---|---|")
    for asset, png in results:
        check_path = DEMO_DIR / asset["slug"] / "check_pixel_asset.json"
        if not check_path.exists():
            lines.append(f"| {asset['name']} | 未生成 | 尚未运行 `check_pixel_asset.py` |")
            continue
        check = json.loads(check_path.read_text(encoding="utf-8"))
        verdict = check.get("verdict", {}).get("overall", "?")
        palette = check.get("metrics", {}).get("palette", {})
        note = ""
        if verdict == "FAIL":
            note = "调色板缺少亮色档（bright_count=%s）。" % palette.get("bright_count", "?")
        lines.append(f"| {asset['name']} | `{verdict}` | {note} |")
    lines.append("")
    lines.append("## 结果")
    for asset, png in results:
        h = json.loads((DEMO_DIR / asset["slug"] / "hashes.json").read_text(encoding="utf-8"))
        sim = h.get("index_similarity", {})
        lines.append(f"- {asset['name']}: `{png.relative_to(ROOT)}` （prompt {h['prompt_sha256']}，answer {h['answer_sha256']}，attempts {h['attempts']}，最高索引相似度 {sim.get('max_score', '?')}/{ref_label(sim.get('max_reference'))}）")
    lines.append("")
    top = DEMO_DIR / "README.md"
    top.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return top


def main() -> int:
    results = []
    for asset in ASSETS:
        print(f"\n=== {asset['name']} ===", flush=True)
        png = run_asset(asset)
        write_asset_readme(asset, png)
        results.append((asset, png))
    top = write_top_readme(results)
    print(f"\nAll done. Top-level README: {top}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
