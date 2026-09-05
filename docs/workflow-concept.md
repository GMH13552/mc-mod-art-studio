# mc-mod-art-studio 工作流概念：参考与创新平衡

## 一句话

让 LLM **从原版资产中学习“语法”**（配色家族 / 材质质感 / 结构比例 / UV 规则 / 边缘规律），
再按你的想法**写新句子**——不是复读原句，也不是乱造火星文。

## 三个输入，不是两个

每次生成只给“想法 + 原版图”会两极分化：要么抄、要么瞎画。
正确工作流把输入分成三层：

1. **意图层（用户想法 / 概念卡）**
   - 决定“做什么”（语义、部件、氛围、用途）。
   - 例：`一把复古皮革柄的剥皮小刀`。
2. **参考层（原版资产文本）**
   - 提供“材质语法”而不是“答案”：
     - 配色家族（不是具体格子，是主色/亮部/暗部/描边关系）；
     - 材质纹理节奏（木纹方向、金属划痕、石缝、生物皮肤分区）；
     - 结构比例（弓臂粗细、剑刃/柄比例、方块面对齐）；
     - UV/多面规则（方块面怎么拼、实体头/身/腿在哪）。
   - 参考块永远带来源与“禁止逐像素复制”标注。
3. **约束层（通用像素规则 + 形式硬约束 + novelty 参数）**
   - 1px 描边、明暗三档、部件分离、可拼贴、UV 区域、透明边距；
   - `--novelty 0..1`：
     - `0`：尽量贴近原版质感（用户做资源包替换时用）；
     - `0.5`（默认）：学到语法后自由组合；
     - `1`：更大胆的新设计（风格转换/杂交）。

## 模块职责

```text
user intent
   │
   ▼
[Intake] 解析想法 → 明确 form/部件/氛围
   │
   ▼
[Reference Analyzer]
   把原版 texture_to_text 变成“语法特征”，而不是整段塞给 LLM：
   - palette family（主/亮/暗/描边 的均值/范围/色相关系）
   - material signature（木纹/石/金属/发光/生物皮肤 的关键 token）
   - structure hints（细长件、弧形、对称、UV 区域）
   - silhouette bank（每个部件 2–4 个轮廓候选：shape token / X/. 剪影）
   - edge/tiling rules（side wrap、top-side 连续）
   │
   ▼
[Concept Card] 语义层（是什么/部件/避免）——不存像素
   │
   ▼
[Prompt Builder]
   组装 = 意图 + 参考语法（结构化摘要 + silhouette bank + 少量 compact 片段示例）+
          通用像素规则 + 形式硬约束 + novelty 指令 + 输出契约
   │
   ▼
[LLM → raw → PNG]
   │
   ▼
[Validator] 非空/bbox/描边/色阶/tiling/UV/reference-proximity
   │
   ▼
[Post-process] 仅在结构校验失败时做最小修正（可拼贴/边距），
   不替代生成，也不做整图替换
   │
   ▼
[Package] resourcepack + evidence（含原版参考 hash、novelty、validator 输出）
```

## 关键设计点

1. **Reference Analyzer 是核心模块**
   正确做法：**把 compact 文本提炼成结构化语法**（调色板统计、材质 token、结构 hint、UV 区域），
   再决定是否附 1–2 个 compact 片段作为“样式示例”（不逐像素复制）。
2. **Silhouette Bank 提供形状语法**
   每个部件给 2–4 个轮廓候选（shape token / 纯剪影），
   并固定说明“可选一个/可组合/可大改/禁止当最终网格”；避免“过缩”或“过抄”。
3. **Novelty 可调**
   参考层权重随 novelty 变化：novelty 越低，参考 compact 片段越多；越高，越少但保持语法。
4. **Validator 增加 reference-proximity**
   不是“和原版一样”，而是“用原版的语法（色系/亮度/描边/UV）量化”，
   防止输出既不像原版也不好看。
5. **Post-process 最小化**
   允许 seam-stitch / 边距收缩这类结构性小修，但**禁止用写死单个物品的特化补丁**。
6. **Human check 前置**
   `examples/skeleton_staff/` 与 `examples/demon_cow/` 直接放 PNG，用户先看图；数字只是辅助。

## 反模式

- ❌ 删参考 → 无源瞎画。
- ❌ 原样塞 compact → 模型抄格。
- ❌ 只给语义不给参考 → 弓变实心、猪 UV 全乱。
- ❌ 只给一句“短柄/细杖/方形皮”而不给轮廓候选 → 形状过缩。
- ❌ 带完整 compact / 整件索引网格 → 模型抄格。
- ❌ 写死单物品后处理（如 fix_bow）→ 治标不治本且是特化垃圾。
- ❌ 只报数字不给人看图。

## 补充原则

- 原版的**纹理、形状、配色都是可借鉴的素材**；
- 按情况而定：需要保留质感就贴近，需要创新就改；
- 不存在“不能改原版特征”的禁忌，也不存在“必须抄原版”的默认；
- 体现为 prompt 中的一句话：`借鉴但不照抄：形状/纹理/配色可按需要修改。`

## 部件级参考映射（Novel 资产专用）
对原版没有的新资产，不要“找一件最像的原版照抄”，而是**拆成部件 → 给每个部件指定参考来源**：

```
用户想法：骷髅法杖
├─ 骷髅头（头饰/杖顶） → 参考 skeleton 头骨：骨色/眼窝/裂纹纹理
├─ 杖身/握柄           → 参考工具手柄/木棍：结构比例/木纹/防滑槽
├─ 配色主调             → 参考 bone_block / 硬化粘土：骨白/暗灰
└─ 整体形态             → 概念卡自由定义，禁止锁定任何一件原版
```

- 每部件参考只借“这一部分的语法”（纹理/配色/结构/明暗），不借整件物品形态。
- prompt 中按部件列出参考来源，并写：`部件 X 参考 A 的纹样，部件 Y 参考 B 的结构；整体是新物品，不是 A 或 B。`
- novelty 越高，参考片段越少、重组合越自由；novelty 低时才允许整体更贴近单一原版。
- 这是第一版 primary/secondary 融合的升级版：从“两个整件”升级为“每部件多个参考”。

## 轮廓基础（silhouette bank）

部件级参考不仅要借“纹理/配色/结构”，还要给“可挑选的形状基础”：

```
部件: 刀刃
候选轮廓（2-4 个）:
  - curved-blade      来自 iron_sword / stone_sword（刃口微弧）
  - straight-tip      来自 shears / iron_sword（直背短刃）
  - hook-tip          来自 shears（上翘/钩形短刃）
指令:
  - 可选一个；也可组合；也可大改形状
  - 禁止把候选当最终像素答案
```

- `reference_analyzer.build_silhouette_bank(parts, retrieval_anchors, ...)` 负责为每个部件抽取 2–4 个候选；
- 候选可以是 `shape token`（`skull-round`、`curved-blade`、`rabbit-hide-body`），
  也可以是只含 `X/.` 的 `compact` 剪影片段；
- 对 `form=entity_uv`，候选按原版 atlas 区域切（`head/horns/ears/muzzle/body/legs/tail`），
  例如 cow/red_mooshroom 的 64x32 实体模板；
- 视觉 LLM 可通过多张 `--image` / `--llm-image` 直接参考原版 PNG，与文本剪影互补。

详见 `docs/silhouette-bank.md`。

## 配色也必须部件级（重要补充）
- 全局调色板会抹掉材质差异；正确做法是**每个部件一张配色卡**。
- 例：骷髅法杖
  - 骷髅头部件 → 配色卡=骨白/暗灰/眼窝黑（借 skeleton/bone）
  - 杖身部件 → 配色卡=木棕/暗棕/亮木纹（借 wood/planks/handle）
  - 宝石/魂火部件（若有）→ 配色卡=青绿/荧光（借 soul_fire/glowstone 但降饱和）
- Concept Card 的 `parts[]` 应扩展为 `{ part, shape, borrowed_texture, borrowed_palette, borrowed_structure }`；
  提示词按部件写参考，而不是一个全局 `palette_scheme`。
