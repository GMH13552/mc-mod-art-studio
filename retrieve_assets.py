#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
retrieve_assets.py — v2-retrieve: 自动检索与特征提取。

根据一句中文/英文想法，从用户本地扫描索引 / 兼容旧索引中检索 1-8 个锚点，
并输出结构化特征（形状/花纹/颜色/部位/吸引点）与形式判定。

数据源（三选一）
----------------
* ``--index <scan-index.json>``：使用 ``scan_mc_assets.py`` 生成的新格式索引（JSON 对象含 entries）。
* ``--mc-path <path>``：直接扫描 Minecraft/资源包路径，临时建立索引。
* 默认：兼容旧 ``mc_asset_library/library-index.json``（JSON 数组），仓库不强制包含该目录。

用法
----
    python3 retrieve_assets.py --query "蘑菇斧头" --index my_asset_index.json --out retrieval_examples/mushroom_axe.json
    python3 retrieve_assets.py --query "荧石蘑菇方块" --mc-path ~/.minecraft --top 3
    python3 retrieve_assets.py --query "异形水晶法杖" --out retrieval_examples/alien_crystal_wand.json
    python3 retrieve_assets.py --self-test

实现说明
--------
* 检索：内置中文→英文别名映射 + 英文关键词/路径词元匹配（离线可复现）。
* 语义：当前版本 method=rule；不依赖外部 LLM 子代理，因此每次运行结果稳定。
* 特征：Pillow 读取真实 PNG，提取 top colors；形状/花纹/部位/吸引点由
  名称语义 + 图像 alpha/色彩统计生成。
* 形式：按 query 关键词判定 item/block_multi/cross/entity_uv；--form 可强制覆盖。
* 自测：无 ``mc_asset_library/`` 时自动用 Pillow 生成合成小 PNG 索引，不依赖原版素材。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from collections import Counter, OrderedDict
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.stderr.write("ERROR: Pillow is required.  Install with:  pip install pillow\n")
    raise

_THIS_DIR = Path(__file__).resolve().parent
_INDEX_PATH = _THIS_DIR / "mc_asset_library" / "library-index.json"
_LOG_PATH = _THIS_DIR / "retrieve_log.txt"
_RETRIEVAL_DIR = _THIS_DIR / "retrieval_examples"

# ---------------------------------------------------------------------------
# 检索别名表：中文词 -> 英文关键词（精确 token 匹配优先，substring 作为降级）
# ---------------------------------------------------------------------------
ALIASES = OrderedDict(
    [
        ("蘑菇斧头", ["mushroom", "axe"]),  # 短语优先级，防止拆词损失“斧头”
        ("蘑菇", ["mushroom", "mooshroom"]),
        ("红蘑菇", ["red_mushroom"]),
        ("褐蘑菇", ["brown_mushroom"]),
        ("菌", ["mushroom"]),
        ("斧", ["axe"]),
        ("斧头", ["axe"]),
        ("镐", ["pickaxe"]),
        ("剑", ["sword"]),
        ("铲", ["shovel"]),
        ("锄", ["hoe"]),
        ("刀", ["sword"]),
        ("法杖", ["rod", "staff", "wand", "stick"]),
        ("杖", ["rod", "staff", "wand", "stick"]),
        ("棒", ["rod", "stick"]),
        ("魔法", ["blaze_rod", "ender_pearl", "golden_apple", "enchanted"]),
        ("水晶", ["crystal", "diamond", "quartz", "emerald", "lapis", "amethyst"]),
        ("宝石", ["diamond", "emerald", "lapis", "quartz"]),
        ("荧石", ["glowstone"]),
        ("发光", ["glowstone", "blaze", "glow", "lamp"]),
        ("灯", ["glowstone", "lamp"]),
        ("矿石", ["ore"]),
        ("矿", ["ore", "coal", "iron", "gold", "diamond", "emerald", "redstone", "lapis"]),
        ("砖", ["bricks", "brick"]),
        ("石", ["stone", "cobblestone", "sandstone", "obsidian", "end_stone"]),
        ("木", ["log", "planks", "wooden"]),
        ("树苗", ["sapling"]),
        ("花", ["flower", "rose", "tulip"]),
        ("虞美人", ["poppy"]),
        ("草", ["grass", "tall_grass"]),
        ("叶", ["leaves"]),
        ("羊毛", ["wool"]),
        ("玻璃", ["glass"]),
        ("沙", ["sand", "sandstone"]),
        ("泥土", ["dirt"]),
        ("生物", ["entity"]),
        ("实体", ["entity"]),
        ("皮肤", ["entity"]),
        ("怪物", ["creeper", "spider", "zombie", "skeleton"]),
        ("僵尸", ["zombie"]),
        ("骷髅", ["skeleton"]),
        ("蜘蛛", ["spider"]),
        ("苦力怕", ["creeper"]),
        ("猪", ["pig"]),
        ("牛", ["cow", "mooshroom"]),
        ("羊", ["sheep"]),
        ("鸡", ["chicken"]),
        ("村民", ["villager"]),
        ("马", ["horse"]),
        ("蜜蜂", ["bee"]),
        ("苹果", ["apple", "golden_apple"]),
        ("面包", ["bread"]),
        ("胡萝卜", ["carrot"]),
        ("土豆", ["potato"]),
        ("箭", ["arrow"]),
        ("弓", ["bow"]),
        ("眼球", ["ender_eye", "spider_eye"]),
        ("眼睛", ["ender_eye", "spider_eye", "phantom_eyes"]),
        ("眼", ["ender_eye", "spider_eye"]),
        ("恶魔", ["red_mooshroom", "netherite", "soul_fire", "wither"]),
        ("小刀", ["shears", "sword", "iron_sword"]),
        ("皮", ["leather", "rabbit_hide", "hide"]),
        ("皮革", ["leather"]),
        ("剥皮", ["shears", "sword", "knife"]),
        ("骨", ["bone", "skeleton", "skull"]),
        ("骨头", ["bone"]),
        ("线", ["string"]),
        ("珍珠", ["ender_pearl"]),
        ("铁", ["iron"]),
        ("金", ["gold", "golden"]),
        ("煤", ["coal", "charcoal"]),
        ("钻石", ["diamond"]),
        ("绿宝石", ["emerald"]),
        ("石英", ["quartz"]),
        ("红石", ["redstone"]),
        ("青金石", ["lapis"]),
        ("下界", ["netherite", "netherrack", "blaze"]),
        ("烈焰", ["blaze"]),
        ("末影", ["ender"]),
        ("危险", ["creeper", "spider", "zombie", "skeleton", "blaze"]),
        ("可爱", ["pig", "axolotl", "bee", "mushroom"]),
        ("眼睛", ["eye", "spider", "creeper", "ender"]),
    ]
)

# 中英文形式关键词
_FORM_KEYWORDS = {
    "item": ["异形", "水晶", "法杖", "杖", "非方块", "自定义", "物品", "武器", "工具",
             "装备", "剑", "斧", "镐", "铲", "盾", "弓", "箭", "食物", "苹果", "棒"],
    "block_multi": ["方块", "块", "矿石", "矿", "砖", "石", "木", "泥土", "玻璃",
                    "羊毛", "灯", "蘑菇块"],
    "cross": ["树苗", "花", "草", "植物", "花盆"],
    "entity_uv": ["生物", "皮肤", "实体", "怪物", "僵尸", "骷髅", "蜘蛛", "苦力怕",
                  "猪", "牛", "羊", "村民", "马", "蜜蜂", "鸡", "鱿鱼"],
}

# 形状关键词（用于特征/角色）
_SHAPE_KEYWORDS = [
    "axe", "sword", "pickaxe", "shovel", "hoe", "rod", "staff", "wand", "stick",
    "boat", "arrow", "bone", "sapling", "helmet", "chestplate", "leggings", "boots",
]
_PATTERN_KEYWORDS = [
    "mushroom_block", "brick", "planks", "log", "leaves", "grass", "cobblestone",
    "sandstone", "ore", "stone_bricks", "mossy", "wool", "glass", "cactus", "dirt",
]
_COLOR_KEYWORDS = [
    "diamond", "emerald", "glowstone", "redstone", "lapis", "gold", "iron", "coal",
    "quartz", "red_mushroom", "brown_mushroom", "bedrock", "obsidian", "concrete",
]
_ATTRACTION_KEYWORDS = [
    "creeper", "spider", "zombie", "skeleton", "ender_pearl", "blaze",
    "golden_apple", "axolotl",
]

# 形状/零件/吸引点中文标签
_NAME_SHAPE_MAP = {
    "axe": "斧头", "pickaxe": "镐", "sword": "剑", "shovel": "铲", "hoe": "锄",
    "rod": "长条/杖", "staff": "长条/杖", "wand": "长条/杖", "stick": "长条/木棍",
    "boat": "船形", "arrow": "箭", "bone": "骨形", "sapling": "树苗/十字",
    "poppy": "花/十字", "bow": "弯月/弓形",
    "diamond": "菱形/晶体", "emerald": "菱形/晶体", "quartz": "晶体",
    "ender_pearl": "圆珠", "apple": "圆形/苹果", "bread": "面包形",
    "helmet": "头盔形", "chestplate": "胸甲形", "leggings": "护腿形", "boots": "靴形",
    "glowstone": "发光颗粒/方块", "mushroom_block": "蘑菇方块", "mushroom": "蘑菇伞",
}
_NAME_PATTERN_MAP = {
    "mushroom_block": "菌盖斑点/菌褶", "red_mushroom": "红色伞盖+白点",
    "brown_mushroom": "褐色伞盖", "bricks": "砖缝条纹", "planks": "木板条纹",
    "log": "树皮纹理/年轮", "leaves": "树叶孔洞/网点", "grass_block": "草皮混合",
    "wool": "织物纹理", "ore": "矿点散布", "cobblestone": "石头拼接",
    "sandstone": "沙岩条纹", "glass": "透明/边框", "glowstone": "发光颗粒",
}
_NAME_PART_MAP = {
    "axe": ["斧刃/头", "柄"], "pickaxe": ["镐头", "柄"], "sword": ["剑刃", "护手", "柄"],
    "shovel": ["铲头", "柄"], "hoe": ["锄头", "柄"], "rod": ["杖身"],
    "staff": ["杖身"], "wand": ["杖身"], "stick": ["棍身"],
    "boat": ["船体"], "helmet": ["头盔"], "chestplate": ["胸甲"],
    "leggings": ["护腿"], "boots": ["靴子"], "sapling": ["树干", "树叶"],
    "poppy": ["花头", "茎叶"], "bow": ["弓臂", "弦"],
    "mushroom": ["菌盖", "菌柄"], "diamond": ["晶体主体"], "emerald": ["晶体主体"],
    "ore": ["矿石底材", "矿物颗粒"], "glowstone": ["发光颗粒"],
}
_NAME_ATTRACTION_MAP = {
    "glowstone": ["发光"], "diamond": ["闪亮/晶体"], "emerald": ["闪亮/晶体"],
    "quartz": ["闪亮/晶体"], "lapis": ["闪亮/晶体"], "golden_apple": ["发光/珍贵"],
    "ender_pearl": ["魔法/神秘"], "blaze_rod": ["火焰/魔法"],
    "creeper": ["危险/诡异"], "spider": ["危险/诡异"], "zombie": ["危险/诡异"],
    "skeleton": ["危险/诡异"], "red_mushroom": ["鲜艳/可爱"], "brown_mushroom": ["大地色"],
    "axolotl": ["可爱"], "bee": ["可爱"],
}


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

def load_index_with_base(index_path: Path = _INDEX_PATH) -> tuple[list[dict], Path]:
    """
    读取索引，返回 ``(entries, base_dir)``。

    * 旧格式：JSON 数组（兼容 ``mc_asset_library/library-index.json``）。
      ``base_dir`` 取索引文件所在目录。
    * 新格式：JSON 对象含 ``entries`` 列表；``base_dir`` 优先取对象里的
      ``base_dir``，否则取索引文件所在目录。
    """
    from asset_to_text import normalize_path  # 复用已有 Windows/WSL 路径归一化
    index_path = normalize_path(index_path).expanduser().resolve()
    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    base_dir = index_path.parent
    if isinstance(data, list):
        return data, base_dir
    if isinstance(data, dict) and isinstance(data.get("entries"), list):
        raw_base = data.get("base_dir")
        if raw_base:
            base_dir = normalize_path(raw_base).expanduser().resolve()
        return data["entries"], base_dir
    raise ValueError(
        "index file must be a JSON array (old format) or an object with 'entries' list (scan format): %s"
        % index_path
    )


def load_index(index_path: Path = _INDEX_PATH) -> list[dict]:
    """读取索引 entries。兼容旧数组格式与新扫描对象格式。"""
    return load_index_with_base(index_path)[0]


def resolve_entry_path(entry: dict, base_dir: Path | str | None = None) -> Path:
    """把 index 中的 path 解析为真实文件路径。

    * ``entry["path"]`` 是绝对路径时直接使用。
    * 相对路径时，优先用 ``base_dir``，否则用旧默认库目录。
    """
    from asset_to_text import normalize_path  # 复用已有 Windows/WSL 路径归一化
    p = normalize_path(entry["path"])
    if not p.is_absolute():
        if base_dir is not None:
            base = normalize_path(base_dir).expanduser().resolve()
        else:
            base = _INDEX_PATH.parent
        p = base / p
    return p.resolve()


def _path_tokens(entry: dict) -> set[str]:
    """提取 name/path 的英文词元集合。"""
    text = "%s %s %s" % (
        str(entry.get("name", "")),
        str(entry.get("path", "")),
        str(entry.get("category", "")),
    )
    return {t for t in re.split(r"[^A-Za-z0-9]+", text.lower()) if t}


def _query_terms(query: str) -> tuple[set[str], set[str]]:
    """
    返回 (英文检索词集, 中文原词集)。
    中文别名按最长匹配优先展开；英文 query 也按词元加入。
    """
    zh_terms = set()
    en_terms = set()
    # 1) 中文别名：按词条长度降序扫描，避免“红蘑菇”被拆成“蘑菇”后丢失红色语义
    matched_zones = [False] * len(query)
    for zh, engs in sorted(ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        start = 0
        while True:
            idx = query.find(zh, start)
            if idx < 0:
                break
            # 完全落在已匹配区域内的子词条跳过（例如“荧石”里的“石”），避免泛化误命中
            if all(matched_zones[idx:idx + len(zh)]):
                start = idx + len(zh)
                continue
            zh_terms.add(zh)
            en_terms.update(engs)
            for i in range(idx, idx + len(zh)):
                matched_zones[i] = True
            start = idx + len(zh)
    # 2) 英文/数字词元
    en_terms.update(w for w in re.findall(r"[A-Za-z]+", query.lower()))
    # 3) 未匹配中文片段（简短单字也可能有语义，但避免把“头”单独当检索词）
    return en_terms, zh_terms


def _category_intent(query: str) -> str | None:
    """根据 query 推断期望的资产类别：item/block/entity。"""
    q = query.lower()
    if any(k in q for k in ("生物", "皮肤", "实体", "怪物", "entity", "mob")):
        return "entity"
    if any(k in q for k in ("方块", "块", "矿石", "矿", "block", "ore", "brick", "stone", "木", "玻璃")):
        return "block"
    if any(k in q for k in ("物品", "武器", "工具", "装备", "法杖", "剑", "斧", "镐", "item", "tool", "weapon", "staff", "sword", "axe", "pickaxe")):
        return "item"
    return None


def _score_entry(entry: dict, en_terms: set[str], zh_terms: set[str], cat_intent: str | None) -> tuple[int, list[str]]:
    """返回 (score, matched_english_terms)。"""
    tokens = _path_tokens(entry)
    name_lower = str(entry.get("name", "")).lower()
    path_lower = str(entry.get("path", "")).lower()
    score = 0
    matched: list[str] = []
    for term in en_terms:
        if not term:
            continue
        if term in tokens:
            score += 3
            matched.append(term)
        elif term in name_lower or term in path_lower:
            score += 1
            matched.append(term)
    # category 意图加权
    if cat_intent:
        if entry.get("category") == cat_intent:
            score += 2
        # 查询含“方块”时，优先名称里显式含 block 的贴图（如 *_block.png）
        if cat_intent == "block" and "block" in tokens:
            score += 1
    # “法杖/杖”语义下，纯工具（镐/斧/剑等）不如 rod/staff/wand/stick 贴近，降低权重
    if en_terms & {"rod", "staff", "wand", "stick"}:
        if any(t in tokens for t in ("pickaxe", "axe", "sword", "shovel", "hoe")):
            score -= 1
    # 中文短语“蘑菇斧头”整体命中时额外奖励（例如 name 同时含 mushroom + axe）
    if "蘑菇斧头" in zh_terms:
        if "mushroom" in tokens and "axe" in tokens:
            score += 5
    return score, matched


def _top_colors(image_path: Path, n: int = 5) -> list[str]:
    """读取 PNG，返回不透明像素中出现次数最多的 n 个 hex 颜色。"""
    with Image.open(image_path) as im:
        im = im.convert("RGBA")
        colors = im.getcolors(maxcolors=100000)
    if not colors:
        return []
    opaque = [(cnt, rgba) for cnt, rgba in colors if rgba[3] > 128]
    # 按像素数降序；同数量按颜色值稳定排序
    opaque.sort(key=lambda item: (-item[0], item[1]))
    return ["#%02X%02X%02X" % (r, g, b) for _, (r, g, b, a) in opaque[:n]]


def _shape_feature(entry: dict, image_path: Path) -> str:
    """由名称语义 + alpha 统计给出形状标签。"""
    name_lower = str(entry.get("name", "")).lower()
    cat = str(entry.get("category", "")).lower()
    # 1) 名称优先
    for key, label in _NAME_SHAPE_MAP.items():
        if key in name_lower:
            return label
    # 2) 通用类别 fallback
    if cat == "entity":
        return "实体UV/生物剪影"
    if cat == "block":
        # 再依据 alpha 是否满铺
        try:
            with Image.open(image_path) as im:
                im = im.convert("RGBA")
                pix = list(im.getdata())
                opaque = sum(1 for _, _, _, a in pix if a > 128)
                ratio = opaque / len(pix) if pix else 0.0
            if ratio >= 0.98:
                return "方块/满铺"
            return "方块/带透明"
        except Exception:
            return "方块"
    return "item 透明剪影"


def _pattern_feature(entry: dict) -> str:
    """由名称语义给出花纹标签。"""
    name_lower = str(entry.get("name", "")).lower()
    for key, label in _NAME_PATTERN_MAP.items():
        if key in name_lower:
            return label
    if any(k in name_lower for k in ("mushroom", "sapling", "ore", "stone", "planks",
                                     "brick", "log", "leaves", "grass")):
        return "纹理/斑点"
    return "无明显图案"


def _parts_feature(entry: dict) -> list[str]:
    """由名称语义给出部位/组成部分。"""
    name_lower = str(entry.get("name", "")).lower()
    for key, parts in _NAME_PART_MAP.items():
        if key in name_lower:
            return parts
    if str(entry.get("category", "")).lower() == "entity":
        return ["头", "身体", "腿/脚"]
    if str(entry.get("category", "")).lower() == "block":
        return ["贴图主体"]
    return ["主体"]


def _attraction_feature(entry: dict) -> list[str]:
    """由名称语义给出吸引点。无则返回空列表（不编造）。"""
    name_lower = str(entry.get("name", "")).lower()
    for key, attrs in _NAME_ATTRACTION_MAP.items():
        if key in name_lower:
            return attrs
    return []


def _classify_role(entry: dict, en_terms: set[str]) -> str:
    """给锚点分配最主要的 contribution role。"""
    name = str(entry.get("name", "")).lower()
    cat = str(entry.get("category", "")).lower()
    # 先看 query 中是否显式出现形状/花纹/颜色/吸引点词；候选名命中对应词元则归类
    if any(t in name for t in _SHAPE_KEYWORDS if t in en_terms):
        return "shape"
    if any(t in name for t in _PATTERN_KEYWORDS if t in en_terms):
        return "pattern"
    if any(t in name for t in _COLOR_KEYWORDS if t in en_terms):
        return "color"
    if any(t in name for t in _ATTRACTION_KEYWORDS if t in en_terms):
        return "attraction"
    # 未从 query 词元中归类时，按资产固有语义
    if cat == "entity":
        return "part"
    if any(k in name for k in _SHAPE_KEYWORDS):
        return "shape"
    if any(k in name for k in _PATTERN_KEYWORDS):
        return "pattern"
    if any(k in name for k in _COLOR_KEYWORDS):
        return "color"
    if any(k in name for k in _ATTRACTION_KEYWORDS):
        return "attraction"
    return "shape"


def _query_form(query: str, anchors: list[dict], forced: str | None) -> dict:
    """形式判定。返回 (form, form_note, source)。"""
    if forced:
        form = forced
        if form == "item":
            note = "item_sprite：单张 16x16 透明背景物品贴图"
            if any(k in query for k in ("异形", "非方块", "自定义")):
                note = "异形：任意透明剪影（item_sprite）"
        elif form == "block_multi":
            note = "block_multi：顶/侧/底三面 + model + blockstate"
        elif form == "cross":
            note = "cross：十字交叉贴图 + cross model + blockstate"
        elif form == "entity_uv":
            note = "entity_uv：实体 UV 贴图"
        else:
            note = form
        return {"form": form, "form_note": note, "form_source": "forced"}

    q = query
    # 1) 异形/非方块/自定义 -> item
    if any(k in q for k in ("法杖", "杖", "水晶", "异形", "非方块", "自定义")):
        return {
            "form": "item",
            "form_note": "异形：任意透明剪影（item_sprite）",
            "form_source": "query_rule",
        }
    # 2) 方块/矿石/块
    if any(k in q for k in ("方块", "蘑菇块", "矿石", "块", "砖", "玻璃", "羊毛", "灯")):
        return {
            "form": "block_multi",
            "form_note": "block_multi：顶/侧/底三面 + model + blockstate",
            "form_source": "query_rule",
        }
    # 3) 树苗/花/草/植物
    if any(k in q for k in ("树苗", "花", "草", "植物", "花盆")):
        return {
            "form": "cross",
            "form_note": "cross：十字交叉贴图 + cross model + blockstate",
            "form_source": "query_rule",
        }
    # 4) 生物/皮肤
    if any(k in q for k in ("生物", "皮肤", "实体", "怪物", "僵尸", "骷髅", "蜘蛛", "猪", "牛", "羊", "村民", "马", "蜜蜂", "鸡")):
        return {
            "form": "entity_uv",
            "form_note": "entity_uv：实体 UV 贴图",
            "form_source": "query_rule",
        }
    # 5) auto：基于 top anchor category
    if anchors:
        top_cat = anchors[0].get("category", "")
        if top_cat == "item":
            return {
                "form": "item",
                "form_note": "item_sprite：单张 16x16 透明背景物品贴图",
                "form_source": "auto_top_anchor",
            }
        if top_cat == "block":
            return {
                "form": "block_multi",
                "form_note": "block_multi：顶/侧/底三面 + model + blockstate",
                "form_source": "auto_top_anchor",
            }
        if top_cat == "entity":
            return {
                "form": "entity_uv",
                "form_note": "entity_uv：实体 UV 贴图",
                "form_source": "auto_top_anchor",
            }
    return {
        "form": "item",
        "form_note": "item_sprite：单张 16x16 透明背景物品贴图（fallback）",
        "form_source": "fallback",
    }


def _query_role_facets(en_terms: set[str], zh_terms: set[str]) -> set[str]:
    """
    判断 query 在语义上关心哪些锚点 role。
    选择锚点时只在这些 facet 之间做多样性；未出现的 facet 不被“补全”硬拉入无关资产。
    """
    facets: set[str] = set()
    shape_zh = {"斧", "斧头", "镐", "剑", "铲", "锄", "法杖", "杖", "棒", "树苗", "船", "箭", "弓", "盾"}
    shape_en = {"axe", "pickaxe", "sword", "shovel", "hoe", "rod", "staff", "wand",
                "stick", "boat", "arrow", "sapling", "bow", "helmet", "chestplate",
                "leggings", "boots"}
    pattern_zh = {"蘑菇", "红蘑菇", "褐蘑菇", "菌", "花纹", "条纹", "斑点", "砖", "木", "叶", "草", "羊毛", "玻璃"}
    pattern_en = {"mushroom", "mooshroom", "brick", "planks", "log", "leaves", "grass",
                  "wool", "glass", "pattern", "stripe", "dot"}
    color_zh = {"红", "蓝", "金", "荧石", "水晶", "宝石", "矿石", "矿", "绿", "黑", "白", "紫"}
    color_en = {"red", "blue", "gold", "glowstone", "diamond", "emerald", "quartz",
                "lapis", "green", "black", "white", "purple", "crystal", "mushroom"}
    attraction_zh = {"发光", "危险", "可爱", "魔法", "末影", "珍珠", "异形"}
    attraction_en = {"glow", "danger", "cute", "magic", "ender", "pearl", "blaze"}
    part_zh = {"头", "眼睛", "皮肤", "生物", "实体"}
    part_en = {"head", "eye", "part", "entity", "mob"}

    if zh_terms & shape_zh or en_terms & shape_en:
        facets.add("shape")
    if zh_terms & pattern_zh or en_terms & pattern_en:
        facets.add("pattern")
    if zh_terms & color_zh or en_terms & color_en:
        facets.add("color")
    if zh_terms & attraction_zh or en_terms & attraction_en:
        facets.add("attraction")
    if zh_terms & part_zh or en_terms & part_en:
        facets.add("part")
    return facets


def retrieve(
    query: str,
    top: int = 3,
    form: str | None = None,
    index: list[dict] | None = None,
    index_base: Path | str | None = None,
) -> dict:
    """主检索函数：返回 retrieval JSON dict。

    ``index_base`` 用于解析索引中可能存在的相对 ``path``；扫描索引一般使用绝对
    ``path``，传不传均可。
    """
    if index is None:
        index = load_index()
    if top < 1 or top > 32:
        raise ValueError("--top must be 1..32, got %d" % top)

    en_terms, zh_terms = _query_terms(query)
    cat_intent = _category_intent(query)
    query_facets = _query_role_facets(en_terms, zh_terms)

    scored = []
    for entry in index:
        score, matched = _score_entry(entry, en_terms, zh_terms, cat_intent)
        if score > 0:
            scored.append((score, entry, matched))

    # 无命中时 fallback：按 query 类别意图取该类别前若干张，保证至少有 1 个锚点
    if not scored:
        cat = cat_intent or "item"
        candidates = [e for e in index if e.get("category") == cat]
        if not candidates:
            candidates = index[:]
        scored = [(1, e, []) for e in candidates[:top]]

    # 先按分数排序；选择时尽量让 role 多样化（shape/pattern/color/attraction/part）
    scored.sort(key=lambda item: (-item[0], item[1].get("name", "")))
    annotated = [
        (score, entry, matched, _classify_role(entry, en_terms))
        for score, entry, matched in scored
    ]
    remaining = list(annotated)
    top_items: list[tuple[int, dict, list[str]]] = []
    used_roles: set[str] = set()
    # 只关心 query 语义中确实出现的 facet；未出现的 facet 不强行补全
    diversity_roles = query_facets or {"shape", "pattern", "color", "attraction", "part"}
    while remaining and len(top_items) < top:
        if len(top_items) == 0:
            pick_idx = 0
        else:
            # 优先选一个还没有出现过的、且 query 关心的 role 的最高分候选
            pick_idx = next(
                (
                    i for i, (_, _, _, r) in enumerate(remaining)
                    if r in diversity_roles and r not in used_roles
                ),
                0,
            )
        score, entry, matched, role = remaining.pop(pick_idx)
        top_items.append((score, entry, matched))
        if role in diversity_roles:
            used_roles.add(role)

    anchors = []
    seen = set()
    for score, entry, matched in top_items:
        key = entry.get("path", entry.get("name"))
        if key in seen:
            continue
        seen.add(key)
        image_path = resolve_entry_path(entry, index_base)
        role = _classify_role(entry, en_terms)
        anchors.append({
            "path": str(entry["path"]),
            "name": entry.get("name", ""),
            "category": entry.get("category", ""),
            "role": role,
            "features": {
                "shape": _shape_feature(entry, image_path),
                "pattern": _pattern_feature(entry),
                "colors": _top_colors(image_path, 5),
                "parts": _parts_feature(entry),
                "attraction": _attraction_feature(entry),
            },
            "score": score,
            "matched_terms": sorted(set(matched)),
            "palette_count": entry.get("palette_count"),
        })

    forced_form = None if form in (None, "auto") else form
    form_result = _query_form(query, anchors, forced_form)

    result = {
        "query": query,
        "form": form_result["form"],
        "form_note": form_result["form_note"],
        "form_source": form_result["form_source"],
        "method": "rule",
        "method_note": "内置中文别名+关键词规则，未调用外部 LLM 子代理；离线可复现。",
        "top": top,
        "anchors": anchors,
        "count": len(anchors),
        "query_terms": {
            "english": sorted(en_terms),
            "chinese": sorted(zh_terms),
        },
    }
    return result


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

def log_event(message: str) -> None:
    """把一条事件追加到 retrieve_log.txt（带时间戳）。"""
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = "[%s] %s\n" % (ts, message)
    with open(_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)


# ---------------------------------------------------------------------------
# 自测
# ---------------------------------------------------------------------------

SELF_TEST_QUERIES = [
    {"query": "蘑菇斧头", "form": "auto", "top": 3,
     "out": "retrieval_examples/mushroom_axe.json"},
    {"query": "荧石蘑菇方块", "form": "auto", "top": 3,
     "out": "retrieval_examples/glowstone_mushroom_block.json"},
    {"query": "异形水晶法杖", "form": "auto", "top": 8,
     "out": "retrieval_examples/alien_crystal_wand.json"},
]


def _build_synthetic_selftest_index() -> tuple[list[dict], Path]:
    """无内置素材库时，用 Pillow 生成一个迷你合成资源包索引。

    返回 ``(entries, tmp_root)``；调用方负责在结束后删除 ``tmp_root``。
    这些 PNG 是代码生成的纯色/透明小图，不是任何原版素材。
    """
    import scan_mc_assets as sc
    from PIL import Image

    tmp_root = Path(tempfile.mkdtemp(prefix="retrieve_selftest_"))
    root = tmp_root / "mini_resourcepack"
    modid = "demomod"
    assets = root / "assets" / modid

    # 中性化：不再放项目自证的“水晶法杖/蘑菇/火焰棒/蓝水晶”等特征；
    # 改为常见原版资产名，保留 broad 的 block/item/entity/cross 覆盖。
    specs = [
        ("block", "stone.png", (120, 120, 120, 255)),
        ("block", "dirt.png", (134, 96, 67, 255)),
        ("block", "cobblestone.png", (110, 110, 110, 255)),
        ("block", "oak_planks.png", (162, 130, 78, 255)),
        ("block", "bricks.png", (150, 70, 60, 255)),
        ("block", "glowstone.png", (240, 220, 140, 255)),
        ("block", "diamond_block.png", (120, 220, 230, 255)),
        ("block", "iron_block.png", (200, 200, 200, 255)),
        ("block", "lapis_block.png", (50, 70, 160, 255)),
        ("block", "glass.png", (180, 220, 230, 255)),
        ("block", "oak_sapling.png", (90, 140, 70, 255)),
        ("block", "poppy.png", (220, 60, 60, 255)),
        ("item", "stick.png", (140, 110, 60, 255)),
        ("item", "wooden_sword.png", (160, 130, 80, 255)),
        ("item", "stone_sword.png", (140, 140, 140, 255)),
        ("item", "diamond_sword.png", (120, 220, 230, 255)),
        ("item", "bow.png", (130, 90, 50, 255)),
        ("item", "arrow.png", (120, 100, 70, 255)),
        ("item", "golden_apple.png", (240, 200, 60, 255)),
        ("item", "diamond.png", (80, 200, 220, 255)),
        ("item", "emerald.png", (60, 190, 110, 255)),
        ("item", "iron_ingot.png", (200, 200, 200, 255)),
        ("item", "bread.png", (190, 140, 70, 255)),
        ("item", "apple.png", (200, 40, 40, 255)),
        ("entity", "pig.png", (240, 180, 160, 255)),
        ("entity", "cow.png", (150, 110, 80, 255)),
        ("entity", "sheep.png", (220, 220, 220, 255)),
        ("entity", "chicken.png", (230, 230, 230, 255)),
        ("entity", "creeper.png", (80, 170, 80, 255)),
        ("entity", "zombie.png", (70, 130, 60, 255)),
    ]
    for cat, name, color in specs:
        p = assets / "textures" / cat / name
        p.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGBA", (16, 16), color)
        # 隔点留透明，验证 palette 只统计不透明像素
        for x in range(0, 16, 2):
            for y in range(0, 16, 2):
                img.putpixel((x, y), (0, 0, 0, 0))
        img.save(p, "PNG")

    entries = sc.build_index(root, with_palette=True)["entries"]
    return entries, tmp_root


def _validate_result(result: dict) -> list[str]:
    """校验 retrieval JSON 字段完整性/合理性，返回 PASS 项列表。"""
    checks = []
    if result.get("query"):
        checks.append("query present")
    if result.get("form") in ("item", "block_multi", "cross", "entity_uv"):
        checks.append("form valid: %s" % result["form"])
    else:
        raise ValueError("form invalid: %r" % result.get("form"))
    if result.get("form_note"):
        checks.append("form_note present")
    anchors = result.get("anchors", [])
    if not 1 <= len(anchors) <= 8:
        raise ValueError("anchor count must be 1..8, got %d" % len(anchors))
    checks.append("anchor count 1..8: %d" % len(anchors))
    for i, a in enumerate(anchors, 1):
        if not a.get("path"):
            raise ValueError("anchor %d missing path" % i)
        if a.get("role") not in ("shape", "pattern", "color", "part", "attraction"):
            raise ValueError("anchor %d role invalid: %r" % (i, a.get("role")))
        feats = a.get("features", {})
        for key in ("shape", "pattern", "colors", "parts", "attraction"):
            if key not in feats:
                raise ValueError("anchor %d missing feature %s" % (i, key))
        checks.append("anchor %d fields ok: %s (%s)" % (i, a["name"], a["role"]))
    # 异形 query 的形式合理性
    q = result.get("query", "")
    if any(k in q for k in ("异形", "法杖", "水晶", "非方块", "自定义")) and result["form"] != "item":
        raise ValueError("异形/法杖/水晶 query should be form=item, got %s" % result["form"])
    if "树苗" in q and result["form"] != "cross":
        raise ValueError("树苗 query should be form=cross, got %s" % result["form"])
    return checks


def run_self_test() -> int:
    """运行 3 个示例 query 并校验输出；无内置库时自动使用合成索引。"""
    synthetic_tmp: Path | None = None
    if _INDEX_PATH.exists():
        index = load_index()
        print("self-test index: built-in %s" % _INDEX_PATH)
    else:
        index, synthetic_tmp = _build_synthetic_selftest_index()
        print("self-test index: synthetic (no vanilla assets required)")
    all_pass = True
    output_paths = []
    try:
        for spec in SELF_TEST_QUERIES:
            try:
                result = retrieve(spec["query"], top=spec["top"], form=spec["form"], index=index)
                out_path = _THIS_DIR / spec["out"]
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                    f.write("\n")
                checks = _validate_result(result)
                output_paths.append(out_path)
                for c in checks:
                    print("  PASS: %s" % c)
                print("  wrote: %s" % out_path)
                log_event("self-test OK: query=%r form=%s anchors=%s" % (
                    spec["query"], result["form"],
                    ", ".join(a["name"] for a in result["anchors"]),
                ))
            except Exception as e:  # noqa: BLE001
                all_pass = False
                print("  FAIL: %s" % e, file=sys.stderr)
                log_event("self-test FAIL: query=%r error=%s" % (spec["query"], e))
    finally:
        if synthetic_tmp is not None:
            import shutil
            shutil.rmtree(synthetic_tmp, ignore_errors=True)

    if all_pass and len(output_paths) == len(SELF_TEST_QUERIES):
        print("SELF-TEST: PASS (%d queries, %d files)" % (
            len(SELF_TEST_QUERIES), len(output_paths)))
        log_event("SELF-TEST: PASS")
        return 0
    print("SELF-TEST: FAIL", file=sys.stderr)
    log_event("SELF-TEST: FAIL")
    return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="自动检索与特征提取 (v2-retrieve)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--query", help="中文/英文想法，例如 蘑菇斧头")
    parser.add_argument("--form", choices=["auto", "item", "block_multi", "cross", "entity_uv"],
                        default="auto", help="形式判定；auto=按 query 规则/top anchor")
    parser.add_argument("--top", type=int, default=3, choices=list(range(1, 9)), help="锚点数量 1-8")
    parser.add_argument("--out", help="输出 JSON 路径（默认 retrieval_examples/<slug>.json）")
    parser.add_argument("--index", help="scan_mc_assets.py 生成的索引 JSON（扫描结果）")
    parser.add_argument("--mc-path", help="Minecraft/资源包路径；直接调用 scan_mc_assets 扫描生成索引")
    parser.add_argument("--self-test", action="store_true", help="运行 3 个示例并校验")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    if not args.query:
        parser.error("--query is required (or use --self-test)")
    if args.index and args.mc_path:
        parser.error("--index and --mc-path are mutually exclusive")
    if not args.out:
        slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", args.query.strip())
        args.out = str(_RETRIEVAL_DIR / ("%s.json" % slug))

    if args.mc_path:
        import scan_mc_assets as sc
        scan = sc.build_index(args.mc_path, with_palette=True)
        index = scan["entries"]
        print("index: scanned %s -> %d textures, %d entries" % (
            scan["source_dir"], scan["count_textures"], len(index)))
    elif args.index:
        index, _base = load_index_with_base(Path(args.index))
        print("index: %s -> %d entries" % (args.index, len(index)))
    elif _INDEX_PATH.exists():
        index = load_index()
        print("index: built-in %s -> %d entries" % (_INDEX_PATH, len(index)))
    else:
        parser.error(
            "no built-in index found (%s). Run: python3 scan_mc_assets.py --mc-path <your-mc-path> --out my_index.json, "
            "then pass --index my_index.json" % _INDEX_PATH
        )
    try:
        result = retrieve(args.query, top=args.top, form=args.form, index=index)
    except Exception as e:
        log_event("ERROR: query=%r error=%s" % (args.query, e))
        return 1

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = _THIS_DIR / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("query: %s" % result["query"])
    print("form: %s (%s)" % (result["form"], result["form_note"]))
    print("anchors: %d" % len(result["anchors"]))
    for a in result["anchors"]:
        print("  - %s | role=%s | shape=%s | pattern=%s | colors=%s | parts=%s | attraction=%s" % (
            a["path"], a["role"], a["features"]["shape"], a["features"]["pattern"],
            ", ".join(a["features"]["colors"]), ", ".join(a["features"]["parts"]),
            ", ".join(a["features"]["attraction"]) or "-",
        ))
    print("out: %s" % out_path)
    log_event("OK: query=%r form=%s out=%s anchors=%s" % (
        result["query"], result["form"], out_path,
        ", ".join(a["name"] for a in result["anchors"]),
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
