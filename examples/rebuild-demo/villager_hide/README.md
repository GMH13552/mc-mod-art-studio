# 村民皮 (Villager Hide)

- 形式：`item`
- 尺寸：`16x16`
- 输出：`sprite.png`
- novelty：`0.9`（s2 silhouette bank；可大改）
- 生成方式：`programmatic template recolor (vanilla rabbit_hide.png silhouette + hide palette + cloth trim)`
- 原版模板：`rabbit_hide.png (16x16 item hide)`（仅作轮廓/区域基础；原版 PNG 未复制进本仓库）

## 说明
一张被剥下并鞣制的村民皮/兽皮，作为自定义采集材料和掉落物；主体是不规则皮张（像 leather 或 rabbit_hide），带折痕、颗粒、接缝与毛边/纤维感，边缘露出灰褐色村民长袍织物带与缝线。16x16 内非满框矩形。硬性：皮张必须是不规则多边形/带毛边，禁止圆形/椭圆/正方形；边缘有 1px 锯齿或短纤维。

## 部件 → 原版参考 → 轮廓基础 → 改了什么

| 部件 | 参考原版资产 | 借用 texture/palette/structure | 轮廓基础来源 | 改了什么 |
|---|---|---|---|---|
| 皮面主体 hide | leather.png / rabbit_hide.png | 皮革颗粒、折痕高光、不规则剥制边缘/毛边 | 参考 leather/rabbit_hide 的不规则皮张轮廓（非满框矩形） | 改用皮/兔皮轮廓，边缘加毛边；可大改比例，不要方形。 |
| 织物内衬 cloth trim | villager.png | 村民长袍布料层叠、缝线针脚质感 | 皮面下缘/内侧的窄条织物与 1px 缝线 | 只借织物条和缝线节奏，不借人物外形。 |
| 挂环/标签 hanger tag | stick.png / bone_block_side.png | 深色小环/木质小节颗粒 | 上缘 2-3px 小环或木牌 | 小挂环/标签，不借棍/骨头形状。 |

## 轮廓候选（silhouette_candidates 菜单，不是锁）

> 以下候选由 `reference_analyzer.build_silhouette_bank` 从所选原版 assets 生成；
> prompt 中明确：可选一个/可组合/可大改/禁止当最终网格。

### 皮面主体 hide
- 候选 `rabbit-hide-body`（来源：`rabbit_hide.png`）来源：rabbit_hide.png 身体/躯干区域轮廓
- 候选 `villager-body`（来源：`villager.png`）来源：villager.png 身体/躯干区域轮廓
- 候选 `leather-body`（来源：`leather.png`）来源：leather.png 身体/躯干区域轮廓
- 候选 `compact:rabbit_hide.png`（来源：`rabbit_hide.png`）只含 X/. 剪影；rabbit_hide.png 区域/整体轮廓
  ```
.XX....XX.
.XXX..XXX.
..XXXXXX..
XX.XXXX.XX
XXXXXXXXXX
XXXXXXXXXX
..XXXXXX..
..XXXXXX..
..XXXXXX..
.XXXXXXXX.
XXXXXXXXXX
XXX.XX.XXX
  ```

### 折痕/接缝 seams
- 候选 `villager-shape`（来源：`villager.png`）来源：villager.png 整体/部件轮廓
- 候选 `leather-shape`（来源：`leather.png`）来源：leather.png 整体/部件轮廓
- 候选 `rabbit-hide-shape`（来源：`rabbit_hide.png`）来源：rabbit_hide.png 整体/部件轮廓
- 候选 `compact:villager.png`（来源：`villager.png`）只含 X/. 剪影；villager.png 区域/整体轮廓
  ```
XXXXXX..XXXX................
XXXXXXXXXXXXXX..............
XXXXXXXXXXXXXX..............
XXXXXXXXXXXXXX..............
XXXXXXXXXXXXXX..............
....XXXXXXXXXXXXXXXXXX......
....XXXXXXXXXXXXXXXXXX......
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXX..
..........................XX
......................XXXXXX
  ```

### 毛边/纤维 fringe
- 候选 `villager-shape`（来源：`villager.png`）来源：villager.png 整体/部件轮廓
- 候选 `leather-shape`（来源：`leather.png`）来源：leather.png 整体/部件轮廓
- 候选 `rabbit-hide-shape`（来源：`rabbit_hide.png`）来源：rabbit_hide.png 整体/部件轮廓
- 候选 `compact:villager.png`（来源：`villager.png`）只含 X/. 剪影；villager.png 区域/整体轮廓
  ```
XXXXXX..XXXX................
XXXXXXXXXXXXXX..............
XXXXXXXXXXXXXX..............
XXXXXXXXXXXXXX..............
XXXXXXXXXXXXXX..............
....XXXXXXXXXXXXXXXXXX......
....XXXXXXXXXXXXXXXXXX......
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXX..
..........................XX
......................XXXXXX
  ```

### 织物内衬 cloth trim
- 候选 `villager-shape`（来源：`villager.png`）来源：villager.png 整体/部件轮廓
- 候选 `leather-shape`（来源：`leather.png`）来源：leather.png 整体/部件轮廓
- 候选 `rabbit-hide-shape`（来源：`rabbit_hide.png`）来源：rabbit_hide.png 整体/部件轮廓
- 候选 `compact:villager.png`（来源：`villager.png`）只含 X/. 剪影；villager.png 区域/整体轮廓
  ```
XXXXXX..XXXX................
XXXXXXXXXXXXXX..............
XXXXXXXXXXXXXX..............
XXXXXXXXXXXXXX..............
XXXXXXXXXXXXXX..............
....XXXXXXXXXXXXXXXXXX......
....XXXXXXXXXXXXXXXXXX......
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXX..
..........................XX
......................XXXXXX
  ```

### 挂环/标签 hanger tag
- 候选 `villager-shape`（来源：`villager.png`）来源：villager.png 整体/部件轮廓
- 候选 `leather-shape`（来源：`leather.png`）来源：leather.png 整体/部件轮廓
- 候选 `rabbit-hide-shape`（来源：`rabbit_hide.png`）来源：rabbit_hide.png 整体/部件轮廓
- 候选 `compact:villager.png`（来源：`villager.png`）只含 X/. 剪影；villager.png 区域/整体轮廓
  ```
XXXXXX..XXXX................
XXXXXXXXXXXXXX..............
XXXXXXXXXXXXXX..............
XXXXXXXXXXXXXX..............
XXXXXXXXXXXXXX..............
....XXXXXXXXXXXXXXXXXX......
....XXXXXXXXXXXXXXXXXX......
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXX..
..........................XX
......................XXXXXX
  ```

## Why programmatic fallback
- The s2 prompt + silhouette bank were generated and stored; however the text LLM
  output for this form was not stable enough to produce a readable result.
- This demo therefore uses the vanilla asset **only as a silhouette/template base** and
  remaps every opaque texel to a new palette (plus explicit accents), which is the
  'cow/red_mooshroom 64x32 模板改' / 'rabbit_hide 轮廓' approach requested by the brief.

## 生成命令
```bash
set -a; source /tmp/mc_llm.env; set +a
python3 examples/rebuild-demo/rebuild_generate.py --only villager_hide
python3 examples/rebuild-demo/build_programmatic_demos.py
python3 examples/rebuild-demo/update_programmatic_meta.py
```

## Hash
- prompt sha256：`f2d24c540c44ce1998afe030b41838eadbdeadc40edbe418b00ae952b14f9e2e`
- answer sha256：`programmatic-fallback`
- png sha256：`6ea5126ff8def7126dbc4a2d407c2765acba98e6487cf3c696be940180f0ec43`
- attempts：`programmatic-fallback`
- 失败/重试记录：
  - `LLM text-model output for this asset was unstable (all-one-color / empty / oval); final PNG uses vanilla template silhouette + new palette recoloring.`

## 像素/UV 自检
- cmd：`/home/gmh/miniconda3/bin/python3 check_pixel_asset.py /tmp/mc-mod-art-studio-core/examples/rebuild-demo/villager_hide/sprite.png`
- 结论：`PASS`
- 摘要：`[check_pixel_asset.py] /tmp/mc-mod-art-studio-core/examples/rebuild-demo/villager_hide/sprite.png (16x16) -> PASS`
