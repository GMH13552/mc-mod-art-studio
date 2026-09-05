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
