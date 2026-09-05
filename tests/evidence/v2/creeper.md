# creeper v2 运行证据

- 命令：`python3 run_pipeline.py --query "苦力怕" --form entity_uv --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/v2/creeper --package`
- 执行日期：2026-09-05 (UTC)
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- form：entity_uv
- pipeline 状态：PIPELINE PASS
- check 条目判定：FAIL

## 产物
- sprite：`tests/runs/v2/creeper/sprite.png`
  - 尺寸：True opaque=44 bbox=[19, 12, 30, 16]
- raw_answer：`tests/runs/v2/creeper/raw_answer.txt`
- raw_answer sha256：`508e365836f310dc43ba7e8ec63fdad81d344ab086023fa0c4728a84e54b5a9f`

## check_pixel_asset 结果
- sprite：FAIL（`tests/reports/v2/creeper.json`）
  - bbox_ok=True border_ok=True palette_ok=False

## 观察与问题
- 未通过原因：sprite: 色阶不足
