#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write README/hashes metadata for the two programmatic fallback demos."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "examples" / "rebuild-demo"

SLUGS = ["demon_cow", "villager_hide"]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def read_silhouette_bank(slug: str) -> list[dict]:
    p = DEMO / slug / "prompt_pack.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("silhouette_bank") or []


def read_asset(slug: str) -> dict:
    # Import ASSETS from rebuild_generate without running main.
    import importlib.util
    spec = importlib.util.spec_from_file_location("rg", DEMO / "rebuild_generate.py")
    rg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rg)
    for a in rg.ASSETS:
        if a["slug"] == slug:
            return a
    raise KeyError(slug)


def write_hashes(slug: str, asset: dict, method: str) -> None:
    out = DEMO / slug
    prompt = (out / "prompt.txt").read_text(encoding="utf-8") if (out / "prompt.txt").exists() else ""
    png = out / "sprite.png"
    hashes = {
        "prompt_sha256": sha256_text(prompt) if prompt else "",
        "answer_sha256": "programmatic-fallback",
        "png_sha256": sha256_file(png) if png.exists() else "",
        "attempts": "programmatic-fallback",
        "novelty": 0.9,
        "method": method,
        "silhouette_bank_parts": len(read_silhouette_bank(slug)),
        "errors": [
            "LLM text-model output for this asset was unstable (all-one-color / empty / oval); "
            "final PNG uses vanilla template silhouette + new palette recoloring.",
        ],
    }
    (out / "hashes.json").write_text(
        json.dumps(hashes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_readme(slug: str, asset: dict, method: str, template: str) -> None:
    out = DEMO / slug
    bank = read_silhouette_bank(slug)
    h = json.loads((out / "hashes.json").read_text(encoding="utf-8"))
    lines = []
    lines.append("# %s" % asset["name"])
    lines.append("")
    lines.append("- 形式：`%s`" % asset["form"])
    lines.append("- 尺寸：`%dx%d`" % asset["size"])
    lines.append("- 输出：`sprite.png`")
    lines.append("- novelty：`0.9`（s2 silhouette bank；可大改）")
    lines.append("- 生成方式：`%s`" % method)
    lines.append("- 原版模板：`%s`（仅作轮廓/区域基础；原版 PNG 未复制进本仓库）" % template)
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
    lines.append("## Why programmatic fallback")
    lines.append("- The s2 prompt + silhouette bank were generated and stored; however the text LLM")
    lines.append("  output for this form was not stable enough to produce a readable result.")
    lines.append("- This demo therefore uses the vanilla asset **only as a silhouette/template base** and")
    lines.append("  remaps every opaque texel to a new palette (plus explicit accents), which is the")
    lines.append("  'cow/red_mooshroom 64x32 模板改' / 'rabbit_hide 轮廓' approach requested by the brief.")
    lines.append("")
    lines.append("## 生成命令")
    lines.append("```bash")
    lines.append("set -a; source /tmp/mc_llm.env; set +a")
    lines.append("python3 examples/rebuild-demo/rebuild_generate.py --only %s" % slug)
    lines.append("python3 examples/rebuild-demo/build_programmatic_demos.py")
    lines.append("python3 examples/rebuild-demo/update_programmatic_meta.py")
    lines.append("```")
    lines.append("")
    lines.append("## Hash")
    lines.append("- prompt sha256：`%s`" % h.get("prompt_sha256", "?"))
    lines.append("- answer sha256：`%s`" % h.get("answer_sha256", "?"))
    lines.append("- png sha256：`%s`" % h.get("png_sha256", "?"))
    lines.append("- attempts：`%s`" % h.get("attempts", "?"))
    if h.get("errors"):
        lines.append("- 失败/重试记录：")
        for err in h["errors"]:
            lines.append("  - `%s`" % err)
    lines.append("")
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    methods = {
        "demon_cow": "programmatic template recolor (vanilla cow.png silhouette + demon palette)",
        "villager_hide": "programmatic template recolor (vanilla rabbit_hide.png silhouette + hide palette + cloth trim)",
    }
    templates = {
        "demon_cow": "cow.png (64x32 entity atlas)",
        "villager_hide": "rabbit_hide.png (16x16 item hide)",
    }
    for slug in SLUGS:
        asset = read_asset(slug)
        write_hashes(slug, asset, methods[slug])
        write_readme(slug, asset, methods[slug], templates[slug])
        print("updated %s" % slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
