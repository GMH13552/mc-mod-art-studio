# 参考影响验证：默认 vs `--no-original-ref`（“剥皮小刀”）

## 实验设置

统一使用同一 novel prompt 和同一检索索引：

```bash
# 默认（带原版参考块）
python3 run_pipeline.py \
  --query "剥皮小刀" --form item \
  --index /mnt/c/Users/GMH13/Documents/deepseek_harness_workspace/mc_asset_library/library-index.json \
  --novelty 0.5 --prompt-only --out /tmp/n1_with_ref

# 关闭原版参考块
python3 run_pipeline.py \
  --query "剥皮小刀" --form item \
  --index /mnt/c/Users/GMH13/Documents/deepseek_harness_workspace/mc_asset_library/library-index.json \
  --novelty 0.5 --no-original-ref --prompt-only --out /tmp/n1_no_ref
```

两版随后都使用同一 `--llm-cmd` 跑完整生成，得到 `sprite.png`：
`python3 llm_client.py --prompt-file {prompt_file}`（key 仅从 `/tmp/mc_llm.env` 环境变量读取，未写入仓库/文档）。

## Prompt 差异

| 项 | 默认 `n1_with_ref` | `--no-original-ref` `n1_no_ref` |
| --- | --- | --- |
| prompt 字符数 | 8651 | 3848 |
| prompt 行数 | 273 | 85 |
| 原版参考块 | 存在 | **整个块被移除** |
| 参考语法 | 3 个锚点各一段：iron_sword / stone_sword / wooden_sword | 无 |
| compact 片段 | 附 2 个最相关片段（iron_sword、stone_sword） | 无 |
| `reference_block_meta` | `include_compact=True, compact_limit=2` | `include_compact=False, compact_limit=0` |
| diff | 基线 | 删除约 193 行（约 4803 字符）的“## 原版参考（结构化语法 + 少量片段）”整段 |

两版 prompt 中仍有共同部分：概念卡（`reference_nodes` 只列路径与 role）、通用设计原则、通用像素细节、PALETTE+INDEX GRID 输出契约。因此 `--no-original-ref` 并没有删除所有“参考”痕迹，只关闭了**原版 compact 引用块**。

## 输出差异

### 1. 设计分析/方位

- `n1_with_ref` 的 `raw_answer.txt` 写：
  “主方向：剑沿左上到右下对角线方向延伸，剑尖指向右下角，整体呈45°斜向构图。”
- `n1_no_ref` 的 `raw_answer.txt` 写：
  “主方向：剑沿垂直轴线从下到上依次为柄→护手→剑刃，剑尖朝上；整体呈细长对称结构，宽约4-5px，高约14px。”

这直接对应视觉差异：带参考的版本呈现 Minecraft 原版 iron_sword 式斜向剑；关参考的版本变成更居中的立式短剑/匕首状物体。

### 2. 像素/检查器指标

| 指标 | `n1_with_ref/sprite.png` | `n1_no_ref/sprite.png` |
| --- | --- | --- |
| 不透明像素 | 84 | 46 |
| bbox | `[0,0,16,16]`，margin 0 | `[5,2,11,15]`，margin `5/2/5/1` |
| opaque_ratio | 0.3281 | 0.5897 |
| 检查器结论 | **FAIL**（bbox 无透明边距） | **PASS** |
| 暗色/中间/亮色桶 | dark=49, mid=17, bright=18 | dark=37, mid=2, bright=7 |
| 主色 | `#444444`（占比 0.31） | `#444444`（占比 0.57） |

带参考的版本虽然更贴近原版剑的样式，但因为直接继承了 iron_sword 的“贴边/满画布”构图，没有满足 item 需要的至少 1px 透明边距；关参考的版本保留了边距，但亮部/中间调明显更少，视觉上更“块状”和扁平。

### 3. 调色板证据

- `n1_with_ref` palette（7 色）：
  `#444444 #D8D8D8 #181818 #BEBEBE #FFFFFF #6B6B6B #896727`
  - 与 `iron_sword.png` 调色板重合 7/7，保留了棕色点缀 `#896727`。
- `n1_no_ref` palette（7 色）：
  `#444444 #181818 #D8D8D8 #FFFFFF #BEBEBE #2E2E2E #7A7A7A`
  - 与 `iron_sword.png` 调色板重合 5/7，缺少 `#896727`，新增 `#2E2E2E` / `#7A7A7A`。

两版仍共享 `#444444/#FFFFFF/#D8D8D8/#BEBEBE/#181818`，说明概念卡的调色板（base/light/dark/accent/outline）本身已从 iron_sword 检索结果中提取；`--no-original-ref` 去掉的是 compact 纹理细节，不是概念卡中的基础配色方向。

### 4. 网格接近度（是否复制原版）

以原版 compact 的 Index grid 为参考逐格比对：

| 生成结果 vs 参考 | 精确索引一致率 |
| --- | --- |
| `n1_with_ref` vs `iron_sword.png` | **91.8%** |
| `n1_no_ref` vs `iron_sword.png` | 61.3% |
| `n1_with_ref` vs `n1_no_ref` | 61.3% |

带参考的生成结果几乎复刻了 iron_sword 的 index grid（84 个不透明像素，与 iron_sword 完全相同），这解释了为什么它看起来很像原版剑、同时也不可避免地带上了原版“零边距/贴边”特征。关参考后复制率显著下降，但形状/配色仍受概念卡中的 iron_sword 基础调色板影响。

## 证据文件

- 默认版：`/tmp/n1_with_ref/prompt.txt`、`/tmp/n1_with_ref/raw_answer.txt`、`/tmp/n1_with_ref/sprite.png`、`/tmp/n1_with_ref/check_pixel_asset.json`
- 关参考版：`/tmp/n1_no_ref/prompt.txt`、`/tmp/n1_no_ref/raw_answer.txt`、`/tmp/n1_no_ref/sprite.png`、`/tmp/n1_no_ref/check_pixel_asset.json`
- 哈希：
  - `n1_with_ref`：prompt.sha256 `98129c8a8a3d87e2ccaf4f100ffdaa2d45cf13ad04a5df67794539dcf62d537d`，raw.sha256 `c7d188bd77dad463badee7bf9408ec9d36ccbbe65eb1facd25c0c6b0a967a244`
  - `n1_no_ref`：prompt.sha256 `7e6950b448467d2b06562e0c49f0f05f5b071a7e7331f1f2cb881f6eede7590a`，raw.sha256 `0c6b9350362d08db49c85afb34f23272e00ac84f16615e7b127283317cc1977f`

## 结论

- 默认参考块对模型有**强引导作用**：不只是提供“语法”，在本次测试里几乎把最相关原版 compact 的 index grid 复制出来（91.8% 精确索引一致）。
- `--no-original-ref` 会显著缩小 prompt（减少约 4803 字符）、移除全部原版 compact 片段，生成结果更“自创”也更符合边距检查，但同时失去原版的金属质感/高光层次和斜向构图，视觉上更像一个通用像素剑/短剑，而不是 Minecraft 原版风格的剥皮小刀。
- 仅靠当前 `--no-original-ref` 并不能彻底消除原版影响：概念卡仍从检索结果提炼了基础调色板；若想真正“无原版影响”，需要同时弱化/移除概念卡中的原版派生配色。
