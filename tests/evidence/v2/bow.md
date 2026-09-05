# bow v2 运行证据

- 命令：`python3 run_pipeline.py --query "弓" --form item --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/v2/bow --package`
- 执行日期：2026-09-05 (UTC)
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- form：item
- pipeline 状态：PIPELINE PASS
- check 条目判定：FAIL

## 产物
- sprite：`tests/runs/v2/bow/sprite.png`
  - 尺寸：True opaque=92 bbox=[2, 1, 16, 16]
- raw_answer：`tests/runs/v2/bow/raw_answer.txt`
- raw_answer sha256：`7886116cd237532ae46c686bf8f3e3ee132b47fd9cf1640feb87419fd7afd90a`

## check_pixel_asset 结果
- sprite：FAIL（`tests/reports/v2/bow.json`）
  - bbox_ok=False border_ok=True palette_ok=True

## 观察与问题
- 未通过原因：sprite: bbox/贴边
