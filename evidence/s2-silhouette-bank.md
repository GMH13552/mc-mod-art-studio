# s2-shape: silhouette bank（轮廓基础候选）实现证据

本任务把“形状借鉴”从一句结构小作文升级为**可挑选、可组合、可大改的轮廓候选菜单**，
并让最终生成模型真的能看到借鉴内容：

- 文本 LLM：prompt 中注入 `silhouette_candidates`（shape token + X/. compact fragment）；
- 视觉 LLM：`llm_client --image` / `run_pipeline --llm-image` 支持多张参考 PNG；
- 恶魔牛：按 cow/red_mooshroom 的 64x32 atlas 区域生成 `entity_uv`。

---

## 1. 修改能力清单

| 模块 | 改动 |
|---|---|
| `reference_analyzer.py` | 新增 `build_silhouette_bank(parts, retrieval_anchors, ...)`；每个部件生成 2-4 个 silhouette 候选；`analyze_compact()` 也返回 `silhouette_candidates` 与原始 `silhouette` 行；新增 `render_silhouette_candidates()` 渲染候选菜单。 |
| `build_style_prompt.py` | `build_prompt_pack_v2` 自动计算 `silhouette_bank` 并写入 `concept_card.shape_pattern.silhouette_candidates` 与 pack；`_build_v2_prompt_text` 在 `### 形状图样 shape_pattern` 下渲染“部件轮廓候选”。 |
| `run_pipeline.py` | 最终紧凑 prompt 也渲染 `silhouette_candidates`；`--llm-image` 支持多次/逗号分隔多图。 |
| `llm_client.py` | `--image` 可多次/逗号分隔；全部图片放入 OpenAI 兼容 `user.content` 的 image_url 列表。 |
| `entity_uv_spec.py` | 新增 cow / red_mooshroom 64x32 atlas 区域：`head / horns / ears / muzzle / body / legs / tail`。 |
| `check_entity_uv.py` | `--entity` 支持 `cow`、`red_mooshroom`，自测覆盖这两个实体。 |

---

## 2. 示例 prompt 片段：骷髅法杖（item）

来自 `run_pipeline.py --query '骷髅法杖' --form item --prompt-only` 生成的 prompt。
可以看到每个部件都有 2-4 个候选，包含 shape token 与 X/. 剪影片段，并明确“可选/组合/大改/禁止当最终网格”。

```text
### 部件轮廓候选 silhouette_candidates（2-4 个/部件）
> 形状候选 = 菜单，不是锁。
> - 可选其中一个；
> - 可组合多个；
> - 可大改形状（加长/加粗/弯曲/变形/换比例都允许）；
> - 禁止把候选当成最终网格/逐像素复制候选剪影。

- [杖身]
  - 候选 1：blaze-rod-handle（来源：blaze_rod.png）；来源：blaze_rod.png 柄/杖身轮廓
  - 候选 2：stick-handle（来源：stick.png）；来源：stick.png 柄/杖身轮廓
  - 候选 3：skeleton-handle（来源：skeleton.png）；来源：skeleton.png 柄/杖身轮廓
  - 候选 4：compact:blaze_rod.png（来源：blaze_rod.png）；只含 X/. 剪影；blaze_rod.png 区域/整体轮廓
    ```
...........XX.
..........XXXX
.........XXXX.
.......XXXX...
......XXXX....
.....XXXX.....
....XXXX......
...XXXX.......
..XXXX........
XXXX..........
XXX...........
XX............
    ```

- [头]
  - 候选 1：skeleton-head（来源：skeleton.png）；来源：skeleton.png 头部区域轮廓
  - 候选 2：blaze-rod-head（来源：blaze_rod.png）；来源：blaze_rod.png 头部区域轮廓
  - 候选 3：stick-head（来源：stick.png）；来源：stick.png 头部区域轮廓
  - 候选 4：compact:skeleton.png（来源：skeleton.png）；只含 X/. 剪影；skeleton.png 区域/整体轮廓
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
```

---

## 3. 示例 prompt 片段：恶魔牛（entity_uv 64x32）

来自 `run_pipeline.py --query '恶魔牛' --form entity_uv --prompt-only` 生成的 prompt。
此时 `form=entity_uv`、`width=64 height=32`，`silhouette_candidates` 从 cow/red_mooshroom
的 64x32 atlas 区域（head/body/legs 等）切出，而不是 16x16 居中牛头图标。

```text
### 部件轮廓候选 silhouette_candidates（2-4 个/部件）
> 形状候选 = 菜单，不是锁。
> - 可选其中一个；
> - 可组合多个；
> - 可大改形状（加长/加粗/弯曲/变形/换比例都允许）；
> - 禁止把候选当成最终网格/逐像素复制候选剪影。

- [头]
  - 候选 1：red-mooshroom-head（来源：red_mooshroom.png）；来源：red_mooshroom.png 头部区域轮廓
  - 候选 2：cow-head（来源：cow.png）；来源：cow.png 头部区域轮廓
  - 候选 3：compact:red_mooshroom.png（来源：red_mooshroom.png）；只含 X/. 剪影；head 区域/整体轮廓
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
  - 候选 4：round-head（来源：通用原版形状语法）；圆头轮廓；正面/侧面均可用

# 形式硬约束（entity_uv：标准 UV 图集/皮肤，不是单个侧视图）
- 这不是单个侧视图，是标准 64x32/64x64 atlas；每个区域按语义填，禁止把整张图画成一个居中侧视剪影。
...
# ENTITY UV 语义
- 当前尺寸：64x32（原版 cow 标准尺寸）
- 原版 cow atlas 关键区域（坐标 x1,y1 -> x2,y2）：
  - head: 0,0 -> 32,16
  - horns: 0,0 -> 32,6
  - ears: 0,0 -> 32,4
  - muzzle: 0,8 -> 16,16
  - body: 16,16 -> 64,32
  - legs: 0,16 -> 16,32
  - tail: 48,16 -> 64,32
```

`check_entity_uv.py --self-test` 对 cow/red_mooshroom 的合成 64x32 区域正例全部 PASS，
说明标准实体模板可用。

---

## 4. 多图参考（视觉 LLM 真正看到借鉴内容）

`llm_client` 和 `run_pipeline` 都支持多次/逗号分隔传入多张参考 PNG：

```bash
# llm_client 多图：--image 可多次，也可逗号分隔
python3 llm_client.py --prompt-file prompt.txt \
  --image cow.png --image red_mooshroom.png

# run_pipeline 多图：--llm-image 可多次，也可逗号分隔
python3 run_pipeline.py --query '恶魔牛' --form entity_uv \
  --index /path/to/library-index.json --top 4 \
  --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' \
  --llm-image cow.png --llm-image red_mooshroom.png \
  --out out/demon_cow
```

在 `llm_client` 中，多张图会全部放入 OpenAI 兼容的 user content：

```json
[
  {"type": "text", "text": "...prompt..."},
  {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
  {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
]
```

---

## 5. 自测结果

```text
$ python3 reference_analyzer.py --self-test
reference_analyzer self-test: PASS

$ python3 -m unittest discover -s tests -v
...
Ran 12 tests in 0.012s
OK

$ python3 build_style_prompt.py --self-test
SELF-TEST: PASS (2 packs, 44 checks passed)

$ python3 check_entity_uv.py --self-test
...
check_entity_uv self-test: PASS

$ python3 llm_client.py --help | grep -- --image
  --image PNG           参考 PNG 路径；可多次使用（--image a.png --image b.png）或用逗号分隔（--image a.png,b.png）；全部传给支持视觉的模型（如 deepseek-v4-flash-vision-exp）
```

---

## 6. 结论

- `reference_analyzer.build_silhouette_bank` 已为每个部件输出 2-4 个 silhouette 基础；
- prompt 中已出现“部件轮廓候选”段与“可选一个/可组合/可大改/禁止当最终网格”规则；
- 文本 LLM 看到 silhouette/compact；视觉 LLM 可通过多 `--image` / `--llm-image` 看到多张参考 PNG；
- cow / red_mooshroom 已有 64x32 atlas 区域，并可被 `check_entity_uv` 检查。
