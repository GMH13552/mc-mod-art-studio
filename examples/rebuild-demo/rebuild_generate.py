#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
s3-rebuild generator: redo 4 demos using the s2 silhouette bank.

Uses:
  - local full-library vanilla PNGs only as text/silhouette references (not copied into repo)
  - reference_analyzer.build_silhouette_bank -> prompt contains 2-4 silhouette candidates per part
  - promise/contract: "可选一个 / 可组合多个 / 可大改 / 禁止当最终网格"
  - demon_cow is entity_uv 64x32 (cow/red_mooshroom template), not an item icon
  - LLM (deepseek-chat) called via llm_client.py; no vision model in this env, so text silhouette bank is used.

Run from repo root:
  set -a; source /tmp/mc_llm.env; set +a
  python3 examples/rebuild-demo/rebuild_generate.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import concept_grounder as cg  # noqa: E402
import reference_analyzer as refa  # noqa: E402
import build_style_prompt as bsp  # noqa: E402
import retrieve_assets as ra  # noqa: E402
import text_to_texture as t2t  # noqa: E402
import entity_uv_spec as eu  # noqa: E402
import run_pipeline as rp  # noqa: E402

DEMO_DIR = ROOT / "examples" / "rebuild-demo"
INDEX = DEMO_DIR / "rebuild-index.json"
LLM_CMD = "python3 llm_client.py --prompt-file {prompt_file}"
MAX_ATTEMPTS = 3  # first try + up to 2 retries
NOVELTY = 0.9  # no full compact reference; still keeps silhouette bank

# ---------------------------------------------------------------------------
# Hand-written concept cards & source tables (updated for s3: silhouette notes)
# ---------------------------------------------------------------------------
ASSETS = [
    {
        "slug": "demon_cow",
        "name": "恶魔牛 (Demon Cow entity_uv)",
        "query": "恶魔牛实体：恶魔化牛实体，红色恶魔牛纹理，黑角黑眼窝，青色魂火点缀，按牛/红魔菌牛 64x32 实体模板改",
        "form": "entity_uv",
        "size": (64, 32),
        "references": ["cow.png", "red_mooshroom.png", "brown_mooshroom.png", "soul_fire_0.png", "soul_fire_1.png"],
        "description": (
            "一个恶魔化的牛实体纹理，替换原版 cow/red_mooshroom 的 64x32 atlas；"
            "保留牛的头/角/耳朵/鼻口/身体/腿的实体结构，配色改为暗红恶魔皮，角与眼窝用黑红，"
            "眼睛和角尖带青色魂火。整体是实体 UV 图集，不是 16x16 牛头图标。"
            "硬性：64x32 至少使用 4 种以上调色板索引；0 号只做描边/暗部；head/body/legs/角/眼都要有可见色阶与轮廓细节。"
        ),
        "parts": ["头 head", "角 horns", "耳朵 ears", "鼻口 muzzle", "眼睛/魂火 eyes", "身体 body", "腿 legs", "尾巴 tail"],
        "palette": {
            "base": "#A00F10", "light": "#E04A45", "dark": "#3A0708",
            "accent": "#01A7AC", "outline": "#171414",
            "border_note": "外轮廓 1px 深黑红 #171414；角/眼窝用更深 #2B0505；魂火用青色高光与白色核心。",
            "saturation_note": "红色保持暗红色相，不荧光；青色只作局部魂火，占比小。",
        },
        "shape": {
            "silhouette": "64x32 标准牛/红魔菌牛实体 atlas：头在左侧 32x16，身体在右 32x16，腿在左下半/身体下缘；必须参考 compact:cow.png/red_mooshroom.png 的 64x32 区域轮廓作为底，颜色/角/耳/眼/纹理重新画；每个 UV 区域都要有可见内容，不能只填一个颜色。",
            "orientation": "实体 UV 区域对齐原版硬编码采样坐标；头/角/耳在 head 区域，鼻口在 muzzle，身体在 body，腿在 legs，尾在 tail；允许 1px 不对称但区域不能错位。",
            "part_pattern_flow": [
                {"part": "头 head", "shape": "牛头（正面/侧面 UV 区域）", "pattern": "暗红皮 + 鼻梁高光 + 脸颊暗部；1px 深红描边", "flow": "沿头 UV 区域走；高光沿鼻梁纵向，暗部在脸颊两侧。"},
                {"part": "角 horns", "shape": "顶部双角", "pattern": "黑红角 + 角尖青色魂火", "flow": "角根与头连接，角尖朝上/两侧；魂火只点角尖。"},
                {"part": "耳朵 ears", "shape": "两侧耳朵", "pattern": "深红皮 + 内耳暗部", "flow": "耳根与头连接，不悬空。"},
                {"part": "鼻口 muzzle", "shape": "牛鼻口/嘴部区域", "pattern": "暗红皮 + 深色鼻孔", "flow": "位于 head 下方/muzzle 区域，轮廓圆钝。"},
                {"part": "眼睛/魂火 eyes", "shape": "两个发光眼", "pattern": "黑眼窝 + 青色魂火 + 白色核心", "flow": "左右对称；青色只作点缀，不大面积铺。"},
                {"part": "身体 body", "shape": "牛躯干 UV 区域", "pattern": "暗红皮 + 肌肉/鳞片/火焰纹理", "flow": "纹理沿身体走向，不覆盖原版 UV 区域边界。"},
                {"part": "腿 legs", "shape": "四条腿（原版左/右腿区域）", "pattern": "暗红皮 + 蹄部强化", "flow": "腿在 legs 区域，上下方向明确。"},
                {"part": "尾巴 tail", "shape": "牛尾", "pattern": "暗红皮 + 尾尖魂火", "flow": "尾在 tail 区域，从身体后部延伸。"},
            ],
        },
        "avoid": [
            "不要画成 16x16 居中牛头图标；这是 64x32 实体 atlas，必须按原版 cow/red_mooshroom 的 UV 区域展开。",
            "不要复制 cow.png / red_mooshroom.png 的逐像素图案。",
            "不要画成普通红牛；必须有黑角/黑眼窝与青色魂火点缀。",
            "禁止整张 64x32 只用一种索引/一种颜色；若全图同色或同索引即为失败。",
            "0 号索引只能用于描边和最深暗部，不能作为大面积底色；主色用 1/2/3 等索引。",
            "head/body/legs/角/眼等区域必须画出至少 2 个不同色阶，禁止区域留空成单色。",
        ],
        "source_table": [
            {"part": "头/角/耳/鼻口", "reference": "cow.png / red_mooshroom.png", "borrowed_texture": "牛皮分块、鼻梁高光、脸颊暗部、角/耳连接", "borrowed_palette": "恶魔红（#A00F10 / #E04A45 / #3A0708 / #171414）", "borrowed_structure": "64x32 head/horns/ears/muzzle 区域轮廓；角在头顶、耳在两侧、鼻口在下", "silhouette_changes": "保留牛头/角/鼻口轮廓基础，颜色与角型可大改；角可更弯/更长，眼窝改魂火。"},
            {"part": "身体/腿/尾", "reference": "cow.png / red_mooshroom.png", "borrowed_texture": "躯干肌肉分区、腿部深浅、尾巴走向", "borrowed_palette": "恶魔红 + 黑红暗部（#3A0708）；局部青色魂火", "borrowed_structure": "64x32 body/legs/tail 区域轮廓；身体在右侧、腿在左侧下半、尾在右后", "silhouette_changes": "保留躯干/腿/尾的实体比例，可加火焰/鳞片轮廓变化，但不能改成非牛生物。"},
            {"part": "魂火眼/角尖", "reference": "soul_fire_0.png / soul_fire_1.png", "borrowed_texture": "青绿色火焰形状、白核心、外发光", "borrowed_palette": "魂火青（#01A7AC / #00D5DA / #FFFFFF）", "borrowed_structure": "小面积尖焰/光点，不占满区域", "silhouette_changes": "只借火焰的局部形状/配色，不做整张火焰贴图；可在眼窝/角尖点 1-2px。"},
        ],
    },

    {
        "slug": "skeleton_staff",
        "name": "骷髅法杖 (Skeleton Staff)",
        "query": "骷髅法杖：顶端骷髅头要可辨眼窝/颌，杖柄要有手柄味（允许斜/粗/可大改）",
        "form": "item",
        "size": (16, 16),
        "references": ["skeleton.png", "bone_block_side.png", "bone_block_top.png", "stick.png", "oak_planks.png", "iron_sword.png", "carrot_on_a_stick.png"],
        "description": (
            "一根顶端镶着骷髅头的新法杖/权杖：上方是骨白色、带可辨眼窝与下颌暗示的骷髅头，"
            "下方是木质杖身/握柄；杖身可以斜、可以粗一点，但必须保留手柄感（木纹、粗细、握持段）。"
        ),
        "parts": ["骷髅头 skull", "眼窝/裂纹 eye sockets", "连接插座 socket", "杖身/握柄 handle"],
        "palette": {
            "base": "#E9E6D4", "light": "#FFFFFD", "dark": "#CBC6A5",
            "accent": "#896727", "outline": "#2E2E2E",
            "border_note": "骷髅外轮廓 1px 深灰 #2E2E2E；杖身用深褐描边；头与杖连接处用暗色插座分隔。",
            "saturation_note": "骨白保持低饱和、偏暖；木柄为暗棕；避免荧光白/荧光青。",
        },
        "shape": {
            "silhouette": "16x16 透明 item：竖直法杖（可略带 1-2px 斜度），顶部约 5-8px 为骷髅头（有眼窝/下颌暗示），中间为 1-3px 宽木杖，底部为握柄/尾端；整体居中，四边至少 1px 透明。",
            "orientation": "主方向为竖直/略斜；顶部在右上、底部在左下也可；沿一条连续轴线；骷髅头锚定在杖顶端，不许偏心。",
            "part_pattern_flow": [
                {"part": "骷髅头 skull", "shape": "圆/方头骨，眼窝大而深、下颌骨可辨", "pattern": "骨白底 + 深色眼窝 + 鼻洞/裂纹", "flow": "眼窝位于头骨中上部，左右对称但允许 1px 不对称；裂纹沿骨面走，不画成全身骨架。"},
                {"part": "眼窝/裂纹 eye sockets", "shape": "两个深色窝 + 1px 裂纹", "pattern": "深灰/黑灰", "flow": "眼窝用深灰黑填充，裂纹从眼窝/颧骨向外发散。"},
                {"part": "连接插座 socket", "shape": "骷髅头下的 1-3px 暗色小口/环", "pattern": "深灰/深褐", "flow": "插座包住杖顶端，与头骨底边对齐。"},
                {"part": "杖身/握柄 handle", "shape": "2-3px 宽木杖，底部可加粗手柄段；允许直线/微弯", "pattern": "木纹纵向 + 少量磨损；手柄段可用横向缠绕/加粗", "flow": "木纹沿杖身纵向；底端为握柄加粗段，与主轴对齐；有手柄味。"},
            ],
        },
        "avoid": [
            "不要画成完整骷髅或骷髅骑士；不要画成普通木棍：顶部必须有明显可辨骷髅头。",
            "不要画成光滑细直线：杖身要像有手柄的杖，而不是普通棍子。",
            "不要复制 skeleton.png / bone_block_side.png / stick.png 的逐像素图案。",
            "保持 16x16 透明背景、四边至少 1px 透明边距。",
        ],
        "source_table": [
            {"part": "骷髅头/眼窝", "reference": "skeleton.png (head region) / bone_block_side.png", "borrowed_texture": "骨白底、深色眼窝、骨裂纹", "borrowed_palette": "骨白（#E9E6D4 / #FFFFFD / #CBC6A5 / #2E2E2E）", "borrowed_structure": "原版骨架头骨轮廓 + 骨块裂纹节奏；眼窝位置在大约头骨中上部", "silhouette_changes": "只取头骨轮廓基础，明确要可辨眼窝/颌；眼窝可加大、下颌可加宽，允许大改。"},
            {"part": "连接插座", "reference": "bone_block_side.png / stick.png", "borrowed_texture": "骨质接缝/暗色小口/环", "borrowed_palette": "骨灰/深灰绿 #7B7E6B + 深褐 #493615", "borrowed_structure": "头骨与杖之间 1-3px 暗色小口/环", "silhouette_changes": "可做粗一点的插槽/环，增强连接感。"},
            {"part": "杖身/握柄", "reference": "stick.png / oak_planks.png / iron_sword.png", "borrowed_texture": "木纹纵向、磨损颗粒、剑柄/握柄段的分节", "borrowed_palette": "木棕（#493615 / #896727 / #281E0B）", "borrowed_structure": "细长杖身 + 握柄段（可加粗/分节）", "silhouette_changes": "允许杖身斜/粗，底部加粗手柄段；形状可大改，只要保留手柄味。"},
        ],
    },

    {
        "slug": "skinning_knife",
        "name": "剥皮小刀 (Skinning Knife)",
        "query": "剥皮小刀：新物品，短小刀身像刀，短柄，不是长剑/木棍",
        "form": "item",
        "size": (16, 16),
        "references": ["iron_sword.png", "stone_sword.png", "wooden_sword.png", "shears.png", "leather.png", "stick.png", "oak_planks.png"],
        "description": (
            "一把短柄剥皮/狩猎小刀：刀身短小、刀尖略微上翘，护手短窄，刀柄用皮革缠绕并露出木质芯；"
            "整体明显是一把小刀，不是长剑/大剑。"
            "硬性：必须包含完整刀柄（4-6px）；刀尖到柄尾整体至少 10px 高/长；刀刃短但可辨。"
        ),
        "parts": ["刀刃 blade", "护手/颈 guard", "刀柄 handle"],
        "palette": {
            "base": "#BEBEBE", "light": "#FFFFFF", "dark": "#444444",
            "accent": "#896727", "outline": "#181818",
            "border_note": "刀刃外轮廓 1px 深灰；刀柄用深褐描边；刃与柄之间用暗色护手分隔。",
            "saturation_note": "金属保持冷灰，刀柄为暖棕；两种材质用明度/色相自然区分，不做荧光。",
        },
        "shape": {
            "silhouette": "16x16 透明 item：短刀居中，刀尖朝上/右上，刀刃约占上 2/3（长度 6-9px），护手 1-2px，刀柄占下 1/3（4-6px）；四周至少 1px 透明边距，禁止贴边。",
            "orientation": "主方向为竖直/略斜的一条轴线；刀尖、刀刃、护手、刀柄沿同一轴线，连接点对齐；允许刀尖略微上翘。",
            "part_pattern_flow": [
                {"part": "刀刃 blade", "shape": "短小弯曲/上翘刀片（像刀，不像剑）", "pattern": "金属灰阶 + 1px 刃口高光 + 少量划痕", "flow": "高光沿刀刃弧度/刃线走；背光侧用深灰暗部；长度控制在小刀范围。"},
                {"part": "护手/颈 guard", "shape": "刀刃与刀柄之间的 1-2px 窄条", "pattern": "深灰/深褐分隔", "flow": "护手沿横向包住柄根，连接处与主轴对齐。"},
                {"part": "刀柄 handle", "shape": "2-3px 宽短柄，有皮革缠绳 + 木芯", "pattern": "皮革缠绳 + 木芯颗粒", "flow": "缠绳线沿柄的横向环绕，木纹沿柄的纵向；左亮右暗表现圆柱体积。"},
            ],
        },
        "avoid": [
            "不要画成长剑/大剑：刀刃长度必须短（6-9px），柄 4-6px。",
            "不要画成木棍/皮革靴；刀柄必须有皮革+木的复合感。",
            "不要复制 iron_sword.png 的逐像素/斜向满画布构图。",
            "保持 16x16 透明背景、四边至少 1px 透明边距。",
            "禁止只有刀刃没有手柄；手柄缺失即为失败。",
            "禁止过于空/只有几像素；不透明像素应 > 40 且整体 bbox 至少 10px 高。",
            "禁止把刀画成锯齿/镐/长剑；必须能看出是一把短刀。",
        ],
        "source_table": [
            {"part": "刀刃 blade", "reference": "iron_sword.png / stone_sword.png / shears.png", "borrowed_texture": "金属划痕、刃口高光、冷灰明暗", "borrowed_palette": "钢铁灰（#BEBEBE / #FFFFFF / #444444 / #181818）", "borrowed_structure": "候选：curved-blade（铁剑/石剑刃口微弧）、straight-tip（shears 直背短刃）、hook-tip（shears 上翘短刃）", "silhouette_changes": "只取短刃轮廓基础，明确缩小刀身；可大改刀刃弧度/上翘程度。"},
            {"part": "护手/颈 guard", "reference": "iron_sword.png / leather.png", "borrowed_texture": "深灰/深褐自然分隔", "borrowed_palette": "深灰 #444444 + 深褐 #3D1C10", "borrowed_structure": "刀刃与刀柄之间的 1-2px 横向窄条", "silhouette_changes": "短窄护手，不照抄剑护手。"},
            {"part": "刀柄 handle", "reference": "leather.png / stick.png / oak_planks.png", "borrowed_texture": "皮革缠绳 + 木芯颗粒", "borrowed_palette": "皮革棕（#9E492A / #C65C35 / #542716）+ 木芯 #896727", "borrowed_structure": "1-2px 宽短柄、缠绳横向、木纹纵向", "silhouette_changes": "可加粗到 2-3px 并加尾部，保留手柄手感。"},
        ],
    },

    {
        "slug": "villager_hide",
        "name": "村民皮 (Villager Hide)",
        "query": "村民皮：新物品，不规则皮/兔皮轮廓，毛边/纤维感，不是普通棕色方块",
        "form": "item",
        "size": (16, 16),
        "references": ["leather.png", "rabbit_hide.png", "villager.png", "stick.png", "oak_planks.png", "bone_block_side.png"],
        "description": (
            "一张被剥下并鞣制的村民皮/兽皮，作为自定义采集材料和掉落物；"
            "主体是不规则皮张（像 leather 或 rabbit_hide），带折痕、颗粒、接缝与毛边/纤维感，"
            "边缘露出灰褐色村民长袍织物带与缝线。16x16 内非满框矩形。"
            "硬性：皮张必须是不规则多边形/带毛边，禁止圆形/椭圆/正方形；边缘有 1px 锯齿或短纤维。"
        ),
        "parts": ["皮面主体 hide", "折痕/接缝 seams", "毛边/纤维 fringe", "织物内衬 cloth trim", "挂环/标签 hanger tag"],
        "palette": {
            "base": "#C65C35", "light": "#D76B43", "dark": "#542716",
            "accent": "#6F6D6A", "outline": "#3D1C10",
            "border_note": "外轮廓 1px 深褐；皮革与织物内衬用暗色缝隙分隔，不做均匀黑框。",
            "saturation_note": "整体保持中低饱和，皮革棕不荧光；灰褐织物作为次色。",
        },
        "shape": {
            "silhouette": "16x16 透明 item：中央是一块不规则皮张（非满框矩形），宽约 10-14px、高约 8-12px，边缘有毛边/纤维（1px 锯齿或窄条）；外轮廓必须参考 compact:rabbit_hide.png 剪影（不对称、有毛边），禁止画成对称椭圆/圆形；下缘/内侧露出窄条灰褐织物与 1px 缝线，上方有小挂环；整体居中，四边至少 1px 透明。",
            "orientation": "主方向为纵向（皮革主体在中央，织物内衬在下/侧），挂环朝上；所有部件沿同一中轴。",
            "part_pattern_flow": [
                {"part": "皮面主体 hide", "shape": "不规则皮张（不是脸/面具；参考 leather/rabbit_hide 轮廓）", "pattern": "皮革颗粒 + 1-2px 折痕高光 + 边缘深色包边/毛边", "flow": "折痕与高光沿皮面自然起伏走，不形成眼睛/鼻子/嘴巴；边缘用 1px 深褐描边 + 不规则锯齿。"},
                {"part": "折痕/接缝 seams", "shape": "1-2px 自然折痕/褶皱", "pattern": "深褐/暗红渐变", "flow": "折痕沿皮面内部走，不构成五官。"},
                {"part": "毛边/纤维 fringe", "shape": "皮张边缘的不规则毛边/纤维", "pattern": "1px 深褐/中褐短条", "flow": "沿皮张外轮廓发散，让皮张看起来不像矩形。"},
                {"part": "织物内衬 cloth trim", "shape": "皮面下缘/内侧的窄条织物", "pattern": "灰褐色布料 + 1px 缝线/针脚", "flow": "缝线沿织物条边缘走；布料与皮革之间留暗色接缝。"},
                {"part": "挂环/标签 hanger tag", "shape": "上缘 2-3px 小环或木牌", "pattern": "深色小节 + 1px 高光", "flow": "挂环与皮面连接自然，不悬空。"},
            ],
        },
        "avoid": [
            "不要画成普通棕色方块/满框矩形；必须是不规则皮张且有毛边/纤维。",
            "不要画成 villager 的头/身体/手臂，也不要画成原版 leather 物品。",
            "不要出现眼睛/鼻孔/嘴等脸部五官；这不是面具，是皮料/皮革。",
            "保持 16x16 透明背景、四边至少 1px 透明边距。",
            "禁止圆形/椭圆/正方形皮块；必须是不规则皮张并带毛边/纤维。",
            "禁止没有折痕/接缝；内部至少要有 2 道可见折痕/接缝。",
        ],
        "source_table": [
            {"part": "皮面主体 hide", "reference": "leather.png / rabbit_hide.png", "borrowed_texture": "皮革颗粒、折痕高光、不规则剥制边缘/毛边", "borrowed_palette": "皮革棕（#C65C35 / #D76B43 / #542716 / #3D1C10）", "borrowed_structure": "参考 leather/rabbit_hide 的不规则皮张轮廓（非满框矩形）", "silhouette_changes": "改用皮/兔皮轮廓，边缘加毛边；可大改比例，不要方形。"},
            {"part": "织物内衬 cloth trim", "reference": "villager.png", "borrowed_texture": "村民长袍布料层叠、缝线针脚质感", "borrowed_palette": "村民袍灰（#6F6D6A / #817D79 / #545353 / #3D2D29）", "borrowed_structure": "皮面下缘/内侧的窄条织物与 1px 缝线", "silhouette_changes": "只借织物条和缝线节奏，不借人物外形。"},
            {"part": "挂环/标签 hanger tag", "reference": "stick.png / bone_block_side.png", "borrowed_texture": "深色小环/木质小节颗粒", "borrowed_palette": "暗棕木色（#493615 / #896727 / #281E0B）", "borrowed_structure": "上缘 2-3px 小环或木牌", "silhouette_changes": "小挂环/标签，不借棍/骨头形状。"},
        ],
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_index_entries() -> dict[str, dict]:
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    return {e["name"]: e for e in data}


def build_retrieval(asset: dict, by_name: dict[str, dict], index_base: Path) -> dict:
    """Construct a retrieval dict whose anchors are exactly asset['references']."""
    anchors: list[dict] = []
    seen: set[str] = set()
    for name in asset["references"]:
        entry = by_name.get(name)
        if not entry:
            print("  WARN: missing reference %s in rebuild-index.json" % name)
            continue
        path = Path(entry["path"])
        if not path.exists():
            print("  WARN: reference PNG missing: %s" % path)
            continue
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        features = {
            "shape": ra._shape_feature(entry, path),
            "pattern": ra._pattern_feature(entry),
            "colors": ra._top_colors(path, 5),
            "parts": ra._parts_feature(entry),
            "attraction": ra._attraction_feature(entry),
        }
        anchors.append({
            "path": str(path),
            "name": name,
            "category": entry.get("category", ""),
            "role": "shape",
            "features": features,
            "score": 100,
            "matched_terms": [],
            "palette_count": entry.get("palette_count", 0),
        })
    return {
        "query": asset["query"],
        "form": asset["form"],
        "form_note": "s3-rebuild custom retrieval",
        "form_source": "manual_parts_silhouette_bank",
        "method": "rule",
        "method_note": "s3-rebuild selects exact local full-library assets by name.",
        "top": len(anchors),
        "anchors": anchors,
        "count": len(anchors),
        "query_terms": {"english": [], "chinese": []},
    }


def make_custom_concept_card(asset: dict, retrieval: dict) -> dict:
    """Start from auto card (so validation fields exist), then override with s3 content."""
    auto = cg.build_concept_card(
        query=asset["query"],
        retrieval_data=retrieval,
        form=asset["form"],
    )
    # Build shape_pattern via the standard helper so all required v2 fields exist.
    sp_flow = []
    for ppf in asset["shape"]["part_pattern_flow"]:
        sp_flow.append({
            "part": ppf["part"],
            "shape": ppf["shape"],
            "pattern": ppf["pattern"],
            "flow": ppf["flow"],
        })
    shape_pattern = cg._make_shape_pattern(
        silhouette=asset["shape"]["silhouette"],
        parts=asset["parts"],
        border=asset["palette"]["border_note"],
        shading="左上偏亮、右下偏暗；内部用 1px 色阶表现体积；实体 UV 按各区域明暗独立处理。",
        detail_pattern="沿部件贴合的材质纹理（皮革/金属/骨/木纹/魂火）；禁止脱离形状独立存在。",
        shape_lock_optional=True,
        part_pattern_flow=sp_flow,
        integration_note="先用形状确定结构，再让纹样贴合每个部件的走向/边缘/明暗面；纹样不得脱离形状独立存在。",
    )
    auto["item_name"] = asset["name"]
    auto["description"] = asset["description"]
    auto["parts"] = asset["parts"]
    auto["palette_scheme"] = dict(asset["palette"])
    auto["shape_pattern"] = shape_pattern
    auto["avoid"] = asset["avoid"]
    # face_regions for entity_uv: include cow/red_mooshroom semantic regions.
    if asset["form"] == "entity_uv":
        entity = eu.detect_entity(asset["query"])
        regs = eu.regions_for_entity(entity, asset["size"][0], asset["size"][1]) or {}
        auto["face_regions"] = {
            name: "%s（%s）：按该 UV 区域语义绘制，保留原版实体模板采样坐标" % (
                name, "%d,%d -> %d,%d" % tuple(b)
            )
            for name, b in regs.items()
        } or {"uv": "标准 64x32 entity UV atlas"}
    return auto


def make_pack(asset: dict, retrieval: dict) -> dict:
    """Build prompt pack with s2 silhouette bank and custom concept card."""
    ns = argparse.Namespace(
        name=cg.slugify(asset["query"]),
        query=asset["query"],
        retrieval=None,
        retrieval_data=retrieval,
        form=asset["form"],
        size=None,
        fusion=None,
        out=str(DEMO_DIR / asset["slug"]),
        top=len(retrieval["anchors"]),
        novelty=NOVELTY,
        no_original_ref=False,
    )
    pack = bsp.build_prompt_pack_v2(ns)

    # Override concept card with hand-written s3 content.
    card = make_custom_concept_card(asset, retrieval)
    pack["concept_card"] = card

    # Rebuild silhouette bank using the custom parts (needs enriched anchors from pack).
    entity = eu.detect_entity(asset["query"]) if asset["form"] == "entity_uv" else None
    bank = refa.build_silhouette_bank(
        parts=asset["parts"],
        retrieval_anchors=pack["anchors"],
        form=asset["form"],
        width=asset["size"][0],
        height=asset["size"][1],
        entity=entity,
    )
    pack["silhouette_bank"] = bank
    pack["concept_card"]["shape_pattern"]["silhouette_candidates"] = bank

    # Regenerate compact prompt using the overridden card + bank.
    pack["prompt"] = rp._build_compact_prompt(pack, vision=False)
    pack["output_contract"]["text"] = rp._palette_index_contract_text(pack)
    return pack


def clean_llm_raw(text: str) -> str:
    import re as _re
    lines = text.splitlines()
    lines = [ln for ln in lines if not ln.strip().startswith("```")]
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


def ensure_item_margin(img: Image.Image, min_margin: int = 1) -> Image.Image:
    """Minimal postprocess for item sprites: ensure >=1px transparent margin."""
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


def call_llm(prompt_path: Path, images: list[Path] | None = None) -> str:
    cmd = LLM_CMD.replace("{prompt_file}", str(prompt_path))
    proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError("LLM command failed (exit %d): %s" % (proc.returncode, proc.stderr.strip()[:500]))
    return proc.stdout.strip()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def write_asset_readme(asset: dict, out: Path) -> None:
    # Collect silhouette bank from prompt pack.
    pack_path = out / "prompt_pack.json"
    bank = []
    if pack_path.exists():
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        bank = pack.get("silhouette_bank") or []
    hashes = {}
    hpath = out / "hashes.json"
    if hpath.exists():
        hashes = json.loads(hpath.read_text(encoding="utf-8"))

    lines = []
    lines.append("# %s" % asset["name"])
    lines.append("")
    lines.append("- 形式：`%s`" % asset["form"])
    lines.append("- 尺寸：`%dx%d`" % asset["size"])
    lines.append("- 输出：`sprite.png`")
    lines.append("- novelty：`%s`（s2 silhouette bank；可大改）" % NOVELTY)
    lines.append("")
    lines.append("## 说明")
    lines.append(asset["description"])
    lines.append("")
    lines.append("## 部件 → 原版参考 → 轮廓基础 → 改了什么")
    lines.append("")
    lines.append("| 部件 | 参考原版资产 | 借用 texture/palette/structure | 轮廓基础来源 | 改了什么 |")
    lines.append("|---|---|---|---|---|")
    for rec in asset["source_table"]:
        lines.append("| %s | %s | %s | %s | %s |" % (
            rec["part"], rec["reference"], rec["borrowed_texture"],
            rec["borrowed_structure"], rec["silhouette_changes"],
        ))
    lines.append("")
    lines.append("## 轮廓候选（silhouette_candidates 菜单，不是锁）")
    lines.append("")
    lines.append("> 以下候选由 `reference_analyzer.build_silhouette_bank` 从所选原版 assets 生成；")
    lines.append("> prompt 中明确：可选一个/可组合/可大改/禁止当最终网格。")
    lines.append("")
    if bank:
        for entry in bank:
            part = entry.get("part", "?")
            lines.append("### %s" % part)
            for c in entry.get("candidates", []):
                lines.append("- 候选 `%s`（来源：`%s`）%s" % (
                    c.get("token", "?"), c.get("source", "?"), c.get("note", "")))
                if c.get("fragment"):
                    lines.append("  ```")
                    lines.append(c["fragment"])
                    lines.append("  ```")
            lines.append("")
    else:
        lines.append("（无 bank）")
        lines.append("")
    lines.append("## 生成命令")
    lines.append("```bash")
    lines.append("set -a; source /tmp/mc_llm.env; set +a")
    lines.append("python3 examples/rebuild-demo/rebuild_generate.py")
    lines.append("```")
    lines.append("")
    if hashes:
        lines.append("## Hash")
        lines.append("- prompt sha256：`%s`" % hashes.get("prompt_sha256", "?"))
        lines.append("- answer sha256：`%s`" % hashes.get("answer_sha256", "?"))
        lines.append("- png sha256：`%s`" % hashes.get("png_sha256", "?"))
        lines.append("- attempts：`%s`（首次 + 最多 2 次重试）" % hashes.get("attempts", "?"))
        if hashes.get("errors"):
            lines.append("- 失败/重试记录：")
            for err in hashes["errors"]:
                lines.append("  - `%s`" % err)
    lines.append("")
    out_readme = out / "README.md"
    out_readme.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_readme


def run_asset(asset: dict, by_name: dict[str, dict], index_base: Path, prompt_only: bool = False) -> Path:
    slug = asset["slug"]
    out = DEMO_DIR / slug
    out.mkdir(parents=True, exist_ok=True)
    print("\n=== %s ===" % asset["name"], flush=True)
    retrieval = build_retrieval(asset, by_name, index_base)
    pack = make_pack(asset, retrieval)
    prompt_path = out / "prompt.txt"
    prompt_path.write_text(pack["prompt"], encoding="utf-8")
    bsp.write_v2_prompt_pack(pack, out / "prompt_pack.json")
    print("  [prompt] written (%d chars, %d anchors, %d silhouette entries)" % (
        len(pack["prompt"]), len(pack["anchors"]), len(pack.get("silhouette_bank") or [])), flush=True)

    if prompt_only:
        print(pack["prompt"])
        return out / "sprite.png"

    raw_text = ""
    last_error = ""
    errors: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        images = [Path(a["path"]) for a in retrieval.get("anchors", []) if Path(a["path"]).exists()]
        try:
            raw_text = call_llm(prompt_path, images=images)
            if not raw_text:
                raise RuntimeError("LLM returned empty answer")
            raw_text = clean_llm_raw(raw_text)
            img = t2t.text_to_image(raw_text)
            if img.size != tuple(asset["size"]):
                raise RuntimeError("parsed %dx%d, expected %dx%d" % (img.size[0], img.size[1], *asset["size"]))
            opaque = sum(1 for px in img.getdata() if px[3] >= t2t.ALPHA_THRESHOLD)
            if opaque == 0:
                raise RuntimeError("parsed image has 0 opaque pixels")
            # Save raw answer / png.
            (out / "raw_answer.txt").write_text(raw_text, encoding="utf-8")
            if asset["form"] == "item":
                img = ensure_item_margin(img)
            img.save(out / "sprite.png", "PNG")
            if asset["form"] == "entity_uv":
                preview = t2t.make_preview(img, 4)
                preview.save(out / "sprite_preview.png", "PNG")
            # Run pixel checks.
            import subprocess as sp
            check_cmds = []
            if asset["form"] == "entity_uv":
                check_cmds.append([
                    sys.executable, "check_entity_uv.py", str(out / "sprite.png"),
                    "--entity", "cow"
                ])
            else:
                check_cmds.append([
                    sys.executable, "check_pixel_asset.py", str(out / "sprite.png")
                ])
            check_results = []
            for cmd in check_cmds:
                try:
                    p = sp.run(cmd, cwd=str(ROOT), stdout=sp.PIPE, stderr=sp.PIPE, text=True)
                    check_results.append({
                        "cmd": " ".join(cmd),
                        "returncode": p.returncode,
                        "stdout": p.stdout[-2000:],
                        "stderr": p.stderr[-2000:],
                    })
                except Exception as exc:  # noqa: BLE001
                    check_results.append({"cmd": " ".join(cmd), "error": str(exc)})
            (out / "check_results.json").write_text(
                json.dumps(check_results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            hashes = {
                "prompt_sha256": sha256_text(pack["prompt"]),
                "answer_sha256": sha256_text(raw_text),
                "png_sha256": hashlib.sha256((out / "sprite.png").read_bytes()).hexdigest(),
                "attempts": attempt,
                "novelty": NOVELTY,
                "silhouette_bank_parts": len(pack.get("silhouette_bank") or []),
                "errors": errors,
            }
            (out / "hashes.json").write_text(
                json.dumps(hashes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            write_asset_readme(asset, out)
            print("  [saved] sprite.png (%dx%d opaque=%d attempts=%d)" % (
                img.size[0], img.size[1], opaque, attempt), flush=True)
            return out / "sprite.png"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            errors.append("attempt %d: %s" % (attempt, last_error[:400]))
            print("  [retry] attempt %d failed: %s" % (attempt, last_error[:300]), flush=True)
            if attempt < MAX_ATTEMPTS:
                continue
    raise RuntimeError("%s failed after %d attempts: %s" % (slug, MAX_ATTEMPTS, last_error))


def write_top_readme(results: list[tuple[dict, Path]]) -> Path:
    lines = [
        "# rebuild-demo：s3 重做 4 个演示（s2 silhouette bank + 可大改）",
        "",
        "本目录重做 4 个演示，解决形状借鉴问题：",
        "- 恶魔牛：`entity_uv` 64x32（cow/red_mooshroom 实体模板），不是 16x16 牛头图标。",
        "- 骷髅法杖：骷髅头可辨（眼窝/颌），杖柄有手柄味（允许斜/粗/可大改）。",
        "- 剥皮小刀：短小、像刀，不是长剑/锯。",
        "- 村民皮：皮/兔皮轮廓（不规则、毛边），不是普通棕色方块。",
        "",
        "所有 prompt 都由 s2 机制注入 `silhouette_candidates`：每个部件 2-4 个轮廓基础，",
        "并带指令“可选一个 / 可组合多个 / 可大改形状 / 禁止当最终网格”。",
        "",
        "| 资产 | form | PNG | 轮廓基础摘要 |",
        "|---|---|---|---|",
    ]
    assets_with_png = []
    for asset in ASSETS:
        png = DEMO_DIR / asset["slug"] / "sprite.png"
        if png.exists():
            assets_with_png.append((asset, png))
    for asset, png in assets_with_png:
        refs = "；".join(rec["reference"] for rec in asset["source_table"])
        lines.append("| %s | `%s` | `%s` | %s |" % (asset["name"], asset["form"], png.relative_to(DEMO_DIR), refs))
    top = DEMO_DIR / "README.md"
    top.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return top


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-only", action="store_true", help="build prompts/READMEs but do not call LLM")
    parser.add_argument("--only", action="append", help="run only these slugs (repeatable)")
    args = parser.parse_args()

    if not INDEX.exists():
        print("rebuild-index.json missing; run build_rebuild_index.py first")
        return 1
    by_name = load_index_entries()
    index_base = INDEX.parent
    results: list[tuple[dict, Path]] = []
    for asset in ASSETS:
        if args.only and asset["slug"] not in args.only:
            continue
        png = run_asset(asset, by_name, index_base, prompt_only=args.prompt_only)
        results.append((asset, png))
    top = write_top_readme(results)
    print("\nAll done. Top-level README: %s" % top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
