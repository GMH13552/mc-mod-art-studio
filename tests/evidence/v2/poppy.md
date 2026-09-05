# poppy v2 运行证据

- 命令：`python3 run_pipeline.py --query "虞美人" --form cross --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/v2/poppy --package`
- 执行日期：2026-09-05 (UTC)
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- form：cross
- pipeline 状态：PIPELINE PASS
- check 条目判定：FAIL

## 产物
- sprite：`tests/runs/v2/poppy/sprite.png`
  - 尺寸：True opaque=98 bbox=[3, 1, 13, 16]
- raw_answer：`tests/runs/v2/poppy/raw_answer.txt`
- raw_answer sha256：`becfe75c0d3afdecce227ed0d3a260521379e2b710814272895070b86981e3e7`

## check_pixel_asset 结果
- sprite：FAIL（`tests/reports/v2/poppy.json`）
  - bbox_ok=False border_ok=True palette_ok=True

## 观察与问题
- 未通过原因：sprite: bbox/贴边
