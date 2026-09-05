#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_pipeline.py — 一键整合 Minecraft 自定义资源生成流水线。

流程（全部用 Python 函数调用）：
  scan -> retrieve -> concept -> prompt_pack -> LLM/raw -> text_to_texture -> package_asset

用法示例：
    # 用已有 raw_answer 直接出 PNG（并可选打包）
    python3 run_pipeline.py --query "骷髅法杖" --form item \\
        --raw examples/skeleton_staff/raw_answer.txt \\
        --out out/skeleton_staff

    # 调用外部 LLM 命令生成 raw_answer
    python3 run_pipeline.py --query "异形水晶法杖" --form item --top 5 \\
        --llm-cmd 'python3 my_llm.py --prompt-file {prompt}' \\
        --out out/alien_crystal_wand

    # 只输出 prompt 文本
    python3 run_pipeline.py --query "异形水晶法杖" --form item --prompt-only

所有函数只 import 核心脚本，不依赖 shell 手工串步骤。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import re  # noqa: E402

import scan_mc_assets as sc  # noqa: E402
import retrieve_assets as ra  # noqa: E402
import concept_grounder as cg  # noqa: E402
import build_style_prompt as bsp  # noqa: E402
import reference_analyzer as refa  # noqa: E402
import text_to_texture as t2t  # noqa: E402
import package_asset as pa  # noqa: E402
import entity_uv_spec as eu  # noqa: E402


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _persist_synthetic_refs(retrieval: dict, out_dir: Path, synthetic_tmp: Path | None) -> dict:
    """合成索引的 PNG 在临时目录，清理后会失效；复制到输出目录并重写 anchors.path。"""
    if synthetic_tmp is None:
        return retrieval
    assets_dir = out_dir / "retrieval_assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    for a in retrieval.get("anchors", []):
        src = Path(str(a.get("path", "")))
        if not src.exists() or synthetic_tmp not in src.parents:
            continue
        dest = assets_dir / src.name
        shutil.copy2(src, dest)
        a["path"] = str(dest)
    return retrieval


def _load_retrieval_for_pipeline(
    args: argparse.Namespace,
) -> tuple[list[dict], Path | None, Path | None]:
    """执行扫描/读取索引/合成索引。

    返回 ``(entries, index_base, synthetic_tmp)``：
    - ``index_base`` 传给 ``retrieve_assets.retrieve``，用于解析索引中的相对 path；
    - ``synthetic_tmp`` 仅在有生成临时素材时非空，用于结束后清理。
    """
    if args.mc_path:
        print("[1/7] scan_mc_assets: scanning %s" % args.mc_path)
        scan = sc.build_index(args.mc_path, with_palette=True)
        entries = scan["entries"]
        print("      -> %d entries from %s" % (len(entries), scan.get("source_dir")))
        return entries, None, None

    if args.index:
        index_path = Path(args.index)
        print("[1/7] load index: %s" % index_path)
        entries, base = ra.load_index_with_base(index_path)
        print("      -> %d entries (base=%s)" % (len(entries), base))
        return entries, base, None

    # 无 mc-path/index：使用 retrieve_assets 的合成迷你索引（代码生成，非原版素材）。
    print("[1/7] no --mc-path/--index: using synthetic minimal index")
    entries, tmp_root = ra._build_synthetic_selftest_index()
    print("      -> %d synthetic entries (will be cleaned after prompt pack)" % len(entries))
    return entries, tmp_root, tmp_root


def _generate_raw_text(args: argparse.Namespace, prompt_text: str, auto_images: list[str] | None = None) -> str:
    """按 --raw > --llm-cmd 的顺序获得 raw_answer 文本。"""
    if args.raw:
        raw_path = Path(args.raw)
        if not raw_path.exists():
            raise FileNotFoundError("--raw not found: %s" % raw_path)
        print("[5/7] raw_answer: reading %s" % raw_path)
        return raw_path.read_text(encoding="utf-8")

    if args.llm_cmd:
        cmd = args.llm_cmd.replace("{prompt}", prompt_text)
        cmd = cmd.replace("{prompt_file}", _prompt_file_placeholder(prompt_text))
        image_paths: list[str] = []
        for raw in (auto_images or []):
            for item in str(raw).split(","):
                item = item.strip()
                if item:
                    image_paths.append(str(Path(item).resolve()))
        for raw in args.llm_image:
            for item in str(raw).split(","):
                item = item.strip()
                if item:
                    image_paths.append(str(Path(item).resolve()))
        if image_paths:
            missing = [p for p in image_paths if not Path(p).exists()]
            if missing:
                raise FileNotFoundError("--llm-image not found: %s" % "; ".join(missing))
            # 兼容外部命令里的 {image} 占位符：有几个占位符就替换几个；多出的图追加 --image。
            remaining = [p for p in image_paths]
            while "{image}" in cmd and remaining:
                cmd = cmd.replace("{image}", remaining.pop(0), 1)
            if "{image}" in cmd:
                # 占位符多于图片时移除残留，避免传给模型奇怪文本。
                cmd = cmd.replace("{image}", "")
            if remaining:
                cmd += " " + " ".join("--image %s" % p for p in remaining)
        print("[5/7] llm-cmd: %s" % cmd)
        proc = subprocess.run(
            cmd, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                "LLM command failed (exit %d): %s" % (proc.returncode, proc.stderr.strip())
            )
        return proc.stdout.strip()

    raise ValueError("need --raw or --llm-cmd to generate (or use --prompt-only)")


def _prompt_file_placeholder(prompt_text: str) -> str:
    """把 prompt 文本写入临时文件，返回路径。仅用于 --llm-cmd 的 {prompt_file} 替换。"""
    import tempfile
    tmp = Path(tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".txt", delete=False,
    ).name)
    tmp.write_text(prompt_text, encoding="utf-8")
    return str(tmp)


def _standardize_face_block(block: str, face_meta: dict | None) -> str:
    """标准化单个 face 输出：
    1) 裁掉 PALETTE/HEX 之前的“设计分析”等文字；
    2) 若缺 W/H 头，按 output_contract 补上（避免把好图当失败丢掉）。
    """
    m = re.search(r"^\s*(PALETTE|HEX GRID)\b", block, re.M | re.I)
    if m:
        block = block[m.start():]
    if not re.search(r"^\s*W\s*=", block, re.M):
        w = int((face_meta or {}).get("width", 16))
        h = int((face_meta or {}).get("height", 16))
        block = "W=%d H=%d\n%s" % (w, h, block)
    return block


def _standardize_raw(raw_text: str, pack: dict) -> str:
    """把整个 raw_answer 标准化：每个 face 裁掉前置文字、补 W/H 头。"""
    blocks = pa.split_face_blocks(raw_text)
    if not blocks:
        return raw_text
    faces_meta = {f["face"]: f for f in pack["output_contract"]["faces"]}
    out: list[str] = []
    for fid, blk in blocks:
        blk = _standardize_face_block(blk, faces_meta.get(fid or ""))
        out.append("=== face: %s ===\n%s" % (fid or "sprite", blk))
    return "\n\n".join(out)


def _render_raw_faces(raw_text: str, out_dir: Path, pack: dict) -> list[Path]:
    """把 raw_answer 转为 PNG。支持单 face 与多 face，返回生成的文件路径列表。"""
    blocks = pa.split_face_blocks(raw_text)
    if not blocks:
        raise ValueError("raw_answer contains no face blocks")
    faces_meta = {f["face"]: f for f in pack["output_contract"]["faces"]}
    saved: list[Path] = []
    if len(blocks) == 1:
        fid, block = blocks[0]
        block = _standardize_face_block(block, faces_meta.get(fid or ""))
        cleaned = pa._clean_face_text(block)
        img = t2t.text_to_image(cleaned)
        sprite = out_dir / "sprite.png"
        img.save(sprite, "PNG")
        saved.append(sprite)
        print("      -> %s (%dx%d)" % (sprite, *img.size))
        return saved

    for fid, block in blocks:
        face_meta = faces_meta.get(fid or "")
        block = _standardize_face_block(block, face_meta)
        cleaned = pa._clean_face_text(block)
        img = t2t.text_to_image(cleaned)
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "PNG")
        saved.append(dest)
        print("      -> %s (%dx%d)" % (dest, *img.size))
    return saved


def _assert_nonempty_pngs(paths: list[Path], query: str) -> None:
    """非空门禁：任何一张生成 PNG 不透明像素为 0 即 FAIL，不再报告 PASS。"""
    from PIL import Image

    empties: list[str] = []
    for p in paths:
        with Image.open(p) as im:
            rgba = im.convert("RGBA")
            opaque = sum(1 for _, _, _, a in rgba.getdata() if a >= t2t.ALPHA_THRESHOLD)
        if opaque == 0:
            empties.append("%s (opaque_pixels=0)" % p)
        else:
            print("      -> nonempty check: %s opaque=%d" % (p, opaque))
    if empties:
        raise RuntimeError(
            "generated PNG has 0 opaque pixels (all transparent) for query %r: %s"
            % (query, "; ".join(empties))
        )


def _write_audit_evidence(pack: dict, raw_text: str, out_dir: Path, subagent_id: str | None) -> None:
    """写 raw_answer.txt / raw_answer.sha256 / hashes.json。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "raw_answer.txt"
    raw_path.write_text(raw_text, encoding="utf-8")

    prompt_text = pack.get("prompt", "")
    prompt_path = out_dir / "prompt.txt"
    prompt_path.write_text(prompt_text, encoding="utf-8")

    prompt_hash = _sha256_bytes(prompt_path.read_bytes())
    answer_hash = _sha256_bytes(raw_path.read_bytes())
    (out_dir / "raw_answer.sha256").write_text(
        "%s  %s\n" % (answer_hash, raw_path),
        encoding="utf-8",
    )
    if subagent_id:
        (out_dir / "subagent_id.txt").write_text(subagent_id + "\n", encoding="utf-8")
    hashes = {
        "prompt_sha256": prompt_hash,
        "answer_sha256": answer_hash,
        "subagent_id": subagent_id or "",
    }
    _write_json(hashes, out_dir / "hashes.json")
    print("      -> raw_answer.sha256=%s" % answer_hash)
    print("      -> prompt.sha256=%s" % prompt_hash)


def _form_specific_constraints(pack: dict) -> list[str]:
    """返回 form-specific 的结构化输出硬约束（参考完整资源，不做单张图/剪影）。"""
    form = pack.get("form", "item")
    lines: list[str] = []
    if form == "block_multi":
        lines.append("# 形式硬约束（block_multi：完整方块，不是物品剪影）")
        lines.append("- 三面 top/side/bottom 都是 16x16 全不透明方块面，边缘必须连续；禁止沿用透明物品剪影或棋盘格。")
        lines.append("- side 左右边可环绕平铺（四个侧面共用同一张 side，左右 wrap 一致）；side 顶/底边与 top/bottom 边缘颜色连续。")
        lines.append("- 参考完整资源：不是只看单张参考图；必须同时理解方块三面 + 原版 blockstate/model（cube_bottom_top）契约，按结构化 face 输出。")
    elif form == "entity_uv":
        lines.append("# 形式硬约束（entity_uv：标准 UV 图集/皮肤，不是单个侧视图）")
        lines.append("- 这不是单个侧视图，是标准 64x32/64x64 atlas；每个区域按语义填，禁止把整张图画成一个居中侧视剪影。")
        lines.append("- 按 entity_uv_spec 注入的区域坐标逐区域展开（头/身/腿/手臂等）；Java 资源包只能替换原版实体贴图路径，原版模型硬编码。")
        lines.append("- 参考完整资源：原版实体 64x32/64x64 texture atlas + 标准模型采样坐标，不是只看单张截图。")
    elif form == "cross":
        lines.append("# 形式硬约束（cross：植物/十字透明贴图）")
        lines.append("- 这是 16x16 透明背景的十字交叉贴图；主体居中、四周保留至少 1px 透明边距，禁止铺满到边缘。")
    else:  # item
        lines.append("# 形式硬约束（item：16x16 透明物品贴图）")
        lines.append("- 这是 16x16 透明背景物品贴图；主体居中、四周保留至少 1px 透明边距，禁止铺满到边缘。")
    return lines


def _file_contract_summary(pack: dict) -> list[str]:
    """生成 file_contract 的紧凑摘要：输出文件/模型 parent/blockstate 清单。

    只读 pack 里的 file_contract / output_contract，不把大 JSON 塞进 prompt。
    """
    fc = pack.get("file_contract") or {}
    oc = pack.get("output_contract") or {}
    lines = ["# 文件契约摘要（输出文件 / model / blockstate；不贴大 JSON）"]

    faces = oc.get("faces") or []
    if faces:
        for f in faces:
            face = f.get("face") or f.get("id") or "sprite"
            path = f.get("file") or "?"
            lines.append("- face %s -> %s" % (face, path))
    else:
        for e in fc.get("files", []):
            if e.get("kind") == "texture":
                lines.append("- %s -> %s" % (e.get("face") or "texture", e.get("path")))

    for e in fc.get("files", []):
        if e.get("kind") == "model":
            tpl = (fc.get("templates") or {}).get(e.get("path"), {})
            parent = tpl.get("parent") or e.get("format") or ""
            short_parent = parent.rsplit(":", 1)[-1] or parent
            lines.append("- model %s (parent=%s)" % (e.get("path"), short_parent))

    for e in fc.get("files", []):
        if e.get("kind") == "blockstate":
            lines.append("- blockstate %s" % e.get("path"))

    form = pack.get("form", "item")
    if form == "entity_uv":
        entity = eu.detect_entity(pack.get("query") or pack.get("name") or "")
        vanilla_path = eu.MOB_VANILLA_TEXTURE_PATHS.get(entity, "")
        if vanilla_path:
            lines.append("- 原版实体替换路径：%s（模型/blockstate 由原版硬编码，无需生成）" % vanilla_path)
        else:
            lines.append("- 原版实体替换路径：assets/minecraft/textures/entity/<原版路径>.png（模型/blockstate 由原版硬编码，无需生成）")
    return lines


def _build_catalog_text(entries: list[dict]) -> str:
    """把索引中的全部资源名按分类列成目录，供模型自己挑参考。"""
    cats: dict[str, list[str]] = {}
    for e in entries:
        if not isinstance(e, dict):
            continue
        name = str(e.get("name", "") or Path(str(e.get("path", ""))).stem or "")
        cat = str(e.get("category", "item") or "item")
        if name:
            cats.setdefault(cat, []).append(name)
    lines = ["# 可用资源全目录（请从下面自己挑 2-4 个做参考）", ""]
    for cat in sorted(cats):
        names = sorted(set(cats[cat]))
        lines.append("## %s (%d)" % (cat, len(names)))
        lines.append(", ".join(names))
    lines.append("")
    lines.append("> 从上面**任意分类**中挑选 2-4 个你判断最相关的作为参考；在“设计分析”里写清楚：")
    lines.append("> 选择了哪几个、每个借什么（结构/配色/纹理/明暗）、组合成什么新物品；不选的说一句理由即可。")
    lines.append("> 禁止把任何参考当最终像素网格；参考只为质感/结构/配色，不改变主体语义。")
    return "\n".join(lines)


def _catalog_names(entries: list[dict]) -> set[str]:
    names = set()
    for e in entries:
        if isinstance(e, dict):
            n = str(e.get("name", ""))
            if n:
                names.add(n)
    return names


def _build_selection_prompt(query: str, form: str, catalog_text: str) -> str:
    """两段式第一段：只给名字清单，让模型选 2-4 个参考并说明借什么。"""
    return (
        "# 选择参考（第一段：只输出选中的名字，不要画图）\n"
        "目标：%s（form=%s）\n"
        "下面是全部可用的资源名（只有名字）。请从中**选择 2-4 个**你最想参考的资产，\n"
        "并各用一行说明借什么（结构/配色/纹理/明暗）。\n\n"
        "%s\n\n"
        "输出格式：\n"
        "- <资源名>: 借什么（如：bow: 弓形/弦；ender_eye: 绿色瞳孔/高光）\n"
        "只要名字与借法，**不要输出像素网格**。\n"
    ) % (query, form, catalog_text)


def _select_references_from_catalog(args, entries, query: str) -> list[str]:
    """执行第一段选择调用，返回选中的资源名列表。"""
    catalog_text = _build_catalog_text(entries)
    sel_prompt = _build_selection_prompt(query, args.form or "item", catalog_text)
    sel_args = argparse.Namespace(**vars(args))
    sel_args.llm_image = []
    sel_args.auto_visual_ref = False
    print("[two-stage] selecting references from catalog ...")
    resp = _generate_raw_text(sel_args, sel_prompt, auto_images=[])
    print("[two-stage] selection response: %s" % resp.strip()[:300])
    names = _catalog_names(entries)
    found: list[str] = []
    for line in resp.splitlines():
        for n in names:
            if n and n in line and n not in found:
                found.append(n)
    chosen = found[:4]
    if not chosen:
        print("[two-stage] no names parsed; fallback to top anchors")
    return chosen


def _entry_by_name(entries: list[dict], name: str) -> dict | None:
    for e in entries:
        if isinstance(e, dict) and e.get("name") == name:
            return e
    return None


def _build_anchor_from_entry(entry: dict, index_base) -> dict:
    """把一个索引条目变成 build_style_prompt 能吃的 anchor（带绝对 path 与 compact_text）。"""
    raw_path = entry.get("path", "")
    try:
        abs_path = str(ra.resolve_entry_path({"path": raw_path}, index_base))
    except Exception:  # noqa: BLE001
        abs_path = raw_path
    anchor = {
        "name": entry.get("name", Path(abs_path).stem),
        "path": abs_path,
        "category": entry.get("category", "item"),
        "role": entry.get("role", "shape"),
        "features": dict(entry.get("features", {})),
        "score": entry.get("score"),
        "matched_terms": entry.get("matched_terms", []),
        "palette_count": entry.get("palette_count"),
        "size": entry.get("size"),
    }
    try:
        anchor.update(bsp._extract_feature_per_anchor(anchor))
    except Exception as _e:  # noqa: BLE001
        print("      [warn] extract compact for %s failed: %s" % (anchor.get("name"), _e))
    return anchor


def _select_anchors_by_name(pack: dict, entries: list[dict], index_base, names: list[str]) -> list[dict]:
    """按选中的名字返回 anchor 列表；不在 top 锚点里的条目动态构建 compact anchor。"""
    selected: list[dict] = []
    seen = set()
    for name in names:
        # 先看 pack 里已有 anchor（带 compact_text）
        for a in pack.get("anchors", []):
            if a.get("name") == name and name not in seen:
                selected.append(a)
                seen.add(name)
                break
        if name in seen:
            continue
        entry = _entry_by_name(entries, name)
        if entry is None:
            continue
        a = _build_anchor_from_entry(entry, index_base)
        if a.get("compact_text"):
            selected.append(a)
            seen.add(name)
    # 补齐到至少 2 个：从 top anchors 拿未选中的
    if len(selected) < 2:
        for a in pack.get("anchors", []):
            if a.get("name") in seen:
                continue
            selected.append(a)
            seen.add(a.get("name"))
            if len(selected) >= 4:
                break
    return selected[:4]


def _build_selected_reference_block(pack: dict, selected: list[dict], novelty: float, no_original_ref: bool) -> str:
    form = pack.get("form", "item")
    faces = pack.get("output_contract", {}).get("faces") or [{"width": 16, "height": 16}]
    f0 = faces[0] if faces else {}
    w = int(f0.get("width", 16))
    h = int(f0.get("height", 16))
    entity = eu.detect_entity(pack.get("query") or pack.get("name") or "")
    block, _inc, _lim = bsp._reference_block_for_anchors(
        selected, form, w, h, entity, novelty, no_original_ref
    )
    return block or ""


def _build_compact_prompt(pack: dict, vision: bool = False) -> str:
    """生成紧凑 prompt：设计要点 + PALETTE/INDEX GRID（-1 0 1 索引模式）。

    通用设计原则（不针对某个具体物品）：方向统一、连接自然、剪影可辨、
    纹样贴合形状、1px 描边/材质高光/纹理/明暗分层；输出固定格式，不写解释。
    """
    cc = pack.get("concept_card") or {}
    lines = []
    asset_label = cc.get("item_name") or pack.get("query", "")
    lines.append("# 任务")
    lines.append("生成一个 %s 的 Minecraft 资源：%s" % (
        pack.get("form", "item"), asset_label
    ))
    lines.append("")
    if pack.get("catalog"):
        lines.append(pack["catalog"])
        lines.append("")
    lines.append("# 本体硬约束（最重要）")
    lines.append("- 必须生成「%s」这个物体本身；参考节点不能改变主体类别、形状或语义。" % asset_label)
    lines.append("- 参考节点只允许借用配色、材质、明暗、尺度与局部图案；若参考节点与 %s 语义冲突，请忽略其形状与语义。" % asset_label)
    lines.append("")
    lines.extend(_form_specific_constraints(pack))
    lines.append("")
    lines.append("# 设计要点（先理解，再直接输出）")
    if cc.get("description"):
        lines.append("- 语义：%s" % cc["description"])
    ps = cc.get("palette_scheme") or {}
    if ps:
        lines.append("- 调色板（5~8 色）：base=%s light=%s dark=%s accent=%s outline=%s" % (
            ps.get("base", "?"), ps.get("light", "?"), ps.get("dark", "?"),
            ps.get("accent", "?"), ps.get("outline", "?")))
        if ps.get("border_note"):
            lines.append("  描边：%s" % ps["border_note"])
        if ps.get("saturation_note"):
            lines.append("  饱和度：%s" % ps["saturation_note"])
    sp = cc.get("shape_pattern") or {}
    if sp.get("silhouette"):
        lines.append("- 形状：%s" % sp["silhouette"])
    ori = sp.get("orientation") or {}
    if ori:
        lines.append("- 方位/构图：%s" % ori.get("composition_axis", "统一方向"))
        lines.append("- 连接：%s" % ori.get("connection_rule", "连接点自然对齐"))
    ppf = sp.get("part_pattern_flow") or []
    if ppf:
        lines.append("- 形状-纹样一体：")
        for item in ppf[:4]:
            lines.append("  · %s：形状=%s 纹样=%s 走向=%s" % (
                item.get("part", ""), item.get("shape", ""),
                item.get("pattern", ""), item.get("flow", "")))
    # catalog 模式下：不渲染 top 锚点的 silhouette 剪影候选，只给名字清单让模型自己挑。
    if not pack.get("catalog"):
        silhouette_candidates = sp.get("silhouette_candidates") or pack.get("silhouette_bank") or []
        if silhouette_candidates:
            candidate_block = refa.render_silhouette_candidates(silhouette_candidates)
            if candidate_block:
                lines.append(candidate_block)
                lines.append("")
    chk = cc.get("design_checklist") or []
    if chk:
        lines.append("- 设计自检（输出前逐项自查）：%s" % "；".join(
            c.get("item", "") for c in chk))
    avoid = cc.get("avoid") or []
    if avoid:
        lines.append("- 硬性避免（违反即失败）：")
        for a in avoid:
            lines.append("  · %s" % a)
    refs = cc.get("reference_nodes") or []
    if refs:
        lines.append("- 参考节点（仅语义参考，禁止复制像素）：%s" % "、".join(
            "%s(%s)" % (r.get("asset", "?"), r.get("role", "?")) for r in refs))
    lines.append("")

    # catalog 模式下仍保留“全目录名字清单”，同时注入 top 锚点的 compact/silhouette 参考；
    # 让模型既能从全目录挑，也有真实像素结构可依。
    reference_block = pack.get("reference_block", "") or ""
    if reference_block:
        lines.append(reference_block)
        lines.append("")

    lines.append("# 通用设计原则（每个物体都适用）")
    for rule in getattr(cg, "GENERIC_DESIGN_PRINCIPLES", []) or []:
        lines.append("- %s" % rule)
    lines.append("")
    lines.append("# 通用像素细节（每个物体都适用）")
    for rule in getattr(cg, "GENERIC_PIXEL_DETAIL_RULES", []) or []:
        lines.append("- %s" % rule)
    lines.append("")
    lines.append("# 输出格式（PALETTE + INDEX GRID，-1 0 1 索引模式）")
    lines.append("- 先写 2~3 行设计分析：总结你要借/组合的关键特征（形状/配色/花纹/明暗），放在 FORMAT 之前。")
    lines.append("- 然后按下面的固定头输出 PALETTE 与 INDEX GRID；设计分析中提到的每个关键特征必须在网格中可见（例如“眼球”要有瞳孔/虹膜/高光），非 -1 像素 >= 40；禁止全 -1 空图。")
    lines.extend(_file_contract_summary(pack))
    lines.append("")
    oc = pack.get("output_contract") or {}
    lines.append(oc.get("text", ""))
    if vision:
        lines.append("# 已附带参考图（仅视觉引导；不要照搬像素，只参考结构/配色方向）")
    lines.append("")
    lines.append("> 设计分析放在 FORMAT 之前；face 块内只允许 PALETTE + INDEX GRID 数据；ENTITY UV 语义是格式元数据，不写入 face 块。")
    lines.append("")
    return "\n".join(lines)


def _palette_index_contract_text(pack: dict) -> str:
    """生成 PALETTE + INDEX GRID 格式骨架（-1 0 1 索引模式）。"""
    form = pack.get("form", "item")
    faces = pack.get("output_contract", {}).get("faces") or [
        {"face": "sprite", "file": "assets/mcmod/textures/item/sprite.png", "width": 16, "height": 16}
    ]
    lines = ["FORM=%s" % form, "FACES=%d" % len(faces), ""]
    for f in faces:
        lines.append("=== face: %s ===" % f.get("face", "sprite"))
        lines.append("FILE: %s" % f.get("file", "assets/mcmod/textures/item/sprite.png"))
        lines.append("W=%d H=%d" % (f.get("width", 16), f.get("height", 16)))
        lines.append("")
        lines.append("PALETTE")
        lines.append("# 在此列出 5~8 个颜色，每行：索引 十六进制，例如 0: #10282A")
        lines.append("")
        lines.append("INDEX GRID")
        lines.append("# 共 %d 行，每行 %d 个整数；-1=透明，非负整数引用上面 PALETTE 索引；非 -1 像素必须 >= 40；禁止全 -1 空图。" % (
            f.get("height", 16), f.get("width", 16)))
        lines.append("")
    if form == "entity_uv":
        entity = eu.detect_entity(pack.get("query") or pack.get("name") or "")
        face0 = faces[0] if faces else {}
        lines.append(eu.contract_text(
            int(face0.get("width", 64)), int(face0.get("height", 32)), entity=entity))
        lines.append("")
    return "\n".join(lines).strip()


def run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out or ("generated/" + cg.slugify(args.query)))
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    print("output dir: %s" % out_dir)

    # 1. scan / load index
    entries, index_base, synthetic_tmp = _load_retrieval_for_pipeline(args)
    try:
        # 2. retrieve
        pool_top = max(args.top, args.pool)
        forced_form = None if args.form in (None, "", "auto") else args.form
        print("[2/7] retrieve_assets.retrieve: query=%r top=%d form=%s" % (
            args.query, pool_top, args.form or "auto"))
        retrieval = ra.retrieve(
            args.query, top=pool_top, form=forced_form,
            index=entries, index_base=index_base,
        )
        # 修复 --index 相对路径：把索引中的相对 raw 路径解析为真实绝对路径，
        # 后续 build_style_prompt._extract_feature_per_anchor 才能找到 PNG。
        if index_base is not None:
            for a in retrieval.get("anchors", []):
                try:
                    a["path"] = str(ra.resolve_entry_path({"path": a["path"]}, index_base))
                except Exception:  # noqa: BLE001
                    # 已是绝对路径或无法解析时保留原值，交给后续逻辑报错/兜底。
                    pass
        retrieval = _persist_synthetic_refs(retrieval, out_dir, synthetic_tmp)
        _write_json(retrieval, out_dir / "retrieval.json")
        print("      -> form=%s anchors=%d" % (retrieval["form"], len(retrieval.get("anchors", []))))

        # 3. concept
        print("[3/7] concept_grounder.build_concept_card")
        concept = cg.build_concept_card(
            query=args.query,
            retrieval_data=retrieval,
            form=(None if args.form in (None, "", "auto") else args.form),
        )
        _write_json(concept, out_dir / "concept.json")
        print("      -> palette_scheme=%s shape_pattern.part_pattern_flow=%d" % (
            "ok" if concept.get("palette_scheme") else "MISSING",
            len(concept.get("shape_pattern", {}).get("part_pattern_flow", [])),
        ))

        # 4. prompt pack
        print("[4/7] build_style_prompt.build_prompt_pack_v2")
        ns = argparse.Namespace(
            name=cg.slugify(args.query),
            query=args.query,
            retrieval=None,
            retrieval_data=retrieval,
            form=args.form,
            size=None,
            fusion=None,
            out=str(out_dir),
            top=args.top,
            novelty=args.novelty,
            no_original_ref=args.no_original_ref,
        )
        pack = bsp.build_prompt_pack_v2(ns)
        pack["catalog"] = _build_catalog_text(entries)
        selected_anchors: list[dict] = []
        if args.two_stage and args.raw is None and not args.prompt_only:
            print("[two-stage] 1/2: pick references from full resource name catalog")
            chosen = _select_references_from_catalog(args, entries, args.query)
            print("      chosen: %s" % "、".join(chosen) if chosen else "      chosen: (none, fallback top)")
            selected_anchors = _select_anchors_by_name(pack, entries, index_base, chosen)
            pack["selected_refs"] = [a.get("name", "?") for a in selected_anchors]
            # 生成阶段不再塞全目录，只把选中参考的 compact 细节注入
            pack["catalog"] = None
            pack["reference_block"] = _build_selected_reference_block(
                pack, selected_anchors, args.novelty, args.no_original_ref
            )
            print("[two-stage] 2/2: generation prompt uses %d selected refs (compact/silhouette)" % len(selected_anchors))
        auto_images: list[str] = []
        ref_source = selected_anchors if selected_anchors else pack.get("anchors", [])
        if args.auto_visual_ref:
            for a in ref_source:
                p = a.get("path") or ""
                if p and Path(p).exists():
                    auto_images.append(str(Path(p).resolve()))
        pack["auto_visual_refs"] = auto_images
        pack.setdefault("output_contract", {})["text"] = _palette_index_contract_text(pack)
        pack["prompt"] = _build_compact_prompt(pack, vision=bool(args.llm_image) or bool(auto_images))  # 用紧凑 HEX prompt；vision 模式更短（图作引导）
        bsp.write_v2_prompt_pack(pack, out_dir / "prompt_pack.json")
        print("      -> prompt_pack.json (%d anchors, concept=%s%s%s)" % (
            len(pack.get("anchors", [])),
            "ok" if pack.get("concept_card") else "MISSING",
            " auto_refs=%d" % len(auto_images) if auto_images else "",
            " selected=%d" % len(selected_anchors) if selected_anchors else "",
        ))

        if args.prompt_only:
            print("--prompt-only: printing prompt text only")
            print("\n" + pack["prompt"] + "\n")
            return 0

        # 5-6. raw generation + text_to_texture，允许自动重试（模型偶发全 -1 / 缺头）
        max_attempts = max(1, args.retries)
        raw_text: str | None = None
        saved: list[Path] = []
        for attempt in range(1, max_attempts + 1):
            try:
                raw_text = _generate_raw_text(args, pack["prompt"], auto_images=auto_images)
                raw_text = _standardize_raw(raw_text, pack)
                out_dir.joinpath("raw_answer.txt").write_text(raw_text, encoding="utf-8")
                print("[6/7] text_to_texture: raw -> PNG (attempt %d/%d)" % (attempt, max_attempts))
                saved = _render_raw_faces(raw_text, out_dir, pack)
                if not saved:
                    raise RuntimeError("no PNG generated from raw_answer")
                _assert_nonempty_pngs(saved, args.query)
                break
            except Exception as _e:
                if attempt < max_attempts:
                    print("[retry] attempt %d/%d failed: %s" % (attempt, max_attempts, _e))
                    continue
                raise
        if raw_text is None or not saved:
            raise RuntimeError("failed to generate a non-empty PNG")

        # 7. package_asset (optional)
        if args.package:
            print("[7/7] package_asset: %s" % (out_dir / "resourcepack"))
            res = pa.package_asset(
                spec=pack,
                raw_text=raw_text,
                modid=args.modid,
                out_root=out_dir / "resourcepack",
                write_pack_mcmeta=True,
                quiet=True,
            )
            print("      -> validation=%s files=%d" % (
                res["validation"]["status"], len(res["manifest"]["files"])
            ))
        else:
            print("[7/7] package_asset: skipped (use --package to enable)")

        # audit evidence
        _write_audit_evidence(pack, raw_text, out_dir, args.subagent_id)
        print("PIPELINE: PASS -> %s" % out_dir)
        return 0
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print("PIPELINE: FAIL: %s" % exc, file=sys.stderr)
        return 1
    finally:
        if synthetic_tmp is not None:
            shutil.rmtree(synthetic_tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="One-command Minecraft asset generation pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--query", required=True, help="中文/英文想法，例如：异形水晶法杖")
    parser.add_argument("--mc-path", default=None, help="扫描 Minecraft/资源包路径")
    parser.add_argument("--index", default=None, help="已有 scan_mc_assets 索引 JSON")
    parser.add_argument("--form", default="auto",
                        choices=["auto", "item", "block_multi", "cross", "entity_uv"],
                        help="形式（默认 auto）")
    parser.add_argument("--top", type=int, default=5, choices=list(range(1, 33)),
                        help="兼容参数：用于候选池下限；模型在 --pool 范围里自选（默认 5）")
    parser.add_argument("--pool", type=int, default=12, choices=list(range(1, 33)),
                        help="候选资源池大小（默认 12）；模型从池中自选 2-4 个参考")
    parser.add_argument("--retries", type=int, default=2,
                        help="生成空图/解析失败时自动重试次数（默认 2）")
    parser.add_argument("--two-stage", action="store_true", default=True,
                        help="两段式：先从全资源名选参考，再把选中参考的 compact 细节注入生成 prompt（默认开启）")
    parser.add_argument("--no-two-stage", dest="two_stage", action="store_false",
                        help="关闭两段式，直接单段生成")
    parser.add_argument("--novelty", type=float, default=0.5,
                        help="参考自由度 0..1；默认 0.5。越高越少附原版 compact 片段，越低越贴原版。")
    parser.add_argument("--no-original-ref", action="store_true",
                        help="关闭原版参考块（不注入参考语法与 compact 片段）")
    parser.add_argument("--out", default=None, help="输出目录")
    parser.add_argument("--raw", default=None, help="现成 LLM raw_answer 文件路径")
    parser.add_argument("--llm-cmd", default=None,
                        help="外部 LLM 命令；支持 {prompt} / {prompt_file} / {image} 替换")
    parser.add_argument("--llm-image", action="append", default=[],
                        help="参考 PNG 路径；可多次使用（--llm-image a.png --llm-image b.png）或用逗号分隔（--llm-image a.png,b.png）；"
                             "全部传给支持视觉的模型（如 deepseek-v4-flash-vision-exp）")
    parser.add_argument("--auto-visual-ref", action="store_true", default=True,
                        help="自动把检索到的 top 锚点原版图传给视觉模型（默认开启；用 --no-auto-visual-ref 关闭）")
    parser.add_argument("--no-auto-visual-ref", dest="auto_visual_ref", action="store_false",
                        help="关闭自动传递检索锚点参考图")
    parser.add_argument("--prompt-only", action="store_true",
                        help="只生成并打印 prompt 文本，不生成 raw/PNG")
    parser.add_argument("--package", action="store_true", help="同时打包成资源包")
    parser.add_argument("--modid", default="demo", help="资源包 modid（默认 demo）")
    parser.add_argument("--subagent-id", default=None, help="可选：记录子代理 id")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
