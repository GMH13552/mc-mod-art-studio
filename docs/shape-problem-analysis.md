# 形状借鉴问题分析：为什么“无轮廓基础选择 / 恶魔牛当物品 / 借鉴过缩或过抄 / 部件不像原版”

## 0. 术语约定

- **轮廓基础 / silhouette 候选**：从原版资产中抽取的**形状语法**，不是完整索引网格，也不是“整件答案”。
  可以是：
  - `silhouette compact 片段`：只含 `X/.` 剪影行的紧凑文本（不含 Palette / Index grid）；
  - `shape token`：短小的形状标签，例如 `thin-handle`、`curved-blade`、`skull-round`、`hide-fringe`。
- **形状锁定**：把某个原版轮廓直接当成最终答案，只改配色或加装饰。
- **形状空白**：只给部件文字（“刀身短小、刀柄 1-2px”），不给任何候选，模型只能自由发挥。

---

## 1. 现状核查：现有 novel-demo 为什么“轮廓没有借鉴味”

### 1.1 四个 novel-demo 的参考卡实际给了什么

| 资产 | 部件级参考 | 参考里写到的“形状/结构” | 是否给出可挑选的轮廓候选 | 是否明确“可大改形状” |
|---|---|---|---|---|
| villager_hide | leather.png / villager.png / stick.png + iron_sword.png | “16x16 中央皮面主体、边缘包边、自然折痕”；“皮面下缘窄条织物”；“上缘小环” | ❌ 只有一句话结构总结 | ⚠️ 有“不借外形”，但没有“可选 / 可大改”的候选句式 |
| skinning_knife | iron_sword.png / leather.png / stick.png / oak_planks.png | “短小弯曲刀片（非长剑）”；“1-2px 横向窄条”；“1-2px 宽短柄” | ❌ 同样只有一句话结构总结 | ⚠️ 同上 |
| skeleton_staff | skeleton.png / bone_block_side.png / stick.png / oak_planks.png | “杖顶骨白头骨”；“1-2px 暗色小口/环”；“1-2px 宽木杖” | ❌ 没有头骨轮廓、杖柄轮廓的候选 | ⚠️ 同上 |
| demon_cow | cow.png / red_mooshroom.png / soul_fire_0.png | “正面牛头剪影、鼻梁纵向”；“顶部双角、两侧耳朵”；“两眼左右对称、鼻口在下方” | ❌ 没有牛头/角/鼻口的原版区域轮廓候选 | ⚠️ 同上 |

结论：当前 `source_table` 的 `borrowed_structure` 本质上是**人工写的结构小作文**，
它既不是可挑选的 silhouette 候选集，也没有把“从原版学形状”升级成“形状语法菜单”。

### 1.2 `reference_analyzer` 现状：有剪影解析，却只输出统计，不输出候选

`reference_analyzer.py` 其实已经做了关键的一步：

- `_parse_silhouette()` 能解析 `## Silhouette` 的 `X/.` 行；
- `_structure_hints()` 能从剪影算出“细长 / 弧形 / 对称 / 多部件”等 hint。

但 `analyze_compact()` 的返回结构里**没有保留 silhouette 行本身**，也没有生成“剪影候选片段”或“shape token 列表”：

```text
return {
    "source": name,
    "form": form,
    "palette_family": ...,        # 有
    "material_signature": ...,    # 有
    "structure_hints": ...,        # 只有总结句，如 "细长；单件"
    "uv_regions": ...,             # 有（entity_uv 专用）
}
```

所以在 prompt 里，模型只能看到：

> 结构提示：细长；单件

而看不到可组合、可替换的轮廓基础。这正是“轮廓没有借鉴味”的第一个根因：**形状被降维成了几个形容词，而不是一组候选基础。**

### 1.3 `build_style_prompt` 现状：参考节点信息进入 prompt，但形状仍由概念卡“一句剪影”决定

`_build_v2_prompt_text()` 会输出：

- `### 形状图样 shape_pattern`：`剪影 silhouette` 是概念卡里的一句中文；
- `形状-纹样联动 part_pattern_flow`：每个部件仍是一句 `形状：... | 纹样：... | 走向：...`；
- `参考节点 reference_nodes`：只写 `asset / role / reason`；
- `## 原版参考（结构化语法 + 少量片段）`：包含配色家族、材质签名、结构提示、UV 区域。

也就是说，参考块把**颜色和材质**讲得比**形状**具体得多：
- 配色有 hex、有均值、有范围；
- 材质有 token（木质/金属/发光/软质）；
- 形状只有一句结构提示，而且不会变成“候选清单”。

### 1.4 四个部件“头/柄/刀/皮不像”的对应关系

用户反馈的“头/柄/刀/皮不像”，在实际 demo 中可对应为：

| 部件 | demo | 当前 prompt 给形状的方式 | 为什么不像 |
|---|---|---|---|
| **头**（牛头 / 骷髅头） | demon_cow / skeleton_staff | “正面牛头剪影”、“圆/方形骨白头骨” | 没有从 cow / red_mooshroom / skeleton 的原版头、角、眼窝、鼻口区域提取轮廓候选；模型只能画一个通用“红牛脸 / 白骷髅脸” |
| **柄**（杖柄 / 刀柄） | skeleton_staff / skinning_knife | “1-2px 宽木杖”、“1-2px 宽短柄” | 没有借用 stick / blaze_rod / wooden_sword / 工具柄的柄部轮廓差异（直柄、微曲柄、缠绳柄、锥形柄等），导致柄是“通用直线” |
| **刀**（刀身） | skinning_knife | “短小弯曲刀片（非长剑）” | 没有从 iron_sword / stone_sword / shears / 原版短刀类轮廓中给 2-4 个候选；模型只能自创一个不新不旧的轮廓 |
| **皮**（皮面） | villager_hide | “折叠/铺开的方形皮革” | 没有从 leather / rabbit_hide / villager 织物边缘提取“皮料 + 衣料”的轮廓候选，结果容易像“棕色方块”或“普通布片” |

---

## 2. 四项缺点与根因

### 缺点 ①：无轮廓基础选择（silhouette bank 缺失）

**表现**：参考卡只写“部件结构文字”，没有“可挑选的原版轮廓基础”。

**根因**：
1. `reference_analyzer` 解析剪影后只生成 `structure_hints` 总结，未输出 `silhouette_candidates` / `shape_tokens`；
2. `build_style_prompt` 没有在 `shape_pattern` 下渲染“部件 → 2-4 个原版轮廓候选”的段落；
3. prompt 缺少“候选不是答案，可选一个、可组合、可大改”的指令，模型容易把一句中文剪影当唯一方案，或者干脆自由发挥。

**证据**：
- `examples/novel-demo/*/prompt.txt` 中只有 `### 部件级参考映射` 表，没有“轮廓候选”字段；
- `reference_analyzer.analyze_compact()` 返回值不含 silhouette 候选；
- `_build_v2_prompt_text()` 的 `shape_pattern` 段落只有 `silhouette / parts / border / shading / detail_pattern / part_pattern_flow`，没有 `silhouette_candidates`。

### 缺点 ②：恶魔牛被当 item（form 选错）

**表现**：`demon_cow` 输出是 `16x16 item` 的“正面牛头图标”，而不是按实体模板 `cow / red_mooshroom` 生成 `64x32` 的实体 UV 贴图。

**根因**：
1. 手工概念卡把 `demon_cow` 的 `form` 定为 `item`、`size` 为 `16x16`；
2. 参考来源 `cow.png / red_mooshroom.png` 是**实体纹理**（标准 UV atlas），不是 item 像素；用 item 契约会强制“单张 16x16 居中剪影”，导致整个实体被压缩成一个牛头图标；
3. `entity_uv_spec` / `form=entity_uv` 没有参与该 demo 的生成，因此没有 64x32 画布、没有区域坐标、没有“头/角/鼻口/身体/腿”区域语义。

**期望**：
- 恶魔牛应使用 `form=entity_uv`，尺寸 `64x32`（或遵循 `cow / red_mooshroom` 的标准实体模板）；
- 参考 analyzer 应对该 form 返回区域级 silhouette 候选（例如 head / horn / muzzle / legs），而不是一个 16x16 居中图标。

### 缺点 ③：借鉴要么过缩、要么过抄

**表现**：
- 过缩：只给一句“短柄/细杖/方形皮”，形状完全靠模型自创，失去原版骨架感；
- 过抄：走另一极端时把原版 compact 整段或最相关项的索引网格直接带进 prompt，模型把整件原版复制出来。

**根因**：
1. 当前 prompt 的“形状输入”只有两种模式：
   - 模式 A：完全没有原版剪影（novel-demo 手工卡），退化成“无源瞎画”；
   - 模式 B：保留完整 compact 片段（见 `docs/reference-influence.md`），退化成“照着原版抄格”。
2. 缺少中间层：**有来源、有候选、可组合、可改形、但不给最终像素答案**。
3. `--no-original-ref` 实验已经证明：去掉参考块会失去原版质感/方向，但带完整 compact 又会产生 91.8% 的索引网格相似度。这说明当前“参考开关”是二值的，缺少“形状候选”这个可控夹层。

**教训（烈焰棒 → 改色棍）**：
> 如果把“烈焰棒”仅当作用来改色的原版，只把颜色换成水晶青、形状完全不动，结果就是“改色棍”——没有形成新物品，也没有真正借用原版的形状语法。
> 反过来，如果因为怕抄就完全不给形状参考，模型会自己造一根“标准直线棍”，同样不像原版工具。
> 正确做法是：把原版工具柄的轮廓当作 2-4 个候选，明确告诉模型“可选其一、可组合、可大改”，而不是把它当作唯一答案或完全回避。

### 缺点 ④：头/柄/刀/皮不像

**表现**：部件各自没有“原版那味”。

**根因**：
1. 每个部件只被概念卡的 `shape` 字段描述，没有按部件绑定 2-4 个原版轮廓基础；
2. `reference_analyzer` 目前按“整件锚点”分析，不是按“部件/区域”分析；`cow.png` 的头、角、鼻口、身体没有被拆成不同候选；
3. 没有 `shape token` 词汇表，模型无法在文字层面对比“刀身候选：直刃 / 上翘刃 / 弯刃”等差异。

---

## 3. 改造方案：silhouette bank（轮廓基础候选）

### 3.1 目标

让“形状借鉴”和“配色借鉴”一样结构化：

```text
当前：
  部件: 刀刃
  形状: 短小弯曲刀片（非长剑）
  ▲ 只有一句人工描述

改造后：
  部件: 刀刃
  候选轮廓（2-4 个）:
    - curved-blade      来自 iron_sword / stone_sword（刃口微弧）
    - straight-tip      来自 shears / iron_sword（直背短刃）
    - hook-tip          来自 shears（上翘/钩形短刃）
  指令:
    - 可选一个；也可组合；也可大改形状
    - 禁止把候选当最终像素答案
```

### 3.2 模块职责

| 模块 | 改动方向（不实现代码，仅方案） |
|---|---|
| `reference_analyzer` | `analyze_compact()` 返回值增加 `silhouette_candidates` / `shape_tokens`；内部复用 `_parse_silhouette()`，把剪影行转成候选片段或 token；对 `entity_uv` 还要按 `uv_regions` 返回区域候选 |
| `concept_grounder` / 概念卡 | `shape_pattern` 新增 `silhouette_candidates` 字段：`part -> [{token, source, silhouette_fragment?, note}]` |
| `build_style_prompt` | `_build_v2_prompt_text()` 在 `### 形状图样 shape_pattern` 下渲染“部件轮廓候选”；参考块中保留原版来源路径与“禁止逐像素复制”标注 |
| `examples/novel-demo` | 手工概念卡补充候选字段；`demon_cow` 改为 `form=entity_uv`、`size=64x32`，按 cow/red_mooshroom 实体区域出候选 |
| `docs/prompt-design.md` | 增加“形状候选菜单 + 可选/组合/可大改”规则 |

### 3.3 `reference_analyzer`：每个参考返回 2-4 个轮廓基础

建议输出结构（示意，不是代码）：

```text
silhouette_candidates:
  [
    {
      "token": "thin-handle",
      "source": "stick.png",
      "kind": "shape_token",
      "note": "1-2px 直线细柄；适合杖身/握柄基础"
    },
    {
      "token": "curved-blade",
      "source": "iron_sword.png",
      "kind": "shape_token",
      "note": "略向上翘的短刃；适合小刀/匕首刀身"
    },
    {
      "token": "skull-round",
      "source": "skeleton.png (head region)",
      "kind": "compact_fragment",
      "fragment": "....XXXX....\\n..XXXXXXXX..\\n..XX..XX..XX.\\n....XXXX....",
      "note": "只含 X/. 剪影，不含 Palette / Index grid"
    }
  ]
```

要点：
- **一个部件对应 2-4 个**：太少会退化成“唯一答案”，太多会噪音；
- **优先 shape token**：交给 LLM 的语义更清晰，也不容易触发逐像素复制；
- **可选 silhouette compact 片段**：只用 `X/.` 剪影行，仍然禁止把 Palette / Index grid 注入；
- **`entity_uv` 按区域返回**：如 `head` 给 `skull-round / cow-head-front`，`handle` 给 `thin-handle / wooden-curve`，避免把整张 64x32 当 16x16 图标。

### 3.4 `build_style_prompt`：把候选作为“可挑选/可组合/可大改”的菜单

在 `### 形状图样 shape_pattern` 中新增段落：

```text
### 部件轮廓候选 silhouette_candidates（2-4 个/部件）

- [刀刃]
  - 候选 1：curved-blade（来源：iron_sword / stone_sword）
  - 候选 2：straight-tip（来源：shears / iron_sword）
  - 候选 3：hook-tip（来源：shears）
  - 使用规则：可选其中一个；也可把多个候选组合；也可在此基础上**大改形状**。
    候选只是“轮廓语法”，不是最终答案；禁止把任何候选当成原版答案逐像素复制。
```

并把这些规则写入通用原则（或形状候选段落开头）：

> 形状候选 = 菜单，不是锁。
> - 可选一个；
> - 可组合多个；
> - 可大改形状（加长、加粗、弯曲、变形、换比例都允许）；
> - 禁止逐像素复制候选轮廓/禁止把候选剪影直接当最终 INDEX GRID。

### 3.5 建议 shape token 词汇表（初版）

| token | 适用部件 | 可来源于 |
|---|---|---|
| `thin-handle` | 杖身/握柄 | stick.png / blaze_rod.png / iron_sword.png / wooden_sword.png |
| `curved-blade` | 刀刃 | iron_sword.png / stone_sword.png / shears.png |
| `straight-blade` | 刀刃 | stone_sword.png / wooden_sword.png |
| `skull-round` | 头/杖顶 | skeleton.png / wither_skeleton.png |
| `horn-split` / `horn-curved` | 牛/恶魔角 | cow.png / red_mooshroom.png / goat.png |
| `hide-fringe` | 皮面/织物边缘 | leather.png / rabbit_hide.png / villager.png |
| `muzzle-block` | 牛/羊/猪鼻口 | cow.png / red_mooshroom.png / pig.png |
| `ear-side` | 耳/附属 | cow.png / red_mooshroom.png |
| `leaf-round` | 植物/菌盖 | red_mushroom_block.png / oak_leaves.png |

### 3.6 对 `demon_cow` 的专项修正（方案）

- `form`: `item` → `entity_uv`；
- `size`: `16x16` → `64x32`（按 cow / red_mooshroom 实体模板）；
- `parts`: 从“牛头图标部件”改为“实体 UV 区域部件”，例如 `head / horns / ears / muzzle / body / legs / tail`；
- `silhouette_candidates`:
  - `head`：`cow-head-around`（来源 cow.png 头部区域）、`red-mooshroom-head`（来源 red_mooshroom.png 头部区域）、`skull-round`（若做恶魔化也可选骨架式头骨）；
  - `horns`：`horn-curved` / `horn-split`（来源 cow / red_mooshroom / goat）；
  - `muzzle`：`muzzle-block` / `snout-wide`；
  - `body`：按标准实体区域给“四足站立剪影候选”，而不是 16x16 居中正脸；
- prompt 同时保留原有“恶魔红 / 魂火青”的配色与材质借鉴，但形状不再被锁成 16x16 图标。

---

## 4. 验证方式（后续任务验收时使用）

1. **静态检查**
   - `reference_analyzer.analyze_compact()` 返回的 dict 含 `silhouette_candidates`；
   - 每个候选有来源；每个部件候选数在 2~4；
   - `build_style_prompt` 生成的 prompt 含 `部件轮廓候选` 与“可选/可组合/可大改”指令；
   - `examples/novel-demo/demon_cow` 的 `form=entity_uv`、`size=64x32`（或按实体模板正确值）。
2. **生成质量**
   - 对 4 个 demo 分别跑一次生成，人工检查“头/柄/刀/皮”是否仍能看出对应原版部件轮廓；
   - 对 `demon_cow` 检查输出为 64x32 实体 UV atlas，不是 16x16 居中图标；
   - 用 `check_entity_uv.py` 或实体 UV 检查器验证区域语义。
3. **防抄/防缩**
   - 不复刻完整原版 INDEX GRID；
   - 也不退回“完全无形状参考”；
   - 参考相似度应低于“整件照抄”阈值，同时形状可识别度不能低于“无源瞎画”版本。

---

## 5. 一句话总结

> 当前系统缺的不是“更多原版图”，而是**“把形状变成可挑选、可组合、可大改的候选菜单”**。
> 先用 `reference_analyzer` 输出 2-4 个 silhouette 基础 / shape token，
> 再由 `build_style_prompt` 明确“候选可选可组合可大改”，
> 最后把 `demon_cow` 从 item 修正为 entity_uv 64x32，即可同时解决“无轮廓基础、恶魔牛当物品、借鉴过缩过抄、部件不像原版”四项问题。
