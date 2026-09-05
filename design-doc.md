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
| 参考语法 | `reference_analyzer.py` | `reference_analysis` / `reference_block` |
| 概念 | `concept_grounder.py` | concept JSON（语义 + 配色 + 形状 + 参考节点） |
| 提示 | `build_style_prompt.py` | prompt_pack JSON / 纯文本 prompt |
| 生成 | 纯文本 LLM | raw_answer.txt |
| 转换 | `text_to_texture.py` / `compose_asset.py` | PNG |
| 打包 | `package_asset.py` | 资源包目录 + manifest |
| 像素校验 | `check_pixel_asset.py` | 非空/bbox/描边/色阶/部件分离 evidence |
| 方块拼贴校验 | `check_tiling.py` | side_wrap / top_side / bottom_side 边缘连续性 |
| 实体 UV 校验 | `check_entity_uv.py` | 尺寸/非空/画布边距/标准 UV 区域 |
| 一键整合 | `run_pipeline.py` | 串起 scan → retrieve → concept → prompt → raw → PNG → package，并执行非空门禁 |
| 后处理 | `fix_tiling.py` / `fix_entity_margin.py` | 方块 seam-stitch、实体 atlas margin inset |

## 3. 参考语法与 novelty

`reference_analyzer.py` 把原版 `compact` 文本提炼成结构化语法，而不是把整段文本直接塞给 LLM：

- `palette_family`：主/亮/暗/描边的均值与范围；
- `material_signature`：木质/石/金属/发光/软质等材质 token；
- `structure_hints`：细长/弧形/对称/部件数等结构提示；
- `uv_regions`：实体 UV 区域坐标（`entity_uv` 时注入）。

prompt 中固定标注“借鉴但不照抄”，并用 `--novelty` 控制参考片段数量：

| novelty | 行为 |
| --- | --- |
| `0` | 最贴近原版：附 2 个 compact 片段 |
| `0.5`（默认） | 标准：附 1–2 个最相关片段 |
| `0.6~0.84` | 较自由：只附 1 个片段 |
| `0.85~1.0` | 最自由：不附片段，仅保留结构化参考语法 |

`--no-original-ref` 可完全关闭参考块，回到“仅语义摘要”模式。

## 4. 通用像素细节规则

提示词中注入**不绑定具体物品的通用像素细节规则**，维护在
`concept_grounder.GENERIC_PIXEL_DETAIL_RULES`：

1. 外轮廓 `1px 深色描边`；部件接缝用暗色分隔，不做均匀黑框。
2. 材质高光沿形状走向，暗部在背光侧；按金属/木/石/发光/软质语义推理。
3. 材质纹理贴合形状；有原版参考则参考质感，没有则按语义合理推理。
4. 每个部件至少 `base/light/dark` 三档色阶，用 `1px` 明暗过渡表现体积。
5. 整体方向一致，部件连接自然、不悬空。
6. 细长部件宽度控制在 `1~2px`，避免糊成实心色带。
7. 透明负空间是像素资产的一部分；`block_multi` 的方块面除外。

详细设计见 `docs/prompt-design.md`，像素级验证见 `docs/check_pixel_asset.md`。

## 5. 非空门禁与 parser 容错

- `run_pipeline._assert_nonempty_pngs()`：生成后逐张检查不透明像素；出现全透明 PNG 即
  输出 `PIPELINE: FAIL` 并列出文件，不再误报 PASS。
- `text_to_texture.py` 容错：
  - `PALETTE` 行允许行尾 `#` 注释；
  - INDEX/HEX GRID 多余透明尾列可裁剪、缺少尾部透明列自动补 `-1` / `----`；
  - entity_uv 多出的尾行按容错处理，不因整段多余数据整体 FAIL。

## 6. 方块可拼贴（block_multi）

`block_multi` 由三张 16x16 全不透明方块面组成：

- 模型父类：`minecraft:block/cube_bottom_top`，纹理变量 `#top / #bottom / #side`；
- `side` 左右两列必须一致（四个侧面共用同一张 `side`）；
- `side` 顶行与 `top` 四边、`side` 底行与 `bottom` 四边颜色连续。

校验器 `check_tiling.py` 输出 `side_wrap / top_side / bottom_side`；
`fix_tiling.py` 提供只改 1px 边缘的通用 seam-stitch 后处理。

## 7. 实体 UV 标准（entity_uv）

Java 原版实体模型是硬编码的；资源包只能替换原版实体贴图路径。因此 `entity_uv`
必须满足“尺寸 + atlas 区域语义”，而不是把 64x32 画成一张居中侧视图。

当前 `entity_uv_spec.py` 内置猪/苦力怕等标准 64x32 atlas 区域，`check_entity_uv.py`
检查尺寸、非空、画布边距与各标准区域；`fix_entity_margin.py` 可做通用画布边距后处理。

## 8. 资产参考边界

本仓库**不内置原版素材**。可复现参考有三类：

1. `builtin_models_fallback/`：内置 blockstate/model 占位模板。
2. 外部公开来源：Minecraft Wiki、公开 vanilla assets 镜像。
3. 用户本机扫描：`scan_mc_assets.py --mc-path <本地>/--index <索引>`。

`vanilla_entity_ref/` 仅作本地纸质 UV 模板，已被 `.gitignore` 排除，克隆仓库不会得到原版 PNG。

## 9. 示例

- `examples/skeleton_staff/`：`item` 16x16 离线示例，含 `sprite.png`、`raw_answer.txt`、`prompt.txt`、`concept.json`、`hashes.json` 与 `check_results.json`。
- `examples/demon_cow/`：`entity_uv` 64x32 实体示例，含 `sprite.png`、`concept.json`、`hashes.json`、`check_results.json`；最终 PNG 使用原版 cow.png 轮廓/区域 + 恶魔牛配色程序化重着色。

## 10. 仓库边界

- 只保留核心脚本、`builtin_models_fallback/` 模板、最小 examples、`docs/` 设计说明与 `tests/` 单元测试。
- 不包含 `mc_asset_library*`、`generated_assets*`、`prompt_packs*`、`retrieval_examples*`、
  `concept_examples*`、`example_resourcepack*`、历史 evidence/审核记录、旧 showcase 图与日志。
- `tests/runs/` 为本地大产物，不入库。
- 所有自检使用合成资源，不依赖原版贴图。
