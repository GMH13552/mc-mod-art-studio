# glowstone v2 运行证据

- 命令：`python3 run_pipeline.py --query "荧石" --form block_multi --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/v2/glowstone --package`
- 执行日期：2026-09-05 (UTC)
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- form：block_multi
- pipeline 状态：PIPELINE PASS
- check 条目判定：FAIL

## 产物
- top：`tests/runs/v2/glowstone/assets/mcmod/textures/block/q_836777f3_top.png`
  - 尺寸：True opaque=64 bbox=[4, 4, 12, 12]
- side：`tests/runs/v2/glowstone/assets/mcmod/textures/block/q_836777f3_side.png`
  - 尺寸：True opaque=88 bbox=[4, 3, 12, 14]
- bottom：`tests/runs/v2/glowstone/assets/mcmod/textures/block/q_836777f3_bottom.png`
  - 尺寸：True opaque=72 bbox=[4, 4, 12, 13]
- raw_answer：`tests/runs/v2/glowstone/raw_answer.txt`
- raw_answer sha256：`560c00dbd4b1602ce0877174a882d517fdeacbe69ffb6ac3dc8eec9c9e9cfc2c`

## check_pixel_asset 结果
- top：PASS（`tests/reports/v2/glowstone_top.json`）
  - bbox_ok=True border_ok=True palette_ok=True
- side：PASS（`tests/reports/v2/glowstone_side.json`）
  - bbox_ok=True border_ok=True palette_ok=True
- bottom：FAIL（`tests/reports/v2/glowstone_bottom.json`）
  - bbox_ok=True border_ok=True palette_ok=False

## 观察与问题
- 未通过原因：bottom: 色阶不足
