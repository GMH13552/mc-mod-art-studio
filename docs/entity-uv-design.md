# Entity UV 可用性设计

- **任务**：e2-entity
- **日期 (UTC)**：2026-09-05
- **配套代码**：
  - `entity_uv_spec.py`：标准坐标表 + prompt 语义文本
  - `check_entity_uv.py`：尺寸/区域占位检查器
  - `run_pipeline.py` / `build_style_prompt.py`：prompt 输出契约
  - `package_asset.py`：note / manifest 模型引用说明

---

## 1. 为什么“能生成 64x32 PNG”不等于“可用”

Java Edition 原版实体模型（猪、苦力怕、玩家等）是**硬编码模型**：
资源包只能覆盖 `assets/minecraft/textures/entity/<path>.png` 的贴图，
不能通过普通 `assets/<ns>/models/entity/*.json` 直接替换原版实体模型。

因此，entity 贴图“真正可用”至少要求：

1. **尺寸正确**：例如猪/苦力怕原版贴图为 `64x32`，玩家皮肤为 `64x32`（legacy）或 `64x64`（modern）。
2. **UV 区域语义正确**：在硬编码模型采样的区域里有内容。若把 64x32 当成一个“居中侧视图”，
   模型的头/身/腿面会采样到透明区域或错误区域，成品不能正确渲染。
3. **模型引用说明**：说明这个 PNG 如何被 Java/Bedrock 使用（替换原版路径 / CEM / geometry / 模组 renderer）。

---

## 2. 标准玩家皮肤布局（64x32 / 64x64）

坐标约定：左侧为 64 宽，x 向右；`x1,y1 -> x2,y2` 代表半开区间 `[x1,x2) × [y1,y2)`（左上原点）。

### 64x64 现代皮肤

| 区域 | 坐标 |
|---|---|
| head | `0,0 -> 32,16` |
| body | `16,16 -> 40,32` |
| right_leg | `0,16 -> 16,32` |
| right_arm | `40,16 -> 56,32` |
| left_leg | `16,48 -> 32,64` |
| left_arm | `32,48 -> 48,64` |

### 64x32 legacy 皮肤

只有内层（无 overlay/hat 层）：

| 区域 | 坐标 |
|---|---|
| head | `0,0 -> 32,16` |
| body | `16,16 -> 40,32` |
| right_leg | `0,16 -> 16,32` |
| right_arm | `40,16 -> 56,32` |

渲染器会把 `right_leg` / `right_arm` 镜像为左侧部件，所以 legacy 不需要单独的 left 区域。
64x64 则必须同时满足 `left_leg` / `left_arm` 非空。

---

## 3. 猪 / 苦力怕 Vanilla 64x32 atlas 布局

猪和苦力怕**不是**玩家皮肤布局。它们使用各自的原版 64x32 图集。
以下粗粒度区域来自原版贴图与 UV template，可用于“标准模型是否能加载”的占位检查。

### 猪（`assets/minecraft/textures/entity/pig/pig.png`）

| 部件 | 区域 |
|---|---|
| head | `0,0 -> 32,16` |
| body | `28,8 -> 64,32` |
| legs | `0,16 -> 16,26` |

### 苦力怕（`assets/minecraft/textures/entity/creeper/creeper.png`）

| 部件 | 区域 |
|---|---|
| head | `0,0 -> 32,16` |
| body | `16,16 -> 40,32` |
| legs | `0,16 -> 16,26` |

> 说明：这些区域是粗粒度“至少要有内容”的检查；实际逐 face 的 UV
> （top/bottom/right/front/left/back）在 `entity_uv_spec.MOB_ENTITY_REGIONS`
> 与 `docs/method-survey.md §2` 中引用。若要做像素级替换，建议直接以原版 PNG 为模板。

---

## 4. Pipeline 输出契约

`entity_uv` 现在在 prompt 的 `output_contract` 中追加 `# ENTITY UV 语义` 段落：

- 明确禁止“把整个 64x32/64x64 画成单个居中侧视图”。
- 列出目标实体的标准区域坐标（玩家皮肤或猪/苦力怕 atlas）。
- 说明 Java 资源包只能替换 `assets/minecraft/textures/entity/<path>.png`。

`run_pipeline.py` 的 `_palette_index_contract_text()` 和
`build_style_prompt.py` 的 `_build_v2_output_contract()` 都会调用
`entity_uv_spec.contract_text(width, height, entity)`。

---

## 5. 模型引用方案

| 目标 | 方案 | 优点 | 限制 |
|---|---|---|---|
| 替换原版生物贴图（Java） | 把 PNG 放到 `assets/minecraft/textures/entity/pig/pig.png` 等原版路径 | 纯原版资源包，最可靠 | 只能换皮，不能换模型；必须遵循该实体的原版 UV |
| 新建/自定义 Java 实体模型 | OptiFine CEM | 资源包 + OptiFine 客户端即可 | 依赖 OptiFine，非原版；需要写 `.properties`/`.json` 模型绑定 |
| Bedrock 自定义实体 | `*.geo.json` + render controller + client entity | 数据驱动，官方支持 | 需要 Bedrock 客户端；格式与 Java 不同 |
| Java 模组级自定义 | JsonEM / Entity Texture Features / 自写 renderer | 能力最强 | 依赖模组，超出纯资源包范围 |

`package_asset.py` 会在 entity_uv 输出旁生成 `.note.txt`，说明：
- 是否检测到原版实体（pig/creeper/player）；
- 标准替换路径；
- 自定义模型需要 CEM / Bedrock geometry / 模组 renderer；
- 用 `check_entity_uv.py` 验证布局。

---

## 6. 检查器用法

```bash
# 无原版素材自测：内存合成 pig/creeper 正例应 PASS
python3 check_entity_uv.py --self-test

# 当前 v2 LLM 产物（旧 prompt，未按 atlas 布局）应 FAIL
python3 check_entity_uv.py tests/runs/v2/pig/sprite.png --entity pig
python3 check_entity_uv.py tests/runs/v2/creeper/sprite.png --entity creeper
```

> 仓库不再内置原版 `pig.png`/`creeper.png`；如果本地有原版贴图，可用
> `python3 check_entity_uv.py <原版 pig.png> --entity pig` 验证其应 PASS。
> `vanilla_entity_ref/` 下的 `*_template.png` 是 1280x640 的纸质 UV 模板，
> 仅作布局参考，不是 64x32 成品贴图。

输出 `JSON/MD` 记录尺寸、非空、每个区域的 opaque 像素数与 PASS/FAIL。

---

## 7. 现状与修复建议

### 现有 v2 产物

| 产物 | 尺寸 | 区域检查 | 结论 |
|---|---|---|---|
| `tests/runs/v2/pig/sprite.png` | 64x32 | head/body 有内容，**legs 为空** | FAIL |
| `tests/runs/v2/creeper/sprite.png` | 64x32 | 只有 head 有内容，body/legs 为空 | FAIL |

原因：旧 prompt 只声明 `W=64 H=32`，没有要求 Vanilla atlas 区域语义；LLM 把 64x32
当成一个居中侧视图（猪/苦力怕都只画了一个小矩形）。

### 修复建议

1. 使用更新后的 prompt 重新生成（`entity_uv_spec.contract_text()` 已注入区域坐标）。
2. 生成后跑 `check_entity_uv.py --entity pig|creeper` 确认各区域非空。
3. 若要真正替换原版猪/苦力怕贴图，将 PNG 放到
   `assets/minecraft/textures/entity/pig/pig.png` / `assets/minecraft/textures/entity/creeper/creeper.png`。
4. 若要自定义实体模型，按第 5 节选择 CEM / Bedrock geometry / 模组 renderer。

> e4 实现：仓库根目录 `fix_entity_margin.py` 可把 atlas 外圈 1px 裁掉并居中，用于满足左右/四周至少 1px 透明边距；v4 已将 creeper 修复为 PASS（见 `tests/results/v4/summary.md`）。
