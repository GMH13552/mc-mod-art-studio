# t4-run 广谱测试结果汇总

- 日期：2026-09-05 (UTC)
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- 来源：tests/test_set.md t01-t12；t01-t10 使用 `run_pipeline.py` 在线 LLM 生成，t11/t12 使用 `package_asset.py --template chest|stairs` 模板打包。

## 汇总表

| ID | slug | query | form | run exit | check verdict | opaque | bbox | border ok | palette ok | pipeline status |
|---|------|-------|------|----------|---------------|--------|------|-----------|-------------|-----------------|
| t01 | diamond_sword | 钻石剑 | item | 0 | FAIL | sprite=54 | sprite=[4, 0, 11, 16] | sprite=True | sprite=True | PIPELINE PASS |
| t02 | golden_apple | 金苹果 | item | 0 | FAIL | sprite=0 | sprite=None | sprite=False | sprite=False | PIPELINE PASS (first attempt exit 1: PALETTE parser error; retry exit 0) |
| t03 | bow | 弓 | item | 0 | FAIL | sprite=120 | sprite=[2, 0, 13, 16] | sprite=True | sprite=True | PIPELINE PASS |
| t04 | glowstone | 荧石 | block_multi | 0 | PASS | top=26; side=36; bottom=26 | top=[5, 6, 11, 11]; side=[5, 5, 11, 13]; bottom=[5, 6, 11, 11] | top=True; side=True; bottom=True | top=True; side=True; bottom=True | PIPELINE PASS |
| t05 | bricks | 红砖 | block_multi | 0 | FAIL | top=0; side=0; bottom=0 | top=None; side=None; bottom=None | top=False; side=False; bottom=False | top=False; side=False; bottom=False | PIPELINE PASS |
| t06 | lapis_block | 青金石块 | block_multi | 0 | FAIL | top=0; side=0; bottom=0 | top=None; side=None; bottom=None | top=False; side=False; bottom=False | top=False; side=False; bottom=False | PIPELINE PASS |
| t07 | poppy | 虞美人 | cross | 0 | FAIL | sprite=70 | sprite=[3, 4, 12, 16] | sprite=False | sprite=False | PIPELINE PASS |
| t08 | oak_sapling | 橡树树苗 | cross | 0 | FAIL | sprite=32 | sprite=[5, 5, 11, 16] | sprite=False | sprite=True | PIPELINE PASS |
| t09 | pig | 猪 | entity_uv | 1 | N/A | - | - | - | - | PIPELINE FAIL: unexpected extra data after index grid (LLM output 33 rows for 64x32; raw_answer contains 246 non -1 index values, not all -1; no PNG) |
| t10 | creeper | 苦力怕 | entity_uv | 1 | N/A | - | - | - | - | PIPELINE FAIL: unexpected extra data after index grid (LLM output 33 rows for 64x32; raw_answer all -1; no PNG) |
| t11 | chest | 箱子 | block_custom | 0 | PASS | chest_all=196; chest_particle=196 | chest_all=[1, 1, 15, 15]; chest_particle=[1, 1, 15, 15] | chest_all=True; chest_particle=True | chest_all=True; chest_particle=True | VALIDATE PASS (5 checks) |
| t12 | stone_brick_stairs | 石砖楼梯 | block_custom | 0 | PASS | bottom=196; top=196; side=196; particle=196 | bottom=[1, 1, 15, 15]; top=[1, 1, 15, 15]; side=[1, 1, 15, 15]; particle=[1, 1, 15, 15] | bottom=True; top=True; side=True; particle=True | bottom=True; top=True; side=True; particle=True | VALIDATE PASS (9 checks) |

## 聚合

- t01-t10 条目 check PASS 率：1/10 = 10.0%
- t01-t10 PNG check PASS 率：3/14 = 21.4%
- t01-t10 PNG 非空率：7/14 = 50.0%
- 全部 12 项（含 t11/t12 模板打包）PNG check PASS 率：9/20 = 45.0%
- 全部 12 项 PNG 非空率：13/20 = 65.0%
- 全部 12 项条目 check PASS：3/12 = 25.0%
- t01-t10 PNG bbox 可辨率：3/14 = 21.4%
- t01-t10 PNG 边框率：5/14 = 35.7%
- t01-t10 PNG 色阶率：6/14 = 42.9%
- 全部 12 项 PNG bbox 可辨率：9/20 = 45.0%
- 全部 12 项 PNG 边框率：11/20 = 55.0%
- 全部 12 项 PNG 色阶率：12/20 = 60.0%

## 与已知退化基线对比

### 全 -1 透明/空 raw

- 影响的条目：t02, t05, t06, t10
- 证据：golden_apple/bricks/lapis_block check reports bbox=None opaque=0; creeper raw_answer all -1 (parser fails on extra 33rd row before PNG); pig raw_answer has 246 non -1 index values (33 rows), so t09 is excluded from this baseline.
- 校正说明：t09 pig 的 raw_answer.txt 不是全 -1（非 -1 索引共 246 个），仍因 LLM 输出 33 行导致 parser 失败，故不归入“全 -1/空 raw”基线。
- 结论：当前 LLM 生成链路在多个非自证 query 上退化到与基线同质

### 实心楔形/实心占位

- 影响的条目：t11, t12
- 证据：check reports opaque=196 bbox=[1,1,15,15] for chest/stairs placeholder textures
- 结论：模板打包通过，但占位纹理不是语义资产；不作为 LLM 生成质量指标

### 语义错/自证特征漂移

- 影响的条目：t01, t02, t03, t05, t06, t07, t08, t09, t10
- 证据：tests/runs/<slug>/concept.json 中 shape_pattern.silhouette/description 反复为“长条/杖；菱形/晶体”或“蘑菇/斧头”
- 结论：生成“成功”的 8 个 LLM 条目存在大面积语义错配；仅 t04 glowstone 的概念较接近目标（发光颗粒/方块）

## 关键观察

1. `run_pipeline.py` 在无 `--mc-path/--index` 时使用 `retrieve_assets` 合成迷你索引；该索引明显由项目自证概念（外星水晶法杖/蘑菇等）构成，导致非自证 query 的 concept 被漂移到“长条/杖；菱形/晶体”或“蘑菇/斧头”。
2. t09/t10 entity_uv 失败是 LLM 输出 33 行（期望 32），`text_to_texture._parse_index_grid` 在读取 32 行后把第 33 行判为 unexpected extra data。t10 creeper raw_answer 确为全 -1；t09 pig raw_answer 含 246 个非 -1 索引（非全 -1）。若修复为“多余 33rd 行可裁剪”或限制 LLM 行数，可让 t09 的非空实体图有机会生成，但 t10 当前 raw 仍为空图。
3. t02 首次失败是 LLM palette 行带 inline `#` 注释，`PALETTE_LINE_RE` 要求行尾无注释；重试后通过解析但输出全透明。
4. t11/t12 模板打包链路稳定：chest 5 项 semantic PASS，stairs 9 项 semantic PASS；模板占位纹理均通过 `check_pixel_asset`（16x16, opaque=196, bbox 1px margin）。
5. 当前“PIPELINE PASS”不等于生成质量通过；8 个 PASS 条目中仅 t04 glowstone pixel-check 三面全 PASS，其余单面/多面存在全透明、贴边无 margin、描边不足等问题。

## 文件

- `tests/results/summary.json`：结构化逐项指标
- `tests/results/summary.md`：本文
- `tests/evidence/<slug>.md`：t01-t12 逐项运行证据
- `tests/reports/<name>.json`：每张 PNG 的 check_pixel_asset 证据
- `tests/runs/<slug>/`：run_pipeline/package_asset 原始产物与 raw_answer
- `tests/results/t01_run.log`、`tests/results/t02_t10_run.log`、`tests/results/t02_t09_t10_retry.log`：完整命令输出
- `tests/results/package_templates.log`：模板打包独立复跑日志（t11/t12）；其路径输出指向 `/tmp/package_chest_log`、`/tmp/package_stairs_log`，与 summary/evidence 中记载的正式产物路径 `tests/runs/chest/resourcepack`、`tests/runs/stone_brick_stairs/resourcepack` 是不同的独立复跑产物。
