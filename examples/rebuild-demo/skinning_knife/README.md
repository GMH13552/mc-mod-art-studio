# 剥皮小刀 (Skinning Knife)

- 形式：`item`
- 尺寸：`16x16`
- 输出：`sprite.png`
- novelty：`0.9`（s2 silhouette bank；可大改）

## 说明
一把短柄剥皮/狩猎小刀：刀身短小、刀尖略微上翘，护手短窄，刀柄用皮革缠绕并露出木质芯；整体明显是一把小刀，不是长剑/大剑。硬性：必须包含完整刀柄（4-6px）；刀尖到柄尾整体至少 10px 高/长；刀刃短但可辨。

## 部件 → 原版参考 → 轮廓基础 → 改了什么

| 部件 | 参考原版资产 | 借用 texture/palette/structure | 轮廓基础来源 | 改了什么 |
|---|---|---|---|---|
| 刀刃 blade | iron_sword.png / stone_sword.png / shears.png | 金属划痕、刃口高光、冷灰明暗 | 候选：curved-blade（铁剑/石剑刃口微弧）、straight-tip（shears 直背短刃）、hook-tip（shears 上翘短刃） | 只取短刃轮廓基础，明确缩小刀身；可大改刀刃弧度/上翘程度。 |
| 护手/颈 guard | iron_sword.png / leather.png | 深灰/深褐自然分隔 | 刀刃与刀柄之间的 1-2px 横向窄条 | 短窄护手，不照抄剑护手。 |
| 刀柄 handle | leather.png / stick.png / oak_planks.png | 皮革缠绳 + 木芯颗粒 | 1-2px 宽短柄、缠绳横向、木纹纵向 | 可加粗到 2-3px 并加尾部，保留手柄手感。 |

## 轮廓候选（silhouette_candidates 菜单，不是锁）

> 以下候选由 `reference_analyzer.build_silhouette_bank` 从所选原版 assets 生成；
> prompt 中明确：可选一个/可组合/可大改/禁止当最终网格。

### 刀刃 blade
- 候选 `iron-sword-blade`（来源：`iron_sword.png`）来源：iron_sword.png 刃部轮廓
- 候选 `stone-sword-blade`（来源：`stone_sword.png`）来源：stone_sword.png 刃部轮廓
- 候选 `wooden-sword-blade`（来源：`wooden_sword.png`）来源：wooden_sword.png 刃部轮廓
- 候选 `compact:iron_sword.png`（来源：`iron_sword.png`）只含 X/. 剪影；iron_sword.png 区域/整体轮廓
  ```
.............XXX
............XXXX
..........XXXXX.
.........XXXXX..
........XXXXX...
..XXX.XXXXX.....
...XXXXXXX......
....XXXX........
...XXXXXX.......
..XXX.XXXX......
XXX.............
XXX.............
  ```

### 护手/颈 guard
- 候选 `iron-sword-shape`（来源：`iron_sword.png`）来源：iron_sword.png 整体/部件轮廓
- 候选 `stone-sword-shape`（来源：`stone_sword.png`）来源：stone_sword.png 整体/部件轮廓
- 候选 `wooden-sword-shape`（来源：`wooden_sword.png`）来源：wooden_sword.png 整体/部件轮廓
- 候选 `compact:iron_sword.png`（来源：`iron_sword.png`）只含 X/. 剪影；iron_sword.png 区域/整体轮廓
  ```
.............XXX
............XXXX
..........XXXXX.
.........XXXXX..
........XXXXX...
..XXX.XXXXX.....
...XXXXXXX......
....XXXX........
...XXXXXX.......
..XXX.XXXX......
XXX.............
XXX.............
  ```

### 刀柄 handle
- 候选 `iron-sword-blade`（来源：`iron_sword.png`）来源：iron_sword.png 刃部轮廓
- 候选 `stone-sword-blade`（来源：`stone_sword.png`）来源：stone_sword.png 刃部轮廓
- 候选 `wooden-sword-blade`（来源：`wooden_sword.png`）来源：wooden_sword.png 刃部轮廓
- 候选 `compact:iron_sword.png`（来源：`iron_sword.png`）只含 X/. 剪影；iron_sword.png 区域/整体轮廓
  ```
.............XXX
............XXXX
..........XXXXX.
.........XXXXX..
........XXXXX...
..XXX.XXXXX.....
...XXXXXXX......
....XXXX........
...XXXXXX.......
..XXX.XXXX......
XXX.............
XXX.............
  ```

## 生成命令
```bash
set -a; source /tmp/mc_llm.env; set +a
python3 examples/rebuild-demo/rebuild_generate.py
```

## Hash
- prompt sha256：`4c613fbd51e5578fb42b282de3c0a0519647a40616b99815b0621388192b7fc1`
- answer sha256：`fa00dc3e00f9ef612b27aebd64a43463301a76d4c769a9c0d17ba0be36e92d24`
- png sha256：`11605849ba33a332af601694e60f5e687cb79fdce8b355b63ac325638b51919c`
- attempts：`1`（首次 + 最多 2 次重试）

## 像素/UV 自检
- cmd：`/home/gmh/miniconda3/bin/python3 check_pixel_asset.py /tmp/mc-mod-art-studio-core/examples/rebuild-demo/skinning_knife/sprite.png`
- 结论：`PASS`
- 摘要：`[check_pixel_asset.py] /tmp/mc-mod-art-studio-core/examples/rebuild-demo/skinning_knife/sprite.png (16x16) -> PASS`
