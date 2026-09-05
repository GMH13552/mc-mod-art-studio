# 恶魔牛 (Demon Cow entity_uv)

- 形式：`entity_uv`
- 尺寸：`64x32`
- 输出：`sprite.png`
- novelty：`0.9`（silhouette bank；可大改）
- 生成方式：`programmatic template recolor (vanilla cow.png silhouette + demon palette)`
- 原版模板：`cow.png (64x32 entity atlas)`（仅作轮廓/区域基础；原版 PNG 未复制进本仓库）

## 说明
一个恶魔化的牛实体纹理，替换原版 cow/red_mooshroom 的 64x32 atlas；保留牛的头/角/耳朵/鼻口/身体/腿的实体结构，配色改为暗红恶魔皮，角与眼窝用黑红，眼睛和角尖带青色魂火。整体是实体 UV 图集，不是 16x16 牛头图标。硬性：64x32 至少使用 4 种以上调色板索引；0 号只做描边/暗部；head/body/legs/角/眼都要有可见色阶与轮廓细节。

## 部件 → 原版参考 → 轮廓基础 → 改了什么

| 部件 | 参考原版资产 | 借用 texture/palette/structure | 轮廓基础来源 | 改了什么 |
|---|---|---|---|---|
| 头/角/耳/鼻口 | cow.png / red_mooshroom.png | 牛皮分块、鼻梁高光、脸颊暗部、角/耳连接 | 64x32 head/horns/ears/muzzle 区域轮廓；角在头顶、耳在两侧、鼻口在下 | 保留牛头/角/鼻口轮廓基础，颜色与角型可大改；角可更弯/更长，眼窝改魂火。 |
| 身体/腿/尾 | cow.png / red_mooshroom.png | 躯干肌肉分区、腿部深浅、尾巴走向 | 64x32 body/legs/tail 区域轮廓；身体在右侧、腿在左侧下半、尾在右后 | 保留躯干/腿/尾的实体比例，可加火焰/鳞片轮廓变化，但不能改成非牛生物。 |
| 魂火眼/角尖 | soul_fire_0.png / soul_fire_1.png | 青绿色火焰形状、白核心、外发光 | 小面积尖焰/光点，不占满区域 | 只借火焰的局部形状/配色，不做整张火焰贴图；可在眼窝/角尖点 1-2px。 |

## 轮廓候选（silhouette_candidates 菜单，不是锁）

> 以下候选由 `reference_analyzer.build_silhouette_bank` 从所选原版 assets 生成；
> prompt 中明确：可选一个/可组合/可大改/禁止当最终网格。

### 头 head
- 候选 `cow-head`（来源：`cow.png`）来源：cow.png 头部区域轮廓
- 候选 `red-mooshroom-head`（来源：`red_mooshroom.png`）来源：red_mooshroom.png 头部区域轮廓
- 候选 `brown-mooshroom-head`（来源：`brown_mooshroom.png`）来源：brown_mooshroom.png 头部区域轮廓
- 候选 `compact:cow.png`（来源：`cow.png`）只含 X/. 剪影；head 区域/整体轮廓
  ```
....XXXXXXXXXXXXXXXX.XX.....
....XXXXXXXXXXXXXXXXXXXX....
....XXXXXXXXXXXXXXXXXXXX....
....XXXXXXXXXXXXXXXX......XX
....XXXXXXXXXXXXXXXX......XX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
................XXXXXXXXXXXX
................XXXXXXXXXXXX
  ```

### 角 horns
- 候选 `cow-horn`（来源：`cow.png`）来源：cow.png 角/耳区域轮廓
- 候选 `red-mooshroom-horn`（来源：`red_mooshroom.png`）来源：red_mooshroom.png 角/耳区域轮廓
- 候选 `brown-mooshroom-horn`（来源：`brown_mooshroom.png`）来源：brown_mooshroom.png 角/耳区域轮廓
- 候选 `compact:cow.png`（来源：`cow.png`）只含 X/. 剪影；horns 区域/整体轮廓
  ```
XXXXXXXXXXXXXXXX.XX.......
XXXXXXXXXXXXXXXXXXXX......
XXXXXXXXXXXXXXXXXXXX......
XXXXXXXXXXXXXXXXXXXX......
XXXXXXXXXXXXXXXX......XXXX
XXXXXXXXXXXXXXXX......XXXX
  ```

### 耳朵 ears
- 候选 `cow-ear`（来源：`cow.png`）来源：cow.png 耳朵区域轮廓
- 候选 `red-mooshroom-ear`（来源：`red_mooshroom.png`）来源：red_mooshroom.png 耳朵区域轮廓
- 候选 `brown-mooshroom-ear`（来源：`brown_mooshroom.png`）来源：brown_mooshroom.png 耳朵区域轮廓
- 候选 `compact:cow.png`（来源：`cow.png`）只含 X/. 剪影；ears 区域/整体轮廓
  ```
XXXXXXXXXXXXXXXX.XX.
XXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXX
  ```

### 鼻口 muzzle
- 候选 `cow-muzzle`（来源：`cow.png`）来源：cow.png 鼻口区域轮廓
- 候选 `red-mooshroom-muzzle`（来源：`red_mooshroom.png`）来源：red_mooshroom.png 鼻口区域轮廓
- 候选 `brown-mooshroom-muzzle`（来源：`brown_mooshroom.png`）来源：brown_mooshroom.png 鼻口区域轮廓
- 候选 `compact:cow.png`（来源：`cow.png`）只含 X/. 剪影；muzzle 区域/整体轮廓
  ```
XXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXX
  ```

### 眼睛/魂火 eyes
- 候选 `cow-shape`（来源：`cow.png`）来源：cow.png 整体/部件轮廓
- 候选 `red-mooshroom-shape`（来源：`red_mooshroom.png`）来源：red_mooshroom.png 整体/部件轮廓
- 候选 `brown-mooshroom-shape`（来源：`brown_mooshroom.png`）来源：brown_mooshroom.png 整体/部件轮廓
- 候选 `compact:cow.png`（来源：`cow.png`）只含 X/. 剪影；cow.png 区域/整体轮廓
  ```
XXXX.XX.....................
XXXXXXXX....................
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
  ```

### 身体 body
- 候选 `cow-body`（来源：`cow.png`）来源：cow.png 身体/躯干区域轮廓
- 候选 `red-mooshroom-body`（来源：`red_mooshroom.png`）来源：red_mooshroom.png 身体/躯干区域轮廓
- 候选 `brown-mooshroom-body`（来源：`brown_mooshroom.png`）来源：brown_mooshroom.png 身体/躯干区域轮廓
- 候选 `compact:cow.png`（来源：`cow.png`）只含 X/. 剪影；body 区域/整体轮廓
  ```
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXXXXXXXXXXXXXX
  ```

### 腿 legs
- 候选 `cow-leg`（来源：`cow.png`）来源：cow.png 腿部区域轮廓
- 候选 `red-mooshroom-leg`（来源：`red_mooshroom.png`）来源：red_mooshroom.png 腿部区域轮廓
- 候选 `brown-mooshroom-leg`（来源：`brown_mooshroom.png`）来源：brown_mooshroom.png 腿部区域轮廓
- 候选 `compact:cow.png`（来源：`cow.png`）只含 X/. 剪影；legs 区域/整体轮廓
  ```
....XXXXXXXX....
....XXXXXXXX....
....XXXXXXXX....
XXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXX
XXXXXXXXXXXXXXXX
  ```

### 尾巴 tail
- 候选 `cow-tail`（来源：`cow.png`）来源：cow.png 尾部区域轮廓
- 候选 `red-mooshroom-tail`（来源：`red_mooshroom.png`）来源：red_mooshroom.png 尾部区域轮廓
- 候选 `brown-mooshroom-tail`（来源：`brown_mooshroom.png`）来源：brown_mooshroom.png 尾部区域轮廓
- 候选 `compact:cow.png`（来源：`cow.png`）只含 X/. 剪影；tail 区域/整体轮廓
  ```
XXXXXXXXXXXXXX
XXXXXXXXXXXXXX
XXXXXXXXXXXXXX
XXXXXXXXXXXXXX
XXXXXXXXXXXXXX
XXXXXXXXXXXXXX
XXXXXXXXXXXXXX
XXXXXXXXXXXXXX
XXXXXXXXXXXXXX
XXXXXXXXXXXXXX
XXXXXXXXXXXXXX
XXXXXXXXXXXXXX
  ```

## Why programmatic fallback
- The prompt + silhouette bank were generated and stored; however the text LLM
  output for this form was not stable enough to produce a readable result.
- This demo therefore uses the vanilla asset **only as a silhouette/template base** and
  remaps every opaque texel to a new palette (plus explicit accents), which is the
  'cow/red_mooshroom 64x32 模板改' approach requested by the brief.

## 生成/复现
- 本示例的最终 PNG 是已提交产物；重新生成需要本机 `cow.png`（64x32 entity atlas）作为轮廓/区域基础，并按恶魔牛配色重着色。
- `raw_answer.txt` 是 `programmatic-fallback` 标记，不能直接作为 `run_pipeline --raw` 的像素文本输入。

## Hash
- prompt sha256：`9a4c8e158f599e98bbe8de8c415483a01347193226ca6e04f48fc444d5207477`
- answer sha256：`programmatic-fallback`
- png sha256：`701cf982ae8cd9092d00ce77bae6c02a5136a50b4e99d61f22dab48d961103b8`
- attempts：`programmatic-fallback`
- 失败/重试记录：
  - `LLM text-model output for this asset was unstable (all-one-color / empty / oval); final PNG uses vanilla template silhouette + new palette recoloring.`

## 像素/UV 自检
- cmd：`python3 check_entity_uv.py examples/demon_cow/sprite.png --entity cow`
- 结论：`PASS`
- 摘要：`PASS: 符合标准实体 UV 布局 (entity=cow, size=64x32, opaque=1616, regions=7, margins={'left': 1, 'top': 0, 'right': 1, 'bottom': 0} margins_lt_1=top/bottom)`
