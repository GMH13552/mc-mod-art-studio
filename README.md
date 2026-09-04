# mc-mod-art-studio-core

一个面向 **非多模态纯文本 LLM** 的最小 Minecraft 自定义资源生成仓库。

仓库只包含核心脚本与两个最小示例（`examples/alien_crystal_wand/`、`examples/mushroom_sprout/`），
不包含任何原版 PNG、大型资产库、旧评审/日志目录或 resourcepack 输出目录。

## 核心流程

```
scan_mc_assets.py -> retrieve_assets.py -> concept_grounder.py
          -> build_style_prompt.py -> (纯文本 LLM) -> text_to_texture.py
          -> compose_asset.py -> package_asset.py
```

1. **扫描**：`scan_mc_assets.py` 扫描本地 Minecraft/资源包路径，生成资产索引。
2. **检索**：`retrieve_assets.py` 根据一句想法检索 1~8 个参考节点，提取形状/图案/颜色/部位/吸引点。
3. **概念卡**：`concept_grounder.py` 先生成语义概念卡：先理解“这个东西是什么”，再给出
   `palette_scheme`（配色方案）、`shape_pattern`（形状图样）、`reference_nodes`（3~8 个参考节点）。
4. **提示包**：`build_style_prompt.py` 把概念卡、检索特征、风格规则、输出契约合成为适合纯文本 LLM 的提示文本。
5. **LLM 生成**：让纯文本 LLM 按 `W/H + PALETTE + INDEX GRID` 输出像素答案；不要求多模态模型。
6. **转纹理**：`text_to_texture.py` 把 raw answer 转为 PNG；`compose_asset.py` 可做形状/配色组合；
   `package_asset.py` 打包成 Minecraft 资源包结构。
7. **审计/校验**：`audit_generation.py` 与 `validate_raw_answers_v3.py` 对生成结果做哈希/格式校验。

## 设计流程（先理解 → 配色 → 形状）

- **参考素材是“参考节点”，不是硬性指标**：模型先理解“在做什么”，再设计配色和形状图样。
- 每个概念卡包含：
  - `palette_scheme`：`base`、`light`、`dark`、`accent`、`outline`、`border_note`、`saturation_note`。
  - `shape_pattern`：`silhouette`、`parts`、`border`、`shading`、`detail_pattern`、`shape_lock_optional`、`part_pattern_flow`、`integration_note`。
  - `reference_nodes`：3~8 条，每条含 `asset`、`role`（shape/color/pattern/border/material）、`reason`。
- 提示中明确要求：**不要复制参考贴图；优先保证“这个东西是什么”的语义可辨认；允许 3~8 个参考节点**。
- 形状-纹样一体：每个部件都要描述“形状 → 纹样沿该形状结构走”，例如水晶尖柱的棱面/高光带沿柱体轴向、蘑菇菌盖放射菌褶沿伞面弧线、法杖纹样沿杖身纵向流动；**纹样不得脱离形状独立存在**。
- 示例 `examples/alien_crystal_wand/` 演示了“顶部明显水晶簇 + 低饱和青绿配色 + 暗部/1px 描边”，
  而不是照抄 blaze_rod 形状。

## 使用示例

### 一键流水线（推荐）

```bash
# 只生成 prompt 文本
python3 run_pipeline.py --query "异形水晶法杖" --form item --prompt-only

# 用现成 LLM raw_answer 生成 PNG
python3 run_pipeline.py --query "异形水晶法杖" --form item \
    --raw examples/alien_crystal_wand/raw_answer.txt \
    --out examples/alien_crystal_wand

# 调用外部 LLM 命令（支持 {prompt} / {prompt_file} 替换）
python3 run_pipeline.py --query "异形水晶法杖" --form item --top 5 \
    --llm-cmd 'python3 my_llm.py --prompt-file {prompt_file}' \
    --out out/alien_crystal_wand

# 同时打包成资源包
python3 run_pipeline.py --query "异形水晶法杖" --form item \
    --raw examples/alien_crystal_wand/raw_answer.txt \
    --out examples/alien_crystal_wand --package
```

### 分步使用

```bash
# 1. 扫描资产索引（可选；没有索引时 run_pipeline/retrieve 会使用合成自检索引）
python3 scan_mc_assets.py --mc-path ~/.minecraft --out my_asset_index.json --with-palette

# 2. 检索参考节点（支持 --top 1..8）
python3 retrieve_assets.py --query "异形水晶法杖" --top 5 --index my_asset_index.json --out retrieval_examples/alien_crystal_wand.json

# 3. 生成概念卡
python3 concept_grounder.py --query "异形水晶法杖" --retrieval retrieval_examples/alien_crystal_wand.json --form item --out concept_examples/alien_crystal_wand.json

# 4. 生成提示包
python3 build_style_prompt.py --query "异形水晶法杖" --form item --out examples/alien_crystal_wand/prompt_pack.json

# 5. 让纯文本 LLM 按输出契约生成 raw_answer.txt，然后：
python3 text_to_texture.py examples/alien_crystal_wand/raw_answer.txt --output examples/alien_crystal_wand/sprite.png

# 6. 打包
python3 package_asset.py --spec examples/alien_crystal_wand/prompt_pack.json --raw examples/alien_crystal_wand/raw_answer.txt --out resourcepack_demo/
```

## 自检

```bash
python3 scan_mc_assets.py --self-test
python3 retrieve_assets.py --self-test
python3 concept_grounder.py --self-test
python3 build_style_prompt.py --self-test
python3 compose_asset.py --self-test
python3 package_asset.py --self-test
```

所有自检均不依赖原版素材：缺失素材库时自动使用代码生成的迷你合成资源包。

## 仓库包含

- 核心脚本：`scan_mc_assets.py`、`retrieve_assets.py`、`concept_grounder.py`、`build_style_prompt.py`、
  `compose_asset.py`、`package_asset.py`、`asset_to_text.py`、`text_to_texture.py`、
  `audit_generation.py`、`validate_raw_answers_v3.py`、`run_pipeline.py`。
- `minecraft_texture_tool/texture_to_text.py`（唯一保留的纹理转换工具文件）。
- `builtin_models_fallback/`：极简模板 JSON（无原版贴图）。
- `examples/`：`alien_crystal_wand` 与 `mushroom_sprout` 两个最小示例。

## 安全说明

仓库不包含原版 Minecraft 素材或任何密钥。`.gitignore` 忽略自检/生成产物与日志。
生成示例均为自产/合成内容。
