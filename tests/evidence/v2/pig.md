# pig v2 运行证据

- 命令：`python3 run_pipeline.py --query "猪" --form entity_uv --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/v2/pig --package`
- 执行日期：2026-09-05 (UTC)
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- form：entity_uv
- pipeline 状态：PIPELINE PASS
- check 条目判定：PASS

## 产物
- sprite：`tests/runs/v2/pig/sprite.png`
  - 尺寸：True opaque=319 bbox=[16, 6, 46, 17]
- raw_answer：`tests/runs/v2/pig/raw_answer.txt`
- raw_answer sha256：`b21b8efa4d850aebb97e2ca6959af8f7d892379c24ad6c0b0ca274c34d3b6f66`

## check_pixel_asset 结果
- sprite：PASS（`tests/reports/v2/pig.json`）
  - bbox_ok=True border_ok=True palette_ok=True

## 观察与问题
- 像素检查全部通过。
