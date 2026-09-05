# Prompt Design：通用像素细节规则

## 1. 目的

`mc-mod-art-studio` 的提示词不仅要告诉模型“画什么”，还要约束“怎么画得像 Minecraft 像素资产”。
本文件记录 t2-prompt 新增的**通用像素细节规则**，它们不绑定任何具体物品、
不绑定具体材质贴图，只描述所有 Minecraft 像素资产都应遵守的共同设计约束。

## 2. 新增规则

统一维护在 `concept_grounder.GENERIC_PIXEL_DETAIL_RULES`，内容如下：

1. **边框/描边**：外轮廓用 `1px 深色描边`；部件接缝用暗色分隔；不做均匀黑框。
2. **材质高光**：亮部高光沿形状走向，暗部在背光侧；金属/木/石/发光/软质等不同材质
   按语义推理使用不同高光强度与纹理提示，**不给死例子**。
3. **纹理**：材质纹理（木纹/石裂纹/金属划痕/发光颗粒等）贴合形状；
   **如果原版有参考就参考其质感，没有就自行推理合理材质**。
4. **明暗分层**：每个部件至少 `base/light/dark` 三档色阶；用 `1px` 明暗过渡表现体积，避免平涂。
5. **方向/连接**：整体方向一致，部件连接自然、不悬空。

## 3. 为什么设计成“通用”

- **避免提示词被特定物品劫持**：如果只对“蘑菇”、“水晶法杖”写死高光/纹理，
  换一个新想法时规则就失效；通用规则让任意物品都能套用。
- **保留语义推理空间**：规则只给出“要有亮暗”、“沿形状走”、“按语义推理材质”，
  不规定金属必须几像素高光、木纹必须几像素宽。具体材质表现由模型根据物品语义判断。
- **与检查器对齐**：`docs/check_pixel_asset.md` 的非空/bbox/深色描边/明暗分桶检查，
  正是从像素侧验证这些通用规则；通用规则先约束生成，检查器再给出可复现 evidence。

## 4. 如何在 `run_pipeline` 中使用

`run_pipeline._build_compact_prompt()` 在生成 LLM 提示时：

1. 读取 `concept_card`（语义、调色板、形状、参考节点）。
2. 输出 `# 通用设计原则`：方向统一、连接自然、剪影可辨、纹样贴合形状。
3. 新增 `# 通用像素细节`：直接从 `concept_grounder.GENERIC_PIXEL_DETAIL_RULES`
   逐条写入，保证与概念卡中的设计自检清单同源。
4. 最后附上 `PALETTE + INDEX GRID` 输出格式骨架（`-1` 透明、非负整数引用 PALETTE）。

因此 `--prompt-only` / `--llm-cmd {prompt}` 拿到的最终提示，会同时包含：
通用像素细节规则 + 当前物品概念卡 + PALETTE/INDEX GRID 输出契约。

## 5. 输出格式保持不变

本次改动只增加设计约束，**没有修改输出格式**：
- 仍是 `PALETTE + INDEX GRID`；
- 索引模式仍是 `-1 0 1` 语义（`-1` = 透明，非负整数引用 PALETTE）；
- 没有改回 `HEX GRID`；
- `text_to_texture.py` 对 `PALETTE + INDEX GRID` 的解析契约不受影响。

## 6. 涉及文件

| 文件 | 改动 |
| --- | --- |
| `concept_grounder.py` | 增加 `GENERIC_PIXEL_DETAIL_RULES`；`design_checklist` 增加外轮廓描边、材质高光、材质纹理三个自检项；明暗分层要求写入配色层次自检。 |
| `build_style_prompt.py` | `_build_v2_prompt_text` 新增“通用像素细节”段；`_FALLBACK_STYLE_RULES` 补充明暗三档、材质高光、材质纹理条目。 |
| `run_pipeline.py` | `_build_compact_prompt` 新增“通用像素细节”段，逐条引用 `concept_grounder.GENERIC_PIXEL_DETAIL_RULES`。 |
| `docs/prompt-design.md` | 本说明文档。 |

## 7. 验证方式

```bash
python3 concept_grounder.py --self-test
python3 build_style_prompt.py --self-test
python3 text_to_texture.py --self-test
python3 package_asset.py --self-test
```

生成的提示文本可通过 `run_pipeline.py --prompt-only` 检查：
应看到“通用像素细节”标题及其五条规则，且仍以 `PALETTE + INDEX GRID` 输出。
