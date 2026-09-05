# 独立复核记录：v2 广谱测试（t5-review 任务）

- 日期：2026-09-05 (UTC)
- Reviewer：独立 reviewer（本会话）
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- 工作目录：`/tmp/mc-mod-art-studio-core`
- 复核模板：`evidence/review-template.md`

## 核验范围

对 `tests/results/v2/` 的广谱测试证据做一次**独立复核**，覆盖：

- `tests/results/v2/summary.md`
- `tests/results/v2/summary.json`
- `tests/evidence/v2/*.md`
- `tests/reports/v2/*.json`
- `tests/runs/v2/<slug>/` 下实际生成的 PNG（作为 check_pixel_asset 输入）
- `check_pixel_asset.py`

复核限制：只重跑像素级/聚合统计校验，未重新调用 LLM 或重跑 `run_pipeline.py` 生成流程；未做人工语义审美判定。

## 执行命令

### 1. 重跑全部 16 张 v2 PNG 的 `check_pixel_asset`

从仓库根目录执行（脚本化，逐个生成到 `/tmp/rev_*.json`）：

```bash
cd /tmp/mc-mod-art-studio-core
python3 - <<'PY'
import json, subprocess, os

summary=json.load(open('tests/results/v2/summary.json'))
face_to_path={}
for item in summary['items']:
    slug=item['slug']; form=item['form']
    exp='64x32' if form=='entity_uv' else '16x16'
    for f in item['faces']:
        face_to_path[os.path.basename(f['report'])]=(f['path'], exp)

for rep,(png,exp) in sorted(face_to_path.items()):
    out='/tmp/rev_'+rep.replace('.json','')+'.json'
    r=subprocess.run(['python3','check_pixel_asset.py',png,'--expected-size',exp,'--out',out],
                     cwd='/tmp/mc-mod-art-studio-core',capture_output=True,text=True)
    print(f'{rep}: exit={r.returncode}')
PY
```

全部 16 次运行均成功（PASS 的报告 exit 0，FAIL 的报告 exit 1，符合脚本设计）。

### 2. 对比重跑结果与仓库 `tests/reports/v2/*.json`

比对字段：

```text
opaque_count, bbox, margins, bbox_ok,
boundary_pixel_count, boundary_dark_pixel_count, boundary_dark_ratio,
border_ok, palette_ok, component_count, part_separation, size_ok,
verdict.overall, input.path
```

结果：**16/16 完全一致，0 个 mismatch**。

### 3. 校验“无空图被记为 PASS”

- 扫描 `tests/reports/v2/*.json`：所有 report 的 `metrics.opaque_count > 0`；不存在 `opaque_count == 0` 且 `overall == PASS`。
- `tests/results/v2/summary.json` 的 items 中 `all_transparent` 全部为 `false`。
- 负向自测：生成全透明 PNG 并运行 `check_pixel_asset.py`：
  - `python3 check_pixel_asset.py /tmp/rev_empty.png --expected-size 16x16 --out /tmp/rev_empty.json`
  - exit code = 1
  - verdict = `FAIL`
  - `opaque_count = 0`

### 4. 核对 summary 聚合数字与 reports 一致

从 `tests/reports/v2/*.json` 独立重新计算，并与 `tests/results/v2/summary.json` 的 `aggregate` 比较。

| 指标 | summary.json | 独立重算 | 一致 |
|---|---|---:|---:|---|
| t01_t10_png_total | 16 | 16 | ✅ |
| t01_t10_png_nonempty | 16 | 16 | ✅ |
| t01_t10_png_nonempty_rate | 1.0 | 1.0 | ✅ |
| t01_t10_png_pass | 4 | 4 | ✅ |
| t01_t10_png_pass_rate | 0.25 | 0.25 | ✅ |
| t01_t10_png_bbox_pass | 12 | 12 | ✅ |
| t01_t10_png_bbox_pass_rate | 0.75 | 0.75 | ✅ |
| t01_t10_png_border_pass | 13 | 13 | ✅ |
| t01_t10_png_border_pass_rate | 0.8125 | 0.8125 | ✅ |
| t01_t10_png_palette_pass | 10 | 10 | ✅ |
| t01_t10_png_palette_pass_rate | 0.625 | 0.625 | ✅ |
| t01_t10_item_pass | 2 | 2 | ✅ |
| t01_t10_item_total | 10 | 10 | ✅ |
| t01_t10_pipeline_pass | 10 | 10 | ✅ |

同时逐 face 核对 `summary.json` items 中的 `opaque/bbox/bbox_ok/border_ok/palette_ok/verdict` 与对应 `tests/reports/v2/*.json`：16 个 face 全部一致。

## 复跑对比明细

| 报告 | 实际 verdict | opaque | bbox | bbox_ok | border_ok | palette_ok | repo 一致 |
|---|---|---:|---:|---:|---:|---:|---|
| diamond_sword.json | PASS | 70 | [4,1,11,15] | True | True | True | ✅ |
| golden_apple.json | FAIL | 89 | [3,2,12,16] | False | True | True | ✅ |
| bow.json | FAIL | 92 | [2,1,16,16] | False | True | True | ✅ |
| glowstone_top.json | PASS | 64 | [4,4,12,12] | True | True | True | ✅ |
| glowstone_side.json | PASS | 88 | [4,3,12,14] | True | True | True | ✅ |
| glowstone_bottom.json | FAIL | 72 | [4,4,12,13] | True | True | False | ✅ |
| bricks_top.json | FAIL | 169 | [1,1,14,14] | True | True | False | ✅ |
| bricks_side.json | FAIL | 169 | [1,1,14,14] | True | True | False | ✅ |
| bricks_bottom.json | FAIL | 169 | [1,1,14,14] | True | True | False | ✅ |
| lapis_block_top.json | FAIL | 60 | [4,3,12,12] | True | False | True | ✅ |
| lapis_block_side.json | FAIL | 52 | [4,5,12,13] | True | False | True | ✅ |
| lapis_block_bottom.json | FAIL | 52 | [4,6,12,14] | True | False | True | ✅ |
| poppy.json | FAIL | 98 | [3,1,13,16] | False | True | True | ✅ |
| oak_sapling.json | FAIL | 42 | [5,5,11,16] | False | True | False | ✅ |
| pig.json | PASS | 319 | [16,6,46,17] | True | True | True | ✅ |
| creeper.json | FAIL | 44 | [19,12,30,16] | True | True | False | ✅ |

## 结论

**pass**

- 所有 16 张 v2 PNG 的 `check_pixel_asset` 重跑结果与仓库 `tests/reports/v2/*.json` 数值/判定完全一致。
- 未发现空图被标记为 PASS；负向自测证明全透明图会被正确判 FAIL。
- `tests/results/v2/summary.json` 的 PNG/条目聚合数字与 `tests/reports/v2/*.json` 独立重算结果完全一致。
- `tests/evidence/v2/*.md` 中记录的关键数字与 `tests/reports/v2/*.json` 一致（抽查与结构化比对均未发现冲突）。

## 可复用步骤

后续复核 v2 或同类广谱测试请直接使用 `evidence/review-template.md`：

1. 读 `tests/results/v2/summary.md` 与 `tests/evidence/v2/*.md`。
2. 读 `tests/reports/v2/*.json`。
3. 用 `check_pixel_asset.py` 对每个 PNG（按 form 传 `--expected-size 16x16` 或 `64x32`）重跑并输出到 `/tmp/rev_*.json`。
4. 逐字段重跑结果与仓库报告比对。
5. 扫描空图并做全透明负向自测。
6. 从 reports 独立计算聚合指标，与 `summary.json` 比对。
7. 记录 `evidence/review-N.md`，输出 pass / borderline / reject。

## 发现的 gap / 限制

- 本次复核未重新调用 LLM、未重跑 `run_pipeline.py`；因此不验证生成过程是否可在线复现，只验证已产生的像素证据可离线复现。
- `check_pixel_asset.py` 的 `part_separation` 默认仅报告（`separation_required=false`），不纳入 PASS/FAIL；这符合 v2 当前验收口径，但不是对“形状/部件分离”的强校验。
- 未做像素内容的人眼/语义鉴赏；复核范围限定为通用像素证据与汇总一致性。

## 文件

- `evidence/review-template.md`
- `evidence/review-1.md`
