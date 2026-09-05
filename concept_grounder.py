#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
concept_grounder.py — v4-concept: 语义概念卡生成器。

让 LLM 在输出像素纹理之前先“知道自己做的是什么物体”：根据 query / retrieval /
form 生成一张概念卡，包含 item_name、description、parts、face_regions、
visual_goals、minecraft_reference、avoid。

数据来源
--------
* 优先读取 ``retrieval_examples/<slug>.json``（v2-retrieve 产物）。
* 若没有 retrieval 文件，离线调用 ``retrieve_assets.retrieve()`` 生成（method=rule）。
* block_custom 的 face 键通过 ``package_asset.resolve_block_template()`` 读取
  真实原版模型/父模板获得（如 anvil -> top/particle/body）。

用法
----
    python3 concept_grounder.py \
        --query "蘑菇铁砧" --form block_custom \
        --retrieval retrieval_examples/mushroom_anvil.json \
        --out concept_examples/mushroom_anvil.json

    python3 concept_grounder.py --query "异形水晶法杖" --form item \
        --out concept_examples/alien_crystal_wand.json

    python3 concept_grounder.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_RETRIEVAL_DIR = _THIS_DIR / "retrieval_examples"
_CONCEPT_DIR = _THIS_DIR / "concept_examples"
_LOG_PATH = _THIS_DIR / "v4-concept-log.txt"
_SELFTEST_REPORT = _THIS_DIR / "concept_grounder_selftest.txt"

# 本工具支持的形式。build_style_prompt 的 --form 仍为
# auto|item|block_multi|cross|entity_uv；block_custom 是打包/模型形式，
# 概念卡需要显式支持它。
_VALID_FORMS = ("item", "block_multi", "cross", "entity_uv", "block_custom")

# 已知示例的中文 -> 英文 slug，保证文件名可读且稳定。
_SLUG_MAP = {
    "蘑菇铁砧": "mushroom_anvil",
    "异形水晶法杖": "alien_crystal_wand",
    "蘑菇树苗": "mushroom_sapling",
    "蘑菇幼苗": "mushroom_sprout",
    "蘑菇斧头": "mushroom_axe",
    "荧石蘑菇方块": "glowstone_mushroom_block",
    "蘑菇法杖": "mushroom_staff",
}

# form -> 默认 face 描述。block_custom 由模板动态决定。
_FORM_DEFAULT_FACES = {
    "item": [("sprite", "单张 16x16 透明背景物品贴图")],
    "block_multi": [
        ("top", "方块顶面（16x16）"),
        ("side", "方块侧面（16x16）"),
        ("bottom", "方块底面（16x16）"),
    ],
    "cross": [("cross", "十字交叉透明贴图（16x16）")],
    "entity_uv": [("uv", "实体 UV 贴图（64x32/64x64）")],
    "block_custom": [],
}

# 已知模板的可读描述，后续会叠加在 face_regions 上。
_BLOCK_TEMPLATE_LABELS = {
    "anvil": "铁砧（anvil）模板：body=主体+底座+窄颈，top=顶面，particle=粒子采样",
    "slab": "台阶（slab）模板：上下两层 + 侧边",
    "door": "门（door）模板：门板下半/上半 + 铰链",
    "stairs": "楼梯（stairs）模板：台阶/内角/外角 + 侧面",
    "fence": "栅栏（fence）模板：柱/侧栏/背包栏",
    "wall": "墙（wall）模板：柱/侧墙/高侧墙/背包栏",
    "chest": "箱子（chest）模板：正面/侧面/顶面粒子",
    "flower_pot": "花盆（flower_pot）模板：盆体/盆口/泥土",
}


def normalize_path(path: str | Path) -> Path:
    """接受 Windows 风格路径（C:\\...）与 POSIX /mnt/c/..."""
    s = str(path)
    if s.startswith("\\\\") and s[2:3].isalpha() and s[3:4] in ("\\", "/"):
        s = s.replace("\\", "/")
    if len(s) >= 3 and s[0].isalpha() and s[1] == ":" and s[2] in ("\\", "/"):
        drive = s[0].lower()
        rest = s[2:].replace("\\", "/")
        return Path("/mnt") / drive / rest
    return Path(s)


def log_message(message: str, path: str | Path = _LOG_PATH) -> None:
    """追加带时间戳的事件到 v4-concept-log.txt。"""
    p = normalize_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(p, "a", encoding="utf-8") as f:
        f.write("[%s] %s\n" % (ts, message))


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("JSON must be an object: %s" % path)
    return data


def _write_json(data: dict, path: Path) -> Path:
    path = normalize_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


def slugify(query: str, retrieval: dict | None = None) -> str:
    """为中文想法生成稳定英文 slug。"""
    if query in _SLUG_MAP:
        return _SLUG_MAP[query]
    english = (retrieval or {}).get("query_terms", {}).get("english", []) or []
    if english:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", "_".join(english)).strip("_")
        if slug:
            return slug
    ascii_part = re.sub(r"[^A-Za-z0-9]+", "_", query.lower()).strip("_")
    if ascii_part:
        return ascii_part
    # 纯中文：用前 6 个字符的 unicode hex 生成稳定 slug
    hex_slug = "".join("%x" % ord(ch) for ch in query.strip() if ch.strip())[:24]
    if hex_slug:
        return "q_" + hex_slug
    return "concept_card"


def _load_or_generate_retrieval(
    retrieval_path: str | Path | None,
    query: str,
    form: str,
) -> tuple[dict, Path | None]:
    import retrieve_assets as ra

    if retrieval_path:
        p = normalize_path(retrieval_path)
        if not p.is_absolute():
            p = _THIS_DIR / p
        if p.exists():
            return _load_json(p), p
        raise FileNotFoundError("--retrieval not found: %s" % p)

    # 离线复用已有检索器；block_custom 作为强制 form 传入（retrieve 内部接受）。
    forced_form = None if form in (None, "", "auto") else form
    result = ra.retrieve(query, top=3, form=forced_form)
    return result, None


def _infer_block_template(query: str, retrieval: dict | None, explicit: str | None) -> str:
    """为 block_custom 推断原版模型模板。"""
    if explicit:
        return explicit
    # retrieval 可携带 template 字段（概念卡专用扩展）。
    rt = (retrieval or {}).get("block_template")
    if rt:
        return str(rt)
    q = query.lower()
    if any(k in q for k in ("铁砧", "anvil")):
        return "anvil"
    if any(k in q for k in ("门", "door")):
        return "door"
    if any(k in q for k in ("楼梯", "stairs")):
        return "stairs"
    if any(k in q for k in ("栅栏", "fence")):
        return "fence"
    if any(k in q for k in ("墙", "wall")):
        return "wall"
    if any(k in q for k in ("箱子", "chest")):
        return "chest"
    if any(k in q for k in ("花盆", "flower_pot")):
        return "flower_pot"
    if any(k in q for k in ("台阶", "slab")):
        return "slab"
    # 无关键字时用铁砧作为最通用的异形模板（与 v3 演示一致）。
    return "anvil"


def _block_custom_texture_keys(template: str) -> list[str]:
    """通过 package_asset 的模板解析获取真实纹理 key，避免硬编码。"""
    try:
        from package_asset import resolve_block_template
        desc = resolve_block_template(template)
        keys = list(desc.get("texture_keys", []))
        if keys:
            # 保持可读顺序：top/particle/body 常见；不改变原库返回的真实键。
            return keys
    except Exception as exc:  # noqa: BLE001
        log_message("WARN: resolve_block_template failed for %r: %s" % (template, exc))
    # 铁砧模板的原生 key 兜底。
    return ["top", "particle", "body"]


def _anchor_summary(retrieval: dict | None) -> dict:
    """聚合 retrieval anchors 的形状/图案/颜色/部位/吸引点。"""
    anchors = (retrieval or {}).get("anchors", []) or []
    buckets = {
        "shape": [], "pattern": [], "colors": [], "parts": [], "attraction": [],
    }
    for a in anchors:
        feats = a.get("features", {}) or {}
        for field in buckets:
            vals = feats.get(field)
            if isinstance(vals, str):
                vals = [vals]
            for v in vals or []:
                if v and v not in buckets[field]:
                    buckets[field].append(v)
    return buckets


# ---------------------------------------------------------------------------
# 设计字段辅助：palette_scheme / shape_pattern / reference_nodes
# ---------------------------------------------------------------------------

_DESIGN_ROLE_MAP = {
    "shape": "shape",
    "color": "color",
    "pattern": "pattern",
    "part": "shape",
    "attraction": "color",
}


_PATTERN_INTENT: dict[str, tuple[list[str], str]] = {
    "眼球": (["eye 眼球（镶嵌于主体，1-2px 小区域）"],
             "眼球：深色眼窝/眼眶 + 绿色虹膜/瞳孔 + 1px 白高光；眼球是视觉焦点，嵌在主体中央，不做大区域。"),
    "眼睛": (["eye 眼睛（小区域视觉焦点）"],
             "眼睛：深色眼眶 + 高亮瞳孔/虹膜 + 1px 白高光；小区域镶嵌，不占主体大半。"),
    "眼": (["eye 眼睛（小区域视觉焦点）"],
          "眼睛：深色眼眶 + 高亮瞳孔/虹膜 + 1px 白高光；小区域镶嵌。"),
    "恶魔": (["flame 魂火/恶魔纹"],
             "恶魔纹：青色/青绿色魂火或恶魔火焰，带发光边缘 + 深色轮廓，与本体暗红/黑红形成对比。"),
    "魂": (["flame 魂火"],
          "魂火：青色/青绿发光，边缘 1px 高亮，中心白/青。"),
    "骨": (["bone 骨纹"],
          "骨纹：骨白底 + 深色眼窝 + 裂纹；不要画成完整骨架，只取头骨/骨骼质感。"),
    "骷髅": (["skull 骷髅纹"],
            "骷髅：骨白头骨 + 深色眼窝/鼻洞 + 裂纹；只取头部语义，不做全身动画。"),
    "刀": (["blade 刃面", "handle 刀柄"],
          "刃面：冷灰金属高光 + 刀身渐变/划痕；刀柄：皮革/木纹。"),
    "剑": (["blade 刃面", "guard 护手", "handle 剑柄"],
          "刃面：金属高光 + 中脊亮线；护手：深色；柄：皮革/木纹。"),
    "皮": (["hide_edge 皮张边缘"],
          "皮张：不规则边缘/毛边 + 皮革纹理（颗粒+折痕）+ 织物内衬/缝线。"),
}


def _pattern_intent(query: str) -> tuple[list[str], str | None]:
    """从 query 推断“花纹/结构意图”，避免因锚点 pattern 为空而让模型不画细节。"""
    extra_parts: list[str] = []
    override: str | None = None
    for zh in sorted(_PATTERN_INTENT, key=len, reverse=True):
        if zh in query:
            parts, pat = _PATTERN_INTENT[zh]
            for p in parts:
                if p not in extra_parts:
                    extra_parts.append(p)
            if override is None or len(pat) > len(override):
                override = pat
    return extra_parts, override


def _far_color(base: str, colors: list[str]) -> str | None:
    """返回与 base 色差异最大、且差异达到阈值的颜色；用于把“点缀色”从非主锚点并进来。"""
    def rgb(h: str) -> tuple[int, int, int]:
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if not base or not colors:
        return None
    br, bg, bb = rgb(base)
    best = None
    best_d = 60  # 低于此差异视为同色系，不用
    for c in colors:
        try:
            r, g, b = rgb(c)
        except Exception:
            continue
        d = abs(r - br) + abs(g - bg) + abs(b - bb)
        if d > best_d:
            best_d = d
            best = c
    return best


def _make_palette_scheme(
    base: str,
    light: str,
    dark: str,
    accent: str,
    outline: str,
    border_note: str,
    saturation_note: str,
) -> dict:
    """生成符合 v5 设计升级的 palette_scheme 对象。"""
    return {
        "base": base,
        "light": light,
        "dark": dark,
        "accent": accent,
        "outline": outline,
        "border_note": border_note,
        "saturation_note": saturation_note,
    }


def _make_shape_pattern(
    silhouette: str,
    parts: list[str],
    border: str,
    shading: str,
    detail_pattern: str,
    shape_lock_optional: bool = True,
    part_pattern_flow: list[dict] | None = None,
    integration_note: str = "纹样必须贴合形状的走向/边缘/明暗面，不得脱离形状独立存在。",
) -> dict:
    """生成符合 v5 设计升级的 shape_pattern 对象。

    ``part_pattern_flow`` 是“部件形状 → 纹样沿该形状走向”的一体化描述，
    避免把形状与花纹割裂成两个孤立清单。
    """
    if part_pattern_flow is None:
        part_pattern_flow = [
            {
                "part": p,
                "shape": "该部件形状/轮廓",
                "pattern": "沿形状走向的纹理与明暗",
                "flow": "纹样沿该部件轮廓/明暗面方向贴合，不脱离形状独立存在。",
            }
            for p in parts[:3]
        ]
    return {
        "silhouette": silhouette,
        "parts": parts,
        "border": border,
        "shading": shading,
        "detail_pattern": detail_pattern,
        "shape_lock_optional": shape_lock_optional,
        "part_pattern_flow": part_pattern_flow,
        "integration_note": integration_note,
    }


def _reference_nodes_from_retrieval(retrieval: dict | None, min_count: int = 3) -> list[dict]:
    """从 retrieval anchors 生成 reference_nodes；不足 3 条时补风格兜底节点。"""
    nodes: list[dict] = []
    for a in (retrieval or {}).get("anchors", []) or []:
        role = _DESIGN_ROLE_MAP.get(a.get("role", ""), "shape")
        feats = a.get("features", {}) or {}
        reasons = []
        if feats.get("shape"):
            reasons.append("形状参考：%s" % feats["shape"])
        if feats.get("pattern"):
            reasons.append("图案参考：%s" % feats["pattern"])
        if feats.get("colors"):
            reasons.append("配色参考：%s" % " ".join(feats["colors"][:3]))
        nodes.append({
            "asset": a.get("path") or a.get("name") or "reference",
            "role": role,
            "reason": "；".join(reasons) or "同类风格参考",
        })

    # 允许 3~8 个参考节点；若检索不到 3 条，用风格兜底节点补足，保证设计卡始终有多个参考。
    fallback_roles = ["shape", "color", "pattern"]
    fallback_reasons = [
        "同类物品轮廓尺度参考（非硬性指标）",
        "色相/饱和度参考（非硬性指标）",
        "细节纹理参考（非硬性指标）",
    ]
    i = 0
    while len(nodes) < min_count:
        nodes.append({
            "asset": "minecraft_style_fallback_%d" % (i + 1),
            "role": fallback_roles[i % len(fallback_roles)],
            "reason": fallback_reasons[i % len(fallback_reasons)],
        })
        i += 1
    return nodes[:8]


# ---------------------------------------------------------------------------
# 高质量概念卡（针对任务三个示例；generic 分支覆盖任意 query）
# ---------------------------------------------------------------------------

def _card_mushroom_anvil(retrieval: dict | None, template: str = "anvil") -> dict:
    """蘑菇铁砧（block_custom / anvil）。"""
    return {
        "item_name": "蘑菇铁砧 (Mushroom Anvil)",
        "description": "一个以铁砧几何为骨架、顶面变成红色菌盖、侧面与底座带有菌柄/菌褶纹理的 Minecraft 自定义方块。",
        "parts": [
            "base 金属/石质底座",
            "neck 窄颈",
            "top 蘑菇菌盖顶面",
            "body 铁砧侧面主体",
            "particle 粒子/整体材质采样",
        ],
        "face_regions": {
            "body": "铁砧底座+窄颈+侧面主体：深灰金属/石质底色，侧面加入褐色菌柄纵向纹理与少量红色菌盖边缘。",
            "top": "顶面中央红蘑菇菌盖：红色主体 (#C32826/#BE2321)，白色斑点 (#FFBFBF/#FF9898)，边缘深红 (#A9121A)；菌盖覆盖铁砧顶面，四角露出金属耳。",
            "particle": "整体材质颗粒：深灰/褐/红混合小颗粒，用于破坏粒子效果。",
        },
        "visual_goals": [
            "body 底部画 4-8 像素深灰金属底座 (#3D3D3D/#525252)，右侧画窄颈过渡；",
            "body 窄颈区域用褐色菌柄 (#493615/#684E1E) 纵向条纹，保留铁砧侧面有颈的结构；",
            "top 的 16x16 中央 10x10 区域铺红色菌盖 (#C32826/#BE2321)，边缘 1-2 像素深红 (#A9121A)；",
            "top 菌盖上散布 3-5 个白色斑点 (#FFBFBF/#FF9898)，斑点 1-2 像素，避免等距规则网格；",
            "particle 面作为全图采样：灰色底 + 红色/褐色小点，不得复制原版 anvil_top.png 的条纹。",
        ],
        "minecraft_reference": "anvil（block_custom 模板：body/top/particle 三纹理）；red_mushroom_block（菌盖红底+白点）；red_mushroom（菌盖红色）",
        "avoid": [
            "不要复制原版 anvil.png / anvil_top.png 的逐像素纹样；",
            "不要只画成普通灰色铁砧：必须有明显蘑菇菌盖/菌柄语义；",
            "不要画成完整蘑菇方块：保留底座-窄颈-顶面的铁砧剪影；",
            "不要用过多绿色/蓝色：主体应是蘑菇红 + 深灰金属。",
        ],
        "palette_scheme": _make_palette_scheme(
            base="#C32826",
            light="#FFBFBF",
            dark="#A9121A",
            accent="#493615",
            outline="#1F1210",
            border_note="顶面菌盖边缘 1-2px 深红；底座/侧面用深灰金属与褐色菌柄形成自然边界。",
            saturation_note="红色保持中等饱和度，避免荧光；灰/褐作为低饱和过渡。",
        ),
        "shape_pattern": _make_shape_pattern(
            silhouette="铁砧主体+窄颈+顶面菌盖；顶面为方形模块，侧面保留底座/窄颈几何。",
            parts=["base 底座", "neck 窄颈", "top 菌盖顶面", "body 侧面主体", "particle 粒子采样"],
            border="顶面菌盖边缘 1-2px 深红；金属边缘用 1px 深灰描边。",
            shading="左上偏亮、右下偏暗；菌盖有白点高光，菌柄有纵向暗缝。",
            detail_pattern="菌盖白点 + 菌柄纵向纹理 + 金属颗粒噪点。",
            shape_lock_optional=True,
            part_pattern_flow=[
                {"part": "base 底座", "shape": "方形/梯形金属底座", "pattern": "深灰颗粒与横向锻痕", "flow": "颗粒沿底座平面和棱边分布，锻痕沿底座横向走。"},
                {"part": "neck 窄颈", "shape": "细窄颈", "pattern": "褐色菌柄纵向纹理", "flow": "纵向纹理沿窄颈的竖向走向贴合，不跨越成横纹。"},
                {"part": "top 菌盖顶面", "shape": "方形顶面 / 半圆菌盖", "pattern": "白色斑点 + 放射菌褶", "flow": "斑点沿伞面弧线分布，放射状菌褶从中心向边缘展开。"},
                {"part": "body 侧面主体", "shape": "铁砧侧面轮廓", "pattern": "金属噪点 + 菌柄分割", "flow": "噪点保留侧面结构线，菌柄分割线沿侧面的纵向/斜向轮廓走。"},
                {"part": "particle 粒子采样", "shape": "整体随机颗粒", "pattern": "灰/褐/红小点", "flow": "小点作为整体材质采样，不形成独立图案。"},
            ],
            integration_note="每个部件的纹样都必须沿该部件形状的轮廓/明暗面走向；不得把形状与花纹割裂成两套独立描述。",
        ),
        "reference_nodes": [
            {"asset": "anvil", "role": "shape", "reason": "提供铁砧底座/窄颈/顶面的几何骨架参考（非硬性指标）。"},
            {"asset": "red_mushroom_block", "role": "pattern", "reason": "菌盖红底+白斑点图案与色调参考。"},
            {"asset": "red_mushroom", "role": "border", "reason": "菌盖边缘深红和菌柄大地色参考。"},
        ],
    }


def _card_alien_crystal_wand(retrieval: dict | None) -> dict:
    """异形水晶法杖（item / 语义是法杖，不是复制 blaze_rod）。"""
    sp = _make_shape_pattern(
        silhouette="沿左下→右上的斜向细杖 + 顶端水晶簇：杖身顶端即水晶簇锚点，中央主水晶与杖身同轴，左右副水晶分叉；整体是一条连续斜向‘法杖’剪影。",
        parts=["rod 杖身", "crystal_cluster 顶部多根尖柱/棱面水晶", "handle 握柄"],
        border="晶体沿外轮廓 1px 深色 #10282A；杖身与水晶交界用暗色过渡；描边沿对角线构图走，不形成独立竖直框。",
        shading="沿对角线方向：左上/上侧亮，右下/下侧暗；每根晶体有亮面和暗面，避免平涂发光。",
        detail_pattern="水晶棱面用小三角/菱形切面 + 1px 噪点；杖身用暗棕颗粒，颗粒沿杖身轴线流动。",
        shape_lock_optional=True,
        part_pattern_flow=[
            {"part": "crystal_cluster 水晶簇", "shape": "多根尖柱/棱面尖柱（中央主晶与杖身同轴）", "pattern": "棱面 + 纵向高光带 + 两侧暗面", "flow": "每根尖柱从尖端到底座都有一条沿柱体轴向（即杖身对角线方向）的纵向高光带；中央主晶与杖身同轴，暗面位于柱体两侧。"},
            {"part": "rod 杖身", "shape": "2-3px 宽斜向细杖（左下→右上）", "pattern": "暗棕颗粒 / 微弱魔法纹", "flow": "颗粒与魔法纹沿杖身轴线纵向流动，不出现横向/竖直孤立纹样。"},
            {"part": "handle 握柄", "shape": "杖身下段加粗/深色段", "pattern": "暗棕分段 + 颗粒", "flow": "分段线沿握柄径向环绕，颗粒沿握柄纵向分布；整体仍在同一对角线上。"},
        ],
        integration_note="先用形状确定结构（尖柱/杖身/握柄），再让棱面、高光带、颗粒纹样贴合每个部件的走向/边缘/明暗面；纹样不得脱离形状独立存在。",
    )
    sp["orientation"] = {
        "composition_axis": "整根法杖为一条从‘左下→右上’的对角线构图；杖身与杖头必须沿同一条轴线",
        "head_anchor": "水晶簇锚定在杖身右上端（顶端），不是悬在画布垂直中心",
        "connection_rule": "连接处位于杖身顶端端点，且与杖身轴线重合；严禁‘手柄斜、杖头正’或连接点偏到侧面",
        "axis_check": "从杖尾到杖头用一条假想对角线贯穿，任何部件（握柄、杖身、中央主水晶）都不得偏离该轴线",
    }
    return {
        "item_name": "异形水晶法杖 (Alien Crystal Wand)",
        "description": "一根以法杖为语义骨架、顶端长着多根尖柱状异形水晶簇的 Minecraft 物品；整体沿同一条对角线构图，水晶簇锚定在杖身顶端，视觉主体是水晶簇，不是简单火焰棒。",
        "parts": [
            "rod 杖身",
            "crystal_cluster 顶部明显水晶簇（多根尖柱/棱面）",
            "handle 握柄/尾部",
        ],
        "face_regions": {
            "sprite": "单张 16x16 透明背景：整根法杖沿从左下到右上的对角线；杖身是一条 2-3px 宽斜向柄，顶端端点处锚定一组 3-5 根水晶尖柱簇；中央主水晶的轴线与杖身轴线重合，左右副水晶以主水晶为轴对称分叉；连接点在手柄顶端，不允许错位。",
        },
        "visual_goals": [
            "sprite 构图：整根法杖沿‘左下→右上’对角线，从杖尾到杖头可连成一条假想直线；",
            "sprite 杖身：2-3px 宽斜向柄，方向必须指向右上，不能竖直；",
            "sprite 连接：水晶簇必须锚定在杖身右上端端点，连接点与杖身轴线重合，严禁‘手柄斜、杖头正’或连接点偏到侧面；",
            "sprite 水晶簇：顶部 3-5 根尖柱，中央主水晶沿杖身轴线方向伸出，左右副水晶向两侧分叉；每根有纵向棱面高光和两侧暗面；",
            "sprite 配色：低饱和青绿 #3E8F84/#2F6F68/#1F4E4A，亮面 #8FCEC4，暗面 #16403C，1px 描边 #10282A；",
            "sprite 杖身/握柄：琥珀/暗棕 #7A4A1E/#5A3413/#3E2613，树纹沿杖身纵向；",
            "sprite 保持透明背景，16x16 内不贴边、不出现方块外轮廓。",
        ],
        "minecraft_reference": "blaze_rod（仅借用物品尺度，不是形状锁）；diamond + emerald（晶体色相）；quartz（晶体棱面/暗部）",
        "avoid": [
            "不要复制原版 blaze_rod.png 的逐像素图案，也不要把它当成锁死形状；",
            "不要画成普通木棍/火把/长条棒：顶部必须有明显、多根的异形水晶簇；",
            "不要出现‘手柄斜、杖头正’或连接点偏到侧面的构图；",
            "不要画成方块：保持物品透明剪影，不出现满铺背景；",
            "不要用高饱和荧光青/绿：降低饱和度、加入暗部与 1px 描边。",
        ],
        "palette_scheme": _make_palette_scheme(
            base="#3E8F84",
            light="#8FCEC4",
            dark="#16403C",
            accent="#C9A227",
            outline="#10282A",
            border_note="水晶外轮廓用 1px 深色描边 #10282A；杖身与水晶之间用暗棕/深绿自然分隔；描边沿对角线构图走。",
            saturation_note="青绿/水晶色整体降低饱和度，避免高饱和荧光；亮部仅作局部 1px 提示。",
        ),
        "shape_pattern": sp,
        "reference_nodes": [
            {"asset": "blaze_rod", "role": "shape", "reason": "仅参考物品尺度/细长剪影，不锁形状，也不复制像素。"},
            {"asset": "diamond", "role": "color", "reason": "提供青绿/晶体色相与高光方向，但要降低饱和度。"},
            {"asset": "emerald", "role": "pattern", "reason": "提供宝石棱面/切面质感与暗部参考。"},
            {"asset": "quartz", "role": "border", "reason": "提供低饱和晶体暗部与自然描边参考。"},
            {"asset": "stick", "role": "material", "reason": "法杖把手/杖身材质尺度参考（非硬性指标）。"},
        ],
    }


def _card_mushroom_sapling(retrieval: dict | None) -> dict:
    """蘑菇树苗（cross / birch_sapling 剪影）—— 保留给旧 slug/历史文档兼容。"""
    return {
        "item_name": "蘑菇树苗 (Mushroom Sapling, legacy)",
        "description": "一棵刚长出的小蘑菇树苗：细菌柄为干，顶部长着小菌盖，使用十字交叉模型。",
        "parts": [
            "trunk 菌柄/树干（细）",
            "cap 小菌盖/叶冠",
            "root 根部小点",
        ],
        "face_regions": {
            "cross": "十字交叉贴图：中央 2-3 像素菌柄，上方 4-6 像素菌盖，两侧有少量叶片/菌褶剪影。",
        },
        "visual_goals": [
            "cross 中央底部画 1-2 像素宽菌柄，高 5-7 像素，褐色 #8A5A2B/#5A3B1A；",
            "cross 菌柄顶部画 5x5 左右圆/半圆菌盖，红 #C32826 或褐 #CC9978，边缘 1 像素深色；",
            "cross 菌盖下沿画 2-3 像素白色/米色菌褶 #E3DDBA/#CFC47F；",
            "cross 两侧画 1-2 像素小叶片/菌褶剪影，左右对称但不等距；",
            "cross 保持透明背景，根部用 1 像素 #7A5C33。",
        ],
        "minecraft_reference": "birch_sapling（十字树苗形态）；brown_mushroom / red_mushroom（菌盖颜色）",
        "avoid": [
            "不要复制原版 birch_sapling.png 的逐像素图案；",
            "不要画成大树苗：16x16 内应是幼体/小型，高度约占 8-11 像素；",
            "不要画成普通蘑菇方块：要保留十字交叉的透空剪影；",
            "不要用大块纯绿：菌盖应红/褐，叶片绿只作少量点缀。",
        ],
        "palette_scheme": _make_palette_scheme(
            base="#C32826",
            light="#FFBFBF",
            dark="#A9121A",
            accent="#CC9978",
            outline="#5A3B1A",
            border_note="菌盖下沿与菌褶用米白/褐色自然分隔；外轮廓 1px 深褐，不做均匀黑框。",
            saturation_note="菌盖红色保持中等饱和度，菌柄大地色低饱和；避免荧光红/绿。",
        ),
        "shape_pattern": _make_shape_pattern(
            silhouette="16x16 小蘑菇：半圆菌盖 + 细菌柄，高度约 8-11 像素。",
            parts=["cap 菌盖", "gills 菌褶", "stem 菌柄"],
            border="菌盖边缘 1px 深红；菌柄两侧深褐形成自然描边。",
            shading="菌盖左上高光/右下暗面；菌柄左亮右暗。",
            detail_pattern="菌盖少量白点 + 菌褶 1px 横纹 + 菌柄噪点。",
            shape_lock_optional=True,
            part_pattern_flow=[
                {"part": "cap 菌盖", "shape": "半圆伞面", "pattern": "红色底 + 白色斑点 + 顶部高光", "flow": "白点沿伞面弧线分布，高光沿伞面左上方走势，不脱离伞面边缘。"},
                {"part": "gills 菌褶", "shape": "菌盖下沿弧线", "pattern": "米白/褐色横向 1px 菌褶", "flow": "菌褶线沿下沿弧线排列，跟随伞边缘弯曲。"},
                {"part": "stem 菌柄", "shape": "竖向菌柄", "pattern": "浅褐/褐色纵向纹理", "flow": "纵向纹理沿菌柄走向分布，左亮右暗形成体积。"},
            ],
            integration_note="菌盖斑点/菌褶、菌柄纹理都必须沿各自形状的弧线或纵向走向；纹样不得脱离形状独立存在。",
        ),
        "reference_nodes": [
            {"asset": "birch_sapling", "role": "shape", "reason": "仅参考十字交叉渲染形式/物体尺度，不锁具体树苗形状。"},
            {"asset": "red_mushroom", "role": "color", "reason": "菌盖红色、菌褶白色与菌柄大地色参考。"},
            {"asset": "brown_mushroom_block", "role": "border", "reason": "菌盖边缘暗色与自然分隔参考。"},
        ],
    }


def _card_mushroom_sprout(retrieval: dict | None) -> dict:
    """蘑菇幼苗：cross 只是渲染形式，内容/形状都是蘑菇本体（菌盖+菌柄）。"""
    return {
        "item_name": "蘑菇幼苗 (Mushroom Sprout)",
        "description": "一棵刚长出的小蘑菇幼苗：内容就是蘑菇本体（菌盖+菌柄），使用 Minecraft cross 十字交叉渲染形式；cross 只是展示形式，不是树苗。",
        "parts": [
            "cap 小菌盖（红/褐）",
            "gills 菌盖下沿菌褶（白/米）",
            "stem 菌柄（浅褐/褐色）"
        ],
        "face_regions": {
            "cross": "十字交叉贴图：中央 2-3 像素菌柄，上方 6-8 像素半圆菌盖，菌盖下沿 1-2 像素菌褶；整体是蘑菇剪影，不是树苗/叶冠。",
        },
        "visual_goals": [
            "cross 形状 mask 应为 16x16 小蘑菇剪影：菌盖半圆 + 菌柄，高度约 8-11 像素；",
            "cross 菌盖用 red_mushroom 系红色 #E21212/#C41D26/#A9121A，边缘深色；",
            "cross 菌盖下沿画 1-2 像素白色/米色菌褶 #E3DDBA/#CFC47F；",
            "cross 菌柄用 brown_mushroom 系浅褐/褐色 #CC9978/#916D55/#725643；",
            "cross 保持透明背景，不出现树苗的枝干/叶冠/草丛。",
        ],
        "minecraft_reference": "red_mushroom（菌盖红/菌褶白）、brown_mushroom（菌柄褐/菌盖棕）、cross 仅借用十字交叉渲染形式",
        "avoid": [
            "不要复制原版 birch_sapling.png 的逐像素图案；",
            "不要画成大树苗：必须有明显菌盖+菌柄蘑菇剪影，不是树苗叶冠；",
            "不要画成普通蘑菇方块：保留 cross 透明剪影，不铺满 16x16；",
            "不要用大块纯绿：本资源内容为蘑菇，红色/褐色为主。",
        ],
        "palette_scheme": _make_palette_scheme(
            base="#C41D26",
            light="#FFB4B0",
            dark="#8E1016",
            accent="#E3DDBA",
            outline="#5A3B1A",
            border_note="菌盖外轮廓 1px 深红/暗褐；菌褶与菌柄用米白/褐色自然分隔，不做均匀黑框。",
            saturation_note="菌盖红、菌柄褐均为中低饱和大地色，避免荧光和刺眼亮色。",
        ),
        "shape_pattern": _make_shape_pattern(
            silhouette="小蘑菇剪影：半圆菌盖 + 菌柄，高度约 8-11 像素；cross 只是展示形式。",
            parts=["cap 菌盖", "gills 菌褶", "stem 菌柄"],
            border="菌盖边缘 1px 深色；菌褶下沿 1px 米白；菌柄两侧深褐。",
            shading="菌盖左上高光、右下暗面；菌柄左亮右暗。",
            detail_pattern="菌盖 1px 噪点/少量斑点；菌褶横向 1px 线条。",
            shape_lock_optional=True,
            part_pattern_flow=[
                {"part": "cap 菌盖", "shape": "半圆伞面", "pattern": "红色系 + 白色斑点 + 左上高光", "flow": "斑点沿伞面弧线分布，高光带沿伞面左上到右下走势。"},
                {"part": "gills 菌褶", "shape": "菌盖下沿弧线", "pattern": "米白/褐色 1px 菌褶", "flow": "菌褶线沿下沿弧线排列，随伞缘弯曲。"},
                {"part": "stem 菌柄", "shape": "竖向菌柄", "pattern": "浅褐/褐色纵向纹理", "flow": "纵向纹理沿菌柄走向，左亮右暗表现圆柱体积。"},
            ],
            integration_note="菌盖放射/晕斑、菌褶弧线、菌柄纵向纹理都必须贴合对应部件的形状走向；纹样不得脱离形状独立存在。",
        ),
        "reference_nodes": [
            {"asset": "birch_sapling", "role": "shape", "reason": "仅参考 cross 十字交叉渲染形式/尺度，不锁树苗形状，不复制像素。"},
            {"asset": "red_mushroom", "role": "color", "reason": "菌盖红+菌褶白+菌柄褐的完整配色参考。"},
            {"asset": "brown_mushroom", "role": "pattern", "reason": "菌盖斑点/菌柄纹理与低饱和大地色参考。"},
            {"asset": "red_mooshroom", "role": "border", "reason": "生物体红色暗部/自然边界参考（非硬性指标）。"},
        ],
    }


# ---------------------------------------------------------------------------
# 通用 fallback：任意 query 也能产出具体、非空的概念卡
# ---------------------------------------------------------------------------

def _generic_card(
    query: str,
    retrieval: dict | None,
    form: str,
    template: str | None = None,
) -> dict:
    anchors = _anchor_summary(retrieval)
    parts = list(anchors["parts"]) or ["主体"]
    extra_parts, pattern_override = _pattern_intent(query)
    for p in extra_parts:
        if p not in parts:
            parts.append(p)
    # 去重/去掉 “主体” 这种占位重复
    seen = set()
    clean_parts = []
    for p in parts:
        base = p.replace(" 主体", "").strip()
        if base and base not in seen:
            seen.add(base)
            clean_parts.append(base)
    parts = clean_parts or parts
    # 从 form 决定 face_regions
    if form == "block_custom":
        keys = _block_custom_texture_keys(template or "anvil")
        face_regions = {
            k: "%s：参考检索特征（%s）进行绘制，保持该面在原版模板中的几何角色。"
               % (k, "；".join(anchors["pattern"]) or anchors["shape"][0] if anchors["shape"] else "自定义图案")
            for k in keys
        }
    else:
        default_faces = _FORM_DEFAULT_FACES.get(form, [("sprite", "单张贴图")])
        face_regions = {
            fid: desc + "；主题：%s" % ("；".join(anchors["pattern"]) or anchors["shape"][0] if anchors["shape"] else "检索特征")
            for fid, desc in default_faces
        }

    colors = anchors["colors"] or []
    color_hint = " ".join(colors[:5]) if colors else "使用检索调色板"
    shape_hint = "；".join(anchors["shape"]) if anchors["shape"] else form
    pattern_hint = pattern_override or ("；".join(anchors["pattern"]) if anchors["pattern"] else "无明显图案")
    # 弓类形状规范：用 idle bow（未拉开），不要用 bow_pulling_* 的满弦形态。
    if "弓" in query or "bow" in query.lower():
        shape_hint = "未拉开的弓：沿左下→右上的一条细弓弧（弓臂 1-2px），外侧一条 1px 灰色虚线弦；弓臂与弦之间有大量透明负空间；眼球嵌在弓弧中部（1-2px）。参考原版 idle bow.png，不要用 bow_pulling_*。"
        pat_extra = "弓弦为虚线（1px 灰），弓臂木质/能量材质，中央透明；眼球做小区域视觉焦点。"
        if pattern_override:
            pattern_hint = pattern_override + "；" + pat_extra
        else:
            pattern_hint = pat_extra
    goals = []
    if form == "block_custom":
        keys = list(face_regions.keys())
        for idx, k in enumerate(keys, 1):
            goals.append(
                "%s 使用 %s 作为主色，保留原版 %s 模板的功能分区；%s。"
                % (k, color_hint, template or "block_custom",
                   ("参考纹理：%s" % "；".join(anchors["pattern"])) if anchors["pattern"] else "图案需与检索特征一致")
            )
    else:
        for fid, _ in face_regions.items():
            goals.append(
                "%s 使用 %s 配色，绘制%s；轮廓/剪影保持 %s。"
                % (fid, color_hint, pattern_hint,
                   ("；".join(anchors["shape"]) or "原版同类形态"))
            )

    ref_names = []
    for a in (retrieval or {}).get("anchors", []) or []:
        n = a.get("name")
        if n and n not in ref_names:
            ref_names.append(n)
    if not ref_names:
        ref_names = ["同类原版资源"]
    minecraft_reference = "；".join(ref_names)

    base_color = colors[0] if len(colors) >= 1 else "#8A8A8A"
    light_color = colors[1] if len(colors) >= 2 else "#C0C0C0"
    dark_color = colors[2] if len(colors) >= 3 else "#3A3A3A"
    accent_color = colors[3] if len(colors) >= 4 else "#B8942B"
    outline_color = colors[4] if len(colors) >= 5 else "#222222"

    return {
        "item_name": "%s (%s)" % (
            query,
            " ".join((retrieval or {}).get("query_terms", {}).get("english", [])[:3]) or "Custom Minecraft Asset"
        ),
        "description": "一个基于检索特征生成的 Minecraft %s；它是%s，包含%s。" % (
            form,
            shape_hint,
            ("、".join(parts)),
        ),
        "parts": ["%s 主体" % p if p else "主体" for p in parts],
        "face_regions": face_regions,
        "visual_goals": goals,
        "minecraft_reference": minecraft_reference,
        "avoid": [
            "不要复制任何参考贴图的逐像素图案；",
            "不要画成与检索主题无关的物体；",
            "不要把 query 画成检索锚点的形状/语义；参考节点只允许提供配色/材质/明暗/尺度。",
            "不要丢失 %s 的几何/形式特征。" % form,
        ],
        "palette_scheme": _make_palette_scheme(
            base=base_color,
            light=light_color,
            dark=dark_color,
            accent=accent_color,
            outline=outline_color,
            border_note="外轮廓 1px 深色；不同部件之间用暗色/色差自然分隔。",
            saturation_note="整图保持中等以下饱和度，局部亮面只作 1px 提示，避免荧光刺眼。",
        ),
        "shape_pattern": _make_shape_pattern(
            silhouette=shape_hint,
            parts=parts,
            border="沿外轮廓 1px 深色描边；部件接缝用暗色分隔。",
            shading="左上偏亮、右下偏暗；内部用 1px 色阶表现体积。",
            detail_pattern=pattern_hint,
            shape_lock_optional=True,
            part_pattern_flow=[
                {
                    "part": p,
                    "shape": "部件轮廓/结构",
                    "pattern": pattern_hint,
                    "flow": "纹样沿该部件轮廓/明暗面走向贴合，不脱离形状独立存在。",
                }
                for p in parts[:4]
            ],
            integration_note="先用形状确定结构，再让纹样贴合每个部件的走向/边缘/明暗面；纹样不得脱离形状独立存在。",
        ),
        "reference_nodes": _reference_nodes_from_retrieval(retrieval),
    }


# 已知 query 卡片生成函数；若匹配，则返回 bank 卡并叠加 retrieval 字段。
_KNOWN_CARD_BUILDERS = {
    "蘑菇铁砧": _card_mushroom_anvil,
    "异形水晶法杖": _card_alien_crystal_wand,
    "蘑菇树苗": _card_mushroom_sapling,
    "蘑菇幼苗": _card_mushroom_sprout,
}

# 通用设计原则：每个物体都适用的整体构图/参考资源原则。
# 这些原则与“通用像素细节”配合使用；concept_grounder、build_style_prompt 和
# run_pipeline 共用，避免各处 prompt 口径漂移。
GENERIC_DESIGN_PRINCIPLES = [
    "整体方向统一：所有部件沿同一主方向/轴线；附属物方向与主体一致或围绕主体自然分叉，禁止主体与附属朝向相反。",
    "连接点自然：部件相接处与主轴/重心对齐，不悬空、不偏心、不错位。",
    "剪影可辨：只看形状也能认出“这是什么”；部件之间用描边/色差/空隙区分，不要糊成实心团块。",
    "纹样贴合形状：纹理/高光/图案沿部件的走向与明暗面流动，不脱离形状。",
    "细长部件：所有细长部件（杆/柄/弦/茎/边框等）宽度控制在 1~2px，不能糊成 3px 以上实心色带。",
    "负空间：部件之间与内部孔洞保留至少 1px 透明负空间（block_multi 整面不透明方块除外），避免实心团块。",
    "禁止实心团块：主体必须有内部明暗/纹理/负空间，不能无细节地满涂成一个大色块。",
    "参考完整资源：不要只看单张示例图；方块类要同时理解顶/侧/底三面、模型与 blockstate 契约，实体要按标准 UV 图集/区域语义理解，多面/实体统一走结构化输出。",
]

# 通用像素细节规则：不绑定任何具体物品/材质/形状，只描述 Minecraft 像素资产的
# 共同设计约束。concept_grounder、build_style_prompt 和 run_pipeline 共用这一份，
# 避免各处 prompt 口径漂移。
GENERIC_PIXEL_DETAIL_RULES = [
    "边框/描边：外轮廓用 1px 深色描边；部件接缝用暗色分隔；不做均匀黑框。",
    "材质高光：亮部高光沿形状走向，暗部在背光侧；金属/木/石/发光/软质等不同材质按语义推理使用不同高光强度与纹理提示，不给死例子。",
    "纹理：材质纹理（木纹/石裂纹/金属划痕/发光颗粒等）贴合形状；若原版有参考就参考其质感，没有就自行推理合理材质。",
    "明暗分层：每个部件至少 base/light/dark 三档色阶；用 1px 明暗过渡表现体积，避免平涂。",
    "方向/连接：整体方向一致，部件连接自然、不悬空。",
    "细长部件：所有细长部件（杆/柄/弦/茎/边框等）宽度控制在 1~2px，必要时保留内部明暗/细节，不能糊成 3px 以上实心色带。",
    "负空间（透明/镂空）：透明间隙和内部镂空是像素资产的一部分；部件之间与内部孔洞保留至少 1px 透明负空间（block_multi 整面不透明方块除外），避免实心团块。",
    "禁止实心团块：主体必须有内部结构（明暗/纹理/负空间），不能无细节地满涂成一个大色块；轮廓/部件间用描边或透明间隙区分。",
    "透明边距（物品/植物/实体图集）：非方块多面纹理（item/cross/entity_uv）与画布四边保留至少 1px 透明边距；block_multi 的 top/side/bottom 例外，必须是 16x16 全不透明且边缘连续。",
]


def _make_design_checklist(card: dict) -> list[dict]:
    """通用设计自检清单：生成前必须逐项自查，方位/连接/构图归设计环节统一负责。"""
    form = card.get("form", "item")
    checks = [
        {
            "id": "orientation",
            "item": "方位/构图一致性",
            "must": "所有部件沿同一条构图轴/方向，主体朝向一致；禁止出现‘手柄斜、头部正’、部件各朝各的现象。",
            "self_check": "画之前先用一句话描述整体轴线（如左下→右上），再检查每个部件是否落在这条轴上。",
        },
        {
            "id": "connection",
            "item": "连接点对齐",
            "must": "部件之间的连接点与主轴/中心对齐，不偏心、不悬空、不错位。",
            "self_check": "检查杖头/部件是否锚定在手柄/主体的顶端端点，连接处是否位于轴线上。",
        },
        {
            "id": "semantic",
            "item": "语义可辨",
            "must": "16x16 剪影一眼能看出‘这是什么’；主体清晰，不依赖文字说明。",
            "self_check": "遮住颜色只看 alpha 剪影，仍能认出物品/方块/十字植物语义。",
        },
        {
            "id": "segment_border",
            "item": "外轮廓描边与部件接缝",
            "must": "外轮廓用 1px 深色描边，部件接缝用暗色分隔；不做均匀黑框。",
            "self_check": "检查外轮廓像素是否为 1px 深色/暗色，部件交界处是否有暗色缝。",
        },
        {
            "id": "material_highlight",
            "item": "材质高光方向",
            "must": "亮部高光沿形状走向，暗部在背光侧；不同材质（金属/木/石/发光/软质）用不同高光强度与纹理提示，由模型根据语义推理，不给死例子。",
            "self_check": "每个部件先标出受光面/背光面，再检查高光与暗部是否沿形状方向流动。",
        },
        {
            "id": "material_texture",
            "item": "材质纹理贴合",
            "must": "材质纹理（木纹/石裂纹/金属划痕/发光颗粒等）贴合形状；若原版有参考就参考其质感，没有就自行推理合理材质。",
            "self_check": "纹理是否沿部件边缘/走向/明暗面分布，不横跨形状乱画。",
        },
        {
            "id": "palette",
            "item": "配色层次",
            "must": "包含 base/light/dark/outline；每个部件至少 base/light/dark 三档色阶；有明暗体积和自然描边，避免荧光平涂。",
            "self_check": "每个部件至少有亮部/暗部/描边三档色阶；饱和度不过高。",
        },
        {
            "id": "pattern_flow",
            "item": "纹样与形状一体",
            "must": "纹样沿形状的走向/边缘/明暗面流动，不脱离形状独立存在。",
            "self_check": "逐部件核对 part_pattern_flow：纹样方向是否与部件形状一致。",
        },
        {
            "id": "frame",
            "item": "边框/背景",
            "must": "透明背景、主体不贴边、不留明显空洞；%s 尺寸内主体占位合理（约 8~14px）。" % ("16x16" if form != "entity_uv" else "64x32"),
            "self_check": "检查 bbox 是否居中、四周是否留至少 1px 透明边。",
        },
    ]
    return checks


def _enrich_card(card: dict, retrieval: dict | None, form: str, template: str | None) -> dict:
    """在卡片上补充来源/检索/形式信息，便于追踪与集成。"""
    card = dict(card)
    card["form"] = form
    card["query"] = (retrieval or {}).get("query") or card.get("query") or ""
    card["source"] = "concept_grounder:offline_rule"
    card["method"] = "rule"
    card["method_note"] = "内置中文关键词+原版模板特征，未调用外部 LLM 子代理；离线可复现。"
    if template:
        card["block_template"] = template
    if retrieval:
        card["retrieval_anchor_count"] = len(retrieval.get("anchors", []) or [])
    # v5 设计字段兜底：任何旧/自定义卡片只要缺字段，就用检索特征补出非空设计卡。
    if not isinstance(card.get("palette_scheme"), dict) or not _is_nonempty_palette(card["palette_scheme"]):
        card["palette_scheme"] = _make_palette_scheme(
            base="#8A8A8A", light="#C0C0C0", dark="#3A3A3A",
            accent="#B8942B", outline="#222222",
            border_note="外轮廓 1px 深色；部件之间用暗色/色差自然分隔。",
            saturation_note="保持中等以下饱和度，避免荧光刺眼。",
        )
    if not isinstance(card.get("shape_pattern"), dict) or not _is_nonempty_shape_pattern(card["shape_pattern"]):
        card["shape_pattern"] = _make_shape_pattern(
            silhouette=form,
            parts=card.get("parts", ["主体"]),
            border="沿外轮廓 1px 深色描边；部件接缝用暗色分隔。",
            shading="左上偏亮、右下偏暗；内部用 1px 色阶表现体积。",
            detail_pattern="检索图案/部件纹理",
            shape_lock_optional=True,
        )
    if not card.get("reference_nodes"):
        card["reference_nodes"] = _reference_nodes_from_retrieval(retrieval)
    card["design_checklist"] = _make_design_checklist(card)
    return card


def _is_nonempty_palette(value) -> bool:
    return isinstance(value, dict) and all(
        value.get(k)
        for k in ("base", "light", "dark", "accent", "outline", "border_note", "saturation_note")
    )


def _is_nonempty_shape_pattern(value) -> bool:
    return (
        isinstance(value, dict)
        and value.get("silhouette")
        and value.get("parts")
        and value.get("border")
        and value.get("shading")
        and value.get("detail_pattern")
        and isinstance(value.get("shape_lock_optional"), bool)
        and isinstance(value.get("part_pattern_flow"), list)
        and len(value.get("part_pattern_flow", [])) >= 1
        and bool(value.get("integration_note"))
    )


def build_concept_card(
    query: str,
    retrieval_data: dict | None = None,
    retrieval_path: str | Path | None = None,
    form: str = "auto",
    template: str | None = None,
) -> dict:
    """生成概念卡。

    - retrieval_data 优先；缺失时读取 retrieval_path；再缺失时调用 retrieve_assets。
    - form 支持 item/block_multi/cross/entity_uv/block_custom。
    """
    query = (query or "").strip()
    if not query:
        raise ValueError("--query is required")

    ret: dict | None = retrieval_data
    if ret is None and retrieval_path:
        ret = _load_json(normalize_path(retrieval_path))
    if ret is None:
        ret, _ = _load_or_generate_retrieval(None, query, form)

    # 形式判定：显式 form 优先，否则取 retrieval.form；再 fallback item
    if form in (None, "", "auto"):
        form = ret.get("form") or "item"
    if form not in _VALID_FORMS:
        raise ValueError("unsupported form: %r (must be one of %s)" % (form, "/".join(_VALID_FORMS)))

    # block_custom 模板推断
    block_template = None
    if form == "block_custom":
        block_template = _infer_block_template(query, ret, template)

    if query in _KNOWN_CARD_BUILDERS:
        card = _KNOWN_CARD_BUILDERS[query](ret)
    else:
        card = _generic_card(query, ret, form, block_template)

    return _enrich_card(card, ret, form, block_template)


# ---------------------------------------------------------------------------
# CLI 自检
# ---------------------------------------------------------------------------

SELF_TEST_PRESETS = [
    {
        "query": "蘑菇铁砧",
        "form": "block_custom",
        "retrieval": "retrieval_examples/mushroom_anvil.json",
        "slug": "mushroom_anvil",
    },
    {
        "query": "异形水晶法杖",
        "form": "item",
        "retrieval": "retrieval_examples/alien_crystal_wand.json",
        "slug": "alien_crystal_wand",
    },
    {
        "query": "蘑菇树苗",
        "form": "cross",
        "retrieval": "retrieval_examples/mushroom_sapling.json",
        "slug": "mushroom_sapling",
    },
    {
        "query": "蘑菇幼苗",
        "form": "cross",
        "retrieval": "retrieval_examples/mushroom_sprout.json",
        "slug": "mushroom_sprout",
    },
]


def _ensure_retrieval_file(preset: dict) -> Path:
    """若 retrieval 文件不存在，用 retrieve_assets 生成并保存。

    核心仓库没有 mc_asset_library/library-index.json 时，自动使用
    retrieve_assets 的合成迷你索引（纯代码生成、非原版素材）。
    """
    rel = Path(preset["retrieval"])
    path = _THIS_DIR / rel if not (normalize_path(rel).is_absolute()) else normalize_path(rel)
    if path.exists():
        return path
    import shutil
    import retrieve_assets as ra
    # block_custom 不是 retrieve_assets CLI choices 但 retrieve() 内部接受，
    # 这里用显式 form 保证检索文件与概念卡一致。
    forced = None if preset["form"] in ("auto", None) else preset["form"]
    synthetic_tmp = None
    if ra._INDEX_PATH.exists():
        index = ra.load_index()
    else:
        index, synthetic_tmp = ra._build_synthetic_selftest_index()
    try:
        result = ra.retrieve(preset["query"], top=3, form=forced, index=index)
    finally:
        if synthetic_tmp is not None:
            shutil.rmtree(synthetic_tmp, ignore_errors=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    log_message("generated retrieval example: %s (query=%r form=%s)" % (
        path, preset["query"], result["form"]
    ))
    return path


def _validate_concept_card(card: dict) -> list[str]:
    """校验概念卡字段非空且具体。"""
    checks = []
    required = [
        "item_name", "description", "parts", "face_regions",
        "visual_goals", "minecraft_reference", "avoid",
    ]
    missing = [k for k in required if not card.get(k)]
    if missing:
        raise ValueError("concept card missing fields: %s" % ", ".join(missing))
    checks.append("all required fields present")

    if len(card["parts"]) < 2:
        raise ValueError("parts must have at least 2 entries")
    checks.append("parts non-empty (%d entries)" % len(card["parts"]))

    if not isinstance(card["face_regions"], dict) or not card["face_regions"]:
        raise ValueError("face_regions must be a non-empty dict")
    for fid, desc in card["face_regions"].items():
        if not str(desc).strip():
            raise ValueError("face_regions[%r] is empty" % fid)
        if len(str(desc)) < 12:
            raise ValueError("face_regions[%r] too vague: %r" % (fid, desc))
    checks.append("face_regions non-empty and specific (%d faces)" % len(card["face_regions"]))

    if len(card["visual_goals"]) < 1:
        raise ValueError("visual_goals must be non-empty")
    for i, g in enumerate(card["visual_goals"]):
        if len(str(g).strip()) < 15:
            raise ValueError("visual_goals[%d] too vague: %r" % (i, g))
    checks.append("visual_goals non-empty and specific (%d goals)" % len(card["visual_goals"]))

    if len(str(card["minecraft_reference"]).strip()) < 5:
        raise ValueError("minecraft_reference too vague")
    checks.append("minecraft_reference present and specific")

    if len(card["avoid"]) < 1:
        raise ValueError("avoid must be non-empty")
    checks.append("avoid non-empty (%d entries)" % len(card["avoid"]))

    # v5 设计字段：palette_scheme / shape_pattern / reference_nodes
    ps = card.get("palette_scheme")
    if not isinstance(ps, dict):
        raise ValueError("palette_scheme must be an object")
    for field in ("base", "light", "dark", "accent", "outline", "border_note", "saturation_note"):
        if not ps.get(field):
            raise ValueError("palette_scheme missing field %r" % field)
    checks.append("palette_scheme has base/light/dark/accent/outline/border_note/saturation_note")

    sp = card.get("shape_pattern")
    if not isinstance(sp, dict):
        raise ValueError("shape_pattern must be an object")
    for field in ("silhouette", "parts", "border", "shading", "detail_pattern",
                  "shape_lock_optional", "part_pattern_flow", "integration_note"):
        if field not in sp:
            raise ValueError("shape_pattern missing field %r" % field)
    if not sp.get("silhouette") or not sp.get("parts") or not sp.get("border"):
        raise ValueError("shape_pattern silhouette/parts/border must be non-empty")
    if not isinstance(sp.get("shape_lock_optional"), bool):
        raise ValueError("shape_pattern.shape_lock_optional must be bool")
    ppf = sp.get("part_pattern_flow")
    if not isinstance(ppf, list) or len(ppf) < 1:
        raise ValueError("shape_pattern.part_pattern_flow must be a non-empty list")
    for i, item in enumerate(ppf, 1):
        if not isinstance(item, dict) or not item.get("part") or not item.get("shape") or not item.get("pattern") or not item.get("flow"):
            raise ValueError("shape_pattern.part_pattern_flow[%d] must contain part/shape/pattern/flow" % i)
    if not sp.get("integration_note"):
        raise ValueError("shape_pattern.integration_note must be non-empty")
    checks.append("shape_pattern has integrated part_pattern_flow + integration_note")

    refs = card.get("reference_nodes")
    if not isinstance(refs, list) or len(refs) < 3:
        raise ValueError("reference_nodes must be a list with at least 3 entries")
    if len(refs) > 8:
        raise ValueError("reference_nodes supports 3..8 nodes, got %d" % len(refs))
    for i, node in enumerate(refs, 1):
        if not isinstance(node, dict):
            raise ValueError("reference_nodes[%d] must be an object" % i)
        for field in ("asset", "role", "reason"):
            if not node.get(field):
                raise ValueError("reference_nodes[%d] missing %r" % (i, field))
        if node["role"] not in ("shape", "color", "pattern", "border", "material"):
            raise ValueError("reference_nodes[%d] role invalid: %r" % (i, node["role"]))
    checks.append("reference_nodes 3..8 entries with asset/role/reason (%d nodes)" % len(refs))

    chk = card.get("design_checklist")
    if not isinstance(chk, list) or len(chk) != 9:
        raise ValueError(
            "design_checklist must contain 9 items (got %d)"
            % (len(chk) if isinstance(chk, list) else 0)
        )
    for i, item in enumerate(chk, 1):
        if not isinstance(item, dict) or not item.get("item") or not item.get("must") or not item.get("self_check"):
            raise ValueError("design_checklist[%d] must contain item/must/self_check" % i)
    checklist_ids = {c.get("id") for c in chk}
    required_ids = ("segment_border", "material_highlight", "material_texture")
    missing_ids = [rid for rid in required_ids if rid not in checklist_ids]
    if missing_ids:
        raise ValueError(
            "design_checklist missing border/highlight/texture entry: %s"
            % ", ".join(missing_ids)
        )
    checklist_items = "\n".join(c.get("item", "") for c in chk)
    required_labels = ("描边", "高光", "纹理")
    missing_labels = [label for label in required_labels if label not in checklist_items]
    if missing_labels:
        raise ValueError(
            "design_checklist entries missing required concepts: %s"
            % ", ".join(missing_labels)
        )
    checks.append("design_checklist orientation/connection/border/highlight/texture/palette/pattern/frame (%d items)" % len(chk))
    return checks


def run_self_test() -> int:
    """生成示例概念卡并校验，同时写出自检报告与日志。"""
    _CONCEPT_DIR.mkdir(parents=True, exist_ok=True)
    report_lines = ["# concept_grounder.py self-test", ""]
    all_pass = True
    total_checks = 0
    for preset in SELF_TEST_PRESETS:
        query = preset["query"]
        form = preset["form"]
        out_name = "%s.json" % preset["slug"]
        try:
            ret_path = _ensure_retrieval_file(preset)
            card = build_concept_card(
                query=query,
                retrieval_path=ret_path,
                form=form,
            )
            out_path = _CONCEPT_DIR / out_name
            _write_json(card, out_path)
            checks = _validate_concept_card(card)
            total_checks += len(checks)
            report_lines.append("## %s" % query)
            report_lines.append("- file: %s" % out_path)
            report_lines.append("- item_name: %s" % card["item_name"])
            report_lines.append("- description: %s" % card["description"])
            report_lines.append("- parts: %s" % "；".join(card["parts"]))
            report_lines.append("- face_regions: %s" % "; ".join(
                "%s=%s" % (k, v) for k, v in card["face_regions"].items()
            ))
            report_lines.append("- visual_goals: %s" % " | ".join(card["visual_goals"]))
            report_lines.append("- minecraft_reference: %s" % card["minecraft_reference"])
            report_lines.append("- avoid: %s" % "; ".join(card["avoid"]))
            report_lines.append("- palette_scheme: base=%s light=%s dark=%s accent=%s outline=%s" % (
                card["palette_scheme"]["base"], card["palette_scheme"]["light"],
                card["palette_scheme"]["dark"], card["palette_scheme"]["accent"],
                card["palette_scheme"]["outline"],
            ))
            report_lines.append("- shape_pattern: silhouette=%s | shape_lock_optional=%s" % (
                card["shape_pattern"]["silhouette"], card["shape_pattern"]["shape_lock_optional"],
            ))
            report_lines.append("- shape_pattern.part_pattern_flow: %d flows %s" % (
                len(card["shape_pattern"]["part_pattern_flow"]),
                "；".join("%s->%s" % (x["part"], x["flow"]) for x in card["shape_pattern"]["part_pattern_flow"]),
            ))
            report_lines.append("- reference_nodes: %d nodes %s" % (
                len(card["reference_nodes"]),
                "；".join("%s(%s)" % (n["asset"], n["role"]) for n in card["reference_nodes"]),
            ))
            for c in checks:
                report_lines.append("  PASS: %s" % c)
            report_lines.append("  wrote: %s" % out_path)
            report_lines.append("")
            log_message("self-test OK: query=%r form=%s file=%s checks=%d" % (
                query, form, out_path, len(checks)
            ))
        except Exception as e:  # noqa: BLE001
            all_pass = False
            report_lines.append("## %s" % query)
            report_lines.append("  FAIL: %s" % e)
            report_lines.append("")
            log_message("self-test FAIL: query=%r error=%s" % (query, e))

    if all_pass:
        report_lines.append("summary: PASS (%d cards, %d checks)" % (
            len(SELF_TEST_PRESETS), total_checks))
        log_message("SELF-TEST: PASS (%d cards)" % len(SELF_TEST_PRESETS))
        rc = 0
    else:
        report_lines.append("summary: FAIL")
        log_message("SELF-TEST: FAIL")
        rc = 1

    _SELFTEST_REPORT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print("\n".join(report_lines))
    return rc


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="v4-concept: 生成语义概念卡（先理解再生成）。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--query", help="中文/英文想法，例如 蘑菇铁砧")
    parser.add_argument("--retrieval", default=None,
                        help="已有 retrieval JSON，例如 retrieval_examples/mushroom_anvil.json")
    parser.add_argument("--form", default="auto",
                        choices=list(_VALID_FORMS) + ["auto"],
                        help="形式：item|block_multi|cross|entity_uv|block_custom")
    parser.add_argument("--template", default=None,
                        help="block_custom 模板：anvil|slab|door|stairs|fence|wall|chest|flower_pot")
    parser.add_argument("--out", default=None,
                        help="输出 concept card JSON 路径（默认 concept_examples/<slug>.json）")
    parser.add_argument("--self-test", action="store_true",
                        help="生成示例概念卡并校验")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    if not args.query:
        parser.error("--query is required (or use --self-test)")

    ret_path = args.retrieval
    if ret_path:
        ret_path = normalize_path(ret_path)
    ret_data = None
    if ret_path and ret_path.exists() is False:
        # 不自动生成到不存在的用户指定路径；直接报错更明确
        raise SystemExit("--retrieval not found: %s" % ret_path)
    if ret_path and ret_path.exists():
        ret_data = _load_json(ret_path)

    # 生成卡片
    card = build_concept_card(
        query=args.query,
        retrieval_data=ret_data,
        retrieval_path=None if ret_data is not None else (str(ret_path) if ret_path else None),
        form=args.form,
        template=args.template,
    )

    if args.out:
        out_path = normalize_path(args.out)
        if not out_path.is_absolute():
            out_path = _THIS_DIR / out_path
    else:
        # 用 retrieval 或 query 推断 slug
        slug = slugify(args.query, ret_data or {})
        out_path = _CONCEPT_DIR / ("%s.json" % slug)

    _write_json(card, out_path)
    print("concept card: %s" % out_path)
    for k in ("item_name", "description", "minecraft_reference"):
        print("%s: %s" % (k, card[k]))
    print("parts: %d, face_regions: %d, visual_goals: %d" % (
        len(card["parts"]), len(card["face_regions"]), len(card["visual_goals"])
    ))
    log_message("OK: query=%r form=%s out=%s" % (args.query, card["form"], out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
