# 独立复核记录：r1-survey 方法调研文档

- 日期：2026-09-05 (UTC)
- Reviewer：独立 reviewer（本会话，与 assignee=researcher 不同）
- 仓库 commit：`b9bd17dfe52414fbf2f3f1edbb3fe5d50e9d21ff`
- 工作目录：`/tmp/mc-mod-art-studio-core`
- 被审文件：`docs/method-survey.md`

## 核对范围

按 Acceptance 逐项核对：

1. docs/method-survey.md 覆盖原版方块多面/贴图拼接、实体 UV/模型、现有 LLM→可用资产方法
2. 每条来源带 URL/路径+访问日期；明确采用/拒绝理由

以及 5 个实际抽查点：

- cube_all / cube_bottom_top / cube_column / cross 与 blockstate/model/texture 契约
- 实体 UV（64x64/64x32、模型引用/注记）
- >=6 个外部方法/工具且带 URL
- 每项采用/拒绝理由
- 诚实记录本地完整 vanilla assets 缺失

## 抽查结果

### 1. 方块契约

- 文档 §1.1 给出 blockstate/model/texture 路径映射；§1.2 给出 variants/multipart 与本地 blockstate 证据。
- §1.4 表格列出 `cube`（six faces）、`cube_all`（`#all`）、`cube_bottom_top`（`#bottom/#top/#side`）、`cube_column`（`#end/#side`）、`cross`（`#cross`），并给出用途/多面映射。
- 用 GitHub API 从 `InventivetalentDev/minecraft-assets` 1.21.4 读取原版 `cube.json`、`cube_bottom_top.json`、`cube_all.json`、`cube_column.json`，与表格一致。
- §1.7 对本地 `package_asset.py` 的 `block_multi` 使用 `minecraft:block/cube` + `top/bottom/side` 的问题描述准确；本地代码 `package_asset.py:728-737` 可复现。

### 2. 实体 UV

- §2.1 说明 Java 原版实体模型多为硬编码渲染器，资源包一般仅能替换 `assets/minecraft/textures/entity/...` PNG。
- §2.2 涵盖 64×64/64×32、overlay、坐标表；用 `pkg.go.dev/github.com/mineatar-io/skin-render` 抽查，坐标表与 source 一致。
- §2.6 说明当前 `entity_uv` 只输出 PNG + `.note.txt`、不生成 model/绑定；本地 `example_resourcepack_entity/manifest.json` 与 `tests/runs/v2/pig/raw_answer.txt` 均可复现，pig 确为单侧视图截图/剪影，不是标准 skin atlas。

### 3. 外部方法与来源数量

- 文档 §3 共列出 17 个外部工具/项目（4+4+4+5），另有 §3.5 datagen 程序化方法；远超 >=6 要求。
- 31 个唯一外部 URL，均带访问日期（文档底部统一声明 2026-09-05，正文逐处标注）。
- 对 GitHub 仓库用 GitHub API 抽查，`DWF967/AIPackGenerator`、`Kreaking/...`、`anchapin/portkit`、`xandergos/terrain-diffusion-mc`、`boona13/image-extender`、`Shoeboxam/Texture_Synthesis`、`lukebemishprojects/DynamicAssetGenerator`、`orca-gamedev/img2blockbench`、`YaUhYeah/bbmodel-ai-generator`、`payangar-dev/texlab`、`Jhon-crypt/minecraft-ai`、`InventivetalentDev/minecraft-assets` 均存在且描述与文档一致。
- 对 arXiv、Minecraft Wiki、Fabric Docs、Microsoft Learn、Bedrock Wiki、OptiFine docs、pkg.go.dev 等 URL 做 HTTP 状态检查，绝大多数返回 200。

### 4. 采用/拒绝理由

- §3 每个表格行均有“采用/拒绝/参考/远期参考/只作调研”列并给出理由。
- §5 汇总清单逐项给出决策与理由。

### 5. 本地完整 vanilla assets 缺失

- §0、§2.3、§4 均明确记录 `/tmp/mc-mod-art-studio-core/mc_asset_library_full` 不存在；实测确认目录缺失。
- 同时说明 `builtin_models_fallback` 只是极简几何占位；实测文件内容符合（多为 `parent: minecraft:block/cube` + `#top/#bottom/#side/#particle`）。

## 结论

**pass**

- Acceptance 五项检查均通过，未发现关键证据缺失或事实性错误。
- 文档对“现状是否可用”的判断诚实：明确区分“能生成像素”与“能产出符合原版 JSON/UV 契约的可用资产”，并记录本地无完整 vanilla 资产这一 verified-gap。

## 非阻断性备注 / 可改进点

1. `media.io` 的 URL 在当前环境 CLI 抓取超时（HTTP 000 / ERR_CONNECTION_TIMED_OUT）；搜索引擎索引存在该页面，文档也明确标记为“只作调研/商业站点”，不影响结论。
2. `ai-prompts.online` 对 CLI 返回 403，文档已标注“来源非一手开发仓库，可信度中等”。
3. 个别表述可更精确，例如 §1.3 “子模型 elements 覆盖父模型” 的继承语义，以及 §1.5 “16 的百分比” 可改为“模型 UV 的 0–16 单位比例”。均为措辞/精度问题，非验收阻塞。
