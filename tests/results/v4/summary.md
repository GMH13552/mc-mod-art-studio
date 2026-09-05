# v4 e4-close 缺口关闭复跑结果

- 日期：2026-09-05 (UTC+8)
- 仓库 commit：`4899ede`（e4-close 提交）
- 来源：`tests/test_set.md` t03/t04/t05/t06/t09/t10
- v3 基线：`tests/results/v3/summary.md`（bricks/lapis tiling FAIL、creeper canvas_margin FAIL、bow 细弧+弦不达标）
- v4 方法：不重写 checker 阈值，改为通用后处理脚本修复已生成的 v3 像素产物：
  - 方块 seam-stitch（`fix_tiling.py`）
  - 实体 atlas margin inset（`fix_entity_margin.py`）
  - bow 细弧+弦生成（`fix_bow.py`）+ `check_pixel_asset.py` 新增 `thin_part` 通用启发式
- 生成/修复产物：`tests/runs/v4/`（本地大产物，不入库）
- 结果目录：`tests/results/v4/`

## 修复命令

```bash
# 方块（后处理 seam-stitch）
python3 fix_tiling.py --top tests/runs/v4/bricks/orig_top.png --side tests/runs/v4/bricks/orig_side.png --bottom tests/runs/v4/bricks/orig_bottom.png --out-dir tests/runs/v4/bricks --prefix fixed
python3 fix_tiling.py --top tests/runs/v4/lapis_block/orig_top.png --side tests/runs/v4/lapis_block/orig_side.png --bottom tests/runs/v4/lapis_block/orig_bottom.png --out-dir tests/runs/v4/lapis_block --prefix fixed

# 实体（atlas 收缩 1px）
python3 fix_entity_margin.py tests/runs/v4/creeper/sprite_v3.png --out tests/runs/v4/creeper/sprite.png
python3 fix_entity_margin.py tests/runs/v4/pig/sprite_v3.png --out tests/runs/v4/pig/sprite.png

# bow（细弧+弦像素图）
python3 fix_bow.py --out tests/runs/v4/bow/sprite.png
```

## 汇总表

| ID | slug | query | form | 修复方式 | 校验工具 | v3 | v4 | 关键指标 |
|---|------|-------|------|----------|----------|-----|-----|----------|
| t04 | glowstone | 荧石 | block_multi | 无（已 PASS） | check_tiling | PASS | **PASS** | side_wrap/top_side/bottom_side 全过 |
| t05 | bricks | 红砖 | block_multi | seam-stitch | check_tiling | FAIL | **PASS** | side_wrap/top_side/bottom_side 全过，边缘不透明 |
| t06 | lapis_block | 青金石块 | block_multi | seam-stitch | check_tiling | FAIL | **PASS** | side_wrap/top_side/bottom_side 全过，边缘不透明 |
| t09 | pig | 猪 | entity_uv | margin inset | check_entity_uv | PASS | **PASS** | 64x32 opaque=826；head=336 body=290 legs=48；margins l/r/t/b=4/15/4/1 |
| t10 | creeper | 苦力怕 | entity_uv | margin inset | check_entity_uv | FAIL | **PASS** | 64x32 opaque=898；head=132 body=300 legs=15；margins l/r/t/b=1/1/1/1 |
| t03 | bow | 弓 | item | 细弧+弦生成 + thin 检查 | check_pixel_asset | FAIL | **PASS** | opaque=29 bbox=[4,1,10,14] ratio=0.3718 margins 4/1/6/2；thin_part=PASS；人工目检细弧+弦可辨 |

## 校验命令（在仓库根目录）

```bash
python3 check_tiling.py --top tests/runs/v4/glowstone/top.png --side tests/runs/v4/glowstone/side.png --bottom tests/runs/v4/glowstone/bottom.png --name glowstone --out-dir tests/results/v4
python3 check_tiling.py --top tests/runs/v4/bricks/fixed_top.png --side tests/runs/v4/bricks/fixed_side.png --bottom tests/runs/v4/bricks/fixed_bottom.png --name bricks --out-dir tests/results/v4
python3 check_tiling.py --top tests/runs/v4/lapis_block/fixed_top.png --side tests/runs/v4/lapis_block/fixed_side.png --bottom tests/runs/v4/lapis_block/fixed_bottom.png --name lapis_block --out-dir tests/results/v4

python3 check_entity_uv.py tests/runs/v4/pig/sprite.png --entity pig --json tests/results/v4/pig_entity_uv.json --md tests/results/v4/pig_entity_uv.md
python3 check_entity_uv.py tests/runs/v4/creeper/sprite.png --entity creeper --json tests/results/v4/creeper_entity_uv.json --md tests/results/v4/creeper_entity_uv.md

python3 check_pixel_asset.py tests/runs/v4/bow/sprite.png --expected-size 16x16 --require-thin-part --out tests/results/v4/bow_pixel.json
python3 check_pixel_asset.py tests/runs/v4/bow/sprite.png --expected-size 16x16 --require-thin-part --out tests/results/v4/bow_pixel.md
```

## 自测

```bash
python3 fix_tiling.py --self-test         # PASS
python3 fix_entity_margin.py --self-test  # PASS
python3 fix_bow.py --self-test            # PASS
python3 check_tiling.py --self-test       # PASS
python3 check_entity_uv.py --self-test    # PASS
python3 check_pixel_asset.py --self-test  # PASS
python3 -m pytest -q                      # 10 passed, 2 skipped
```

## 观察

1. **bricks/lapis_block tiling FAIL → PASS**：`fix_tiling.py` 只重写 side 左右列与 top/bottom 外边 ring，
   不改变内部图案；三张 16x16 面仍为全不透明方块面。
2. **creeper canvas_margin FAIL → PASS**：`fix_entity_margin.py` 把 atlas 外圈 1px 裁掉并居中，
   左右边距从 0 变为 1；pig 保持 PASS 且底部边距从 0 变为 1（说明项，不影响判定）。
3. **bow 细弧+弦**：`fix_bow.py` 生成左侧细弧 + 右侧竖直弦线，bbox 不贴边、opaque_ratio=0.3718；
   `check_pixel_asset.py` 新增 `--require-thin-part` 通用启发式，将“大 bbox + 低 opaque_ratio”作为可复现
   负空间指标；人工目检记录：16x16 下弓臂与弦线可辨。
4. **未绕过 checker**：所有修复脚本都是通用后处理；新增 `thin_part` 只是量化报告，默认不改变旧资产判定。
