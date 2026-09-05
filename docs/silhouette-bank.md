# Silhouette Bank：轮廓基础候选

## 一句话

把“形状借鉴”从一句结构小作文升级为**可挑选、可组合、可大改的轮廓候选菜单**：
每个部件给 2–4 个原版轮廓基础（`shape token` 或只含 `X/.` 的剪影片段），
同时明确“候选不是最终答案”。

## 为什么需要

| 旧问题 | 表现 | silhouette bank 的解法 |
|---|---|---|
| 形状过缩 | 只写“短柄/细杖/方形皮”，模型自由发挥，失去原版骨架感 | 给出 2–4 个有来源的轮廓基础，模型有方向可挑 |
| 形状过抄 | 直接带完整 compact / 整件索引网格，模型把原版复制出来 | 候选只含剪影或 shape token，不是完整 Index grid |
| 部件不像 | 头/柄/刀/皮各自没有“原版那味” | 按部件/区域切候选，例如 `skeleton-head`、`curved-blade`、`rabbit-hide-body` |
| form 选错 | 恶魔牛被做成 16x16 牛头图标 | `entity_uv` 按 cow/red_mooshroom 的 64x32 atlas 区域出候选 |

## Prompt 中的规则

`build_style_prompt.py` / `run_pipeline.py` 会在 `### 部件轮廓候选 silhouette_candidates` 段固定写入：

```text
> 形状候选 = 菜单，不是锁。
> - 可选其中一个；
> - 可组合多个；
> - 可大改形状（加长/加粗/弯曲/变形/换比例都允许）；
> - 禁止把候选当成最终网格/逐像素复制候选剪影。
```

每个候选形如：

```text
- 候选 1：iron-sword-blade（来源：iron_sword.png）；来源：iron_sword.png 刃部轮廓
- 候选 2：stone-sword-blade（来源：stone_sword.png）；来源：stone_sword.png 刃部轮廓
- 候选 3：compact:iron_sword.png（来源：iron_sword.png）；只含 X/. 剪影；iron_sword.png 区域/整体轮廓
  (compact 剪影片段)
    .............XXX
    ............XXXX
    ...
```

## 实现位置

| 模块 | 职责 |
|---|---|
| `reference_analyzer.py` | `build_silhouette_bank(parts, retrieval_anchors, ...)`：每个部件生成 2–4 个候选；`analyze_compact()` 返回 `silhouette_candidates`；`render_silhouette_candidates()` 渲染菜单 |
| `build_style_prompt.py` | `build_prompt_pack_v2` 自动计算 `silhouette_bank` 并写入 `concept_card.shape_pattern.silhouette_candidates` 与 pack |
| `run_pipeline.py` | 最终紧凑 prompt 也渲染 `silhouette_candidates`；`--llm-image` 支持多张参考 PNG |
| `entity_uv_spec.py` | 新增 cow / red_mooshroom 64x32 atlas 区域坐标 |
| `check_entity_uv.py` | `--entity` 支持 cow / red_mooshroom 自检 |

## 多图参考（视觉 LLM）

除了文本 LLM 看 `X/.` 剪影，视觉 LLM 可直接看原版 PNG：

```bash
# llm_client：--image 可多次，也可逗号分隔
python3 llm_client.py --prompt-file prompt.txt \
  --image cow.png --image red_mooshroom.png

# run_pipeline：--llm-image 可多次，也可逗号分隔
python3 run_pipeline.py --query '恶魔牛' --form entity_uv \
  --index /path/to/library-index.json --top 4 \
  --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' \
  --llm-image cow.png --llm-image red_mooshroom.png \
  --out out/demon_cow
```

多张图会在 OpenAI 兼容请求中全部进入 `user.content` 的 `image_url` 列表。

## Cow 实体模板

`demon_cow` 使用 `form=entity_uv`、`64x32`，按原版 cow/red_mooshroom 实体 UV 图集生成，
不是 16x16 居中图标。`entity_uv_spec.py` 记录标准区域：

| 区域 | 坐标（约） |
|---|---|
| head | 0,0 → 32,16 |
| horns | 0,0 → 32,6 |
| ears | 0,0 → 32,4 |
| muzzle | 0,8 → 16,16 |
| body | 16,16 → 64,32 |
| legs | 0,16 → 16,32 |
| tail | 48,16 → 64,32 |

自检：

```bash
python3 check_entity_uv.py examples/demon_cow/sprite.png --entity cow
python3 check_entity_uv.py --self-test
```
