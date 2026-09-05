# 独立复核记录：v3 可拼贴/实体UV/物品/原版不误入复核（r2-review-docs）

- 日期：2026-09-05 (UTC)
- Reviewer：独立 reviewer（本会话）
- 仓库 commit（被审）：`3746c715774ad94acd52edb6f7a0a761cde00fd4`（e3-fix2）
- 工作目录：`/tmp/mc-mod-art-studio-core`
- 复核模板：`evidence/review-template.md` 的独立复核原则

## 核验范围

对 v3 e3-pipeline 的非自证测试结果做一次**独立、可复现**复核，不重新调用 LLM，不修改已有证据。覆盖：

- 方块可拼贴：`tests/results/v3/{glowstone,bricks,lapis_block}_tiling.json` 与对应 `.md`
- 实体原版 UV：`tests/results/v3/{pig,creeper}_entity_uv.json` 与对应 `.md`
- 物品/弓：`tests/results/v3/bow_pixel.json`
- 汇总：`tests/results/v3/summary.md` / `summary.json`
- 自检：`check_tiling.py --self-test`、`check_entity_uv.py --self-test`、`check_pixel_asset.py --self-test`、`pytest -q`
- 原版素材误入库：确认 `vanilla_entity_ref/` 未进入 git 跟踪，且没有原版 `pig.png` / `creeper.png`

## 执行命令

### 1. 前置自检

```bash
cd /tmp/mc-mod-art-studio-core
python3 check_tiling.py --self-test      # PASS
python3 check_entity_uv.py --self-test   # PASS
python3 check_pixel_asset.py --self-test # PASS
python3 -m pytest -q                     # 10 passed, 2 skipped
```

结果：4 项均通过。

### 2. 重跑 v3 校验器（从本地 `tests/runs/v3` 实际 PNG 重跑，而非读取已有报告）

```bash
# 方块 tiling（三组）
python3 check_tiling.py --top tests/runs/v3/glowstone/assets/mcmod/textures/block/q_836777f3_top.png --side ..._side.png --bottom ..._bottom.png --name glowstone --out-json /tmp/rev_glowstone_tiling.json
python3 check_tiling.py --top tests/runs/v3/bricks/... --name bricks --out-json /tmp/rev_bricks_tiling.json
python3 check_tiling.py --top tests/runs/v3/lapis_block/... --name lapis_block --out-json /tmp/rev_lapis_block_tiling.json

# 实体 UV（64x32）
python3 check_entity_uv.py tests/runs/v3/pig/sprite.png --entity pig --json /tmp/rev_pig_entity_uv.json
python3 check_entity_uv.py tests/runs/v3/creeper/sprite.png --entity creeper --json /tmp/rev_creeper_entity_uv.json

# 物品（弓）
python3 check_pixel_asset.py tests/runs/v3/bow/sprite.png --expected-size 16x16 --out /tmp/rev_bow_pixel.json
```

所有命令与仓库 `tests/results/v3/*.json` 的最终 verdict 一致；非零退出码仅出现在预期 FAIL 的报告上。

### 3. 结构化比对重跑结果 vs 仓库证据

逐字段比较 `status/checks/regions/metrics/opaque/bbox/failed_checks` 等关键字段：

- `glowstone_tiling.json`：`status=PASS`，`checks` 全等，仅 `output_files` 未写入（重跑未指定 `--out-dir`）。
- `bricks_tiling.json`：`status=FAIL`，`failed_checks` 与 `checks` 全等。
- `lapis_block_tiling.json`：`status=FAIL`，`failed_checks` 与 `checks` 全等。
- `pig_entity_uv.json`：`status=PASS`，`checks/regions/summary` 全等，仅 `checked_at` 时间戳不同。
- `creeper_entity_uv.json`：`status=FAIL`，`checks/regions/summary` 全等，仅 `checked_at` 时间戳不同。
- `bow_pixel.json`：与重跑结果**完全一致**（含 metrics 与 verdict）。

结论：6 份 v3 证据全部可复现，无数字/判定不一致。

## 复核明细

### 方块可拼贴（check_tiling）

| 资产 | 仓库状态 | 重跑状态 | 关键失败/通过 | 复现 |
|---|---|---:|---|---|
| glowstone | PASS | PASS | side_wrap / top_side / bottom_side 全部 PASS，opaque 边缘 16/16 | ✅ |
| bricks | FAIL | FAIL | top_side 四边 max_diff=116/32，transparent_pairs=0/16 | ✅ |
| lapis_block | FAIL | FAIL | side_wrap max_diff=64/32；bottom_side.right max_diff=64/32 | ✅ |

三组 tiling 输出的三张 16x16 面均为全不透明方块面（opaque=256），确认已脱离 v2 的透明剪影，但 bricks/lapis_block 的边缘连续性仍未通过。

### 实体原版 UV（check_entity_uv）

| 资产 | 仓库状态 | 重跑状态 | 尺寸 | opaque | head/body/legs | 失败项 |
|---|---|---:|---:|---:|---|---|
| pig | PASS | PASS | 64x32 | 858 | 336 / 310 / 48 | 无（bottom margin=0 为说明项） |
| creeper | FAIL | FAIL | 64x32 | 920 | 132 / 300 / 16 | canvas_margin left=0 right=0 |

两个实体的标准区域（head/body/legs）在重跑中全部非空；pig 满足左右边距与区域占位，creeper 因 atlas 左右触边被判 FAIL。这与 summary 中“标准 atlas 区域非空 + 新增 canvas_margin 后 creeper 不通过”的表述一致。

### 物品（bow / check_pixel_asset）

| 指标 | 仓库值 | 重跑值 |
|---|---|---:|---:|
| overall | FAIL | FAIL |
| opaque_count | 74 | 74 |
| bbox | [1,2,13,16] | [1,2,13,16] |
| opaque_ratio | 0.4405 | 0.4405 |
| bbox_ok | false | false |
| failed_checks | ["bbox"] | ["bbox"] |

bow 负空间指标满足（opaque_ratio<=0.8），但底部贴边导致 bbox FAIL；目检结论“细弧+弦不完全达标”由 summary 作为人工观察保留，不在此次像素复核范围内。

## 汇总一致性抽查

- `tests/results/v3/summary.md` 的每行关键数字与对应 JSON/MD 一致：
  - glowstone opaque=256；bricks/lapis_block opaque=256；
  - pig opaque=858、regions 336/310/48、PASS；
  - creeper opaque=920、regions 132/300/16、FAIL(canvas_margin)；
  - bow opaque=74、bbox=[1,2,13,16]、FAIL(bbox)。
- `tests/results/v3/summary.json` 中 t10 `check_status` 已从旧版 PASS 修正为 FAIL，`failed_checks` 记录 canvas_margin；与 `creeper_entity_uv.json` 一致。
- `summary.json` 的 `self_tests` 记录与本次实际自检结果一致（PASS/PASS/PASS/PASS）。

## 原版素材不误入库

- `git ls-files | grep -E '(pig|creeper).*(png|PNG)$'` 无输出。
- `git ls-files | grep -i vanilla` 仅有 `evidence/entity_uv_pig_vanilla.json|.md`、`evidence/entity_uv_creeper_vanilla.json|.md` 这类**文本证据/元数据**，不是原版 PNG。
- `git status --ignored --short` 显示 `!! vanilla_entity_ref/`：本地纸质 UV 模板目录已被 `.gitignore` 排除，未入库。
- 仓库中被跟踪的 PNG 只有项目示例与展示图（`examples/...`、`showcase*.png`）。

## 结论

**pass**

- v3 的 3 组 tiling、2 组 entity_uv、1 组 item/bow 证据全部可从 `tests/runs/v3` 实际 PNG 重跑复现，数值与判定一致。
- 自检与 pytest 均通过。
- 未发现原版实体 PNG（`pig.png` / `creeper.png` / `vanilla_entity_ref/`）被 git 跟踪。
- summary 中 t10 的 check_status/失败项已与 JSON/MD 对齐。

## 发现的 gap / 非阻塞说明

1. **语义/审美未重审**：bow 的“细弧+弦”目检、creeper 的“视觉简化几何”依赖人工判断，本次只复核像素检查器与汇总一致性。
2. **creeper 仍 FAIL**：不是证据造假，而是真实存在的 atlas 左右触边；若后续要提升为可用实体贴图，需要让 LLM 在 64x32 画布内保留左右至少 1px 空边。
3. **bricks/lapis_block tiling 仍 FAIL**：非空门禁已通过，但顶/侧/底边缘连续性未全部满足；属于后续像素对齐工作。
4. **`tests/runs/` 不入库**：本次复核使用了本地 `tests/runs/v3` 产物；克隆仓库后需按 `tests/README.md` 重新生成才能重跑同类证据。

## 文件

- `evidence/review-2.md`（本记录）
- `evidence/review-1.md`（v2 复核）
- `evidence/review-template.md`（可复用模板）
