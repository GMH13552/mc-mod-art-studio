# Entity UV Check Summary (e2-entity / e3-fix)

- 时间 (UTC)：2026-09-05
- 工具：`check_entity_uv.py`
- 检查内容：尺寸、整体非空、标准 Vanilla 实体布局区域占位、画布边距（atlas 左右至少 1px；顶/底为说明项）。

## 正向对照（标准 Vanilla 模型可加载）

| PNG | --entity | 尺寸 | 结果 | JSON/MD |
|---|---|---|---|---|
| `vanilla_entity_ref/pig.png` | pig | 64x32 | PASS | `evidence/entity_uv_pig_vanilla.json` / `.md` |
| `vanilla_entity_ref/creeper.png` | creeper | 64x32 | PASS | `evidence/entity_uv_creeper_vanilla.json` / `.md` |

## 当前 v2 LLM 产物（旧 prompt）

| PNG | --entity | 尺寸 | 结果 | 失败原因 |
|---|---|---|---|---|
| `tests/runs/v2/pig/sprite.png` | pig | 64x32 | FAIL | `legs` 区域 opaque=0 |
| `tests/runs/v2/creeper/sprite.png` | creeper | 64x32 | FAIL | `body`、`legs` 区域 opaque=0 |

## 当前 v3 LLM 产物（e3 新 prompt + canvas margin 检查）

| PNG | --entity | 尺寸 | 结果 | 关键指标（含新 canvas_margin） |
|---|---|---|---|---|
| `tests/runs/v3/pig/sprite.png` | pig | 64x32 | PASS | opaque=858；head=336 body=310 legs=48；margins left=4 top=4 right=15 bottom=0（bottom 为说明项，不硬性拦截） |
| `tests/runs/v3/creeper/sprite.png` | creeper | 64x32 | FAIL（新增 canvas_margin） | opaque=920；head=132 body=300 legs=16；margins left=0 right=0 top=1 bottom=1（左右触边，硬性 FAIL） |

结论：旧 prompt 未要求 Vanilla atlas 区域语义，LLM 把 64x32 画成居中侧视图。
修复建议见 `docs/entity-uv-design.md` §7；新 prompt 已注入 `# ENTITY UV 语义` 区域坐标。
e3-fix 新增加 canvas_margin 后，v3 creeper 因左右边距不足 1px 从旧的区域 PASS 变为 FAIL；
v3 pig 底部边距为 0，按 atlas 规则仅作说明项记录，不改变整体 PASS。
