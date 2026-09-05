# 第一版做法复盘：为什么“原版 compact 全量参考 + 风格卡 + 融合”效果好

## 证据来源

- 旧版 prompt 渲染器：`/mnt/c/Users/GMH13/Documents/deepseek_harness_workspace/render_prompt_pack.py`
- 旧版 prompt pack：`/mnt/c/Users/GMH13/Documents/deepseek_harness_workspace/prompt_packs/mushroom_axe.json`
- 旧版实际 LLM prompt：`/mnt/c/Users/GMH13/Documents/deepseek_harness_workspace/generated_assets/mushroom_axe/prompt.txt`
- 旧版生成结果：`/mnt/c/Users/GMH13/Documents/deepseek_harness_workspace/generated_assets/mushroom_axe/mushroom_axe.png`
- 旧版风格卡：`/mnt/c/Users/GMH13/Documents/deepseek_harness_workspace/style_cards/items.md`、`blocks.md`
- 旧版 `build_style_prompt.py`：`build_prompt_pack()`（v1 手动主/副锚点 + `_few_shot_for_type()` + `_extract_style_rules()`）

## 第一版实际做法

旧版 `prompt.txt` 不是“检索特征摘要 + 少量参考片段”，而是把一套**完整的手动锚点混合**直接写进 LLM 提示：

1. **明确融合规则**
   - `fusion: palette overlay on shape`
   - 任务要求：“以 primary 锚点为形状/主体基础，从 secondary 锚点提取配色或材质细节，融合为新的原版风格贴图。”
   - 这把“哪个参考管形状、哪个参考管颜色/材质”讲得很清楚，模型不需要自己去猜融合权重。

2. **全量 compact 文本**
   - 主锚点：`stone_axe.png` 的完整 `asset_to_text --mode compact --no-header` 文本（Silhouette + ASCII color map + Palette hex + Index grid）。
   - 副锚点：`red_mushroom_block.png` 的完整 compact 文本。
   - 不是只给调色板统计，而是把像素级几何、明暗分布、索引网格都放进 prompt。

3. **风格卡注入**
   - “风格规则”段落直接来自 `style_cards/items.md` / `blocks.md`：
     - 调色板数量/透明度范围；
     - 左上偏亮、右下偏暗的明暗趋势；
     - 1px 深色描边/部件接缝；
     - 少量 1px 噪点、避免大面积平涂/渐变。
   - 这些是跨物品的统计规则，和具体锚点互补。

4. **同类 few-shot**
   - 再附一份同类物品（`stone_pickaxe.png`）完整 compact，用于确认格式与质感节奏。

5. **输出契约作为“骨架”**
   - `output_contract` 来自 primary 锚点的 palette/index grid，告诉模型“输出格式必须长这样，内容替换成融合后的”。

## 为什么第一版“除了方位感其实不算差”

旧版 `mushroom_axe` 的直接证据：

| 指标 | 值 |
| --- | --- |
| 不透明像素 | 60 |
| bbox | `[2,1,14,15]`，四边 margin `2/1/2/1`，合格 |
| 描边暗色边界占比 | `1.0000` |
| 调色板分桶 | dark=46, mid=8, bright=6 |
| 整体检查 | **PASS** |

它能通过检查，且视觉上保持了“石斧形状 + 红蘑菇配色”的杂交语义，原因主要是：

- **完整 compact 给出足够强的原版语法**：模型能看到真实原版的 1px 色阶、描边、材质噪点和形状比例，而不是只能靠几句抽象总结去猜。
- **显式融合规则避免“多参考打架”**：primary 管形状、secondary 管调色，模型不会把所有参考平均成四不像。
- **风格卡提供统计性约束**：即使锚点本身没有覆盖某个规则，风格卡也会提醒明暗、描边、噪点等原版共性。
- **few-shot + 输出契约把格式风险压到最低**：模型知道要输出可被 `text_to_texture.py` 解析的文本块。

旧版的主要短板是“方位感”等语义/设计细节，这是概念卡和通用设计原则后来要补的，而不是把完整参考删除。

## 与当前版本的差异

当前 `run_pipeline.py` 的最终 prompt 由 `_build_compact_prompt()` 生成，实际发生了三处关键变化：

| 维度 | 第一版 | 当前默认 |
| --- | --- | --- |
| 参考呈现 | 主/副锚点全量 compact 文本原样注入 | `reference_analyzer` 把 compact 提炼为“结构化语法 + 最多 2 个 compact 片段” |
| 融合指令 | 明确“primary 管形状、secondary 管配色/材质” | 概念卡说“参考节点仅语义参考，禁止复制像素”，没有给每个参考节点分配明确融合角色 |
| 风格卡 | **进入最终 LLM prompt** | `pack["style_rules"]` 仍存在，但 `_build_compact_prompt()` **没有读取/注入**；实际 prompt 中看不到 `# 风格规则` |
| 检索特征摘要 | 旧版无此段；由锚点 compact 承担 | `pack["features"]["summary"]` 存在，但 `_build_compact_prompt()` 没有注入 |
| few-shot | 同类完整 compact 片段 | output_contract 中仍有格式样本，但不再用风格卡 snippets 做 few-shot |
| 通用原则 | 无 | 加入 `GENERIC_DESIGN_PRINCIPLES` / `GENERIC_PIXEL_DETAIL_RULES` |

需要特别指出：`build_style_prompt._build_v2_prompt_text()` 仍然会输出“风格规则”和“检索特征摘要”，但 `run_pipeline._build_compact_prompt()` 会在 pack 生成后**覆盖** `pack["prompt"]`，而 compact prompt 只使用 `concept_card`、`reference_block`、通用规则和输出契约。所以**当前一命令管线的真实 prompt 丢掉了风格卡和特征摘要**。

## 结论

第一版的效果不是“因为把整段 compact 塞给模型所以好”，而是“因为**每个参考都有明确角色 + 完整像素证据 + 风格统计规则 + 格式骨架**”。当前版本把参考层改为“结构化语法 + 少量片段”本身是合理方向，但实际一命令管线又同时移除了风格卡和检索特征摘要，也没有恢复显式融合角色；因此参考信息变少、融合指令变弱，容易退化成“照着某一个最相关锚点抄”或“只靠概念卡硬画”。
