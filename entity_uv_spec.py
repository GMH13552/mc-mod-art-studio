#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
entity_uv_spec.py — Vanilla entity texture layout contract for mc-mod-art-studio.

Java Edition 原版实体模型大多是硬编码的：资源包只能替换
`assets/minecraft/textures/entity/<path>.png`，不能通过普通 `assets/<ns>/models/entity/*.json`
直接替换实体模型。本模块提供：

- 玩家皮肤 64x64 / 64x32 标准布局坐标（Java 原版皮肤布局）。
- 猪 / 苦力怕 / cow / red_mooshroom 等原版生物 64x32 atlas 的关键区域坐标（源自原版贴图/UV 模板）。
- 生成给 LLM 的 “ENTITY UV 语义” 提示文本，避免 LLM 把 64x32 当成单个侧视图。

坐标约定：Pillow 半开区间 [x1, y1, x2, y2)，左上为 (0,0)。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 玩家皮肤：标准 layout
# ---------------------------------------------------------------------------
# 64x64 现代皮肤（双 layer）；64x32 legacy 仅内层，left_* 由渲染器镜像。
PLAYER_64x64_REGIONS: dict[str, tuple[int, int, int, int]] = {
    "head": (0, 0, 32, 16),
    "body": (16, 16, 40, 32),
    "right_leg": (0, 16, 16, 32),
    "right_arm": (40, 16, 56, 32),
    "left_leg": (16, 48, 32, 64),
    "left_arm": (32, 48, 48, 64),
}

PLAYER_64x32_REGIONS: dict[str, tuple[int, int, int, int]] = {
    "head": (0, 0, 32, 16),
    "body": (16, 16, 40, 32),
    "right_leg": (0, 16, 16, 32),
    "right_arm": (40, 16, 56, 32),
}

# ---------------------------------------------------------------------------
# 原版生物：64x32 atlas 关键区域（vanilla texture / UV template 提取）
# ---------------------------------------------------------------------------
# 来源：原版 `assets/minecraft/textures/entity/pig/pig.png` 64x32、
#       `assets/minecraft/textures/entity/creeper/creeper.png` 64x32，
#       以及 papercraft.robhack.com 的 mob UV template（20x 缩放 1280x640）。
# 这些粗粒度区域用于“标准模型是否可能加载”的占位检查；精细 face 坐标见 docs。
# cow / red_mooshroom 共用 64x32 atlas 区域（源自 cow.png / red_mooshroom.png）。
# 这里按语义拆出 head / horns / muzzle / body / legs 等粗粒度区域，
# 供 reference_analyzer 的实体部件轮廓候选与 check_entity_uv 区域占位检查使用。
_COW_REGIONS: dict[str, tuple[int, int, int, int]] = {
    "head": (0, 0, 32, 16),
    "horns": (0, 0, 32, 6),
    "ears": (0, 0, 32, 4),
    "muzzle": (0, 8, 16, 16),
    "body": (16, 16, 64, 32),
    "legs": (0, 16, 16, 32),
    "tail": (48, 16, 64, 32),
}

MOB_ENTITY_REGIONS: dict[str, dict[str, tuple[int, int, int, int]]] = {
    "pig": {
        "head": (0, 0, 32, 16),
        "body": (28, 8, 64, 32),
        "legs": (0, 16, 16, 26),
    },
    "creeper": {
        "head": (0, 0, 32, 16),
        "body": (16, 16, 40, 32),
        "legs": (0, 16, 16, 26),
    },
    "cow": dict(_COW_REGIONS),
    "red_mooshroom": dict(_COW_REGIONS),
}

# Java 资源包替换路径（放在 assets/minecraft/textures/entity/ 下才能覆盖原版实体）
MOB_VANILLA_TEXTURE_PATHS: dict[str, str] = {
    "pig": "assets/minecraft/textures/entity/pig/pig.png",
    "creeper": "assets/minecraft/textures/entity/creeper/creeper.png",
    "cow": "assets/minecraft/textures/entity/cow/cow.png",
    "red_mooshroom": "assets/minecraft/textures/entity/cow/red_mooshroom.png",
}

_ENTITY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("player", ("玩家", "player", "皮肤", "skin", "人物", "steve", "alex")),
    ("red_mooshroom", ("red_mooshroom", "红蘑菇牛", "红色蘑菇牛", "蘑菇牛", "mooshroom", "mushroom cow")),
    ("cow", ("牛", "cow", "cows")),
    ("pig", ("猪", "pig", "pork")),
    ("creeper", ("苦力怕", "creeper", "爬行者")),
]


def detect_entity(query_or_name: str | None) -> str | None:
    """从 query / name 中识别目标实体类型；无法识别返回 None。"""
    if not query_or_name:
        return None
    q = str(query_or_name).lower()
    for entity, keywords in _ENTITY_KEYWORDS:
        if any(k in q for k in keywords):
            return entity
    return None


def regions_for_entity(entity: str | None, width: int, height: int) -> dict[str, tuple[int, int, int, int]] | None:
    """返回指定实体的检查区域；player 根据尺寸返回现代或 legacy 区域。"""
    if entity == "player":
        if (width, height) == (64, 64):
            return dict(PLAYER_64x64_REGIONS)
        return dict(PLAYER_64x32_REGIONS)
    if entity in MOB_ENTITY_REGIONS:
        return dict(MOB_ENTITY_REGIONS[entity])
    return None


def _fmt_box(box: tuple[int, int, int, int]) -> str:
    return "%d,%d -> %d,%d" % box


def contract_text(width: int, height: int, entity: str | None = None) -> str:
    """生成放在 prompt 输出契约里的 ENTITY UV 语义说明。"""
    lines: list[str] = []
    lines.append("# ENTITY UV 语义（最重要：这是标准 64x32/64x64 atlas，不是单个侧视图）")
    lines.append("- 这不是单个侧视图，也不是一张完整画布上的自由构图；必须按原版硬编码模型采样的区域坐标逐块展开像素。")
    lines.append("- 每个区域按语义填：头/身/腿/手臂等各画自己的内容；区域外可为透明/底色，区域内不能留空。")

    if entity == "player":
        lines.append("- 当前尺寸：%dx%d（%s）" % (
            width, height, "现代双层皮肤" if (width, height) == (64, 64) else "legacy 64x32 皮肤"))
        regs = regions_for_entity("player", width, height) or {}
        lines.append("- 标准皮肤关键区域（坐标 x1,y1 -> x2,y2）：")
        for name, box in regs.items():
            lines.append("  - %s: %s" % (name, _fmt_box(box)))
        lines.append("- 64x64 必须同时覆盖 head/body/right_leg/right_arm/left_leg/left_arm；"
                     "64x32 至少覆盖 head/body/right_leg/right_arm，left 由渲染器镜像。")
        lines.append("- 每个部件按六个面（上/下/前/后/左/右）展开；不要让部件只出现一次侧视。")
    elif entity in MOB_ENTITY_REGIONS:
        vanilla_path = MOB_VANILLA_TEXTURE_PATHS.get(entity, "")
        lines.append("- 当前尺寸：64x32（原版 %s 标准尺寸）" % entity)
        lines.append("- 原版 %s atlas 关键区域（坐标 x1,y1 -> x2,y2）：" % entity)
        regs = MOB_ENTITY_REGIONS[entity]
        for name, box in regs.items():
            lines.append("  - %s: %s" % (name, _fmt_box(box)))
        lines.append("- Java 资源包只能替换贴图，不能换原版硬编码模型；原版替换路径为 `%s`。" % vanilla_path)
        lines.append("- 必须按头/身/腿等区域分别绘制，至少保证每个区域都有像素。")
    else:
        lines.append("- 当前尺寸：64x32 或 64x64（如果是玩家皮肤请用标准 skin 坐标；"
                     "如果是原版生物请使用该生物的 Vanilla 64x32 atlas 布局）。")
        lines.append("- 原版硬编码实体只能替换 `assets/minecraft/textures/entity/<原版路径>.png`；"
                     "自定义实体模型需要 OptiFine CEM / Bedrock geometry / 模组 renderer。")
        lines.append("- 待生成后可使用 `check_entity_uv.py --entity pig|creeper|cow|red_mooshroom|player` 验证区域占位。")
    return "\n".join(lines)
