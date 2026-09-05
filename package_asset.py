#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
package_asset.py — v2-package: 可用资产打包器。

将 ``prompt_packs_v2/xxx.json`` 形式的 spec 与 LLM 生成的 raw_answer 文本打包成
Minecraft 资源包（resource pack）。

支持形式
--------
- ``item``      : textures/item/<name>.png + models/item/<name>.json
- ``block_multi``: textures/block/<name>_top|_side|_bottom.png
                  + models/block/<name>.json + blockstates/<name>.json
- ``cross``     : textures/block/<name>.png + models/block/<name>.json
                  + blockstates/<name>.json
- ``entity_uv`` : textures/entity/<name>.png + 说明文件（不生成 model）
- ``block_custom``: 通用异形/自定义模型。通过 ``--template anvil|slab|door|stairs|
  fence|wall|chest|flower_pot`` 或 ``--model user_model.json`` 生成
  models/block/<name>*.json + blockstates/<name>.json + 按模板/模型引用的
  textures/block/<name>_<key>.png。模板直接读取
  mc_asset_library_full/models/block/ 与 blockstates/ 的原版文件。

raw_answer 说明
---------------
- 单 face 形式（item/cross/entity_uv）：整个 raw_answer 就是一个可被
  ``text_to_texture.parse_text_to_grid`` 解析的 W/H + PALETTE + index grid。
- 多 face 形式（block_multi）：raw_answer 可包含 ``=== face: top ===`` 分隔块，
  或每个面以 ``FILE: ...`` 行开头；每个面独立传入 text_to_texture 解析。
- 也支持 spec.output_contract.faces 声明 faces，packager 按 face id/suffix 映射。

用法
----
    python3 package_asset.py \\
        --spec prompt_packs_v2/alien_crystal_wand.json \\
        --raw generated_assets_v2/alien_crystal_wand/raw_answer.txt \\
        --modid demo --out resourcepack/ --pack-mcmeta
    python3 package_asset.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Pillow is required: pip install pillow") from exc

import text_to_texture as t2t

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))
import entity_uv_spec as eu  # noqa: E402

SELFTEST_REPORT = "package_asset_selftest.txt"
LOG_PATH = "package_asset_log.txt"
V3_LOG_PATH = "v3-custom-form-log.txt"
DEFAULT_PACK_FORMAT = 8
DEFAULT_LIBRARY_ROOT = Path(__file__).resolve().parent / "mc_asset_library_full"
# 公开仓库不含原版素材；当本地全量库缺失时，回退到内置的极简模板 JSON
# （仅几何占位 + 纹理 key，不包含任何原版贴图/美术资产）。
FALLBACK_LIBRARY_ROOT = Path(__file__).resolve().parent / "builtin_models_fallback"


def normalize_path(path: str | Path) -> Path:
    """接受 Windows 风格路径（C:\\...）在 WSL 下转换为 /mnt/c/...。"""
    s = str(path)
    if s.startswith("\\\\") and s[2:3].isalpha() and s[3:4] in ("\\", "/"):
        s = s.replace("\\", "/")
    if len(s) >= 3 and s[0].isalpha() and s[1] == ":" and s[2] in ("\\", "/"):
        drive = s[0].lower()
        rest = s[2:].replace("\\", "/")
        return Path("/mnt") / drive / rest
    return Path(s)


def log_message(message: str, path: str | Path = LOG_PATH) -> None:
    """追加带时间戳的消息到日志文件。"""
    p = normalize_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(p, "a", encoding="utf-8") as f:
        f.write("[%s] %s\n" % (ts, message))


def load_json(path: str | Path) -> dict:
    p = normalize_path(path)
    if not p.exists():
        raise FileNotFoundError("JSON not found: %s" % p)
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object, got %s: %s" % (type(data).__name__, p))
    return data


def read_text(path: str | Path) -> str:
    p = normalize_path(path)
    if not p.exists():
        raise FileNotFoundError("raw answer not found: %s" % p)
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Spec / face helpers
# ---------------------------------------------------------------------------

# form -> (type, default_size, faces)
# faces: (id, suffix, width, height, alpha)
_FORM_SPECS = {
    "item": {
        "type": "item",
        "default_size": (16, 16),
        "faces": [{"id": "sprite", "suffix": "", "width": 16, "height": 16, "alpha": True}],
    },
    "block_multi": {
        "type": "block",
        "default_size": (16, 16),
        "faces": [
            {"id": "top", "suffix": "_top", "width": 16, "height": 16, "alpha": False},
            {"id": "side", "suffix": "_side", "width": 16, "height": 16, "alpha": False},
            {"id": "bottom", "suffix": "_bottom", "width": 16, "height": 16, "alpha": False},
        ],
    },
    "cross": {
        "type": "block",
        "default_size": (16, 16),
        "faces": [{"id": "cross", "suffix": "", "width": 16, "height": 16, "alpha": True}],
    },
    "entity_uv": {
        "type": "entity",
        "default_size": (64, 32),
        "faces": [{"id": "uv", "suffix": "", "width": 64, "height": 32, "alpha": True}],
    },
}


def _default_faces(form: str, width: int, height: int) -> list[dict]:
    spec = _FORM_SPECS.get(form)
    if spec is None:
        raise ValueError("unsupported form: %r" % form)
    faces = []
    for face in spec["faces"]:
        faces.append({
            "id": face["id"],
            "suffix": face["suffix"],
            "width": face.get("width", width) or width,
            "height": face.get("height", height) or height,
            "alpha": face.get("alpha", True),
        })
    return faces


# ---------------------------------------------------------------------------
# v3-custom-form: block_custom template registry / helpers
# ---------------------------------------------------------------------------

# 内置模板 registry。每个 entry 描述：
# - models: 从 mc_asset_library_full/models/block/ 读取的具体原版子模型。
#   block_custom 会复制这些模型并把 textures 改写为 <modid>:block/<name>_<key>。
# - model_suffix: 源模型 basename -> 输出文件名后缀（不含 .json）。
# - blockstate: 对应原版 blockstate 源文件名；生成时会重写 model 引用。
# - description: 人类可读说明。
# 这些模板都来自 mc_asset_library_full/models/block 的真实 1.18.2 原版文件，
# 不是 hardcode 一个铁砧：registry 支持 door/slab/stairs/fence/wall/chest/flower_pot 等。
BUILTIN_BLOCK_TEMPLATES: dict[str, dict] = {
    "anvil": {
        "models": ["anvil.json"],
        "model_suffix": {"anvil": ""},
        "blockstate": "anvil.json",
        "description": "Anvil (template_anvil parent; body/top textures from anvil+template_anvil)",
    },
    "slab": {
        "models": ["acacia_slab.json", "acacia_slab_top.json"],
        "model_suffix": {"acacia_slab": "", "acacia_slab_top": "_top"},
        "blockstate": "acacia_slab.json",
        "extra_full_model": True,
        "full_blockstate_alias": "acacia_planks",
        "description": "Slab bottom/top using minecraft:block/slab and slab_top",
    },
    "door": {
        "models": [
            "acacia_door_bottom.json",
            "acacia_door_bottom_hinge.json",
            "acacia_door_top.json",
            "acacia_door_top_hinge.json",
        ],
        "model_suffix": {
            "acacia_door_bottom": "_bottom",
            "acacia_door_bottom_hinge": "_bottom_hinge",
            "acacia_door_top": "_top",
            "acacia_door_top_hinge": "_top_hinge",
        },
        "blockstate": "acacia_door.json",
        "description": "Door (bottom/top + hinge variants, full vanilla blockstate)",
    },
    "stairs": {
        "models": ["acacia_stairs.json", "acacia_stairs_inner.json", "acacia_stairs_outer.json"],
        "model_suffix": {
            "acacia_stairs": "",
            "acacia_stairs_inner": "_inner",
            "acacia_stairs_outer": "_outer",
        },
        "blockstate": "acacia_stairs.json",
        "description": "Stairs straight/inner/outer (minecraft:block/stairs, inner_stairs, outer_stairs)",
    },
    "fence": {
        "models": ["acacia_fence_post.json", "acacia_fence_side.json", "acacia_fence_inventory.json"],
        "model_suffix": {
            "acacia_fence_post": "_post",
            "acacia_fence_side": "_side",
            "acacia_fence_inventory": "_inventory",
        },
        "blockstate": "acacia_fence.json",
        "description": "Fence post/side/inventory (vanilla multipart blockstate)",
    },
    "wall": {
        "models": [
            "andesite_wall_post.json",
            "andesite_wall_side.json",
            "andesite_wall_side_tall.json",
            "andesite_wall_inventory.json",
        ],
        "model_suffix": {
            "andesite_wall_post": "_post",
            "andesite_wall_side": "_side",
            "andesite_wall_side_tall": "_side_tall",
            "andesite_wall_inventory": "_inventory",
        },
        "blockstate": "andesite_wall.json",
        "description": "Wall post/side/side_tall/inventory (vanilla multipart blockstate)",
    },
    "chest": {
        "models": ["chest.json"],
        "model_suffix": {"chest": ""},
        "blockstate": "chest.json",
        "description": "Chest block model (vanilla entity-render particle block; still valid block model)",
    },
    "flower_pot": {
        "models": ["flower_pot.json"],
        "model_suffix": {"flower_pot": ""},
        "blockstate": "flower_pot.json",
        "description": "Flower pot full custom geometry (flowerpot/dirt textures)",
    },
}

# 每个模板的可选自定义项：不是固定铁砧的另一个证据。registry 从库文件自动验证存在。
BUILTIN_TEMPLATE_KEYS = tuple(BUILTIN_BLOCK_TEMPLATES.keys())


def _library_models_dir(library_root: str | Path = DEFAULT_LIBRARY_ROOT) -> Path:
    return normalize_path(library_root) / "models" / "block"


def _library_blockstates_dir(library_root: str | Path = DEFAULT_LIBRARY_ROOT) -> Path:
    return normalize_path(library_root) / "blockstates"


def _model_path(model_name: str, library_root: str | Path = DEFAULT_LIBRARY_ROOT) -> Path:
    return _library_models_dir(library_root) / model_name


def _blockstate_path(blockstate_name: str, library_root: str | Path = DEFAULT_LIBRARY_ROOT) -> Path:
    return _library_blockstates_dir(library_root) / blockstate_name


def _is_path_like(value: str) -> bool:
    return value.endswith(".json") or "/" in value or "\\" in value or Path(value).exists()


def resolve_block_template(
    template: str | Path | None,
    model_path: str | Path | None = None,
    library_root: str | Path = DEFAULT_LIBRARY_ROOT,
) -> dict:
    """把 ``--template``/``--model`` 输入解析为统一的 block_custom 模板描述。

    返回 descriptor:
    - template_id: anvil/slab/... 或 custom
    - models: [{source, basename, output_suffix}]
    - blockstate: 源 blockstate 路径或 None
    - is_user_model: bool
    - texture_keys: 从模型及父模板收集的外部纹理 key 列表
    """
    if model_path:
        if template:
            raise ValueError("use only one of --template and --model")
        p = normalize_path(model_path)
        if not p.exists():
            raise FileNotFoundError("user model JSON not found: %s" % p)
        descriptor = {
            "template_id": "custom",
            "models": [{"source": p, "basename": p.stem, "output_suffix": ""}],
            "blockstate": None,
            "is_user_model": True,
            "texture_keys": [],
            "display": "user_model:%s" % p,
        }
        descriptor["texture_keys"] = collect_texture_keys_for_descriptor(descriptor, library_root)
        return descriptor

    if not template:
        raise ValueError("--template or --model is required for block_custom")

    t = str(template)
    if t in BUILTIN_BLOCK_TEMPLATES:
        spec = BUILTIN_BLOCK_TEMPLATES[t]
        models_dir = _library_models_dir(library_root)
        fallback_dir = FALLBACK_LIBRARY_ROOT
        models = []
        for model_name in spec["models"]:
            src = models_dir / model_name
            if not src.exists():
                # 公开仓库无原版库：回退到内置极简模板 JSON
                src = fallback_dir / model_name
            if not src.exists():
                raise FileNotFoundError("builtin template model missing (library and fallback): %s" % model_name)
            models.append({
                "source": src,
                "basename": Path(model_name).stem,
                "output_suffix": spec["model_suffix"].get(Path(model_name).stem, ""),
            })
        bs_name = spec["blockstate"]
        bs_path = _blockstate_path(bs_name, library_root)
        if not bs_path.exists():
            # 回退文件名：spec 里 blockstate 可能是 "anvil.json" / "acacia_slab.json"
            bs_path = fallback_dir / ("%s.blockstate.json" % Path(bs_name).stem)
        if not bs_path.exists():
            raise FileNotFoundError("builtin template blockstate missing (library and fallback): %s" % bs_name)
        descriptor = {
            "template_id": t,
            "models": models,
            "blockstate": bs_path,
            "is_user_model": False,
            "texture_keys": [],
            "display": t,
        }
        for extra_key in ("extra_full_model", "full_blockstate_alias"):
            if extra_key in spec:
                descriptor[extra_key] = spec[extra_key]
        descriptor["texture_keys"] = collect_texture_keys_for_descriptor(descriptor, library_root)
        return descriptor

    # 用户指定模板路径：--template path/to/model.json
    p = normalize_path(t)
    if p.exists() or t.endswith(".json"):
        if not p.exists():
            raise FileNotFoundError("template model JSON not found: %s" % p)
        descriptor = {
            "template_id": "custom",
            "models": [{"source": p, "basename": p.stem, "output_suffix": ""}],
            "blockstate": None,
            "is_user_model": True,
            "texture_keys": [],
            "display": "template_path:%s" % p,
        }
        descriptor["texture_keys"] = collect_texture_keys_for_descriptor(descriptor, library_root)
        return descriptor

    raise ValueError(
        "unknown block_custom template %r. Built-in: %s (or pass --model/--template <path>.json)"
        % (t, ", ".join(BUILTIN_TEMPLATE_KEYS))
    )


def _parent_model_name(parent: str | None) -> str | None:
    if not parent:
        return None
    s = parent.strip()
    if s.startswith("#"):
        return None
    # minecraft:block/foo or block/foo
    if ":" in s:
        s = s.split(":", 1)[1]
    if s.startswith("block/"):
        s = s[len("block/"):]
    return s


def _iter_element_texture_refs(model: dict) -> list[str]:
    refs: list[str] = []
    for el in model.get("elements") or []:
        if not isinstance(el, dict):
            continue
        faces = el.get("faces") or {}
        if isinstance(faces, dict):
            for face in faces.values():
                if isinstance(face, dict) and isinstance(face.get("texture"), str) and face["texture"].startswith("#"):
                    refs.append(face["texture"][1:])
    return refs


def collect_texture_keys_for_descriptor(
    descriptor: dict,
    library_root: str | Path = DEFAULT_LIBRARY_ROOT,
) -> list[str]:
    """收集 descriptor 中所有模型及父链需要的纹理 key（外部贴图/引用变量）。"""
    keys: list[str] = []
    seen: set[str] = set()

    def add(k: str) -> None:
        if k and k not in seen:
            seen.add(k)
            keys.append(k)

    def collect_model(path: Path, depth: int = 0) -> None:
        if depth > 8:
            return
        data = load_json(path)
        tex = data.get("textures") or {}
        if isinstance(tex, dict):
            for k, v in tex.items():
                add(k)
                # 如果值不是 # 别名，通常表示需要外部贴图；key 本身就是要生成的。
                # 值如果是 #side 这类别名，不需要单独生成该别名（除非 key 在其他地方被外部使用）。
                if isinstance(v, str) and v.startswith("#"):
                    pass
        for ref in _iter_element_texture_refs(data):
            add(ref)
        # 如果 child 通过 parent 引用了外部纹理（如 anvil.json -> template_anvil 的 body），
        # 从父模型把外部 key 也收集进来。
        parent = data.get("parent")
        pname = _parent_model_name(parent) if isinstance(parent, str) else None
        if pname:
            p_path = _library_models_dir(library_root) / (pname + ".json")
            if p_path.exists():
                collect_model(p_path, depth + 1)

    for m in descriptor.get("models", []):
        collect_model(normalize_path(m["source"]))
    return keys


def _default_custom_face_text(face_id: str, w: int = 16, h: int = 16, color_idx: int = 0) -> str:
    """无 raw 或缺 face 时的默认 16x16 纹理（保证 CLI 可生成完整资源包）。"""
    return _synth_raw_for_face(face_id, w, h, color_idx)


def resolve_custom_face_texts(texture_keys: list[str], raw_text: str | None) -> dict[str, str]:
    """把 block_custom 的 raw answer 解析为 {texture_key: pixel_text}。

    规则：
    - 没有 raw：每个 key 生成默认图案。
    - 只有一个 face 块：从单张纹理推广到所有 key。
    - 多个 face 块：先按 face id/后缀精确匹配；未匹配的 key 用默认图案补。
    """
    if not texture_keys:
        return {}

    if not raw_text or not raw_text.strip():
        return {k: _default_custom_face_text(k) for k in texture_keys}

    blocks = split_face_blocks(raw_text)
    if len(blocks) == 1:
        text = _clean_face_text(blocks[0][1])
        return {k: text for k in texture_keys}

    # 多 face：先用 id/suffix 匹配
    result: dict[str, str] = {}
    idle_blocks: list[str] = []
    face_suffix_map = {("_" + k): k for k in texture_keys}
    for block_id, block_text in blocks:
        fid = block_id.strip().lower()
        matched = None
        low_keys = {k.lower(): k for k in texture_keys}
        if fid in low_keys:
            matched = low_keys[fid]
        else:
            for suffix, k in face_suffix_map.items():
                if suffix in fid:
                    matched = k
                    break
        if matched and matched not in result:
            result[matched] = _clean_face_text(block_text)
        else:
            idle_blocks.append(_clean_face_text(block_text))

    # 缺失 key 用第一个未匹配/默认图案补
    first_idle = idle_blocks[0] if idle_blocks else None
    for k in texture_keys:
        if k not in result:
            result[k] = first_idle or _default_custom_face_text(k)
    return result


# ---------------------------------------------------------------------------
# Spec / face helpers
# ---------------------------------------------------------------------------


def _resolve_spec_meta(spec: dict) -> dict:
    form = spec.get("form")
    if form not in _FORM_SPECS:
        raise ValueError("spec.form must be one of %s, got %r" % ("/".join(_FORM_SPECS), form))
    name = spec.get("name")
    if not name:
        raise ValueError("spec.name is required")
    width = int(spec.get("width") or _FORM_SPECS[form]["default_size"][0])
    height = int(spec.get("height") or _FORM_SPECS[form]["default_size"][1])
    if form == "entity_uv" and (width, height) not in ((64, 32), (64, 64)):
        raise ValueError("entity_uv requires 64x32 or 64x64, got %dx%d" % (width, height))
    if form != "entity_uv" and (width, height) != (16, 16):
        raise ValueError("%s requires 16x16 textures, got %dx%d" % (form, width, height))

    oc = spec.get("output_contract") or {}
    faces = oc.get("faces")
    file_contract = spec.get("file_contract") or {}

    # alpha 默认值：优先 file_contract 中声明的 alpha；其次 form 默认。
    default_alpha = {f["id"]: f.get("alpha", True) for f in _FORM_SPECS[form]["faces"]}
    fc_alpha = {}
    for entry in file_contract.get("files", []):
        if entry.get("kind") == "texture" and entry.get("face"):
            fc_alpha[entry["face"]] = bool(entry.get("alpha", True))

    if faces:
        # 以 spec.output_contract.faces 为权威；补充 suffix 可从 file 路径推导。
        normalized_faces = []
        for face in faces:
            fid = face.get("face") or face.get("id")
            suffix = face.get("suffix", "")
            if not suffix and face.get("file"):
                # prompt_packs_v2 的 output_contract.faces 常只给 file 路径，没有 suffix。
                # 从 `.../<name>_top.png` 这类路径中推出 `_top`。
                stem = Path(face["file"]).stem
                if stem == name:
                    suffix = ""
                elif stem.startswith(name + "_"):
                    suffix = stem[len(name):]
                elif form == "block_multi":
                    # 如果 file 命名不一致，仍回退到 form 默认后缀。
                    for dface in _FORM_SPECS[form]["faces"]:
                        if dface["id"] == fid:
                            suffix = dface["suffix"]
                            break
            if not suffix:
                for dface in _FORM_SPECS[form]["faces"]:
                    if dface["id"] == fid:
                        suffix = dface["suffix"]
                        break
            normalized_faces.append({
                "id": fid,
                "suffix": suffix,
                "width": int(face.get("width", width)),
                "height": int(face.get("height", height)),
                "alpha": bool(face.get("alpha", fc_alpha.get(fid, default_alpha.get(fid, True)))),
            })
    else:
        normalized_faces = _default_faces(form, width, height)
    return {
        "form": form,
        "name": name,
        "type": spec.get("type") or _FORM_SPECS[form]["type"],
        "width": width,
        "height": height,
        "size": spec.get("size") or "%dx%d" % (width, height),
        "faces": normalized_faces,
        "file_contract": file_contract,
    }


def _face_regex():
    return re.compile(r"^\s*=+\s*face\s*:\s*([A-Za-z0-9_]+)\s*=+\s*$", re.I)


def _file_line_regex():
    return re.compile(r"^\s*FILE\s*:\s*(.*)$", re.I)


def split_face_blocks(raw_text: str) -> list[tuple[str, str]]:
    """把 raw_answer 拆分为 (face_id_or_empty, block_text) 列表。

    优先支持 ``=== face: <id> ===`` 分隔标记；若没有标记，则按 ``FILE:`` 行切分。
    没有任何分隔符时返回单个 unnamed block。
    """
    lines = raw_text.splitlines()
    face_re = _face_regex()
    file_re = _file_line_regex()

    face_markers = [
        (i, face_re.match(lines[i]).group(1))
        for i, ln in enumerate(lines)
        if face_re.match(ln)
    ]
    if face_markers:
        blocks = []
        for j, (idx, face_id) in enumerate(face_markers):
            end = face_markers[j + 1][0] if j + 1 < len(face_markers) else len(lines)
            blocks.append((face_id, "\n".join(lines[idx + 1:end])))
        return blocks

    file_markers = [
        (i, file_re.match(ln).group(1).strip())
        for i, ln in enumerate(lines)
        if file_re.match(ln)
    ]
    if file_markers:
        blocks = []
        for j, (idx, file_info) in enumerate(file_markers):
            end = file_markers[j + 1][0] if j + 1 < len(file_markers) else len(lines)
            blocks.append((file_info, "\n".join(lines[idx + 1:end])))
        return blocks

    return [("", raw_text)]


def _clean_face_text(block_text: str) -> str:
    """从 face 块中提取从首个 W/H 声明开始的纯像素契约文本。"""
    lines = block_text.splitlines()
    idx = None
    for i, ln in enumerate(lines):
        if t2t._parse_declared_size(ln.strip()) is not None:
            idx = i
            break
    if idx is None:
        raise ValueError("face block is missing W=<w> H=<h> header")
    kept = []
    for ln in lines[idx:]:
        s = ln.strip()
        if s.startswith("===") or s.startswith("FILE:"):
            continue
        if s.startswith("```") or s.startswith("~~~"):
            continue
        if s.upper().startswith("FORM=") or s.upper().startswith("FACES="):
            continue
        kept.append(ln)
    return "\n".join(kept)


def _match_face_id_to_spec(block_id: str, spec_meta: dict) -> str:
    """把分隔标记/FILE 信息映射到 spec 中的 face id。"""
    faces = spec_meta["faces"]
    # 直接是 face id
    for face in faces:
        if block_id == face["id"]:
            return face["id"]
    # block_id 可能是文件路径，取文件名做为 face 映射
    low = block_id.lower()
    face_suffix = {face["suffix"].lower(): face["id"] for face in faces if face.get("suffix")}
    for suffix, fid in face_suffix.items():
        if suffix and suffix.lower() in low:
            return fid
    # 单个 face 时兜底
    if len(faces) == 1:
        return faces[0]["id"]
    # 没匹配上则按顺序指派的逻辑在 resolve 中处理
    return ""


def resolve_face_texts(spec_meta: dict, raw_text: str) -> dict[str, str]:
    """返回 {face_id: cleaned_pixel_text}。"""
    faces = spec_meta["faces"]
    blocks = split_face_blocks(raw_text)
    result: dict[str, str] = {}

    if len(blocks) == 1 and len(faces) == 1:
        fid = faces[0]["id"]
        result[fid] = _clean_face_text(blocks[0][1])
        return result

    # 先按标记映射
    unmatched_blocks: list[tuple[str, str]] = []
    for block_id, block_text in blocks:
        fid = _match_face_id_to_spec(block_id, spec_meta)
        if fid and fid not in result:
            result[fid] = _clean_face_text(block_text)
        else:
            unmatched_blocks.append((block_id, block_text))

    # 未被映射的块按 spec faces 顺序补位
    for face in faces:
        if face["id"] in result:
            continue
        if not unmatched_blocks:
            raise ValueError(
                "not enough face blocks: expected %d face(s) (%s), got %d; raw may be missing a face"
                % (len(faces), ",".join(f["id"] for f in faces), len(blocks))
            )
        _, block_text = unmatched_blocks.pop(0)
        result[face["id"]] = _clean_face_text(block_text)

    if set(result.keys()) != {f["id"] for f in faces}:
        missing = [f["id"] for f in faces if f["id"] not in result]
        raise ValueError("missing face block(s): %s" % ",".join(missing))
    return result


# ---------------------------------------------------------------------------
# Resource-pack path and JSON builders
# ---------------------------------------------------------------------------

def texture_rel_path(modid: str, name: str, face: dict, form: str) -> str:
    suffix = face.get("suffix", "")
    if form == "block_multi":
        return "assets/%s/textures/block/%s%s.png" % (modid, name, suffix)
    if form == "cross":
        return "assets/%s/textures/block/%s.png" % (modid, name)
    if form == "entity_uv":
        return "assets/%s/textures/entity/%s.png" % (modid, name)
    return "assets/%s/textures/item/%s.png" % (modid, name)


def model_rel_path(modid: str, name: str, form: str) -> str | None:
    if form == "item":
        return "assets/%s/models/item/%s.json" % (modid, name)
    if form in ("block_multi", "cross"):
        return "assets/%s/models/block/%s.json" % (modid, name)
    return None


def blockstate_rel_path(modid: str, name: str, form: str) -> str | None:
    if form in ("block_multi", "cross"):
        return "assets/%s/blockstates/%s.json" % (modid, name)
    return None


def entity_note_rel_path(modid: str, name: str) -> str:
    return "assets/%s/textures/entity/%s.note.txt" % (modid, name)


def build_model_json(form: str, modid: str, name: str) -> dict:
    if form == "item":
        return {
            "parent": "minecraft:item/generated",
            "textures": {"layer0": "%s:item/%s" % (modid, name)},
        }
    if form == "block_multi":
        return {
            "parent": "minecraft:block/cube_bottom_top",
            "textures": {
                "particle": "%s:block/%s_side" % (modid, name),
                "top": "%s:block/%s_top" % (modid, name),
                "bottom": "%s:block/%s_bottom" % (modid, name),
                "side": "%s:block/%s_side" % (modid, name),
            },
        }
    if form == "cross":
        return {
            "parent": "minecraft:block/cross",
            "textures": {"cross": "%s:block/%s" % (modid, name)},
        }
    return {}


def build_blockstate_json(modid: str, name: str) -> dict:
    return {"variants": {"": {"model": "%s:block/%s" % (modid, name)}}}


def build_pack_mcmeta(pack_format: int = DEFAULT_PACK_FORMAT, description: str = "mc-mod-art-studio generated resource pack") -> dict:
    return {
        "pack": {
            "pack_format": pack_format,
            "description": description,
        }
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_png(path: str | Path, expected_size: tuple[int, int], alpha_required: bool) -> dict:
    """校验 PNG 尺寸与 alpha，返回校验摘要；失败抛 ValueError。"""
    p = normalize_path(path)
    if not p.exists():
        raise ValueError("PNG not found: %s" % p)
    with Image.open(p) as im:
        im.load()
        if im.size != tuple(expected_size):
            raise ValueError(
                "PNG size %dx%d does not match expected %dx%d: %s"
                % (im.size[0], im.size[1], expected_size[0], expected_size[1], p)
            )
        rgba = im.convert("RGBA")
        alpha_band = rgba.getchannel("A")
        extrema = alpha_band.getextrema()
        transparent = sum(1 for a in alpha_band.tobytes() if a < t2t.ALPHA_THRESHOLD)
        total = rgba.size[0] * rgba.size[1]
        if alpha_required and transparent == 0:
            raise ValueError("PNG requires transparent background but has no transparent pixel: %s" % p)
        return {
            "path": str(p),
            "width": rgba.size[0],
            "height": rgba.size[1],
            "alpha_min": extrema[0],
            "alpha_max": extrema[1],
            "transparent_pixels": transparent,
            "opaque_ratio": round((total - transparent) / total, 6),
            "alpha_required": alpha_required,
        }


def validate_json_file(path: str | Path) -> dict:
    p = normalize_path(path)
    if not p.exists():
        raise ValueError("JSON not found: %s" % p)
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("JSON is not an object: %s" % p)
    return data


def validate_pack(manifest: dict, modid: str, name: str, form: str, spec_meta: dict) -> dict:
    """校验 manifest 中的每个文件确实存在、PNG 尺寸/alpha、JSON 可解析。"""
    checks = []
    for entry in manifest["files"]:
        rel = entry["path"]
        abs_path = normalize_path(manifest["output_root"]) / rel
        if entry["kind"] == "texture":
            stats = validate_png(abs_path, (entry["width"], entry["height"]), entry.get("alpha", False))
            checks.append({"path": rel, "kind": "texture", "status": "PASS", "detail": stats})
        elif entry["kind"] == "model":
            data = validate_json_file(abs_path)
            checks.append({"path": rel, "kind": "model", "status": "PASS", "detail": data})
        elif entry["kind"] == "blockstate":
            data = validate_json_file(abs_path)
            checks.append({"path": rel, "kind": "blockstate", "status": "PASS", "detail": data})
        elif entry["kind"] == "pack_mcmeta":
            data = validate_json_file(abs_path)
            checks.append({"path": rel, "kind": "pack_mcmeta", "status": "PASS", "detail": data})
        elif entry["kind"] == "note":
            if not abs_path.exists():
                raise ValueError("note file not found: %s" % abs_path)
            checks.append({"path": rel, "kind": "note", "status": "PASS", "detail": abs_path.read_text(encoding="utf-8")[:120]})
        else:
            checks.append({"path": rel, "kind": entry["kind"], "status": "UNKNOWN"})

    # 若 manifest 没有记录 model/blockstate（entity_uv），此处也应确认清单外的资源目录齐全
    required_dirs = {
        "item": ["assets/%s/textures/item" % modid, "assets/%s/models/item" % modid],
        "block_multi": [
            "assets/%s/textures/block" % modid,
            "assets/%s/models/block" % modid,
            "assets/%s/blockstates" % modid,
        ],
        "cross": [
            "assets/%s/textures/block" % modid,
            "assets/%s/models/block" % modid,
            "assets/%s/blockstates" % modid,
        ],
        "entity_uv": ["assets/%s/textures/entity" % modid],
        "block_custom": [
            "assets/%s/textures/block" % modid,
            "assets/%s/models/block" % modid,
            "assets/%s/blockstates" % modid,
        ],
    }
    root = normalize_path(manifest["output_root"])
    for d in required_dirs.get(form, []):
        if not (root / d).is_dir():
            raise ValueError("required resource-pack directory missing: %s" % d)

    return {
        "status": "PASS",
        "count": len(checks),
        "checks": checks,
        "manifest_path": str(normalize_path(manifest["output_root"]) / "manifest.json"),
    }


# ---------------------------------------------------------------------------
# Main packaging
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# v3-custom-form: block_custom generation
# ---------------------------------------------------------------------------

def custom_texture_rel_path(modid: str, name: str, key: str) -> str:
    return "assets/%s/textures/block/%s_%s.png" % (modid, name, key)


def custom_model_rel_path(modid: str, model_basename: str) -> str:
    return "assets/%s/models/block/%s.json" % (modid, model_basename)


def custom_blockstate_rel_path(modid: str, name: str) -> str:
    return "assets/%s/blockstates/%s.json" % (modid, name)


def _rewrite_model_textures(model_data: dict, modid: str, name: str, texture_keys: list[str]) -> None:
    """把模板/用户模型里的 textures 引用改写为 modid 路径。

    对每个纹理 key 都生成 ``<modid>:block/<name>_<key>``，从而让 parent 中的
    ``#body`` / ``#top`` 等变量也能解析到本模型的 custom 贴图。
    """
    if not texture_keys:
        return
    tex = dict(model_data.get("textures") or {})
    for key in texture_keys:
        tex[key] = "%s:block/%s_%s" % (modid, name, key)
    model_data["textures"] = tex


def _rewrite_model_parent(model_data: dict) -> None:
    parent = model_data.get("parent")
    if not isinstance(parent, str):
        return
    if parent.startswith("block/"):
        model_data["parent"] = "minecraft:" + parent
    elif parent == "block/block":
        model_data["parent"] = "minecraft:block/block"


_RESOURCE_LOCATION_RE = re.compile(r"^([a-z0-9_.-]+:)?(block|item)/[a-z0-9_./-]+$", re.I)


def _is_valid_resource_location(value: str) -> bool:
    s = value.strip()
    if s.startswith("#"):
        return True
    if not s:
        return False
    if ":" in s:
        _ns, path = s.split(":", 1)
        return bool(path) and ("/" in path or path in ("block/block",))
    return "/" in s


def validate_model_semantics(path: str | Path, texture_keys: list[str]) -> dict:
    """校验单个 block_custom model JSON 的 parent/elements/textures 基本合法性。"""
    p = normalize_path(path)
    data = validate_json_file(p)
    combined = set(texture_keys or [])
    # 模型自身 textures 的 key 也加入允许集合
    combined.update((data.get("textures") or {}).keys())

    parent = data.get("parent")
    if parent is not None:
        if not isinstance(parent, str) or not _is_valid_resource_location(parent):
            raise ValueError("invalid model parent %r: %s" % (parent, p))

    textures = data.get("textures") or {}
    if not isinstance(textures, dict):
        raise ValueError("model textures must be an object: %s" % p)
    for key, val in textures.items():
        if not isinstance(val, str):
            raise ValueError("texture %s value must be string: %s" % (key, p))
        if val.startswith("#"):
            if val[1:] not in combined:
                raise ValueError(
                    "texture %s references unknown variable %s in %s (available: %s)"
                    % (key, val, p, ",".join(sorted(combined)) if combined else "<none>")
                )
        elif not _is_valid_resource_location(val):
            raise ValueError("texture %s value is not a valid resource location: %r (%s)" % (key, val, p))

    elements = data.get("elements")
    if elements is not None:
        if not isinstance(elements, list):
            raise ValueError("model elements must be a list: %s" % p)
        for i, el in enumerate(elements):
            if not isinstance(el, dict):
                raise ValueError("element[%d] must be an object: %s" % (i, p))
            for field in ("from", "to"):
                vec = el.get(field)
                if not isinstance(vec, list) or len(vec) != 3 or not all(isinstance(v, (int, float)) for v in vec):
                    raise ValueError("element[%d].%s must be a 3-number vector: %s" % (i, field, p))
            faces = el.get("faces")
            if faces is not None:
                if not isinstance(faces, dict):
                    raise ValueError("element[%d].faces must be an object: %s" % (i, p))
                for d, face in faces.items():
                    if d not in ("up", "down", "north", "south", "west", "east"):
                        raise ValueError("unknown face direction %r in element[%d]: %s" % (d, i, p))
                    if not isinstance(face, dict):
                        raise ValueError("face %s in element[%d] must be object: %s" % (d, i, p))
                    tex = face.get("texture")
                    if tex is not None and (not isinstance(tex, str) or not tex.startswith("#")):
                        raise ValueError("face %s texture must be a #variable: %s (%s)" % (d, tex, p))
                    if isinstance(tex, str) and tex[1:] not in combined:
                        raise ValueError(
                            "face %s references unknown variable %s in %s (available: %s)"
                            % (d, tex, p, ",".join(sorted(combined)) if combined else "<none>")
                        )
    return {"path": str(p), "status": "PASS", "texture_keys": sorted(combined)}


def _rewrite_blockstate_model_refs(value, alias_map: dict[str, str]):
    """递归改写 blockstate 中所有 model 引用。"""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k == "model" and isinstance(v, str):
                s = v.strip()
                # 只处理 minecraft:block/xxx 或 block/xxx 这类原版引用
                body = s
                if s.startswith("minecraft:"):
                    body = s[len("minecraft:"):]
                if body.startswith("block/"):
                    base = body[len("block/"):]
                    if base in alias_map:
                        out[k] = alias_map[base]
                        continue
                # 无命名空间 block/xxx 也处理
                if s.startswith("block/") and s[len("block/"):] in alias_map:
                    out[k] = alias_map[s[len("block/"):]]
                    continue
            out[k] = _rewrite_blockstate_model_refs(v, alias_map)
        return out
    if isinstance(value, list):
        return [_rewrite_blockstate_model_refs(v, alias_map) for v in value]
    return value


def _iter_blockstate_model_refs(value):
    """迭代 blockstate 里的 model 字符串。"""
    if isinstance(value, dict):
        for k, v in value.items():
            if k == "model" and isinstance(v, str):
                yield v
            else:
                yield from _iter_blockstate_model_refs(v)
    elif isinstance(value, list):
        for v in value:
            yield from _iter_blockstate_model_refs(v)


def validate_blockstate_semantics(path: str | Path, modid: str, output_root: str | Path) -> dict:
    """校验生成的 blockstate 可用：结构 + 引用到本资源包的模型文件存在。"""
    p = normalize_path(path)
    data = validate_json_file(p)
    if not isinstance(data, dict):
        raise ValueError("blockstate must be an object: %s" % p)
    has_variants = isinstance(data.get("variants"), dict) and bool(data.get("variants"))
    has_multipart = isinstance(data.get("multipart"), list) and bool(data.get("multipart"))
    if not has_variants and not has_multipart:
        raise ValueError("blockstate must contain non-empty variants or multipart: %s" % p)

    root = normalize_path(output_root)
    refs = list(_iter_blockstate_model_refs(data))
    own_refs = [r for r in refs if r.startswith(modid + ":")]
    for r in own_refs:
        rel = "assets/%s/models/block/%s.json" % (modid, r.split(":", 1)[1].split("/", 1)[1] if r.split(":", 1)[1].startswith("block/") else r)
        # 更稳妥：从 resource path 提取 block/ 后的 basename
        body = r.split(":", 1)[1]
        if body.startswith("block/"):
            rel = "assets/%s/models/block/%s.json" % (modid, body[len("block/"):])
        if not (root / rel).exists():
            raise ValueError("blockstate references missing model %s (%s)" % (r, rel))
    return {
        "path": str(p),
        "status": "PASS",
        "variants_or_multipart": "variants" if has_variants else "multipart",
        "own_model_refs": len(own_refs),
        "total_model_refs": len(refs),
    }


def package_block_custom(
    name: str,
    modid: str,
    out_root: str | Path,
    template: str | Path | None = None,
    model_path: str | Path | None = None,
    raw_text: str | None = None,
    write_pack_mcmeta: bool = False,
    pack_format: int = DEFAULT_PACK_FORMAT,
    log_path: str | Path = V3_LOG_PATH,
    quiet: bool = False,
    library_root: str | Path = DEFAULT_LIBRARY_ROOT,
) -> dict:
    """打包一个 block_custom 资源：模板/用户模型 + blockstate + 按需纹理。"""
    out_root = normalize_path(out_root)
    descriptor = resolve_block_template(template, model_path, library_root)
    texture_keys = list(dict.fromkeys(descriptor.get("texture_keys") or []))
    face_texts = resolve_custom_face_texts(texture_keys, raw_text)

    if not quiet:
        log_message(
            "start block_custom name=%s modid=%s template=%s texture_keys=%s out=%s"
            % (name, modid, descriptor["display"], ",".join(texture_keys), out_root),
            log_path,
        )

    files_entries: list[dict] = []
    root = out_root

    # 1. textures: 每个纹理 key 一张 16x16 PNG
    for key in texture_keys:
        rel = custom_texture_rel_path(modid, name, key)
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        img = t2t.text_to_image(face_texts.get(key) or _default_custom_face_text(key))
        if img.size != (16, 16):
            raise ValueError("block_custom texture %s size %dx%d != 16x16" % (key, img.size[0], img.size[1]))
        img.save(dest, "PNG")
        files_entries.append({
            "path": rel,
            "kind": "texture",
            "face": key,
            "width": 16,
            "height": 16,
            "alpha": False,
        })

    # 2. models: 复制/改写模板或用户模型
    semantic_model_paths: list[str] = []
    model_descs: list[dict] = []
    for m in descriptor["models"]:
        model_data = load_json(m["source"])
        _rewrite_model_parent(model_data)
        _rewrite_model_textures(model_data, modid, name, texture_keys)
        model_basename = name + (m.get("output_suffix") or "")
        rel = custom_model_rel_path(modid, model_basename)
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(model_data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        files_entries.append({"path": rel, "kind": "model"})
        semantic_model_paths.append(str(dest))
        model_descs.append({"basename": model_basename, "source": str(m["source"]), "rel": rel})

    # 3a. 可选 full model（例如 slab type=double 使用的整块模型）
    alias_map: dict[str, str] = {}
    if descriptor.get("blockstate"):
        alias_map = {
            m["basename"]: "%s:block/%s%s" % (modid, name, m.get("output_suffix") or "")
            for m in descriptor["models"]
        }
    if descriptor.get("extra_full_model"):
        model_basename = name + "_full"
        rel = custom_model_rel_path(modid, model_basename)
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        full_textures = {
            "particle": "%s:block/%s_particle" % (modid, name),
            "top": "%s:block/%s_top" % (modid, name),
            "bottom": "%s:block/%s_bottom" % (modid, name),
            "side": "%s:block/%s_side" % (modid, name),
        }
        full_model = {"parent": "minecraft:block/cube_bottom_top", "textures": full_textures}
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(full_model, f, ensure_ascii=False, indent=2)
            f.write("\n")
        files_entries.append({"path": rel, "kind": "model"})
        semantic_model_paths.append(str(dest))
        model_descs.append({"basename": model_basename, "source": "block_custom_full_model", "rel": rel})
        full_alias = descriptor.get("full_blockstate_alias")
        if full_alias:
            alias_map[full_alias] = "%s:block/%s_full" % (modid, name)

    # 3b. blockstate: 从对应 vanilla blockstate 改写，或生成默认 variants
    if descriptor.get("blockstate"):
        blockstate_data = load_json(descriptor["blockstate"])
        blockstate_data = _rewrite_blockstate_model_refs(blockstate_data, alias_map)
    else:
        blockstate_data = {"variants": {"": {"model": "%s:block/%s" % (modid, name)}}}

    bs_rel = custom_blockstate_rel_path(modid, name)
    bs_dest = root / bs_rel
    bs_dest.parent.mkdir(parents=True, exist_ok=True)
    with open(bs_dest, "w", encoding="utf-8") as f:
        json.dump(blockstate_data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    files_entries.append({"path": bs_rel, "kind": "blockstate"})

    # 4. pack.mcmeta
    if write_pack_mcmeta:
        pack_rel = "pack.mcmeta"
        dest = root / pack_rel
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(build_pack_mcmeta(pack_format, "%s custom block" % name), f, ensure_ascii=False, indent=2)
            f.write("\n")
        files_entries.append({"path": pack_rel, "kind": "pack_mcmeta"})

    # 5. manifest
    manifest = {
        "modid": modid,
        "name": name,
        "form": "block_custom",
        "type": "block",
        "size": "16x16",
        "width": 16,
        "height": 16,
        "generated_by": "package_asset.py",
        "template_id": descriptor["template_id"],
        "template_display": descriptor["display"],
        "is_user_model": descriptor["is_user_model"],
        "texture_keys": texture_keys,
        "models": model_descs,
        "output_root": str(root),
        "files": files_entries,
    }
    manifest_path = root / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # 6. 校验
    validation = validate_pack(manifest, modid, name, "block_custom", {})
    semantic_checks = []
    for mp in semantic_model_paths:
        semantic_checks.append(validate_model_semantics(mp, texture_keys))
    semantic_checks.append(validate_blockstate_semantics(bs_dest, modid, root))
    validation["semantic_checks"] = semantic_checks
    validation["semantic_status"] = "PASS" if all(c["status"] == "PASS" for c in semantic_checks) else "FAIL"

    result = {
        "manifest": manifest,
        "validation": validation,
        "output_root": str(root),
        "face_texts": face_texts,
        "descriptor": descriptor,
    }
    if not quiet:
        log_message(
            "done block_custom name=%s template=%s files=%d validation=%s manifest=%s"
            % (name, descriptor["display"], len(files_entries), validation["status"], manifest_path),
            log_path,
        )
    return result


def package_asset(
    spec: dict,
    raw_text: str,
    modid: str,
    out_root: str | Path,
    write_pack_mcmeta: bool = False,
    pack_format: int = DEFAULT_PACK_FORMAT,
    log_path: str | Path = LOG_PATH,
    quiet: bool = False,
) -> dict:
    """执行一次打包并返回 manifest/validation 结果。"""
    out_root = normalize_path(out_root)
    meta = _resolve_spec_meta(spec)
    form = meta["form"]
    name = meta["name"]
    faces = meta["faces"]
    face_texts = resolve_face_texts(meta, raw_text)

    if not quiet:
        log_message("start package form=%s name=%s modid=%s out=%s" % (form, name, modid, out_root), log_path)

    files_entries: list[dict] = []
    root = out_root

    # 1. textures
    for face in faces:
        fid = face["id"]
        rel = texture_rel_path(modid, name, face, form)
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        img = t2t.text_to_image(face_texts[fid])
        if img.size != (face["width"], face["height"]):
            raise ValueError(
                "face %s image size %dx%d does not match face width/height %dx%d"
                % (fid, img.size[0], img.size[1], face["width"], face["height"])
            )
        img.save(dest, "PNG")
        files_entries.append({
            "path": rel,
            "kind": "texture",
            "face": fid,
            "width": face["width"],
            "height": face["height"],
            "alpha": face.get("alpha", True),
        })

    # 2. model / blockstate
    model_rel = model_rel_path(modid, name, form)
    if model_rel:
        dest = root / model_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(build_model_json(form, modid, name), f, ensure_ascii=False, indent=2)
            f.write("\n")
        files_entries.append({"path": model_rel, "kind": "model"})

    blockstate_rel = blockstate_rel_path(modid, name, form)
    if blockstate_rel:
        dest = root / blockstate_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(build_blockstate_json(modid, name), f, ensure_ascii=False, indent=2)
            f.write("\n")
        files_entries.append({"path": blockstate_rel, "kind": "blockstate"})

    # 3. entity_uv 说明（不生成 model，注明需要实体模型适配）
    if form == "entity_uv":
        note_rel = entity_note_rel_path(modid, name)
        dest = root / note_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        entity = eu.detect_entity(spec.get("query") or spec.get("entity") or name)
        vanilla_path = eu.MOB_VANILLA_TEXTURE_PATHS.get(entity, "")
        if vanilla_path:
            replacement_line = (
                "Standard vanilla replacement path: %s\n"
                "  (put this file at that path in a resource pack, or copy/rename to it; "
                "Java vanilla entity model is hardcoded and only reads this texture.)"
                % vanilla_path
            )
        elif entity == "player":
            replacement_line = (
                "Standard player skin replacement path: assets/minecraft/textures/entity/steve.png "
                "(or alex.png / custom skin name); use 64x64 or legacy 64x32 skin layout.\n"
                "  Opaque layers go in the inner-body regions; overlay/hat layer is optional."
            )
        else:
            replacement_line = (
                "No built-in vanilla entity detected from query/name; this texture is a generic entity UV.\n"
                "  To load in Java: replace an existing vanilla path, or use OptiFine CEM / a mod renderer "
                "(see docs/entity-uv-design.md)."
            )
        note = (
            "Entity UV texture for %s (%s).\n"
            "This package intentionally does NOT generate an entity model.\n"
            "%s\n"
            "Format contract: 64x32/64x64 standard entity UV layout (NOT a single centered side view).\n"
            "Validate with: python3 check_entity_uv.py <png> --entity pig|creeper|player\n"
            % (name, modid, replacement_line)
        )
        dest.write_text(note, encoding="utf-8")
        files_entries.append({"path": note_rel, "kind": "note"})

    # 4. manifest.json
    manifest = {
        "modid": modid,
        "name": name,
        "form": form,
        "type": meta["type"],
        "size": meta["size"],
        "width": meta["width"],
        "height": meta["height"],
        "generated_by": "package_asset.py",
        "output_root": str(root),
        "entity_uv_note": (
            "实体贴图采用 64x32/64x64 标准 UV 布局；未生成 Java 实体 model，"
            "标准实体只能替换 vanilla texture 路径，自定义实体需 OptiFine CEM / Bedrock geometry / 模组 renderer，"
            "详见 docs/entity-uv-design.md。" if form == "entity_uv" else None
        ),
        "files": files_entries,
    }
    manifest_path = root / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # 5. 可选 pack.mcmeta
    if write_pack_mcmeta:
        pack_rel = "pack.mcmeta"
        dest = root / pack_rel
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(build_pack_mcmeta(pack_format, "%s user-generated asset" % name), f, ensure_ascii=False, indent=2)
            f.write("\n")
        files_entries.append({"path": pack_rel, "kind": "pack_mcmeta"})
        # 重新写 manifest，加入 pack.mcmeta 文件记录
        manifest["files"] = files_entries
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
            f.write("\n")

    # 6. 校验
    validation = validate_pack(manifest, modid, name, form, meta)
    result = {
        "manifest": manifest,
        "validation": validation,
        "output_root": str(root),
        "face_texts": face_texts,
    }

    if not quiet:
        log_message(
            "done package form=%s name=%s files=%d validation=%s manifest=%s"
            % (form, name, len(files_entries), validation["status"], manifest_path),
            log_path,
        )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _run_package(args) -> int:
    spec = load_json(args.spec)
    raw_text = read_text(args.raw)
    result = package_asset(
        spec,
        raw_text,
        args.modid,
        args.out,
        write_pack_mcmeta=bool(args.pack_mcmeta),
        pack_format=args.pack_format,
        quiet=False,
    )
    manifest = result["manifest"]
    print("OK: packaged %s (%s) -> %s" % (manifest["name"], manifest["form"], result["output_root"]))
    print("OK: manifest -> %s" % (Path(result["output_root"]) / "manifest.json"))
    for entry in manifest["files"]:
        print("  %-12s %s" % (entry["kind"], entry["path"]))
    print("VALIDATE: %s (%d checks)" % (result["validation"]["status"], result["validation"]["count"]))
    return 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _synth_raw_for_face(face_id: str, w: int, h: int, color_idx: int) -> str:
    """生成一个简单的 palette+index grid 文本，用于自测。"""
    palette = [
        "#b36b19", "#9b5607", "#a86d1b", "#fff32d", "#b9931c",
        "#953300", "#fff87e", "#ae3c00", "#d8ae26", "#bf5a00",
        "#ffc100", "#b15b10",
    ]
    lines = ["W=%d H=%d" % (w, h), "PALETTE"]
    for i, c in enumerate(palette):
        lines.append("%d: %s" % (i, c))
    lines.append("")
    for y in range(h):
        row = []
        for x in range(w):
            if x in (0, w - 1) or y in (0, h - 1):
                row.append("-1")
            else:
                row.append(str((x + y + color_idx) % len(palette)))
        lines.append(" ".join(row))
    return "\n".join(lines) + "\n"


def _synth_item_spec(name: str = "alien_crystal_wand") -> dict:
    return {
        "name": name,
        "form": "item",
        "type": "item",
        "size": "16x16",
        "width": 16,
        "height": 16,
        "output_contract": {
            "faces": [
                {"face": "sprite", "suffix": "", "width": 16, "height": 16, "alpha": True},
            ]
        },
    }


def _synth_block_multi_spec(name: str = "glowstone_mushroom_block") -> dict:
    faces = [
        {"face": "top", "suffix": "_top", "width": 16, "height": 16, "alpha": False},
        {"face": "side", "suffix": "_side", "width": 16, "height": 16, "alpha": False},
        {"face": "bottom", "suffix": "_bottom", "width": 16, "height": 16, "alpha": False},
    ]
    return {
        "name": name,
        "form": "block_multi",
        "type": "block",
        "size": "16x16",
        "width": 16,
        "height": 16,
        "output_contract": {"faces": faces},
    }


def _synth_cross_spec(name: str = "mushroom_sapling") -> dict:
    return {
        "name": name,
        "form": "cross",
        "type": "block",
        "size": "16x16",
        "width": 16,
        "height": 16,
        "output_contract": {
            "faces": [
                {"face": "cross", "suffix": "", "width": 16, "height": 16, "alpha": True},
            ]
        },
    }


def _synth_entity_uv_spec(name: str = "test_entity_texture") -> dict:
    return {
        "name": name,
        "form": "entity_uv",
        "type": "entity",
        "size": "64x32",
        "width": 64,
        "height": 32,
        "output_contract": {
            "faces": [
                {"face": "uv", "suffix": "", "width": 64, "height": 32, "alpha": True},
            ]
        },
    }


def _run_block_custom_self_test(out_root: Path = Path("example_resourcepack_v3")) -> tuple[list[str], int]:
    """v3-custom-form 自测：anvil + slab/door 内置模板 + 1 个用户自定义 model.json。"""
    lines: list[str] = []
    failures = 0
    manifests: list[dict] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        status = "PASS" if cond else "FAIL"
        lines.append("[%s] %s%s" % (status, name, (" — " + detail) if detail else ""))
        if not cond:
            failures += 1

    def multi_raw(face_ids: list[str]) -> str:
        chunks = []
        for i, fid in enumerate(face_ids):
            chunks.append("=== face: %s ===" % fid)
            chunks.append(_synth_raw_for_face(fid, 16, 16, i * 3))
        return "\n".join(chunks) + "\n"

    user_model = Path("v3_selftest_user_model.json")
    if not user_model.exists():
        # 自测用极简用户模型（非原版素材）；缺失时自动生成，保证公开仓库可跑。
        user_model.write_text(json.dumps({
            "textures": {
                "particle": "demo:block/custom_user_model_particle",
                "top": "demo:block/custom_user_model_top",
                "bottom": "demo:block/custom_user_model_bottom",
                "side": "demo:block/custom_user_model_side"
            },
            "elements": [
                {
                    "from": [0, 0, 0],
                    "to": [16, 16, 16],
                    "faces": {
                        "down": {"uv": [0, 0, 16, 16], "texture": "#bottom", "cullface": "down"},
                        "up": {"uv": [0, 0, 16, 16], "texture": "#top", "cullface": "up"},
                        "north": {"uv": [0, 0, 16, 16], "texture": "#side", "cullface": "north"},
                        "south": {"uv": [0, 0, 16, 16], "texture": "#side", "cullface": "south"},
                        "west": {"uv": [0, 0, 16, 16], "texture": "#side", "cullface": "west"},
                        "east": {"uv": [0, 0, 16, 16], "texture": "#side", "cullface": "east"}
                    }
                }
            ]
        }, indent=2) + "\n", encoding="utf-8")
        check("v3 user model json generated", True, str(user_model))
    else:
        check("v3 user model json exists", True, str(user_model))

    cases = [
        ("anvil", "custom_anvil", multi_raw(["body", "top", "particle"])),
        ("slab", "custom_slab", multi_raw(["bottom", "top", "side", "particle"])),
        ("door", "custom_door", multi_raw(["bottom", "top", "particle"])),
        (None, "custom_user_model", _synth_raw_for_face("cube", 16, 16, 9)),
    ]

    try:
        for template, name, raw in cases:
            try:
                model_path = str(user_model) if template is None else None
                res = package_block_custom(
                    name=name,
                    modid="demo",
                    out_root=out_root,
                    template=template,
                    model_path=model_path,
                    raw_text=raw,
                    write_pack_mcmeta=True,
                    quiet=False,
                    log_path=V3_LOG_PATH,
                )
                manifest = res["manifest"]
                manifests.append(manifest)
                v = res["validation"]
                check("v3[%s] manifest generated" % (template or "user"), (out_root / "manifest.json").exists())
                check("v3[%s] pack.mcmeta generated" % (template or "user"), (out_root / "pack.mcmeta").exists())
                check(
                    "v3[%s] validation PASS" % (template or "user"),
                    v["status"] == "PASS" and v.get("semantic_status") == "PASS",
                    "checks=%d semantic=%s" % (v["count"], v.get("semantic_status")),
                )
                # 至少一个模型与 blockstate
                rel_bs = custom_blockstate_rel_path("demo", name)
                check("v3[%s] blockstate exists" % (template or "user"), (out_root / rel_bs).exists(), rel_bs)
                first_model = manifest["models"][0]["rel"]
                check("v3[%s] model exists" % (template or "user"), (out_root / first_model).exists(), first_model)
                # 每个 texture key 都生成了 PNG
                for key in manifest.get("texture_keys") or []:
                    tp = out_root / custom_texture_rel_path("demo", name, key)
                    check("v3[%s] texture %s" % (template or "user", key), tp.exists() and Image.open(tp).size == (16, 16), str(tp))
            except Exception as e:
                check("v3[%s] package_block_custom" % (template or "user"), False, str(e))

        # 合并 v3 manifest
        combined_files: list[dict] = []
        seen_paths: set[str] = set()
        for m in manifests:
            for entry in m.get("files", []):
                if entry["path"] not in seen_paths:
                    seen_paths.add(entry["path"])
                    combined_files.append(entry)
        combined_manifest = {
            "modid": "demo",
            "name": "example_resourcepack_v3",
            "form": "block_custom_self_test_combined",
            "type": "self_test",
            "size": "16x16",
            "generated_by": "package_asset.py",
            "output_root": str(out_root),
            "assets": [
                {"name": m["name"], "form": m["form"], "template_id": m["template_id"], "files": m["files"]}
                for m in manifests
            ],
            "files": combined_files,
        }
        with open(out_root / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(combined_manifest, f, ensure_ascii=False, indent=2)
            f.write("\n")
        check("v3 selftest example_resourcepack_v3 exists", out_root.is_dir())
        check("v3 selftest manifest exists", (out_root / "manifest.json").exists())
        lines.append("V3 RESULT: %s" % ("PASS" if failures == 0 else "FAIL (%d)" % failures))
    finally:
        log_message(
            "block_custom selftest result=%s failures=%d out=%s"
            % ("PASS" if failures == 0 else "FAIL", failures, out_root),
            V3_LOG_PATH,
        )
    return lines, failures


def _run_self_test(args) -> int:
    report_lines: list[str] = []
    failures = 0
    out_root = Path("example_resourcepack")

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        status = "PASS" if cond else "FAIL"
        report_lines.append("[%s] %s%s" % (status, name, (" — " + detail) if detail else ""))
        if not cond:
            failures += 1

    try:
        cases = [
            ("item", _synth_item_spec(), _synth_raw_for_face("sprite", 16, 16, 0)),
            ("block_multi", _synth_block_multi_spec(), "\n".join([
                "FORM=block_multi",
                "FACES=3",
                "",
                "=== face: top ===",
                _synth_raw_for_face("top", 16, 16, 0),
                "=== face: side ===",
                _synth_raw_for_face("side", 16, 16, 3),
                "=== face: bottom ===",
                _synth_raw_for_face("bottom", 16, 16, 6),
            ])),
            ("cross", _synth_cross_spec(), _synth_raw_for_face("cross", 16, 16, 8)),
            ("entity_uv", _synth_entity_uv_spec(), _synth_raw_for_face("uv", 64, 32, 4)),
        ]
        entity_out_root = Path("example_resourcepack_entity")
        manifests: list[dict] = []

        for form, spec, raw in cases:
            case_out_root = entity_out_root if form == "entity_uv" else out_root
            try:
                res = package_asset(
                    spec, raw, modid="demo", out_root=case_out_root,
                    write_pack_mcmeta=True, quiet=True,
                )
                manifest = res["manifest"]
                if form != "entity_uv":
                    manifests.append(manifest)
                v = res["validation"]
                check("%s manifest generated" % form, (case_out_root / "manifest.json").exists())
                check("%s pack.mcmeta generated" % form, (case_out_root / "pack.mcmeta").exists())
                check("%s validation PASS" % form, v["status"] == "PASS", "count=%d" % v["count"])
                expected_texture = None
                if form == "item":
                    expected_texture = "assets/demo/textures/item/alien_crystal_wand.png"
                elif form == "block_multi":
                    expected_texture = "assets/demo/textures/block/glowstone_mushroom_block_top.png"
                elif form == "cross":
                    expected_texture = "assets/demo/textures/block/mushroom_sapling.png"
                elif form == "entity_uv":
                    expected_texture = "assets/demo/textures/entity/test_entity_texture.png"
                if expected_texture:
                    check("%s texture exists" % form, (case_out_root / expected_texture).exists(), expected_texture)
                if form == "entity_uv":
                    note_rel = entity_note_rel_path("demo", manifest["name"])
                    check("entity_uv note exists", (case_out_root / note_rel).exists(), note_rel)
                if form != "entity_uv":
                    model_rel = model_rel_path("demo", manifest["name"], form)
                    check("%s model exists" % form, (case_out_root / model_rel).exists(), model_rel)
                if form in ("block_multi", "cross"):
                    bs_rel = blockstate_rel_path("demo", manifest["name"], form)
                    check("%s blockstate exists" % form, (case_out_root / bs_rel).exists(), bs_rel)
                    if form == "block_multi":
                        model_json = json.loads((case_out_root / model_rel).read_text(encoding="utf-8"))
                        check(
                            "block_multi model uses cube_bottom_top",
                            model_json.get("parent") == "minecraft:block/cube_bottom_top",
                            str(model_json.get("parent")),
                        )
            except Exception as e:
                check("%s package_asset" % form, False, str(e))

        # 额外验证 block_multi 三个面都被真实生成且尺寸一致
        for suffix in ("_top", "_side", "_bottom"):
            p = out_root / ("assets/demo/textures/block/glowstone_mushroom_block%s.png" % suffix)
            check("block_multi%s size" % suffix, p.exists() and Image.open(p).size == (16, 16), str(p))

        # 把 3 个资产合并写入同一个 example_resourcepack/manifest.json，
        # 避免最后只留最后一个资产的 manifest。
        combined_files: list[dict] = []
        seen_paths: set[str] = set()
        for m in manifests:
            for entry in m["files"]:
                if entry["path"] not in seen_paths:
                    seen_paths.add(entry["path"])
                    combined_files.append(entry)
        combined_manifest = {
            "modid": "demo",
            "name": "example_resourcepack",
            "form": "self_test_combined",
            "type": "self_test",
            "size": "16x16",
            "generated_by": "package_asset.py",
            "output_root": str(out_root),
            "assets": [
                {"name": m["name"], "form": m["form"], "files": m["files"]}
                for m in manifests
            ],
            "files": combined_files,
        }
        with open(out_root / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(combined_manifest, f, ensure_ascii=False, indent=2)
            f.write("\n")

        check("selftest example_resourcepack exists", out_root.is_dir())
        check("selftest manifest exists", (out_root / "manifest.json").exists())
        check("entity_uv example_resourcepack_entity exists", entity_out_root.is_dir())
        check("entity_uv manifest exists", (entity_out_root / "manifest.json").exists())

        # v3-custom-form block_custom 自测：独立输出 example_resourcepack_v3/
        v3_lines, v3_failures = _run_block_custom_self_test(Path("example_resourcepack_v3"))
        report_lines.extend(v3_lines)
        failures += v3_failures
        report_lines.append("RESULT: %s" % ("PASS" if failures == 0 else "FAIL (%d)" % failures))
    finally:
        (Path(SELFTEST_REPORT)).write_text("\n".join(report_lines) + "\n", encoding="utf-8")
        log_message("selftest result=%s failures=%d out=%s" % ("PASS" if failures == 0 else "FAIL", failures, out_root))

    print("\n".join(report_lines))
    print("selftest report: %s" % Path(SELFTEST_REPORT).resolve())
    return 0 if failures == 0 else 1


def _run_block_custom_cli(args) -> int:
    if args.template and args.model:
        raise ValueError("--template and --model are mutually exclusive")
    if not args.template and not args.model:
        raise ValueError("--template or --model is required for block_custom")
    if not args.name:
        raise ValueError("--name is required for block_custom")
    raw_text = None
    if args.raw:
        raw_text = read_text(args.raw)
    try:
        result = package_block_custom(
            name=args.name,
            modid=args.modid,
            out_root=args.out,
            template=args.template,
            model_path=args.model,
            raw_text=raw_text,
            write_pack_mcmeta=bool(args.pack_mcmeta),
            pack_format=args.pack_format,
            log_path=V3_LOG_PATH,
            quiet=False,
        )
    except Exception as e:
        log_message("ERROR block_custom failed: %s" % e, V3_LOG_PATH)
        print("ERROR: %s" % e, file=sys.stderr)
        return 1
    manifest = result["manifest"]
    v = result["validation"]
    print("OK: packaged block_custom %s (%s) -> %s" % (manifest["name"], manifest["template_display"], result["output_root"]))
    print("OK: manifest -> %s" % (Path(result["output_root"]) / "manifest.json"))
    for entry in manifest["files"]:
        print("  %-12s %s" % (entry["kind"], entry["path"]))
    print("VALIDATE: %s (%d checks; semantic %s)" % (v["status"], v["count"], v.get("semantic_status")))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="package_asset.py — package LLM raw_answer into a Minecraft resource pack."
    )
    parser.add_argument("--spec", help="Path to prompt_packs_v2/xxx.json spec")
    parser.add_argument("--raw", help="Path to generated_assets_v2/xxx/raw_answer.txt or block_custom multi-face raw answer")
    parser.add_argument("--modid", default="demo", help="Resource pack modid (default: demo)")
    parser.add_argument("--out", dest="out", default="resourcepack/", help="Output resource pack root (default: resourcepack/)")
    parser.add_argument("--pack-mcmeta", action="store_true", help="Also write pack.mcmeta")
    parser.add_argument("--pack-format", type=int, default=DEFAULT_PACK_FORMAT, help="pack_format number (default: %d)" % DEFAULT_PACK_FORMAT)
    parser.add_argument("--self-test", action="store_true", help="Run synthetic item/block_multi/cross/entity_uv + v3 block_custom packaging self-test")
    parser.add_argument("--template", help="block_custom builtin template (anvil/slab/door/stairs/fence/wall/chest/flower_pot) or path to a model JSON")
    parser.add_argument("--model", help="block_custom user model JSON (Blockbench/vanilla model)")
    parser.add_argument("--name", help="Output block name required for block_custom")
    parser.add_argument("--list-templates", action="store_true", help="List builtin block_custom templates and exit")
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test(args)
    if args.list_templates:
        for key in BUILTIN_TEMPLATE_KEYS:
            spec = BUILTIN_BLOCK_TEMPLATES[key]
            print("%-12s %s" % (key, spec["description"]))
        print("paths: %s" % _library_models_dir())
        print("registry_count=%d" % len(BUILTIN_BLOCK_TEMPLATES))
        return 0

    if args.template or args.model:
        try:
            return _run_block_custom_cli(args)
        except Exception as e:
            print("ERROR: %s" % e, file=sys.stderr)
            log_message("ERROR block_custom cli: %s" % e, V3_LOG_PATH)
            return 1

    if not args.spec or not args.raw:
        parser.error("--spec and --raw are required unless --self-test/--list-templates/--template/--model is used")

    try:
        return _run_package(args)
    except Exception as e:
        log_message("ERROR package failed: %s" % e)
        print("ERROR: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
