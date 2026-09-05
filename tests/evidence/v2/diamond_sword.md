# diamond_sword v2 运行证据

- 命令：`python3 run_pipeline.py --query "钻石剑" --form item --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/v2/diamond_sword --package`
- 执行日期：2026-09-05 (UTC)
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- form：item
- pipeline 状态：PIPELINE PASS
- check 条目判定：PASS

## 产物
- sprite：`tests/runs/v2/diamond_sword/sprite.png`
  - 尺寸：True opaque=70 bbox=[4, 1, 11, 15]
- raw_answer：`tests/runs/v2/diamond_sword/raw_answer.txt`
- raw_answer sha256：`9b7ca21c52f4184c055e6df7fda33850d7c593980c3af005ad4f93bb93871f67`

## check_pixel_asset 结果
- sprite：PASS（`tests/reports/v2/diamond_sword.json`）
  - bbox_ok=True border_ok=True palette_ok=True

## 观察与问题
- 像素检查全部通过。
