# Prompt Design：通用设计原则与像素细节规则

## 1. 目的

`mc-mod-art-studio` 的提示词不仅要告诉模型“画什么”，还要约束“怎么画得像 Minecraft 像素资产”。
本文记录**通用设计原则**与**通用像素细节规则**，它们不绑定任何具体物品、
不绑定具体材质贴图，只描述所有 Minecraft 像素资产都应遵守的共同设计约束。

## 2. 通用设计原则

统一维护在 `concept_grounder.GENERIC_DESIGN_PRINCIPLES`，内容如下：

1. **整体方向统一**：所有部件沿同一主方向/轴线；附属物方向与主体一致或围绕主体自然分叉。
2. **连接点自然**：部件相接处与主轴/重心对齐，不悬空、不偏心、不错位。
3. **剪影可辨**：只看形状也能认出“这是什么”；部件之间用描边/色差/空隙区分，不要糊成实心团块。
4. **纹样贴合形状**：纹理/高光/图案沿部件的走向与明暗面流动，不脱离形状。
5. **细长部件**：所有细长部件（杆/柄/弦/茎/边框等）宽度控制在 `1~2px`，不能糊成 `3px` 以上实心色带。
6. **负空间**：部件之间与内部孔洞保留至少 `1px` 透明负空间（`block_multi` 整面不透明方块除外），避免实心团块。
7. **禁止实心团块**：主体必须有内部明暗/纹理/负空间，不能无细节地满涂成一个大色块。
8. **参考完整资源**：不要只看单张示例图；方块类要同时理解顶/侧/底三面、模型与 blockstate 契约，
   实体要按标准 UV 图集/区域语义理解，多面/实体统一走结构化输出。

## 3. 通用像素细节规则

统一维护在 `concept_grounder.GENERIC_PIXEL_DETAIL_RULES`，内容如下：

1. **边框/描边**：外轮廓用 `1px 深色描边`；部件接缝用暗色分隔；不做均匀黑框。
2. **材质高光**：亮部高光沿形状走向，暗部在背光侧；金属/木/石/发光/软质等不同材质
   按语义推理使用不同高光强度与纹理提示，**不给死例子**。
3. **纹理**：材质纹理（木纹/石裂纹/金属划痕/发光颗粒等）贴合形状；
   **如果原版有参考就参考其质感，没有就自行推理合理材质**。
4. **明暗分层**：每个部件至少 `base/light/dark` 三档色阶；用 `1px` 明暗过渡表现体积，避免平涂。
5. **方向/连接**：整体方向一致，部件连接自然、不悬空。
6. **细长部件**：所有细长部件（杆/柄/弦/茎/边框等）宽度控制在 `1~2px`，
   必要时保留内部明暗/细节，不能糊成 `3px` 以上实心色带。
7. **负空间（透明/镂空）**：透明间隙和内部镂空是像素资产的一部分；部件之间与内部孔洞
   保留至少 `1px` 透明负空间（`block_multi` 整面不透明方块除外），避免实心团块。
8. **禁止实心团块**：主体必须有内部结构（明暗/纹理/负空间），不能无细节地满涂成一个大色块；
   轮廓/部件间用描边或透明间隙区分。
9. **透明边距（物品/植物/实体图集）**：非方块多面纹理（`item/cross/entity_uv`）与画布四边
   保留至少 `1px` 透明边距；`block_multi` 的 `top/side/bottom` 例外，必须是 `16x16`
   全不透明且边缘连续。

## 4. 形式硬约束（form-specific）

不同 form 在 prompt 中还会注入专门的“形式硬约束”，见
`run_pipeline._form_specific_constraints()` 与 `build_style_prompt._form_specific_constraints_text()`：

- `block_multi`：三面 `top/side/bottom` 都是 `16x16` 全不透明方块面，边缘必须连续；
  `side` 左右可环绕平铺；禁止沿用透明物品剪影/棋盘格；参考完整资源（三面 + blockstate/model）。
- `entity_uv`：不是单个侧视图，是标准 `64x32/64x64` atlas；每个区域按语义填；
  按 `entity_uv_spec.contract_text()` 注入标准区域坐标；Java 只能替换原版实体贴图路径。
- `cross` / `item`：`16x16` 透明背景，主体居中、四周至少 `1px` 透明边距。

## 5. 为什么设计成“通用”

- **避免提示词被特定物品劫持**：如果只对“蘑菇”、“水晶法杖”写死高光/纹理，
  换一个新想法时规则就失效；通用规则让任意物品都能套用。
- **保留语义推理空间**：规则只给出“要有亮暗”、“沿形状走”、“按语义推理材质”，
  不规定金属必须几像素高光、木纹必须几像素宽。具体材质表现由模型根据物品语义判断。
- **与检查器对齐**：`docs/check_pixel_asset.md` 的非空/bbox/深色描边/明暗分桶/`opaque_ratio` 检查，
  正是从像素侧验证这些通用规则；通用规则先约束生成，检查器再给出可复现 evidence。

## 6. 如何在 `run_pipeline` 中使用

`run_pipeline._build_compact_prompt()` 在生成 LLM 提示时：

1. 读取 `concept_card`（语义、调色板、形状、参考节点）。
2. 输出 form-specific `# 形式硬约束`。
3. 输出 `# 通用设计原则`：逐条写入 `concept_grounder.GENERIC_DESIGN_PRINCIPLES`。
4. 输出 `# 通用像素细节`：逐条写入 `concept_grounder.GENERIC_PIXEL_DETAIL_RULES`。
5. 最后附上 `PALETTE + INDEX GRID` 输出格式骨架（`-1` 透明、非负整数引用 PALETTE）。

`build_style_prompt._build_v2_prompt_text()` 同样输出这些段落，保持两套提示词口径一致。

## 7. 输出格式保持不变

本次改动只增加设计约束，**没有修改输出格式**：
- 仍是 `PALETTE + INDEX GRID`；
- 索引模式仍是 `-1 0 1` 语义（`-1` = 透明，非负整数引用 PALETTE）；
- 没有改回 `HEX GRID`；
- `text_to_texture.py` 对 `PALETTE + INDEX GRID` 的解析契约不受影响。

## 8. 涉及文件

| 文件 | 改动 |
| --- | --- |
| `concept_grounder.py` | 增加 `GENERIC_DESIGN_PRINCIPLES`；扩充 `GENERIC_PIXEL_DETAIL_RULES`（细长部件/负空间/禁止实心团块/透明边距例外）。 |
| `build_style_prompt.py` | `_build_v2_prompt_text` 新增“通用设计原则”与 form-specific 硬约束段。 |
| `run_pipeline.py` | `_build_compact_prompt` 新增 form-specific 硬约束段，并统一引用 `GENERIC_DESIGN_PRINCIPLES`。 |
| `entity_uv_spec.py` | `contract_text()` 强化“标准 atlas、按区域填”表述。 |
| `check_pixel_asset.py` | 新增 `opaque_ratio`（bbox 内覆盖率）指标。 |
| `check_tiling.py` | 自测补 `bottom_side` 断言。 |
| `docs/prompt-design.md` | 本说明文档。 |

## 9. 验证方式

```bash
python3 concept_grounder.py --self-test
python3 build_style_prompt.py --self-test
python3 text_to_texture.py --self-test
python3 package_asset.py --self-test
python3 retrieve_assets.py --self-test
python3 compose_asset.py --self-test
python3 check_tiling.py --self-test
python3 check_entity_uv.py --self-test
python3 check_pixel_asset.py --self-test
python3 -m unittest discover -s tests
```

生成的提示文本可通过 `run_pipeline.py --prompt-only` 检查：
应看到“形式硬约束/通用设计原则/通用像素细节”标题，且仍以 `PALETTE + INDEX GRID` 输出。
