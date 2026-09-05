# lapis_block v2 运行证据

- 命令：`python3 run_pipeline.py --query "青金石块" --form block_multi --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/v2/lapis_block --package`
- 执行日期：2026-09-05 (UTC)
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- form：block_multi
- pipeline 状态：PIPELINE PASS
- check 条目判定：FAIL

## 产物
- top：`tests/runs/v2/lapis_block/assets/mcmod/textures/block/q_975291d177f35757_top.png`
  - 尺寸：True opaque=60 bbox=[4, 3, 12, 12]
- side：`tests/runs/v2/lapis_block/assets/mcmod/textures/block/q_975291d177f35757_side.png`
  - 尺寸：True opaque=52 bbox=[4, 5, 12, 13]
- bottom：`tests/runs/v2/lapis_block/assets/mcmod/textures/block/q_975291d177f35757_bottom.png`
  - 尺寸：True opaque=52 bbox=[4, 6, 12, 14]
- raw_answer：`tests/runs/v2/lapis_block/raw_answer.txt`
- raw_answer sha256：`111282636708dd9c43213695a626925bb26e3ee6fa9ca250f53707aed620ede4`

## check_pixel_asset 结果
- top：FAIL（`tests/reports/v2/lapis_block_top.json`）
  - bbox_ok=True border_ok=False palette_ok=True
- side：FAIL（`tests/reports/v2/lapis_block_side.json`）
  - bbox_ok=True border_ok=False palette_ok=True
- bottom：FAIL（`tests/reports/v2/lapis_block_bottom.json`）
  - bbox_ok=True border_ok=False palette_ok=True

## 观察与问题
- 未通过原因：top: 描边不足；side: 描边不足；bottom: 描边不足
