# oak_sapling v2 运行证据

- 命令：`python3 run_pipeline.py --query "橡树树苗" --form cross --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/v2/oak_sapling --package`
- 执行日期：2026-09-05 (UTC)
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- form：cross
- pipeline 状态：PIPELINE PASS
- check 条目判定：FAIL

## 产物
- sprite：`tests/runs/v2/oak_sapling/sprite.png`
  - 尺寸：True opaque=42 bbox=[5, 5, 11, 16]
- raw_answer：`tests/runs/v2/oak_sapling/raw_answer.txt`
- raw_answer sha256：`8efed51fa8ec126156719d46b4c562abda698f208f22741c66bf1420e6f042d1`

## check_pixel_asset 结果
- sprite：FAIL（`tests/reports/v2/oak_sapling.json`）
  - bbox_ok=False border_ok=True palette_ok=False

## 观察与问题
- 未通过原因：sprite: bbox/贴边, 色阶不足
