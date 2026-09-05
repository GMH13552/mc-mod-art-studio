# v3 e3-pipeline 非自证测试集复跑结果

- 日期：2026-09-05 (UTC+8)
- 仓库 commit：v3 复跑时工作区基于 `b9bd17dfe52414fbf2f3f1edbb3fe5d50e9d21ff`；e3-fix 已本地提交（未 push）
- e3-fix commit：`8cd7fb794b9c785c13d1377025cc8bdc86b9d50d`
- 来源：`tests/test_set.md` t03/t04/t05/t06/t09/t10
- LLM：`set -a; source /tmp/mc_llm.env; set +a`，`deepseek-chat`
- 生成目录：`tests/runs/v3/{glowstone,bricks,lapis_block,pig,creeper,bow}`
- 结果目录：`tests/results/v3/`

## 汇总表

| ID | slug | query | form | run exit | 校验工具 | 校验结果 | 关键指标 |
|---|------|-------|------|----------|----------|----------|----------|
| t04 | glowstone | 荧石 | block_multi | 0 | check_tiling | **PASS** | top/side/bottom opaque=256；4 项边缘检查全过 |
| t05 | bricks | 红砖 | block_multi | 0 | check_tiling | FAIL | top/side/bottom opaque=256；side_wrap PASS；top_side 4 条边 max_diff=116/32 |
| t06 | lapis_block | 青金石块 | block_multi | 0（初跑解析失败，用现有 raw + parser 容错重跑） | check_tiling | FAIL | top/side/bottom opaque=256；side_wrap max_diff=64/32；bottom_side.right max_diff=64/32 |
| t09 | pig | 猪 | entity_uv | 0（第 3 次 LLM 尝试） | check_entity_uv | **PASS** | 64x32 opaque=858；head=336 body=310 legs=48；margins l/r=4/15 top=4 bottom=0（bottom 为说明项） |
| t10 | creeper | 苦力怕 | entity_uv | 0（初跑 legs=0，重试循环第 1 次即 PASS） | check_entity_uv | **FAIL**（新增 canvas_margin：左右触边） | 64x32 opaque=920；head=132 body=300 legs=16；margins left=0 right=0 top=1 bottom=1 |
| t03 | bow | 弓 | item | 0（第 2 次非空尝试） | check_pixel_asset | FAIL（目检：弓形可辨度有限） | opaque=74/20 bbox=[1,2,13,16] opaque_ratio=0.4405（<=0.8，满足负空间抽查）；bbox FAIL（bottom margin=0） |

## 命令摘要

```bash
# 方块（3 条）
python3 run_pipeline.py --query "荧石" --form block_multi --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/v3/glowstone --package
python3 run_pipeline.py --query "红砖" --form block_multi --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/v3/bricks --package
python3 run_pipeline.py --query "青金石块" --form block_multi --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/v3/lapis_block --package
# 实体（2 条）
python3 run_pipeline.py --query "猪" --form entity_uv --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/v3/pig --package
python3 run_pipeline.py --query "苦力怕" --form entity_uv --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/v3/creeper --package
# 弓（item）
python3 run_pipeline.py --query "弓" --form item --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/v3/bow --package
```

## 校验命令

```bash
# 方块 tiling
python3 check_tiling.py --top tests/runs/v3/glowstone/assets/mcmod/textures/block/q_836777f3_top.png --side ..._side.png --bottom ..._bottom.png --name glowstone --out-dir tests/results/v3
python3 check_tiling.py ... --name bricks --out-dir tests/results/v3
python3 check_tiling.py ... --name lapis_block --out-dir tests/results/v3

# 实体 UV
python3 check_entity_uv.py tests/runs/v3/pig/sprite.png --entity pig --json tests/results/v3/pig_entity_uv.json --md tests/results/v3/pig_entity_uv.md
python3 check_entity_uv.py tests/runs/v3/creeper/sprite.png --entity creeper --json tests/results/v3/creeper_entity_uv.json --md tests/results/v3/creeper_entity_uv.md

# bow
python3 check_pixel_asset.py tests/runs/v3/bow/sprite.png --expected-size 16x16 --out tests/results/v3/bow_pixel.json
```

## 观察与结论

1. **block_multi 已从“透明剪影”变成真正 16x16 全不透明方块面**：三个块类资产的 top/side/bottom
   `opaque_pixels=256`（`opaque_ratio=1.0`），不再是 v2 的全透明/剪影。
2. 但 **tiling 连续性仍只部分通过**：glowstone PASS；bricks 的 `top_side` 边缘与 top 不连续
   （max_diff=116），lapis_block 的 `side_wrap`/`bottom_side.right` 不连续（max_diff=64）。
   这属于“next-level 像素对齐”问题，不是“透明/空图”问题。
3. **entity_uv 已达成标准 atlas 区域非空；新增 canvas_margin 后发现 creeper 左右触边**：
   pig/creeper 均为 64x32、标准区域全部有像素；pig 左右边距 4/15、顶部 4、底部 0（atlas 底部不强制，
   说明项标注）；creeper 左右边距均为 0，新增 `canvas_margin` 检查记为 FAIL。视觉上仍是简化几何，不是原版级细节。
4. **bow 负空间通过，视觉“细弧+弦”未完全达标**：`opaque_ratio=0.4405` 显著低于实心 1.0，
   负空间充足；但人工目检当前 v3 产物是弧形主体 + 灰白边缘，未见清晰独立的弦线，
   因此按“细弧+弦目检”记为不通过（可作为后续视觉 prompt 强化项）。
5. **LLM 非确定性已记录**：pig 前 2 次全透明、第 3 次成功；bow 多次出现全透明/团块/弧形，
   最终保留第 2 次非空尝试作为证据。这符合“LLM 复跑可只跑一部分并说明”的约定。

## 文件

- `tests/results/v3/glowstone_tiling.json|.md`
- `tests/results/v3/bricks_tiling.json|.md`
- `tests/results/v3/lapis_block_tiling.json|.md`
- `tests/results/v3/pig_entity_uv.json|.md`
- `tests/results/v3/creeper_entity_uv.json|.md`
- `tests/results/v3/bow_pixel.json`
- `tests/results/v3/<slug>*.log`（完整命令日志，含 retry/attempt）
