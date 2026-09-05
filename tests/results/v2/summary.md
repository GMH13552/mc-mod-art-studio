# v2 广谱测试结果汇总（t4-improve）

- 日期：2026-09-05 (UTC)
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- 来源：tests/test_set.md t01-t10，使用 `run_pipeline.py` 在线 LLM 生成；t11/t12 未重跑（package 在 v1 已稳定）。
- 最终状态：**t01-t10 全部 `PIPELINE: PASS`**；其中 t02/t06/t10 首次/中途曾因全透明被非空门禁拦截，重试后得到非空图。

## 本 v2 关键改动

1. `run_pipeline.py` 增加非空门禁：生成的任何 PNG 不透明像素为 0 时输出 `PIPELINE: FAIL`（明确原因），不再错误 PASS。
2. `text_to_texture.py` 容错：
   - `PALETTE` 行允许行尾 `#` 注释（如 `0: #e0e0e0 # readme`）。
   - 64x32/64x64 entity_uv 索引网格允许裁剪多出的尾行（包括 v1 的全 `-1` 行，以及 v2 出现的非全 `-1` 多余行），不再因 `unexpected extra data after index grid` 整体 FAIL。
3. 合成检索索引中性化：不再以“异形水晶法杖/蘑菇/火焰棒/蓝水晶”为特征源，改为常见原版类资产名（stone/dirt/bricks/glowstone/bow/golden_apple/poppy/pig/creeper 等），并增加 `虞美人 → poppy` 别名与花/弓形状映射。
4. Prompt 防漂移：run_pipeline 紧凑 prompt 增加“本体硬约束”，要求必须画 query 本体，参考节点只允许借配色/材质/明暗/尺度；通用像素规则新增“所有 16x16/64x32 贴图保留至少 1px 透明边距”，以通过 bbox 检查。

## v2 汇总表

| ID | slug | query | form | run exit | check verdict | opaque | bbox | border ok | palette ok | pipeline status |
|---|------|-------|------|----------|---------------|--------|------|-----------|-------------|-----------------|
| t01 | diamond_sword | 钻石剑 | item | 0 | PASS | sprite=70 | [4,1,11,15] | True | True | PIPELINE PASS |
| t02 | golden_apple | 金苹果 | item | 0 | FAIL | sprite=89 | [3,2,12,16] | True | True | PIPELINE PASS |
| t03 | bow | 弓 | item | 0 | FAIL | sprite=92 | [2,1,16,16] | True | True | PIPELINE PASS |
| t04 | glowstone | 荧石 | block_multi | 0 | FAIL | top=64; side=88; bottom=72 | top=[4,4,12,12]; side=[4,3,12,14]; bottom=[4,4,12,13] | top=True; side=True; bottom=True | top=True; side=True; bottom=False | PIPELINE PASS |
| t05 | bricks | 红砖 | block_multi | 0 | FAIL | top=169; side=169; bottom=169 | top=[1,1,14,14]; side=[1,1,14,14]; bottom=[1,1,14,14] | top=True; side=True; bottom=True | top=False; side=False; bottom=False | PIPELINE PASS |
| t06 | lapis_block | 青金石块 | block_multi | 0 | FAIL | top=60; side=52; bottom=52 | top=[4,3,12,12]; side=[4,5,12,13]; bottom=[4,6,12,14] | top=False; side=False; bottom=False | top=True; side=True; bottom=True | PIPELINE PASS |
| t07 | poppy | 虞美人 | cross | 0 | FAIL | sprite=98 | [3,1,13,16] | True | True | PIPELINE PASS |
| t08 | oak_sapling | 橡树树苗 | cross | 0 | FAIL | sprite=42 | [5,5,11,16] | True | False | PIPELINE PASS |
| t09 | pig | 猪 | entity_uv | 0 | PASS | sprite=319 | [16,6,46,17] | True | True | PIPELINE PASS |
| t10 | creeper | 苦力怕 | entity_uv | 0 | FAIL | sprite=44 | [19,12,30,16] | True | False | PIPELINE PASS |

## v1 vs v2 对比（t01-t10）

| 指标 | v1 | v2 | Δ |
|------|----|----|---|
| PIPELINE PASS 条目 | 8/10 = 80.0% | 10/10 = 100.0% | +20.0pp |
| 条目 check PASS（整项全 face 通过） | 1/10 = 10.0% | 2/10 = 20.0% | +10.0pp |
| PNG check PASS 率 | 3/14 = 21.4% | 4/16 = 25.0% | +3.6pp |
| PNG 非空率 | 7/14 = 50.0% | 16/16 = 100.0% | +50.0pp |
| PNG bbox 可辨率 | 3/14 = 21.4% | 12/16 = 75.0% | +53.6pp |
| PNG 边框率 | 5/14 = 35.7% | 13/16 = 81.3% | +45.5pp |
| PNG 色阶率 | 6/14 = 42.9% | 10/16 = 62.5% | +19.6pp |

## 说明

- 非空率提升主要来自非空门禁 + 检索中性化 + 透明边距/本体硬约束 prompt；v2 最终所有生成的 PNG 均非空。
- check PASS 率提升是**实质性但有限**：t01 钻石剑、t09 猪整项 PASS，t04 荧石 top/side 两 face PASS（bottom 色阶不足）。
- 仍存在的失败原因：t02 金苹果底边贴边（bbox false）；t03 弓右侧贴边；t04 底部色阶不足；t05 红砖三面色阶不足；t06 青金石三面描边不足；t07 虞美人底边贴边；t08 橡树树苗底边贴边且色阶不足；t10 苦力怕色阶不足。
- t11/t12 未重跑：v1 已验证 `package_asset --template chest|stairs` 稳定，本次改动未触及模板打包路径。

## 文件

- `tests/results/v2/summary.json`：结构化逐项指标
- `tests/results/v2/summary.md`：本文
- `tests/results/v2/*.log`：t01-t10 完整命令输出（含 retry 日志）
- `tests/reports/v2/*.json`：每张 PNG 的 `check_pixel_asset` 证据
- `tests/runs/v2/<slug>/`：run_pipeline 原始产物与 raw_answer
