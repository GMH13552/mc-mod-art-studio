# rebuild-demo：s3 重做 4 个演示（s2 silhouette bank + 可大改）

本目录重做 4 个演示，解决形状借鉴问题：

- **恶魔牛**：`entity_uv` 64x32（cow/red_mooshroom 实体模板），不是 16x16 牛头图标。
- **骷髅法杖**：骷髅头可辨（眼窝/颌），杖柄有手柄味（允许斜/粗/可大改）。
- **剥皮小刀**：短小、像刀，不是长剑/锯。
- **村民皮**：皮/兔皮轮廓（不规则、毛边），不是普通棕色方块。

所有 prompt 都由 s2 机制注入 `silhouette_candidates`：每个部件 2-4 个轮廓基础，
并带指令「可选一个 / 可组合多个 / 可大改形状 / 禁止当最终网格」。

| 资产 | form | PNG | 轮廓基础摘要 |
|---|---|---|---|
| 恶魔牛 (Demon Cow entity_uv) | `entity_uv` | `demon_cow/sprite.png` | cow.png / red_mooshroom.png / brown_mooshroom.png / soul_fire_0/1.png |
| 骷髅法杖 (Skeleton Staff) | `item` | `skeleton_staff/sprite.png` | skeleton.png (head) / bone_block_side.png / stick.png / oak_planks.png / iron_sword.png |
| 剥皮小刀 (Skinning Knife) | `item` | `skinning_knife/sprite.png` | iron_sword.png / stone_sword.png / wooden_sword.png / shears.png / leather.png / stick.png / oak_planks.png |
| 村民皮 (Villager Hide) | `item` | `villager_hide/sprite.png` | leather.png / rabbit_hide.png / villager.png / stick.png / oak_planks.png / bone_block_side.png |

## 生成方式说明（诚实记录）

- `skeleton_staff` 和 `skinning_knife`：最终 PNG 由 `deepseek-chat` 文本 LLM 根据 prompt 生成；
  prompt 包含 silhouette bank，且外部脚本 `rebuild_generate.py` 可复现。
- `demon_cow` 和 `villager_hide`：同样生成了带 silhouette bank 的 prompt，但文本 LLM
  在 64x32 全 atlas / 不规则皮张轮廓上的输出不稳定（全图单色 / 空图 / 椭圆）。
  这两个 demo 最终使用**原版模板轮廓 + 新调色板程序化重着色**：
  - `demon_cow`：以 `cow.png` 的 64x32 实体轮廓/区域为底，重新映射为恶魔红/黑角/青色魂火眼；
  - `villager_hide`：以 `rabbit_hide.png` 的不规则皮张轮廓为底，重新映射为皮革棕 + 灰褐织物内衬。
- 两者都没有把原版 PNG 复制进本仓库；输出 PNG 均为新配色/新图案结果。

## 像素/UV 自检

| 资产 | 检查命令 | 结论 |
|---|---|---|
| 恶魔牛 | `check_entity_uv.py sprite.png --entity cow` | PASS（左右 1px 边距；顶/底为说明项） |
| 骷髅法杖 | `check_pixel_asset.py sprite.png` | PASS |
| 剥皮小刀 | `check_pixel_asset.py sprite.png` | PASS |
| 村民皮 | `check_pixel_asset.py sprite.png` | PASS |

## 复现命令

```bash
# 1) 生成带 s2 silhouette bank 的 prompt（可选：直接跑全部会调用 LLM）
set -a; source /tmp/mc_llm.env; set +a
python3 examples/rebuild-demo/rebuild_generate.py --prompt-only

# 2) 用文本 LLM 生成 item/骷髅/小刀（demon_cow/villager_hide 见程序化 fallback）
python3 examples/rebuild-demo/rebuild_generate.py --only skeleton_staff --only skinning_knife

# 3) 程序化模板改（demon_cow / villager_hide）
python3 examples/rebuild-demo/build_programmatic_demos.py

# 4) 更新 fallback 资产的 README/hash
python3 examples/rebuild-demo/update_programmatic_meta.py
```

## 来源说明

- 原版参考均来自本机 full 库：`/mnt/c/Users/GMH13/Documents/deepseek_harness_workspace/mc_asset_library_full/`。
- 原版 PNG 未入库；每个资产目录的 `README.md` 记录部件 → 原版资产 → 借 texture/palette/structure
  → 轮廓基础来源 → 改了什么，以及 `prompt_pack.json` 中的 silhouette bank。
