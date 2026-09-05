# 核心设计文档（精简版）

## 1. 定位

`mc-mod-art-studio-core` 是一个把“想法”变成 Minecraft 自定义资源的最小流水线。
它面向**非多模态纯文本 LLM**：不需要模型直接看图，而是把参考素材转成文本特征，
让 LLM 按 `W/H + PALETTE + INDEX GRID` 生成像素。

## 2. 流水线

| 阶段 | 脚本 | 产物 |
| --- | --- | --- |
| 扫描 | `scan_mc_assets.py` | 资产索引 JSON |
| 检索 | `retrieve_assets.py` | retrieval JSON（1~8 个参考节点 + 特征） |
| 概念 | `concept_grounder.py` | concept JSON（语义 + 配色 + 形状 + 参考节点） |
| 提示 | `build_style_prompt.py` | prompt_pack JSON / 纯文本 prompt |
| 生成 | 纯文本 LLM | raw_answer.txt |
| 转换 | `text_to_texture.py` / `compose_asset.py` | PNG |
| 打包 | `package_asset.py` | 资源包目录 + manifest |
| 校验 | `audit_generation.py` / `validate_raw_answers_v3.py` | 哈希/格式审计 |
| 像素校验 | `check_pixel_asset.py` | 非空/bbox/描边/色阶/部件分离 evidence |
| 方块拼贴校验 | `check_tiling.py` | side_wrap / top_side / bottom_side 边缘连续性 evidence |
| 实体 UV 校验 | `check_entity_uv.py` | 尺寸/非空/画布边距/标准 UV 区域 evidence |
| 一键整合 | `run_pipeline.py` | 串起 scan → retrieve → concept → prompt → raw → PNG → package，并执行非空门禁 |

## 3. 概念卡 schema（v5 设计升级）

```
item_name, description, parts, face_regions, visual_goals,
minecraft_reference, avoid, form, query, source, method, ...

palette_scheme: {
  base, light, dark, accent, outline,
  border_note, saturation_note
}

shape_pattern: {
  silhouette, parts, border, shading, detail_pattern,
  shape_lock_optional: bool,
  part_pattern_flow: [
    { part, shape, pattern, flow }  // 每个部件的形状 → 纹样沿该形状结构走
  ],
  integration_note: string
}

reference_nodes: [
  { asset, role: shape|color|pattern|border|material, reason },
  ...  // 3~8 条
]
```

### 设计原则

1. **先理解语义**：模型先描述“这是什么、由哪些部件组成”，再进入配色和形状。
2. **配色方案**：`palette_scheme` 给主色/亮部/暗部/强调/描边与饱和度和自然边框说明。
3. **形状图样**：`shape_pattern` 给剪影/部件/描边/明暗/细节；`shape_lock_optional` 表示参考形状是否可调整。
4. **多参考节点**：`reference_nodes` 允许 3~8 条，每条说明其作用；**参考不是硬性指标，不复制参考贴图**。
5. **语义优先**：生成时优先保证“这个东西是什么”可辨认，而不是机械贴合某个参考形状。
6. **形状-纹样一体**：`shape_pattern.part_pattern_flow` 把“部件形状 → 纹样走向”绑定在一起；
   先用形状确定结构，再让纹样贴合形状的走向/边缘/明暗面，**纹样不得脱离形状独立存在**。

### 3.1 通用像素细节规则

提示词优化引入**不绑定具体物品的通用像素细节规则**，维护在
`concept_grounder.GENERIC_PIXEL_DETAIL_RULES`，并在提示包/紧凑 prompt 中逐条注入：

1. 外轮廓 `1px 深色描边`；部件接缝用暗色分隔，不做均匀黑框。
2. 材质高光沿形状走向，暗部在背光侧；按金属/木/石/发光/软质语义推理高光强度与纹理。
3. 材质纹理贴合形状；有原版参考则参考质感，没有则按语义合理推理。
4. 每个部件至少 `base/light/dark` 三档色阶，用 `1px` 明暗过渡表现体积。
5. 整体方向一致，部件连接自然、不悬空。

详细设计见 `docs/prompt-design.md`。这些规则与 `check_pixel_asset.py` 的非空/bbox/
深色描边/明暗分桶检查对齐。

### 3.2 非空门禁与 parser 容错

- `run_pipeline._assert_nonempty_pngs()`：生成后逐张检查不透明像素；出现全透明 PNG 即
  输出 `PIPELINE: FAIL` 并列出文件，不再误报 PASS。
- `text_to_texture.py` 容错：
  - `PALETTE` 行允许行尾 `#` 注释；
  - INDEX/HEX GRID 多余透明尾列可裁剪、缺少尾部透明列自动补 `-1` / `----`；
  - entity_uv 多出的尾行按容错处理，不因整段多余数据整体 FAIL。
- 对应 v2 广谱测试结果见 `tests/results/v2/summary.md`。

### 3.3 方块可拼贴（block_multi）

`block_multi` 的可用性由“三张 16x16 面”和“它们能否拼成一个无接缝立方体”决定：

- 模型父类：`minecraft:block/cube_bottom_top`，纹理变量 `#top / #bottom / #side`；
  四个侧面共用同一张 `side`，因此 `side` 左右两列必须一致。
- 贴图契约：
  1. 三张面都是 16x16 全不透明方块图（`opaque_pixels=256`，边缘 alpha>=128）。
  2. `side_wrap`：`side(0,y)` 与 `side(w-1,y)` 每行 RGB 最大通道差 <= threshold。
  3. `top_side`：`side` 顶行与 `top` 四条边颜色连续。
  4. `bottom_side`：`side` 底行与 `bottom` 四条边颜色连续。

校验器：

```bash
python3 check_tiling.py \
  --top <top.png> --side <side.png> --bottom <bottom.png> \
  --name <asset> --out-dir tests/results/v3
python3 check_tiling.py --self-test
```

输出 `status`、`checks.side_wrap/top_side/bottom_side`、`failed_checks`；`--allow-transparent`
可关闭不透明边缘门禁（仅作颜色对照）。详见 `docs/tiling-design.md`。

v3 实测：glowstone PASS；bricks 与 lapis_block 因跨面边缘/侧边不一致 FAIL（但三面已非透明）。

### 3.4 实体 UV 标准（entity_uv）

Java 原版实体模型是硬编码的；纯资源包只能替换原版实体贴图路径。因此 entity_uv 必须
满足“尺寸 + atlas 区域语义”，而不是把 64x32 画成一张居中侧视图。

当前内置标准（半开区间 `[x1,x2) × [y1,y2)`）：

| 实体 | 尺寸 | head | body | legs |
|---|---|---|---|---|
| pig | 64x32 | `0,0 -> 32,16` | `28,8 -> 64,32` | `0,16 -> 16,26` |
| creeper | 64x32 | `0,0 -> 32,16` | `16,16 -> 40,32` | `0,16 -> 16,26` |

玩家皮肤另有 64x64 / 64x32 标准布局（见 `entity_uv_spec.py` 与 `docs/entity-uv-design.md`）。

校验器：

```bash
python3 check_entity_uv.py tests/runs/v3/pig/sprite.png --entity pig \
  --json tests/results/v3/pig_entity_uv.json --md tests/results/v3/pig_entity_uv.md
python3 check_entity_uv.py --self-test
```

检查项：`dimension`、`nonempty`、`canvas_margin`（atlas 左右至少 1px，顶/底为说明项）、
`region_head/body/legs`。只有当尺寸正确、各标准区域非空且画布边距达标时判定 PASS。
实现细节见 `docs/entity-uv-design.md` 与 `entity_uv_spec.py`。

v3 实测：pig PASS；creeper 因左右触边（left=0,right=0）FAIL，但 head/body/legs 区域已非空。

### 3.5 完整资产参考与坐标系

本仓库刻意不内置原版素材；可复现的参考来自三类：

1. **仓库内模板/文档**
   - `builtin_models_fallback/`：chest、stairs、door、fence、wall 等 blockstate/model 占位模板。
   - `docs/method-survey.md`：原版 blockstate/model/实体 UV 的调研结论与外部来源。
   - `docs/tiling-design.md`、`docs/entity-uv-design.md`、`docs/prompt-design.md`：实现规范。
   - `evidence/`：v1–v3 独立复核记录、tiling baseline、entity_uv 检查证据。
2. **外部原版参考（不入库）**
   - Minecraft Wiki：模型/资源包/皮肤坐标。
   - 公开 vanilla assets 镜像（如 `InventivetalentDev/minecraft-assets`）。
   - `vanilla_entity_ref/` 本地纸质 UV 模板，已被 `.gitignore` 排除。
3. **坐标/atlas 约定**
   - 方块：16x16 PNG，`cube_bottom_top` 用 `#top/#bottom/#side`；model `uv` 坐标为 0–16 的百分比。
   - 实体：原点是左上，`x1,y1 -> x2,y2` 为半开区间；Java 实体模型按原版 atlas 直接采样。
   - 资源包路径：方块 `assets/<ns>/textures/block/*.png`；实体替换原版 `assets/minecraft/textures/entity/<path>.png`。

这样“完整参考”不是依赖某个私有素材库，而是把原版规则、本地模板、外部可获取来源与检查器绑定在一起。

## 4. 示例

### alien_crystal_wand（异形水晶法杖）

- 核心修正：顶部必须有**明显水晶簇**（多根尖柱/棱面），不是 blaze_rod 长条棒。
- 配色：低饱和青绿/水晶色，含暗部与 1px 深色描边，避免荧光刺眼。
- 产物：`examples/alien_crystal_wand/` 含 `concept.json`、`retrieval.json`、`prompt_pack.json`、
  `raw_answer.txt`、`sprite.png`、`hashes.json` 等。

### mushroom_sprout（蘑菇幼苗）

- 内容/形状是蘑菇本体（菌盖+菌柄），cross 只是渲染形式。
- 产物：`examples/mushroom_sprout/` 含 `concept.json`、`prompt_pack.json`、`raw_answer.txt`、`cross.png`。

## 5. 核心仓库边界

- 只包含核心脚本、`builtin_models_fallback/` 模板 JSON、两个示例、`docs/` 设计说明、
  `evidence/` 可复用审核与 `tests/` 的非自证测试集/证据/汇总。
- 不包含 `mc_asset_library*`、`generated_assets*`、`prompt_packs*`、`retrieval_examples*`、
  `concept_examples*`、`example_resourcepack*`、`style_*`、v4 日志/自测目录、其他 `minecraft_texture_tool` 文件。
- `tests/runs/` 为本地大产物，不入库；克隆后按 `tests/README.md` 重新生成。
- 所有自检使用合成资源，不依赖原版贴图。
