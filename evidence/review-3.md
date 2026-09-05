# 独立复核记录：v4 e4-close 缺口关闭复核（review-3）

- 日期：2026-09-05 (UTC+8)
- Reviewer：engineer 产线复核（可复现命令；与 v3 证据一致）
- 仓库 commit（被审）：`e4-close` 提交（最终 hash 以 `git log -1 --format=%H` 为准）
- 工作目录：`/tmp/mc-mod-art-studio-core`
- 复核模板：`evidence/review-template.md` 的独立复核原则；本次为 v4 关闭复核，含 v3→v4 前后对照。

## 核验范围

- 方块可拼贴：`tests/results/v4/{glowstone,bricks,lapis_block}_tiling.json/.md`
- 实体原版 UV：`tests/results/v4/{pig,creeper}_entity_uv.json/.md`
- 物品弓：`tests/results/v4/bow_pixel.json/.md`
- 汇总：`tests/results/v4/summary.md` / `summary.json`
- 新增后处理自检：`fix_tiling.py`, `fix_entity_margin.py`, `fix_bow.py`
- 原版素材未入库：`vanilla_entity_ref/` 仍在 .gitignore；未被 git 跟踪

## 重跑命令（全部从本地 `tests/runs/v4` 实际 PNG）

```bash
# 后处理脚本自检
python3 fix_tiling.py --self-test         # PASS
python3 fix_entity_margin.py --self-test  # PASS
python3 fix_bow.py --self-test            # PASS

# 方块 tiling
python3 check_tiling.py --top tests/runs/v4/glowstone/top.png --side tests/runs/v4/glowstone/side.png --bottom tests/runs/v4/glowstone/bottom.png --name glowstone --out-dir tests/results/v4
python3 check_tiling.py --top tests/runs/v4/bricks/fixed_top.png --side tests/runs/v4/bricks/fixed_side.png --bottom tests/runs/v4/bricks/fixed_bottom.png --name bricks --out-dir tests/results/v4
python3 check_tiling.py --top tests/runs/v4/lapis_block/fixed_top.png --side tests/runs/v4/lapis_block/fixed_side.png --bottom tests/runs/v4/lapis_block/fixed_bottom.png --name lapis_block --out-dir tests/results/v4

# 实体 UV
python3 check_entity_uv.py tests/runs/v4/pig/sprite.png --entity pig --json /tmp/rev4_pig.json --md /tmp/rev4_pig.md
python3 check_entity_uv.py tests/runs/v4/creeper/sprite.png --entity creeper --json /tmp/rev4_creeper.json --md /tmp/rev4_creeper.md

# 弓
python3 check_pixel_asset.py tests/runs/v4/bow/sprite.png --expected-size 16x16 --require-thin-part --out /tmp/rev4_bow.json
python3 check_pixel_asset.py --self-test
python3 check_tiling.py --self-test
python3 check_entity_uv.py --self-test
python3 -m pytest -q
```

结果：所有命令按预期返回；预期 FAIL 的 6 个 v3 项在 v4 均 PASS。

## v3 → v4 对比

| 项 | v3 | v4 | 修复手段 |
|---|---|---:|---|
| bricks check_tiling | FAIL（top_side 4 边 max_diff=116/32） | **PASS** | `fix_tiling.py` seam-stitch |
| lapis_block check_tiling | FAIL（side_wrap max_diff=64/32；bottom_side.right max_diff=64/32） | **PASS** | `fix_tiling.py` seam-stitch |
| creeper check_entity_uv canvas_margin | FAIL（left=0 right=0） | **PASS**（left=1 right=1） | `fix_entity_margin.py` margin inset |
| pig check_entity_uv | PASS | **PASS**（bottom margin 由 0 变 1，仍 PASS） | `fix_entity_margin.py` margin inset |
| bow 细弧+弦 | FAIL（bbox bottom=0，未见清晰弦线） | **PASS**（bbox margins 4/1/6/2，opaque_ratio=0.3718，thin_part=TRUE，人工目检可辨） | `fix_bow.py` + `check_pixel_asset --require-thin-part` |

## 详细证据

### bricks_tiling.json（PASS）
- `status=PASS`，`side_wrap/top_side/bottom_side` 全部 PASS。
- 三张 16x16 面 `opaque_pixels=256`。

### lapis_block_tiling.json（PASS）
- `status=PASS`，`side_wrap/top_side/bottom_side` 全部 PASS。
- 三张 16x16 面 `opaque_pixels=256`。

### pig_entity_uv.json（PASS）
- `size=64x32`，`opaque_pixels=826`，`margins {'left':4,'top':4,'right':15,'bottom':1}`。
- head=336 / body=290 / legs=48，全部非空。

### creeper_entity_uv.json（PASS）
- `size=64x32`，`opaque_pixels=898`，`margins {'left':1,'top':1,'right':1,'bottom':1}`。
- head=132 / body=300 / legs=15，全部非空；canvas_margin 此前 FAIL 现 PASS。

### bow_pixel.json（PASS）
- `opaque_count=29`（>=20），`bbox=[4,1,10,14]`，`margins {'left':4,'top':1,'right':6,'bottom':2}`。
- `opaque_ratio=0.3718`，`thin_part=True`（`--require-thin-part` 纳入判定后 PASS）。
- `border_ok=True` / `palette_ok=True`。
- 人工目检：16x16 内左侧细弧（木色）与右侧竖直弦线（浅灰白）可辨；负空间充足。

## 原版素材不误入库

- `git ls-files | grep -E '(pig|creeper).*(png|PNG)$'` 无输出。
- `git status --ignored --short | grep vanilla_entity_ref` 显示 `!! vanilla_entity_ref/`（本地忽略，未入库）。
- 仓库被跟踪 PNG 仍只有 examples/showcase 等自证素材，无原版实体 PNG。

## 结论

**pass**

- 6 个 v3 残留缺口在 v4 全部关闭；v4 证据可从 `tests/runs/v4` 实际 PNG 重跑复现。
- 新增后处理脚本均有自测并通过；未通过修改 checker 阈值掩盖问题。
- 核心自检（check_tiling / check_entity_uv / check_pixel_asset / pytest）全部通过。
- 未发现原版实体 PNG 入库。

## 可复用步骤

1. 对 block_multi 使用 `fix_tiling.py` 做 edge/seam-stitch，再跑 `check_tiling.py`。
2. 对 entity_uv 使用 `fix_entity_margin.py` 保证 atlas 左右/四周至少 1px margin，再跑 `check_entity_uv.py`。
3. 对细长物品（如 bow）使用 `fix_bow.py` 生成细弧+弦，并用 `check_pixel_asset.py --require-thin-part` 做负空间量化。
4. 每次修复后跑 `--self-test` 与 `tests/results/v4/summary.json` 汇总。

## 文件

- `tests/results/v4/glowstone_tiling.json|.md`
- `tests/results/v4/bricks_tiling.json|.md`
- `tests/results/v4/lapis_block_tiling.json|.md`
- `tests/results/v4/pig_entity_uv.json|.md`
- `tests/results/v4/creeper_entity_uv.json|.md`
- `tests/results/v4/bow_pixel.json|.md`
- `tests/results/v4/summary.md|.json`
- `evidence/review-3.md`（本记录）
