# novel-demo：原版没有的新资产（部件级参考）

本目录生成 4 个 Minecraft 原版没有的新资产演示。
所有资产都使用“部件级参考映射”：每个部件只从指定原版资产借配色/材质/结构/明暗语法，
不把任何一件原版资产当作整件答案。生成的 PNG 均为新资产，原版 PNG 未复制进本仓库。

| 资产 | form | PNG | 参考摘要 |
|---|---|---|---|
| 村民皮 (Villager Hide) | `item` | `villager_hide/sprite.png` | leather.png；villager.png；stick.png / iron_sword.png |
| 剥皮小刀 (Skinning Knife) | `item` | `skinning_knife/sprite.png` | iron_sword.png；iron_sword.png / leather.png；leather.png + stick.png / oak_planks.png |
| 骷髅法杖 (Skeleton Staff) | `item` | `skeleton_staff/sprite.png` | skeleton.png (head region) + bone_block_side.png；bone_block_side.png / stick.png；stick.png / oak_planks.png |
| 恶魔牛 (Demon Cow) | `item` | `demon_cow/sprite.png` | cow.png / red_mooshroom.png；cow.png / red_mooshroom.png；red_mooshroom.png + soul_fire_0.png |

## 防复制说明
- 生成 prompt 不包含任何原版 compact 索引网格，仅含文字化源表、配色、部件结构和通用像素规则。
- 每个部件参考卡包含三样：`borrowed_texture` / `borrowed_palette` / `borrowed_structure`；配色严格按部件拆分，不作为整图全局调色板。
- novelty 固定 0.75；生成后会做轻量“原版索引网格相似度”检测（同尺寸逐格比对；大图用滑动窗口/最近邻缩放取最高分），超过阈值自动重试并记录在 `hashes.json` 的 `index_similarity`，脚本最多重试 2 次。
- 原版参考 hash 在每个资产 README.md 中记录（full-index.json md5）。

## 来源说明
- 参考来源使用本机 `mc_asset_library_full/full-index.json`（1.18.2 Java 完整纹理库）的 md5。
- `skeleton.png`/`villager.png` 在 115 小库内；`leather.png`、`soul_fire_0/1.png`、`bone_block_side.png` 等不在 115 小库内，已从 full 库检索补充并记录来源。
- 原版 PNG 不复制进本仓库，README/JSON 只记录路径与 md5。

## 复现命令
```bash
set -a; source /tmp/mc_llm.env; set +a
python3 examples/novel-demo/demo_generate.py
```

## 像素自检（check_pixel_asset.py）

| 资产 | 结论 | 说明 |
|---|---|---|
| 村民皮 (Villager Hide) | `FAIL` | 调色板缺少亮色档（bright_count=0）。 |
| 剥皮小刀 (Skinning Knife) | `PASS` |  |
| 骷髅法杖 (Skeleton Staff) | `PASS` |  |
| 恶魔牛 (Demon Cow) | `PASS` |  |

## 结果
- 村民皮 (Villager Hide): `examples/novel-demo/villager_hide/sprite.png` （prompt 391e39c2dc1a0bbf58bbd8c2cbf5f5dc2a323c966f3a6ff38a004ce283503d18，answer 127c9ccb238bd8ddfa5b9e891999ddc41442405a78f07c8a5fc788028818e14d，attempts 1，最高索引相似度 0.515625/villager.png）
- 剥皮小刀 (Skinning Knife): `examples/novel-demo/skinning_knife/sprite.png` （prompt 12062c8269ba8dcd6fd121cf233230ba1f966dafee3a0f637938479db69b9720，answer 389f3ecbb9941967edb660ed86376a8536aa1908ce63340ab78e1c3a7a367813，attempts 1，最高索引相似度 0.5625/stick.png）
- 骷髅法杖 (Skeleton Staff): `examples/novel-demo/skeleton_staff/sprite.png` （prompt 0866cb630444c131f0c7798d5dd21d10e889f6f9a48cef2f144698909682cfd2，answer dd6328fd8bed4407d4717eebe9d8ee2e132159d42ea9b08914c7357bccb06d7f，attempts 1，最高索引相似度 0.710938/skeleton.png）
- 恶魔牛 (Demon Cow): `examples/novel-demo/demon_cow/sprite.png` （prompt 494e66dac45216c132a60fa1b6ef2619db41c48789ab100ad1b9c1a4e465fc47，answer 79bf3f68c81b057ba8748499e4286965a13f2b22c14a7f63030f2dfbd6efc685，attempts 2，最高索引相似度 0.382812/soul_fire_0.png）

