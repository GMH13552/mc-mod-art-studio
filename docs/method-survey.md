# Method Survey: Making Minecraft Assets Truly Usable

- **Task**: r1-survey — 调研“可用资产化”方法
- **Researcher date (UTC)**: 2026-09-05
- **Scope**: 只调研与记录，不实现代码。
- **Local evidence**: `/tmp/mc-mod-art-studio-core`（仓库根目录）

---

## 0. 结论摘要

让 mc-mod-art-studio 的产物“真正可用”，核心不是“会画像素”，而是**严格对齐 Minecraft 的资源包契约**：

1. 方块：`blockstate → model → textures` 三层必须自洽；当前 `block_multi` 使用 `minecraft:block/cube` + `top/bottom/side` 纹理变量，与原版 `cube.json` 的 `#down/#up/#north/#south/#west/#east` 契约不符，建议改为 `minecraft:block/cube_bottom_top` 或显式 `elements/faces/uv`。
2. 实体：Java 原版实体模型是硬编码的，资源包只能替换既有实体贴图路径；当前 `entity_uv` 只输出 `assets/<modid>/textures/entity/*.png` + note，没有模型/渲染绑定，**不能直接让任意原版实体使用**。真正可用需要：替换原版 `minecraft:textures/entity/...` 路径，或走 Bedrock geometry / OptiFine CEM / 模组 renderer。
3. 完整美术资源：本地 `mc_asset_library_full` 不存在，`builtin_models_fallback` 只是几何占位；需要从 Mojang `client.jar` / 公开 vanilla assets 镜像（如 `InventivetalentDev/minecraft-assets`）补齐原版模型、blockstate、实体 UV 布局。
4. LLM/AI 方法池已足够广：文生图后处理、Minecraft 特化 diffusion/LoRA、seamless tile/outpainting、Blockbench 模型生成、程序化/运行时代码生成。采用时要区分“能否产出像素”与“能否产出符合 JSON 契约的资产”。

---

## 1. 原版方块：blockstate / model / 多面贴图拼接

### 1.1 资源包路径

- 文件映射（原版规则）：
  - `assets/<namespace>/blockstates/<name>.json` → blockstate
  - `assets/<namespace>/models/block/<name>.json` → 方块模型
  - `assets/<namespace>/textures/block/<name>.png` → 贴图
- 来源：Minecraft Wiki `Tutorial:Models`（访问 2026-09-05）：https://minecraft.wiki/w/Tutorial:Models
- 来源：Minecraft Wiki `Model`（访问 2026-09-05）：https://minecraft.wiki/w/Model

### 1.2 blockstate 如何挂模型

- `variants`：每个 state 配一个模型，可用 `x/y/z` 旋转、`uvlock`、`weight`。
- `multipart`：按连接状态组合多个模型（如栅栏/墙）。
- 来源：Minecraft Wiki `Tutorial:Models`（访问 2026-09-05）。

本地对应：
- `builtin_models_fallback/acacia_door.blockstate.json` 是最简 `variants: {"": {"model": "minecraft:block/acacia_door"}}`。
- `example_resourcepack_v3/assets/demo/blockstates/*.json` 是生成器输出的自测 blockstate。
- 路径：`/tmp/mc-mod-art-studio-core/builtin_models_fallback/`、`/tmp/mc-mod-art-studio-core/example_resourcepack_v3/`（访问 2026-09-05）。

**采用**：以原版 blockstate 文件为模板，只改写 `model` 引用；这是当前 `package_asset.py` 已走的路，方向正确。

### 1.3 model 根字段

- `parent`：加载另一模型；子模型的 `elements` 会覆盖父模型。
- `textures`：定义纹理变量，`#name` 引用，`particle` 是破坏粒子/水中覆盖纹理。
- `elements`：只有立方体；每个 element 含 `from/to`、`rotation`、`faces`。
- 每个 face 含 `uv`（`[x1,y1,x2,y2]`，相对 16 的“百分比”坐标）、`texture`（`#变量`）、`cullface`、`rotation`、`tintindex`。
- 来源：Minecraft Wiki `Model`（访问 2026-09-05）、Minecraft Wiki `Tutorial:Models`（访问 2026-09-05）、Fabric Docs `Block Models`（访问 2026-09-05）：https://docs.fabricmc.net/develop/blocks/block-models

### 1.4 常见原版父模型与纹理变量

| 父模型 | 纹理变量 | 用途 / 多面映射 |
|---|---|---|
| `minecraft:block/cube` | `#down #up #north #south #west #east` | 六面独立变量；`cube.json` 是基础立方体，见 Wiki 示例 |
| `minecraft:block/cube_all` | `#all`（通常另含 `#particle`） | 六个面共用同一张纹理 |
| `minecraft:block/cube_bottom_top` | `#bottom #top #side` | 顶/底各一张，四个侧面共用 `#side`；适合 grass block、砂岩 |
| `minecraft:block/cube_column` | `#end #side` | 顶/底用 `#end`，侧面用 `#side`；适合原木 |
| `minecraft:block/cross` | `#cross` | 两个 45° 相交平面，植物类 |

- 来源（`cube.json` 明确列出 `#down/#up/#north/#south/#west/#east`）：Minecraft Wiki `Tutorial:Models`（访问 2026-09-05）。
- 来源（`cube_all`、`cube_column`、`cube_bottom_top` 示例）：Fabric Docs `Block Model Generation`（访问 2026-09-05）：https://docs.fabricmc.net/develop/data-generation/block-models

### 1.5 多面纹理如何拼成完整方块

原版有两种主流做法：

1. **每面一个 PNG**（当前 `block_multi` 采用）
   - 生成 `<name>_top.png`、`<name>_side.png`、`<name>_bottom.png`。
   - 模型用 `cube_bottom_top`，四个侧面都引用 `#side`，保证侧边连续；顶面单独 `#top`、底面单独 `#bottom`。
   - 取/决定：**采用**，最符合 LLM 逐面生成。

2. **一个图集 PNG + UV 子区域**
   - `uv` 以“16 的百分比”描述，`[0,0,16,8]`=上半、`[0,8,16,16]`=下半；不随 PNG 尺寸变化。
   - Wiki 用 fletching table / bone block / barrel 示例解释“一张贴图放多个面，用 UV 切开”。
   - 来源：Minecraft Wiki `Tutorial:Models`（访问 2026-09-05）。
   - 取/决定：**作为备选采用**，适合减少 LLM 输出文件数，但需要严格 UV 校验。

### 1.6 边连续 / cullface

- 同一块方块的相邻面在同一个完整方块内，`cullface` 可隐藏被相邻方块遮住的面，减少面数并保证光照正确。
- 四个侧面都用同一个 `#side` 纹理变量时，纹理的左右边在相邻侧面之间自然连续；顶/底与侧边的交界需要 UV 裁剪/作者手工对齐（原版 grass_block/砂岩即如此）。
- 来源：Minecraft Wiki `Tutorial:Models`、`Model`（访问 2026-09-05）。

### 1.7 本地现状与关键 gap（本地代码阅读）

- `package_asset.py::build_model_json` 对 `block_multi` 输出：
  ```json
  {
    "parent": "minecraft:block/cube",
    "textures": {
      "particle": "<ns>:block/<name>_side",
      "top": "<ns>:block/<name>_top",
      "bottom": "<ns>:block/<name>_bottom",
      "side": "<ns>:block/<name>_side"
    }
  }
  ```
- **问题**：原版 `cube` 父模型期望 `#down/#up/#north/#south/#west/#east`，不是 `#top/#bottom/#side`。因此当前 `block_multi` 模型很可能不能正确渲染到四面。
- **建议**：改成 `"parent": "minecraft:block/cube_bottom_top"`，或直接写显式 `elements/faces/uv`（如 `example_resourcepack_v3/assets/demo/models/block/custom_user_model.json` 已实现）。
- 本地路径：`/tmp/mc-mod-art-studio-core/package_asset.py`（访问 2026-09-05）。
- 取/决定：**拒绝当前 cube+top/bottom/side 组合，改为 cube_bottom_top。**

---

## 2. 原版实体 UV / 模型

### 2.1 Java Edition：实体纹理与模型的关系

- Java 原版实体模型（猪、苦力怕、玩家等）大多由 **硬编码渲染器** 定义，资源包一般只能覆盖 `assets/minecraft/textures/entity/...` 的 PNG；不能用普通 `assets/<ns>/models/entity/*.json` 直接替换原版实体模型。
- 来源：Minecraft Wiki `Model`（访问 2026-09-05）说明非硬编码模型仅用于方块/物品及少量实体；`Resource pack`（访问 2026-09-05）说明实体纹理位于 `assets/minecraft/textures/entity/`：https://minecraft.wiki/w/Resource_pack

### 2.2 玩家皮肤 64×32 / 64×64 布局

- 皮肤是贴在玩家模型上的纹理；现代格式 64×64（双层），旧/legacy 64×32；Bedrock 还支持 128×128。
- 外层（overlay/hat）比内层大 0.5px（身体/手臂/腿）或 1px（头）。
- 来源：Minecraft Wiki `Skin`（访问 2026-09-05）：https://minecraft.wiki/w/Skin

**64×64 标准坐标表**（来源：`github.com/mineatar-io/skin-render` README/`parts.go`，访问 2026-09-05）：https://pkg.go.dev/github.com/mineatar-io/skin-render

| 部件/面 | x1,y1 → x2,y2 |
|---|---|
| Head Top | 8,0 → 16,8 |
| Head Bottom | 16,0 → 24,8 |
| Head Right | 0,8 → 8,16 |
| Head Front | 8,8 → 16,16 |
| Head Left | 16,8 → 24,16 |
| Head Back | 24,8 → 32,16 |
| Right Leg Top/Bottom | 4,16→8,20 / 8,16→12,20 |
| Right Leg Right/Front/Left/Back | 0,20→4,32 / 4,20→8,32 / 8,20→12,32 / 12,20→16,32 |
| Torso Top/Bottom | 20,16→28,20 / 28,16→36,20 |
| Torso Right/Front/Left/Back | 16,20→20,32 / 20,20→28,32 / 28,20→32,32 / 32,20→40,32 |
| Right Arm Top/Bottom | 44,16→48,20 / 48,16→52,20 |
| Right Arm Right/Front/Left/Back | 40,20→44,32 / 44,20→48,32 / 48,20→52,32 / 52,20→56,32 |
| Left Leg Top/Bottom | 20,48→24,52 / 24,48→28,52 |
| Left Leg Right/Front/Left/Back | 16,52→20,64 / 20,52→24,64 / 24,52→28,64 / 28,52→32,64 |
| Left Arm Top/Bottom | 36,48→40,52 / 40,48→44,52 |
| Left Arm Right/Front/Left/Back | 32,52→36,64 / 36,52→40,64 / 40,52→44,64 / 44,52→48,64 |

- 第二层（overlay）坐标在库中也有完整映射（`HeadOverlay*`、`TorsoOverlay*`、`RightArmOverlay*` 等），同一源。
- 64×32 legacy 可理解为“只有内层、无 second layer”的 64×32 变体；Wiki 明确说 64×32 是 legacy texture（assumption：其布局使用同一上半区坐标，未在 Wiki 正文逐格列出）。

**对 mc-mod-art-studio 的含义**：让 LLM 输出“真正可用的玩家皮肤”，需要按上述坐标分区域生成；当前 `entity_uv` 提示词只要求“包含头/身体/腿/脚”，实测 pig raw_answer 是单个侧视图，未按皮肤图集布局展开（本地证据见下）。

### 2.3 原版生物实体 UV 不是统一皮肤布局

- 猪/苦力怕/村民等生物的贴图布局**随实体不同**，由各自硬编码模型或 Bedrock 几何体决定；玩家皮肤的坐标表不能直接套用到任意生物。
- 要精确生成某个生物的可用 UV，必须拿到该生物的 vanilla 贴图/模型作参考（例如 `pig.png` 的像素区域布局）。
- 本地 `mc_asset_library_full` 不存在，无法提供原版生物 layout；这是 **verified-gap**。

### 2.4 Bedrock：数据驱动几何体模型 JSON

- 实体模型文件为 `*.geo.json`，位于 `models/entity`。
- 格式：
  - `description.identifier`、`texture_width`、`texture_height`
  - `bones[]`：骨骼层级，`name`、`parent`（骨骼父级）、`pivot`、`rotation`、`cubes`
  - `cubes[]`：`origin`、`size`、`uv`（左上角坐标）、`inflate`、`mirror`；也可用 per-face `uv` 对象
- 纹理不直接写在 geometry 内，而是通过 render controller / client entity 绑定（Microsoft Learn 说明“Each model uses a texture that can be assigned through render controllers”）。
- 来源：Microsoft Learn `Entity Modeling and Animation`（访问 2026-09-05）：https://learn.microsoft.com/en-us/minecraft/creator/documents/entitymodelingandanimation?view=minecraft-bedrock-stable
- 来源：Bedrock Wiki `Player Geometry` 示例（访问 2026-09-05）：https://wiki.bedrock.dev/visuals/player-geometry
- 来源：Microsoft 官方 geometry schema（访问 2026-09-05）：https://raw.githubusercontent.com/MicrosoftDocs/minecraft-creator/main/creator/Reference/Content/SchemasReference/Schemas/minecraftSchema_geometry_1.16.0.md

**注意“parent”一词的版本差异**：
- Java 方块/物品 model：`parent` = 模型继承。
- Bedrock geometry：`parent` = 骨骼层级父节点。

### 2.5 Java 自定义实体模型（非原版资源包能力）

- 原版 Java 资源包无法直接替换实体模型；要自定义模型通常需要：
  - OptiFine CEM（资源包 + OptiFine 客户端），文档：https://optifine.readthedocs.io/cem.html 、https://optifine.readthedocs.io/cem_models.html （访问 2026-09-05）
  - 模组（JsonEM、CustomEntityModels、Entity Texture Features 等）的 JSON / renderer
- 取/决定：**不作为主线**；仅在“必须自定义实体模型”时提及，因为它们依赖第三方客户端/模组，不是纯原版资源包方案。

### 2.6 本地现状与关键 gap

- `package_asset.py` 对 `entity_uv` 只生成：
  - `assets/<modid>/textures/entity/<name>.png`
  - `assets/<modid>/textures/entity/<name>.note.txt`
  - 不生成 model / render controller / 实体绑定。
- 本地证据：`/tmp/mc-mod-art-studio-core/example_resourcepack_entity/manifest.json` 中 `"entity_uv_note": "需要实体模型适配；未生成 model。"`（访问 2026-09-05）。
- 实测 `tests/runs/v2/pig/raw_answer.txt`（访问 2026-09-05）表明 LLM 把 64×32 当作“一个侧视猪剪影”，不是按皮肤/生物 UV 图集布局逐面展开。
- 取/决定：
  - 若目标是**新实体贴图**：必须绑定到具体实体路径/模型，当前输出不满足。
  - 若目标是**替换原版某实体贴图**：应输出到 `assets/minecraft/textures/entity/<原版路径>/...`，并且仍要遵循该实体的原版 UV 布局。

---

## 3. 现有 “LLM/AI 生成 → 可用 Minecraft 资产” 方法

### 3.1 文生图 + 后处理打包（通用图 → 资源包）

| 工具/项目 | 方式 | 来源（访问 2026-09-05） | 采用/拒绝 |
|---|---|---|---|
| DWF967/AIPackGenerator | 用 Craiyon 对每个源纹理生成 AI 图，resize 后写 pack.mcmeta | https://github.com/DWF967/AIPackGenerator | **参考后处理/打包思路**；但它不理解 UV/模型，逐张替换会破坏多面/实体语义，拒绝直接采用 |
| media.io Minecraft Texture Generator | 文生图站点 | https://www.media.io/ai/zh/text-to-image/minecraft-texture-generator | **只作调研**：商业壁纸/文生图，无法保证像素级/原版 UV；拒绝作为核心 |
| Orca Minecraft Resource Pack Maker | 描述风格→AI 绘制纹理、建模型、生成 pack.mcmeta 和 zip | https://orcaclient.com/minecraft-resource-pack-maker | **认同“生成后打包为可用资源包”的目标**；封闭平台，不能直接集成，可借鉴流程 |
| Pixel GPT (Spigot) | Minecraft Item Texture Generator 插件 | https://www.spigotmc.org/resources/pixel-gpt-item-texture-generator.109705/ | **只作调研**；插件/商业形态，未开放可复现管线，拒绝作为核心 |

### 3.2 Minecraft 特化 diffusion / LoRA（更接近“原版风格”）

| 项目/论文 | 方式 | 来源（访问 2026-09-05） | 采用/拒绝 |
|---|---|---|---|
| BLOCK: Bi-Stage MLLM Character-to-Skin Pipeline | MLLM 生成 3D 预览 → 微调 FLUX.2 解码为皮肤 atlas；EvolveLoRA 渐进课程 | https://arxiv.org/abs/2603.03964 | **高度相关**：证明“先生成预览再解码成 Minecraft UV atlas”可行；但依赖较重（FLUX 微调），可作为后续方向，不适合当前纯文本低资源主线 |
| Stable Diffusion Finetuned Minecraft Skin Generator | 文本→64×64 皮肤；HuggingFace monadical-labs/minecraft-skin-generator | https://github.com/Kreaking/Stable_Diffusion_Finetuned_Minecraft_Skin_Generator | **参考**：与 BLOCK 同属“Minecraft skin 特化生成”；依赖扩散模型/GPU，当前纯文本管线不采用 |
| portkit #996 / PR #1317（Diffusion LoRA for Minecraft Texture Pair Conversion） | FLUX/SD + LoRA 处理 Java↔Bedrock 纹理转换、低分辨率像素 16–64px、SSIM/LPIPS 门槛 | https://github.com/anchapin/portkit/issues/996 https://github.com/anchapin/portkit/pull/1317 | **可作落地参考**：明确低分辨率/风格一致性/质量门槛；目前是 issue/PR 阶段，未作为已验证生产方案 |
| terrain-diffusion-mc | Fabric mod 集成 Terrain Diffusion（SIGGRAPH 2026）生成地形/世界 | https://github.com/xandergos/terrain-diffusion-mc | **拒绝**：目标是地形而非方块/物品贴图或实体资产；仅供“Minecraft 特化 AI 生成”佐证 |

### 3.3 Seamless tile / outpainting / 程序化纹理

| 工具 | 方式 | 来源（访问 2026-09-05） | 采用/拒绝 |
|---|---|---|---|
| image-extender | AI outpainting + Poisson-blended seams + Tile Studio（13-tile autotile 一套） | https://github.com/boona13/image-extender | **强烈相关**：侧边纹理需要 seamless、相邻纹理需要 tile 一致性；可借鉴 Tile Studio 的“一次生成 autotile 集 + 角落修复”，但输出不是 Minecraft model |
| TileMaker / AI seamless tiles | 文本→无缝 tile/壁纸（商业/社区） | https://ai-prompts.online/threads/bricks-tilemaker-generatsiya-besshovnykh-tailov-i-oboyev-iz-teksta-na-baze-ii.4242/ | **作方法论参考**：seamless 是关键；来源非一手开发仓库，可信度中等 |
| Texture_Synthesis | 基于已有资源包图集生成新纹理，支持 mod/resourcepack 转换 | https://github.com/Shoeboxam/Texture_Synthesis | **程序化纹理合成参考**；不是 LLM，可用于“补全缺失纹理/风格统一” |
| DynamicAssetGenerator | 运行时/资源包驱动的纹理与资产生成（Minecraft mod） | https://github.com/lukebemishprojects/DynamicAssetGenerator | **程序化运行时生成参考**；需要 mod 环境，可作为后续“动态生成”方向 |

### 3.4 模型生成（Blockbench / JSON）

| 项目 | 方式 | 来源（访问 2026-09-05） | 采用/拒绝 |
|---|---|---|---|
| img2blockbench | 参考图→Blockbench `.bbmodel`（3 条路线：mesh-guided / direct / img2threejs） | https://github.com/orca-gamedev/img2blockbench | **高相关**：把“图→Minecraft 原生模型”当成可编译问题；可研究其确定性编译阶段，但当前目标是非代码调研，不即时集成 |
| bbmodel-ai-generator | 自然语言→bbmodel（模型+动画+纹理），商业/社区平台 | https://github.com/YaUhYeah/bbmodel-ai-generator | **参考**：证明“描述→bbmodel”方向存在；缺少可复现的 Minecraft JSON 输出契约 |
| texlab | MCP 集成的 Minecraft 资源包像素编辑/生成 | https://github.com/payangar-dev/texlab | **相关**：让 LLM 通过 MCP 工具编辑资源包；可借鉴“编辑器+LLM”交互，但当前项目是纯文本生成，不需要外部编辑器 |
| Blockbench MCP 插件 | MCP 操作 Blockbench | https://glama.ai/mcp/servers/sosadly/blockbench-mcp | **参考**：未来可做“LLM 直接生成/修 .bbmodel”的桥接；当前不采用 |
| Jhon-crypt/minecraft-ai | 声称 PyTorch GAN 纹理 + Transformer 模型 JSON | https://github.com/Jhon-crypt/minecraft-ai | **低可信度**：README 很粗，未见可复现资产/评测；拒绝作为依据 |

### 3.5 程序化 / datagen（不依赖 AI 也能生成资产）

- Fabric `BlockModelGenerators`：`createTrivialCube` → `cube_all`；`createTrivialBlock(... COLUMN_ALT)` → `cube_column`；`TexturedModel` 映射纹理槽。这是**原版生成器使用的“正确模板”来源**。
- 来源：Fabric Docs `Block Model Generation`（访问 2026-09-05）：https://docs.fabricmc.net/develop/data-generation/block-models
- 取/决定：**采用**：以 Fabric 的 `TextureSlot` / `TexturedModel` 为“哪些父模型该配哪些变量”的事实清单。

---

## 4. 完整美术资源从哪里来

- 本地 `mc_asset_library_full` 不存在（`/tmp/mc-mod-art-studio-core/mc_asset_library_full` 缺失，访问 2026-09-05）。
- `builtin_models_fallback` 只有极简几何占位（多为 `parent: cube` + `#top/#bottom/#side/#particle`），不是原版真实模型。
- 建议资源来源：
  - Mojang `client.jar` / asset object store 提取（Minecraft Wiki `Resource pack` 提到默认资源包来自 assets 目录与 asset object store，访问 2026-09-05）。
  - 公开 vanilla assets 镜像：`InventivetalentDev/minecraft-assets`（列为公开镜像）：https://github.com/InventivetalentDev/minecraft-assets
  - 现有项目可用该镜像的 `assets/minecraft/models/block/`、`blockstates/`、`textures/entity/` 做参考，而不是 hardcode 模板。
- 取/决定：**采用**：补一个“原版参考资产”目录，优先使用官方/公开镜像的 1.18.2 原版 JSON + PNG；本地 fallback 只用于离线自测。

---

## 5. 针对 mc-mod-art-studio 的采用/拒绝清单

| 项目 | 决策 | 理由 |
|---|---|---|
| `cube_all` / `cube_bottom_top` / `cube_column` / `cross` 等原版父模型 | 采用 | 最稳妥的“方块多面”契约；`block_multi` 应改用 `cube_bottom_top` |
| 显式 `elements/faces/uv` 的自定义 model | 采用 | 与 `custom_user_model.json` 一致；适合异形/复杂方块 |
| 每面一个 PNG（top/side/bottom） | 采用 | LLM 可逐面生成，调试容易 |
| 一个图集 + UV 子区域 | 备选 | 减少文件数，但需校验 UV 边界；适合成熟后优化 |
| 当前 `entity_uv` 只出 PNG + note | 拒绝 | 不是“可用实体资产”；需绑定到原版实体路径、Bedrock geometry 或 OptiFine CEM |
| 玩家皮肤标准 64×64 坐标 | 采用 | 若做玩家皮肤/生物 humanoid，按 `skin-render` 坐标分区域生成 |
| 原生生物专属 UV 布局 | 采用（需先有参考） | 必须从 vanilla 资产中提取每个生物的 atlas 布局 |
| 通用文生图 → resize → 资源包 | 拒绝作为核心 | 无法保证 UV/模型语义；最多作为贴图风格辅助 |
| Minecraft 特化 diffusion/LoRA（BLOCK、skin generator、portkit） | 远期参考 | 质量/一致性更好，但重，当前轻量纯文本管线不采用 |
| seamless tile / outpainting | 采用思路 | 方块侧边纹理需要 seamless；可先做“16×16 像素纹理无缝校验/修复”，再考虑 AI outpainting |
| Blockbench 模型生成 | 远期参考 | 可生成 `.bbmodel`，但需额外导出步骤；当前手工 JSON 模板更可控 |
| 程序化 datagen / 运行时生成 | 参考 | 适合大规模模板化；不是 LLM 主线 |

---

## 6. 风险与未决问题

1. **未验证**：原版 `cube_bottom_top`/`cube_column`/`cube_all` 的精确 JSON 内容来自公开镜像/文档；本地没有完整库，建议后续抓取镜像逐一确认。
2. **实体绑定**：Java 原版实体模型硬编码，项目需要明确“替换原版贴图”还是“新增自定义实体/模组”。当前未实现。
3. **低分辨率 AI 生成**：多数 diffusion 在 16×16/64×64 上效果差，需后处理（像素化、调色板量化、轮廓修正）。
4. **风格一致性**：一套资源包的所有纹理需统一，AI 单张生成容易漂移；`image-extender` 的 Palette/art director QA 循环可借鉴。
5. **来源可信度**：部分 GitHub 项目（Jhon-crypt/minecraft-ai）README 可信度低；本报告对高相关、有论文/PR/镜像者优先。

---

## 7. Reference List（访问日期均为 2026-09-05）

- Minecraft Wiki Model: https://minecraft.wiki/w/Model
- Minecraft Wiki Tutorial:Models: https://minecraft.wiki/w/Tutorial:Models
- Minecraft Wiki Skin: https://minecraft.wiki/w/Skin
- Minecraft Wiki Resource pack: https://minecraft.wiki/w/Resource_pack
- Fabric Docs Block Models: https://docs.fabricmc.net/develop/blocks/block-models
- Fabric Docs Block Model Generation: https://docs.fabricmc.net/develop/data-generation/block-models
- skin-render (64×64 skin coordinates): https://pkg.go.dev/github.com/mineatar-io/skin-render
- Microsoft Learn Entity Modeling and Animation: https://learn.microsoft.com/en-us/minecraft/creator/documents/entitymodelingandanimation?view=minecraft-bedrock-stable
- Bedrock Wiki Player Geometry: https://wiki.bedrock.dev/visuals/player-geometry
- Microsoft geometry schema reference: https://raw.githubusercontent.com/MicrosoftDocs/minecraft-creator/main/creator/Reference/Content/SchemasReference/Schemas/minecraftSchema_geometry_1.16.0.md
- DWF967/AIPackGenerator: https://github.com/DWF967/AIPackGenerator
- media.io Minecraft Texture Generator: https://www.media.io/ai/zh/text-to-image/minecraft-texture-generator
- Orca Minecraft Resource Pack Maker: https://orcaclient.com/minecraft-resource-pack-maker
- Pixel GPT: https://www.spigotmc.org/resources/pixel-gpt-item-texture-generator.109705/
- BLOCK arXiv: https://arxiv.org/abs/2603.03964
- Stable Diffusion Minecraft Skin Generator: https://github.com/Kreaking/Stable_Diffusion_Finetuned_Minecraft_Skin_Generator
- portkit issue/PR: https://github.com/anchapin/portkit/issues/996 , https://github.com/anchapin/portkit/pull/1317
- terrain-diffusion-mc: https://github.com/xandergos/terrain-diffusion-mc
- image-extender: https://github.com/boona13/image-extender
- TileMaker thread: https://ai-prompts.online/threads/bricks-tilemaker-generatsiya-besshovnykh-tailov-i-oboyev-iz-teksta-na-baze-ii.4242/
- Texture_Synthesis: https://github.com/Shoeboxam/Texture_Synthesis
- DynamicAssetGenerator: https://github.com/lukebemishprojects/DynamicAssetGenerator
- img2blockbench: https://github.com/orca-gamedev/img2blockbench
- bbmodel-ai-generator: https://github.com/YaUhYeah/bbmodel-ai-generator
- texlab: https://github.com/payangar-dev/texlab
- Blockbench MCP: https://glama.ai/mcp/servers/sosadly/blockbench-mcp
- Jhon-crypt/minecraft-ai: https://github.com/Jhon-crypt/minecraft-ai
- InventivetalentDev/minecraft-assets: https://github.com/InventivetalentDev/minecraft-assets
- OptiFine CEM docs: https://optifine.readthedocs.io/cem.html , https://optifine.readthedocs.io/cem_models.html
