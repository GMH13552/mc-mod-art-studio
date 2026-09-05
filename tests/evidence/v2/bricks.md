# bricks v2 运行证据

- 命令：`python3 run_pipeline.py --query "红砖" --form block_multi --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/v2/bricks --package`
- 执行日期：2026-09-05 (UTC)
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- form：block_multi
- pipeline 状态：PIPELINE PASS
- check 条目判定：FAIL

## 产物
- top：`tests/runs/v2/bricks/assets/mcmod/textures/block/q_7ea27816_top.png`
  - 尺寸：True opaque=169 bbox=[1, 1, 14, 14]
- side：`tests/runs/v2/bricks/assets/mcmod/textures/block/q_7ea27816_side.png`
  - 尺寸：True opaque=169 bbox=[1, 1, 14, 14]
- bottom：`tests/runs/v2/bricks/assets/mcmod/textures/block/q_7ea27816_bottom.png`
  - 尺寸：True opaque=169 bbox=[1, 1, 14, 14]
- raw_answer：`tests/runs/v2/bricks/raw_answer.txt`
- raw_answer sha256：`95ff83de1f979cb50a1cbbe1ea521cd2bbabd62741847d68cb7b6d8ada52b2d6`

## check_pixel_asset 结果
- top：FAIL（`tests/reports/v2/bricks_top.json`）
  - bbox_ok=True border_ok=True palette_ok=False
- side：FAIL（`tests/reports/v2/bricks_side.json`）
  - bbox_ok=True border_ok=True palette_ok=False
- bottom：FAIL（`tests/reports/v2/bricks_bottom.json`）
  - bbox_ok=True border_ok=True palette_ok=False

## 观察与问题
- 未通过原因：top: 色阶不足；side: 色阶不足；bottom: 色阶不足
