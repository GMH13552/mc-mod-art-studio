# Reusable Reviewer Checklist (v2 Broad-Spectrum Pixel/Summary Review)

- 用途：任何 reviewer 或 reviewer subagent 可据此对 `tests/results/v2/` 做一次**独立、可复现**复核。
- 不修改任何 `tests/` 数据；只读证据，输出到独立的 `evidence/` 与 `/tmp/`。
- 不使用 LLM 重新生成；只重跑已有 `check_pixel_asset.py` 与聚合统计脚本。

## 1. 输入证据路径

| 类型 | 路径 |
|---|---|
| 汇总文档 | `tests/results/v2/summary.md` |
| 结构化汇总 | `tests/results/v2/summary.json` |
| 每条目证据 | `tests/evidence/v2/*.md` |
| 每张 PNG 的 checker 证据 | `tests/reports/v2/*.json` |
| 运行日志 | `tests/results/v2/*.log` |
| 生成产物 | `tests/runs/v2/<slug>/sprite.png` 与 `assets/mcmod/textures/block/*.png` |
| 校验器 | `check_pixel_asset.py` |

## 2. 前置检查

- 在仓库根目录执行：`git rev-parse HEAD`，记录被审 commit。
- 确认 `check_pixel_asset.py` 存在并可运行：`python3 check_pixel_asset.py --help`。
- 确认 Pillow 可用：`python3 -c "from PIL import Image; print('Pillow OK')"`。

## 3. 复核步骤

### 步骤 A：阅读证据

1. 阅读 `tests/results/v2/summary.md`，记录声称的 pipeline/check 通过率与改进点。
2. 阅读 `tests/evidence/v2/*.md`，记录每个 slug 声称的：
   - pipeline 状态
   - check 条目判定
   - 每张 PNG 的 opaque / bbox / bbox_ok / border_ok / palette_ok
3. 阅读 `tests/reports/v2/*.json`，确认字段存在且与 evidence 一致。

### 步骤 B：重跑 check_pixel_asset（不调用 LLM）

建议重跑全部 v2 报告；若至少 5 个即可满足最低要求，但全量更稳健。

命令模板：

```bash
cd <repo-root>

# item / cross / block_multi 单面 16x16
python3 check_pixel_asset.py tests/runs/v2/<slug>/sprite.png \
  --expected-size 16x16 --out /tmp/rev_<slug>.json

# entity_uv 64x32
python3 check_pixel_asset.py tests/runs/v2/<slug>/sprite.png \
  --expected-size 64x32 --out /tmp/rev_<slug>.json

# block_multi 三面逐个检查
python3 check_pixel_asset.py <face.png> \
  --expected-size 16x16 --out /tmp/rev_<slug>_<face>.json
```

逐字段比对 `/tmp/rev_*.json` 与 `tests/reports/v2/*.json`：

```python
keys = [
  "opaque_count", "bbox", "margins", "bbox_ok",
  "boundary_pixel_count", "boundary_dark_pixel_count",
  "boundary_dark_ratio", "border_ok", "palette_ok",
  "component_count", "part_separation", "size_ok",
]
# 另比较 verdict.overall 与 input.path
```

判定：所有重跑结果与仓库报告数值一致，则该步 PASS。

### 步骤 C：校验“无空图被记为 PASS”

1. 扫描 `tests/reports/v2/*.json`：
   - 每个 `metrics.opaque_count > 0`
   - 不存在 `opaque_count == 0` 且 `verdict.overall == "PASS"`
2. 运行一个负向自测：
   - 生成一张全透明 16x16 PNG；
   - `python3 check_pixel_asset.py /tmp/rev_empty.png --expected-size 16x16 --out /tmp/rev_empty.json`
   - 期望 `verdict.overall == "FAIL"`、`opaque_count == 0`、exit code 1。
3. 也可运行 `python3 check_pixel_asset.py --self-test`。

### 步骤 D：核对 summary 聚合数字与 reports 一致

从 `tests/reports/v2/*.json` 独立计算：

```text
png_total       = 16
png_nonempty    = count(opaque_count > 0)
png_pass        = count(overall == "PASS")
png_bbox_pass   = count(bbox_ok)
png_border_pass = count(border_ok)
png_palette_pass= count(palette_ok)
item_pass       = count(summary.json items[*].check_verdict == "PASS")
pipeline_pass   = count(summary.json items[*].run_status == "PIPELINE PASS")
```

与 `tests/results/v2/summary.json` 的 `aggregate` 逐项比较。

### 步骤 E（可选）：核对 evidence md 与 reports

可解析 `tests/evidence/v2/*.md` 中的数字并与 `tests/reports/v2/*.json` 比较，或人工抽查。

## 4. Verdict 规则

- **pass**：步骤 B 所有重跑数值一致；步骤 C 无空图被 PASS 且负向自测 FAIL；步骤 D 聚合数字全部一致。
- **borderline**：核心数字一致，但存在非阻断性 gap（如仅抽查 5 个、证据文件轻微缺失、语义未人工核验）。
- **reject**：重跑数值与仓库报告不一致；或存在空图被 PASS；或 summary 聚合数字与 reports 明显不一致；或关键证据缺失。

## 5. 输出证据文件

- 本模板：`evidence/review-template.md`
- 本次复核记录：`evidence/review-1.md`

review-1.md 应包含：

```markdown
# 独立复核记录：v2 广谱测试

- 日期 / reviewer / commit
- 核验范围
- 执行命令/脚本
- 对比结果表
- 结论：pass / borderline / reject
- 可复用步骤（若有）
- 发现的 gap（若有）
```
