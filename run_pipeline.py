#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_pipeline.py — 一键整合 Minecraft 自定义资源生成流水线。

流程（全部用 Python 函数调用）：
  scan -> retrieve -> concept -> prompt_pack -> LLM/raw -> text_to_texture -> package_asset

用法示例：
    # 用已有 raw_answer 直接出 PNG（并可选打包）
    python3 run_pipeline.py --query "异形水晶法杖" --form item \\
        --raw examples/alien_crystal_wand/raw_answer.txt \\
        --out examples/alien_crystal_wand

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

import scan_mc_assets as sc  # noqa: E402
import retrieve_assets as ra  # noqa: E402
import concept_grounder as cg  # noqa: E402
import build_style_prompt as bsp  # noqa: E402
import text_to_texture as t2t  # noqa: E402
import package_asset as pa  # noqa: E402


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
) -> tuple[dict, Path | None]:
    """执行扫描/读取索引/合成索引，返回 (retrieval 所需的 index entries, synthetic_tmp)。"""
    if args.mc_path:
        print("[1/7] scan_mc_assets: scanning %s" % args.mc_path)
        scan = sc.build_index(args.mc_path, with_palette=True)
        entries = scan["entries"]
        print("      -> %d entries from %s" % (len(entries), scan.get("source_dir")))
        return entries, None

    if args.index:
        index_path = Path(args.index)
        print("[1/7] load index: %s" % index_path)
        entries, base = ra.load_index_with_base(index_path)
        print("      -> %d entries" % len(entries))
        return entries, None

    # 无 mc-path/index：使用 retrieve_assets 的合成迷你索引（代码生成，非原版素材）。
    print("[1/7] no --mc-path/--index: using synthetic minimal index")
    entries, tmp_root = ra._build_synthetic_selftest_index()
    print("      -> %d synthetic entries (will be cleaned after prompt pack)" % len(entries))
    return entries, tmp_root


def _generate_raw_text(args: argparse.Namespace, prompt_text: str) -> str:
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


def _render_raw_faces(raw_text: str, out_dir: Path, pack: dict) -> list[Path]:
    """把 raw_answer 转为 PNG。支持单 face 与多 face，返回生成的文件路径列表。"""
    blocks = pa.split_face_blocks(raw_text)
    if not blocks:
        raise ValueError("raw_answer contains no face blocks")
    faces_meta = {f["face"]: f for f in pack["output_contract"]["faces"]}
    saved: list[Path] = []
    if len(blocks) == 1:
        fid, block = blocks[0]
        cleaned = pa._clean_face_text(block)
        img = t2t.text_to_image(cleaned)
        sprite = out_dir / "sprite.png"
        img.save(sprite, "PNG")
        saved.append(sprite)
        print("      -> %s (%dx%d)" % (sprite, *img.size))
        return saved

    for fid, block in blocks:
        cleaned = pa._clean_face_text(block)
        img = t2t.text_to_image(cleaned)
        face_meta = faces_meta.get(fid or "")
        if face_meta:
            # file 形如 assets/mcmod/textures/... ; 放入 out_dir 下保留资源包相对路径。
            dest = out_dir / face_meta["file"]
        else:
            dest = out_dir / ("%s.png" % (fid or "face"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "PNG")
        saved.append(dest)
        print("      -> %s (%dx%d)" % (dest, *img.size))
    return saved


def _write_audit_evidence(pack: dict, raw_text: str, out_dir: Path, subagent_id: str | None) -> None:
    """写 raw_answer.txt / raw_answer.sha256 / hashes.json（复用 audit_generation 格式）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "raw_answer.txt"
    raw_path.write_text(raw_text, encoding="utf-8")

    prompt_text = pack.get("prompt", "")
    prompt_path = out_dir / "prompt.txt"
    prompt_path.write_text(prompt_text, encoding="utf-8")

    prompt_hash = _sha256_bytes(prompt_path.read_bytes())
    answer_hash = _sha256_bytes(raw_path.read_bytes())
    (out_dir / "raw_answer.sha256").write_text(
        "%s  %s\n" % (answer_hash, "examples/alien_crystal_wand/raw_answer.txt"),
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


def _hex_sample_lines() -> list[str]:
    """读取真实生成样本 mushroom_sprout，转成 HEX GRID 行（---- 透明）。"""
    import re
    sample = Path(__file__).resolve().parent / "examples" / "mushroom_sprout" / "raw_answer.txt"
    try:
        raw = sample.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    pal: dict[int, str] = {}
    in_pal = False
    for line in raw.splitlines():
        ls = line.strip()
        if ls.upper().startswith("PALETTE"):
            in_pal = True
            continue
        if in_pal:
            m = re.match(r"^\s*(\d+)\s*:\s*(#[0-9a-fA-F]{6})", ls)
            if m:
                pal[int(m.group(1))] = m.group(2).upper()
            elif ls.upper().startswith("INDEX GRID"):
                break
    m = re.search(r"INDEX GRID\s*\n(.*)", raw, re.S)
    rows: list[str] = []
    if m:
        for ln in m.group(1).splitlines():
            toks = ln.split()
            if len(toks) != 16:
                continue
            cells = []
            for t in toks:
                try:
                    idx = int(t)
                except ValueError:
                    cells.append("----")
                    continue
                cells.append(pal.get(idx, "----") if idx >= 0 else "----")
            rows.append(" ".join(cells))
    return rows


def _build_compact_prompt(pack: dict) -> str:
    """生成面向纯文本 LLM 的紧凑 prompt：设计分析 + 直接输出 HEX GRID。

    经验：
    - 全量 prompt（检索特征/风格规则/few-shot）会让模型写一堆理解然后输出全 -1；
    - INDEX GRID 数字索引容易让模型画空；改用直接 #RRGGBB/---- 的 HEX GRID 更直观；
    - 必须让模型先做“走向/轴线分析”，否则会出现手柄斜、水晶正的朝向问题。
    """
    cc = pack.get("concept_card") or {}
    lines = []
    lines.append("# 任务")
    lines.append("生成一个 %s 的 Minecraft 资源：%s" % (
        pack.get("form", "item"), cc.get("item_name") or pack.get("query", "")
    ))
    lines.append("")
    lines.append("# 设计要点（先理解，再直接输出）")
    if cc.get("description"):
        lines.append("- 语义：%s" % cc["description"])
    ps = cc.get("palette_scheme") or {}
    if ps:
        lines.append("- 调色板（直接使用 #RRGGBB，至少 5~8 色）：base=%s light=%s dark=%s accent=%s outline=%s" % (
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
        lines.append("- 方位/构图：%s" % ori.get("composition_axis", "统一轴线"))
        lines.append("- 连接：%s" % ori.get("connection_rule", "连接点对齐主轴"))
        lines.append("- 轴线检查：%s" % ori.get("axis_check", "检查部件是否偏离轴线"))
    ppf = sp.get("part_pattern_flow") or []
    if ppf:
        lines.append("- 形状-纹样一体：")
        for item in ppf[:4]:
            lines.append("  · %s：形状=%s 纹样=%s 走向=%s" % (
                item.get("part", ""), item.get("shape", ""),
                item.get("pattern", ""), item.get("flow", "")))
    chk = cc.get("design_checklist") or []
    if chk:
        lines.append("- 设计自检（输出前逐项自查）：%s" % "；".join(
            c.get("item", "") for c in chk))
    refs = cc.get("reference_nodes") or []
    if refs:
        lines.append("- 参考节点（仅语义参考，禁止复制像素）：%s" % "、".join(
            "%s(%s)" % (r.get("asset", "?"), r.get("role", "?")) for r in refs))
    lines.append("")
    lines.append("# 走向/轴线设计（必须先想清楚，这是最重要的）")
    lines.append("- 整根法杖只有一条主轴线（左下→右上）；杖身、握柄、水晶簇必须沿同一条斜线方向。")
    lines.append("- 水晶簇不能“正着”竖在斜杖上：每根尖柱的方向都要与杖身轴线一致或围绕该轴线轻微分叉。")
    lines.append("- 连接点：水晶簇底端锚定在杖身右上端端点，连接在轴线上，不悬空、不偏侧。")
    lines.append("- 剪影可辨：去掉颜色只看形状，要能认出“斜杖 + 顶部水晶簇”。")
    lines.append("")
    lines.append("# 输出格式（HEX GRID，直接给颜色，不要再输出 PALETTE/INDEX GRID）")
    lines.append("- 先写 2~3 行设计分析（主轴线/部件走向/连接点），放在 FORMAT 之前；face 块内禁止任何解释文字。")
    lines.append("- 然后输出下面的固定头，并紧跟 16 行 × 16 列的 HEX GRID：")
    lines.append("FORM=item")
    lines.append("=== face: sprite ===")
    lines.append("FILE: assets/mcmod/textures/item/alien_crystal_wand.png")
    lines.append("W=16 H=16")
    lines.append("")
    lines.append("HEX GRID")
    lines.append("# 每行 16 个 token：#RRGGBB=不透明像素，----=透明；非 ---- 像素必须 >= 40；禁止输出全 ---- 空图。")
    sample_rows = _hex_sample_lines()
    if sample_rows:
        lines.append("# 真实样本（蘑菇幼苗）的 HEX GRID 格式示例——仅用于理解怎么填颜色；禁止复制它的形状/配色：")
        lines.extend(sample_rows)
    else:
        lines.append("# 示例：---- ---- ---- ----  /  ---- #ff0000 #ff4444 ----  /  ...（16 列）")
    lines.append("")
    lines.append("> 设计分析放在 FORMAT 之前；FORMAT 之后只允许 HEX GRID 数据行。")
    lines.append("")
    return "\n".join(lines)


def _hex_contract_text(pack: dict) -> str:
    """生成与 HEX GRID 匹配的 output_contract.text（只含格式骨架，不含完整示例）。"""
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
        lines.append("HEX GRID")
        lines.append("# %d 行 x %d 列；---- 透明，#RRGGBB 不透明；非 ---- 像素必须 >= 40" % (
            f.get("height", 16), f.get("width", 16)))
        lines.append("")
    return "\n".join(lines).strip()


def run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out or ("generated/" + cg.slugify(args.query)))
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    print("output dir: %s" % out_dir)

    # 1. scan / load index
    entries, synthetic_tmp = _load_retrieval_for_pipeline(args)
    try:
        # 2. retrieve
        forced_form = None if args.form in (None, "", "auto") else args.form
        print("[2/7] retrieve_assets.retrieve: query=%r top=%d form=%s" % (
            args.query, args.top, args.form or "auto"))
        retrieval = ra.retrieve(
            args.query, top=args.top, form=forced_form,
            index=entries, index_base=synthetic_tmp,
        )
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
        )
        pack = bsp.build_prompt_pack_v2(ns)
        pack["prompt"] = _build_compact_prompt(pack)  # 用紧凑 HEX prompt，避免全量 prompt 带偏模型
        pack.setdefault("output_contract", {})["text"] = _hex_contract_text(pack)
        bsp.write_v2_prompt_pack(pack, out_dir / "prompt_pack.json")
        print("      -> prompt_pack.json (%d anchors, concept=%s)" % (
            len(pack.get("anchors", [])),
            "ok" if pack.get("concept_card") else "MISSING",
        ))

        if args.prompt_only:
            print("--prompt-only: printing prompt text only")
            print("\n" + pack["prompt"] + "\n")
            return 0

        # 5. raw generation
        raw_text = _generate_raw_text(args, pack["prompt"])
        out_dir.joinpath("raw_answer.txt").write_text(raw_text, encoding="utf-8")

        # 6. text_to_texture
        print("[6/7] text_to_texture: raw -> PNG")
        saved = _render_raw_faces(raw_text, out_dir, pack)
        if not saved:
            raise RuntimeError("no PNG generated from raw_answer")

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
    parser.add_argument("--top", type=int, default=3, choices=list(range(1, 9)),
                        help="检索参考节点数 1-8（默认 3）")
    parser.add_argument("--out", default=None, help="输出目录")
    parser.add_argument("--raw", default=None, help="现成 LLM raw_answer 文件路径")
    parser.add_argument("--llm-cmd", default=None,
                        help="外部 LLM 命令；支持 {prompt} 与 {prompt_file} 替换")
    parser.add_argument("--prompt-only", action="store_true",
                        help="只生成并打印 prompt 文本，不生成 raw/PNG")
    parser.add_argument("--package", action="store_true", help="同时打包成资源包")
    parser.add_argument("--modid", default="demo", help="资源包 modid（默认 demo）")
    parser.add_argument("--subagent-id", default=None, help="可选：记录子代理 id")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
