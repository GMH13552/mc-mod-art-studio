# Tiling Design: block_multi 可拼贴方块

- **Task**: e1-tiling
- **Date (UTC)**: 2026-09-05
- **Reuses**: `docs/method-survey.md` §1（`cube_bottom_top` 契约 / `block_multi` gap）

---

## 1. 结论摘要

`block_multi` 的资源包三层现在自洽：

- blockstate：仍为 `assets/<modid>/blockstates/<name>.json`，`variants` 指向本包模型。
- model：`assets/<modid>/models/block/<name>.json` 改用 `minecraft:block/cube_bottom_top`。
  - `textures.particle = #side`
  - `textures.down/up/north/south/west/east` 由父模型从 `#bottom/#top/#side` 映射。
  - 四个侧面共用 `#side`，因此 side 左右边需要无缝 wrap。
- textures：沿用 `_top.png / _side.png / _bottom.png` 三张 16x16 贴图。

## 2. 模型/打包修正

| 文件 | 改动 |
|---|---|
| `package_asset.py` | `build_model_json("block_multi")` 的 `parent` 从 `minecraft:block/cube` 改为 `minecraft:block/cube_bottom_top`；`block_custom` 的 `extra_full_model` 同步修正 |
| `build_style_prompt.py` | `block_multi` 的 `file_contract.templates` 与 `format` 同步改为 `block/cube_bottom_top` |

`blockstate` 不需要结构性改动：生成的 `variants: {"": {"model": "<modid>:block/<name>"}}` 已符合原版规则。

## 3. check_tiling.py 设计

### 3.1 输入

```
--top top.png --side side.png --bottom bottom.png [--name name] [--threshold 32] [--allow-transparent] [--side-order north,east,south,west]
```

要求三张 PNG 同尺寸（默认 16x16）。`--side-order` 记录四个侧面绕方块一圈的顺序；
当前 `block_multi` 只有一张复用的 `side`，因此该参数不影响左右 wrap 的计算，只作为契约/审计信息保留。

### 3.2 检查项

| 检查 | 公式 | 通过条件 |
|---|---|---|
| `side_wrap` | `side(0,y)` vs `side(w-1,y)`（每行） | `max_channel_diff <= threshold` 且（默认）两边都不透明 |
| `top_side` | `side(x,0)` vs `top` 的四条边 | 四条边中每条边至少有一个允许方向（正向/反向）通过阈值+不透明 |
| `bottom_side` | `side(x,h-1)` vs `bottom` 的四条边 | 同上 |

阈值为 RGB 最大通道差，默认 `32`。默认开启 `--require-opaque`：只要边缘像素 `alpha < 128` 就判 FAIL，因为 `block_multi` 的 alpha 契约是 `False`（方块贴图边缘必须完全不透明）。

### 3.3 输出

- 人类可读：命令行直接打印 PASS/FAIL 与失败项。
- JSON：`--out-json` / `--out-dir/<name>_tiling.json`
- Markdown：`--out-md` / `--out-dir/<name>_tiling.md`

`--self-test` 会用合成贴图验证 PASS / 颜色突变 FAIL / 透明边缘 FAIL 三种情况。

## 4. v2 基线结果（strict）

在 `tests/runs/v2/{bricks,glowstone,lapis_block}/resourcepack/assets/demo/textures/block/` 上运行。

| 资产 | 状态 | 颜色差 | 失败原因 |
|---|---|---|---|
| bricks | FAIL | max_diff=0 | 边缘 16/16 像素透明（side 左右边、side 顶/底边全部透明） |
| glowstone | FAIL | max_diff=0 | 同上 |
| lapis_block | FAIL | max_diff=0 | 同上 |

补充：使用 `--allow-transparent` 只看 RGB 时三者均为 PASS，但这是因为比较的两侧边缘同为透明像素（diff=0），不代表可用的方块贴图。该“仅颜色”结果也单独存为
`evidence/tiling-baseline-color/` 以备对照。

证据输出（严格/可用）：

```
evidence/tiling-baseline/bricks_tiling.json
evidence/tiling-baseline/bricks_tiling.md
evidence/tiling-baseline/glowstone_tiling.json
evidence/tiling-baseline/glowstone_tiling.md
evidence/tiling-baseline/lapis_block_tiling.json
evidence/tiling-baseline/lapis_block_tiling.md
```

证据输出（仅颜色对照）：

```
evidence/tiling-baseline-color/bricks_tiling.json
evidence/tiling-baseline-color/bricks_tiling.md
evidence/tiling-baseline-color/glowstone_tiling.json
evidence/tiling-baseline-color/glowstone_tiling.md
evidence/tiling-baseline-color/lapis_block_tiling.json
evidence/tiling-baseline-color/lapis_block_tiling.md
```

## 5. 修复建议（供后续 LLM / 后处理使用）

1. `block_multi` 三张面必须都是 **16x16 全不透明方块面**，不应沿用物品/剪影的透明棋盘格。
2. `side` 左右两列必须一致：这是四个侧面绕一圈能无缝平铺的前提。
3. `side` 顶行与 `top` 四边、`side` 底行与 `bottom` 四边应颜色连续；若四个侧面共用同侧贴图，则 `top`/`bottom` 的四周应有一致的边缘色带。
4. 若要方向性图案（如“正面有门、其余侧面不同），应使用每面独立 PNG + 显式 `elements/faces/uv` 模型，而不是复用一张 `side`。
5. 后处理可用 1px 描边/接缝统一：先抽出跨面边缘，再让相邻面共享该边缘像素；或对 side 做左右镜像接缝重绘。

## 6. 自测

- `python3 check_tiling.py --help`：可用
- `python3 check_tiling.py --self-test`：PASS
- `python3 package_asset.py --self-test`：PASS（核心自测未破坏）
