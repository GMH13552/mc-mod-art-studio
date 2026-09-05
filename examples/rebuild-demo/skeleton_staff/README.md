# 骷髅法杖 (Skeleton Staff)

- 形式：`item`
- 尺寸：`16x16`
- 输出：`sprite.png`
- novelty：`0.9`（s2 silhouette bank；可大改）

## 说明
一根顶端镶着骷髅头的新法杖/权杖：上方是骨白色、带可辨眼窝与下颌暗示的骷髅头，下方是木质杖身/握柄；杖身可以斜、可以粗一点，但必须保留手柄感（木纹、粗细、握持段）。

## 部件 → 原版参考 → 轮廓基础 → 改了什么

| 部件 | 参考原版资产 | 借用 texture/palette/structure | 轮廓基础来源 | 改了什么 |
|---|---|---|---|---|
| 骷髅头/眼窝 | skeleton.png (head region) / bone_block_side.png | 骨白底、深色眼窝、骨裂纹 | 原版骨架头骨轮廓 + 骨块裂纹节奏；眼窝位置在大约头骨中上部 | 只取头骨轮廓基础，明确要可辨眼窝/颌；眼窝可加大、下颌可加宽，允许大改。 |
| 连接插座 | bone_block_side.png / stick.png | 骨质接缝/暗色小口/环 | 头骨与杖之间 1-3px 暗色小口/环 | 可做粗一点的插槽/环，增强连接感。 |
| 杖身/握柄 | stick.png / oak_planks.png / iron_sword.png | 木纹纵向、磨损颗粒、剑柄/握柄段的分节 | 细长杖身 + 握柄段（可加粗/分节） | 允许杖身斜/粗，底部加粗手柄段；形状可大改，只要保留手柄味。 |

## 轮廓候选（silhouette_candidates 菜单，不是锁）

> 以下候选由 `reference_analyzer.build_silhouette_bank` 从所选原版 assets 生成；
> prompt 中明确：可选一个/可组合/可大改/禁止当最终网格。

### 骷髅头 skull
- 候选 `skeleton-skull`（来源：`skeleton.png`）来源：skeleton.png 头部区域骨白头骨轮廓
- 候选 `bone-block-side-skull`（来源：`bone_block_side.png`）来源：bone_block_side.png 头部区域骨白头骨轮廓
- 候选 `bone-block-top-skull`（来源：`bone_block_top.png`）来源：bone_block_top.png 头部区域骨白头骨轮廓
- 候选 `compact:skeleton.png`（来源：`skeleton.png`）只含 X/. 剪影；skeleton.png 区域/整体轮廓
  ```
XXXXXXXXXXXXXX..............
XXXXXXX......X..............
XXXXXXX......X..............
XXXXXXXXXXXXXXXXXXXXXX......
XXXXXXXXXXXXXXXXXXXXXX......
XXXXXXXXXXXXXXXXXXXXXX......
..................X..XX..X..
......XXXXXX....XXXXXXXXXXXX
...........XXXXXX........XX.
...........X.XX.X........XX.
.........................XX.
......XXXXXXXXXXXXXXXXXXXXXX
  ```

### 眼窝/裂纹 eye sockets
- 候选 `skeleton-shape`（来源：`skeleton.png`）来源：skeleton.png 整体/部件轮廓
- 候选 `bone-block-side-shape`（来源：`bone_block_side.png`）来源：bone_block_side.png 整体/部件轮廓
- 候选 `bone-block-top-shape`（来源：`bone_block_top.png`）来源：bone_block_top.png 整体/部件轮廓
- 候选 `compact:skeleton.png`（来源：`skeleton.png`）只含 X/. 剪影；skeleton.png 区域/整体轮廓
  ```
XXXXXXXXXXXXXX..............
XXXXXXX......X..............
XXXXXXX......X..............
XXXXXXXXXXXXXXXXXXXXXX......
XXXXXXXXXXXXXXXXXXXXXX......
XXXXXXXXXXXXXXXXXXXXXX......
..................X..XX..X..
......XXXXXX....XXXXXXXXXXXX
...........XXXXXX........XX.
...........X.XX.X........XX.
.........................XX.
......XXXXXXXXXXXXXXXXXXXXXX
  ```

### 连接插座 socket
- 候选 `skeleton-shape`（来源：`skeleton.png`）来源：skeleton.png 整体/部件轮廓
- 候选 `bone-block-side-shape`（来源：`bone_block_side.png`）来源：bone_block_side.png 整体/部件轮廓
- 候选 `bone-block-top-shape`（来源：`bone_block_top.png`）来源：bone_block_top.png 整体/部件轮廓
- 候选 `compact:skeleton.png`（来源：`skeleton.png`）只含 X/. 剪影；skeleton.png 区域/整体轮廓
  ```
XXXXXXXXXXXXXX..............
XXXXXXX......X..............
XXXXXXX......X..............
XXXXXXXXXXXXXXXXXXXXXX......
XXXXXXXXXXXXXXXXXXXXXX......
XXXXXXXXXXXXXXXXXXXXXX......
..................X..XX..X..
......XXXXXX....XXXXXXXXXXXX
...........XXXXXX........XX.
...........X.XX.X........XX.
.........................XX.
......XXXXXXXXXXXXXXXXXXXXXX
  ```

### 杖身/握柄 handle
- 候选 `stick-body`（来源：`stick.png`）来源：stick.png 身体/躯干区域轮廓
- 候选 `carrot-on-a-stick-body`（来源：`carrot_on_a_stick.png`）来源：carrot_on_a_stick.png 身体/躯干区域轮廓
- 候选 `iron-sword-body`（来源：`iron_sword.png`）来源：iron_sword.png 身体/躯干区域轮廓
- 候选 `compact:stick.png`（来源：`stick.png`）只含 X/. 剪影；stick.png 区域/整体轮廓
  ```
...........XX
..........XXX
.........XXX.
........XXX..
.......XXX...
......XXX....
....XXX......
...XXX.......
..XXX........
.XXX.........
XXX..........
XX...........
  ```

## 生成命令
```bash
set -a; source /tmp/mc_llm.env; set +a
python3 examples/rebuild-demo/rebuild_generate.py
```

## Hash
- prompt sha256：`fef53d6ea93cda6a100c5abc8b1070358db899a5b9ae590d4bbd17948c99076c`
- answer sha256：`582a2695bfdd388cc9a2a1d63735cf3f21ae895e2a950baff82be55f3bf0b0db`
- png sha256：`be657abba3cefd30cd8323bf0dc2f9d066727e22e83a1d6fd8e2141e21e741fc`
- attempts：`1`（首次 + 最多 2 次重试）

## 像素/UV 自检
- cmd：`/home/gmh/miniconda3/bin/python3 check_pixel_asset.py /tmp/mc-mod-art-studio-core/examples/rebuild-demo/skeleton_staff/sprite.png`
- 结论：`PASS`
- 摘要：`[check_pixel_asset.py] /tmp/mc-mod-art-studio-core/examples/rebuild-demo/skeleton_staff/sprite.png (16x16) -> PASS`
