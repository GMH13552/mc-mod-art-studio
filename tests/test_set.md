# 非自证广谱测试集（t1-testset）

> 目的：给 mc-mod-art-studio-core 的生成/打包流程提供一组**不是项目自己生成的**、也不是本轮任务示例清单的常见 Minecraft 资产名。测试集只负责定义“测什么”和“为什么非自证”，不负责实际运行（实际运行由 t4 执行）。

## 0. 定义与排除基线

- **自证（self-certifying）**：项目仓库内已有的生成产物，或直接拿项目自身的 concept/prompt/raw 作为“正确答案”来验证。
- **本测试集排除的自证来源**：
  - `examples/alien_crystal_wand/`（异形水晶法杖）
  - `examples/mushroom_sprout/`（蘑菇幼苗）
  - `examples/mushroom_glowstone/`（蘑菇萤石）
  - `concept_examples/mushroom_anvil.json`（蘑菇铁砧）
  - `concept_examples/mushroom_sapling.json`（蘑菇树苗）
- **本轮任务点名示例**（不选入本集合，避免“用户点名即自证”争议）：石剑、铁镐、火把、橡木门、花盆、草、村民头、岩浆膏、末影珍珠、下界砖块。
- 所有条目均来自 Minecraft 官方 Wiki（minecraft.wiki）可检索到的常见资产，且**不在上述排除清单内**。

## 1. 测试集总览

覆盖类别：`item`、`block_multi`、`cross`、`entity_uv`、`block_custom`（`block_custom` 为扩展/单独的打包协议，详见 `tests/README.md`）。

| ID | 中文名 | 英文名 | Pipeline form | Minecraft 类别 | 来源（访问日期 2026-09-05） | 为什么不是自证 |
|---|---|---|---|---|---|---|
| t01 | 钻石剑 | Diamond Sword | item | item | [minecraft.wiki/w/Diamond_Sword](https://minecraft.wiki/w/Diamond_Sword) | 项目 examples 中没有钻石剑；不在本轮点名清单；是 Minecraft 常见武器/工具类 item |
| t02 | 金苹果 | Golden Apple | item | item | [minecraft.wiki/w/Golden_Apple](https://minecraft.wiki/w/Golden_Apple) | 项目 examples/concept_examples 中没有金苹果；属于常见食物/消耗品 item |
| t03 | 弓 | Bow | item | item | [minecraft.wiki/w/Bow](https://minecraft.wiki/w/Bow) | 项目 examples/concept_examples 中没有弓；是常见远程武器 item |
| t04 | 荧石 | Glowstone | block_multi | block | [minecraft.wiki/w/Glowstone](https://minecraft.wiki/w/Glowstone) | 项目 examples 只有“蘑菇萤石”这一自创组合物，没有原版荧石方块；不在点名清单 |
| t05 | 红砖 | Bricks | block_multi | block | [minecraft.wiki/w/Bricks](https://minecraft.wiki/w/Bricks) | 项目 examples 中无红砖；常见建材，适合多面纹理 |
| t06 | 青金石块 | Block of Lapis Lazuli | block_multi | block | [minecraft.wiki/w/Lapis_Block](https://minecraft.wiki/w/Lapis_Block) | 项目 examples 中无青金石块；常见矿石块，测试矿石类纹理 |
| t07 | 虞美人（罂粟花） | Poppy | cross | block（植物） | [minecraft.wiki/w/Poppy](https://minecraft.wiki/w/Poppy) | 项目 examples 只有蘑菇幼苗 cross；没有罂粟花/虞美人；常见花园植物 |
| t08 | 橡树树苗 | Oak Sapling | cross | block（植物） | [minecraft.wiki/w/Oak_Sapling](https://minecraft.wiki/w/Oak_Sapling) | 项目 concept_examples 有“蘑菇树苗”，但那是自创蘑菇，不是原版橡树树苗；cross 形式需独立验证 |
| t09 | 猪 | Pig | entity_uv | entity | [minecraft.wiki/w/Pig](https://minecraft.wiki/w/Pig) | 项目 examples 中没有实体 UV；猪是最常见的原版被动实体，适合做 64x32 实体 UV 测试 |
| t10 | 苦力怕 | Creeper | entity_uv | entity | [minecraft.wiki/w/Creeper](https://minecraft.wiki/w/Creeper) | 项目 examples 中没有实体 UV；苦力怕是最具辨识度的原版怪物，适合测试 UV 纹理辨识度 |
| t11 | 箱子 | Chest | block_custom（chest template） | block | [minecraft.wiki/w/Chest](https://minecraft.wiki/w/Chest) | 项目 examples 中没有箱子；“chest”是 `package_asset.py` 内置模板，且不是自造概念 |
| t12 | 石砖楼梯 | Stone Brick Stairs | block_custom（stairs template） | block | [minecraft.wiki/w/Stone_Brick_Stairs](https://minecraft.wiki/w/Stone_Brick_Stairs) | 项目 examples 中没有；楼梯是 Minecraft 常见建筑方块，适合验证 block_custom 多模型打包 |

> 注：`block_custom` 目前是 `concept_grounder.py`/`package_asset.py` 支持的扩展形式；`run_pipeline --form` 尚未暴露 `block_custom`（见 `tests/README.md`）。测试集先把它列为覆盖项，运行协议中单独标注。
>
> **t11/t12 的未实现 gap（2026-09-05 实测）**：本仓库无 `mc_asset_library/library-index.json` 时，`retrieve_assets.py` 普通模式不会自动使用合成索引，会报 `no built-in index found`；因此“先生成 retrieval JSON → concept_grounder → raw → package”的一键链路不可复现。t11/t12 当前只验证 `package_asset.py --template chest|stairs` 的模板打包，不验证 LLM 生成；详见 `tests/README.md` §5。

## 2. 每个条目应验证的关注点

| ID | form | 重点关注 |
|---|---|---|
| t01 | item | 剑的斜向剪影、剑刃高光/暗部、剑柄细节、16x16 单面透明度 |
| t02 | item | 圆形/球状主体、高光斑点、金/红配色、方形小图标可辨性 |
| t03 | item | 弓的弯月形剪影、弓臂/弦边界、木纹与弦线对比 |
| t04 | block_multi | 顶/侧/底三面一致性、发光颗粒分布、方块边缘描边 |
| t05 | block_multi | 砖块 3 面图案、灰红砖缝节奏、无空洞/无全透明 |
| t06 | block_multi | 矿石块三面纹理、青金石深蓝+金色颗粒、剪影为完整方块 |
| t07 | cross | 透明背景、花头/茎叶剪影、cross 模型中心不偏 |
| t08 | cross | 树苗剪影、叶片与主干结构、cross 中心稳定 |
| t09 | entity_uv | 64x32 或 64x64 UV 尺寸、猪头/身体/腿基础色区分、非空图 |
| t10 | entity_uv | 苦力怕标志性绿/灰方格感、面部特征、UV 尺寸合法 |
| t11 | block_custom | chest 模板的纹理 key 完整、`package_asset --template chest` 打包通过 |
| t12 | block_custom | stairs 模板的 straight/inner/outer 三个模型、各面纹理打包通过 |

## 3. 来源与证据

- 一手来源：Minecraft Wiki（官方 Wiki，community-maintained but primary for names/classification）。
- 本地代码证据（用于确认 pipeline form 支持）：`run_pipeline.py --help`、`build_style_prompt.py` 的 `_VALID_FORMS`、`package_asset.py` 的 `BUILTIN_BLOCK_TEMPLATES`、`concept_grounder.py` 的 `_VALID_FORMS`。
- 访问日期：2026-09-05（UTC）。
- 不确定性/假设：
  - “这些资产在 Minecraft 中常见”为依据 wiki 页面存在与游戏内常用性判断，属于 `assumption`，非绝对统计结论。
  - `block_custom` 的完整生成链路（retrieval → concept → raw → package）当前代码/仓库条件下不可一键复现；这是 `verified-gap`，不是本测试集的断言。t11/t12 仅把 `package_asset --template` 打包作为可复现验证项。
