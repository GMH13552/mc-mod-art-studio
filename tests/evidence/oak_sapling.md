# oak_sapling 运行证据

- 命令：`python3 run_pipeline.py --query "橡树树苗" --form cross --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/oak_sapling --package`
- 执行日期：2026-09-05 (UTC)
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- form：cross
- 产物：
  - `tests/runs/oak_sapling/sprite.png`
- raw_answer sha256：44b896089c188c600dc05950cc36f87ed2b559122807340cad5a571937556a46
- PNG 尺寸：
  - `sprite`: 16x16
- check_pixel_asset 命令：
  - `python3 check_pixel_asset.py tests/runs/oak_sapling/sprite.png --expected-size 16x16 --out tests/reports/oak_sapling.json`
- check_pixel_asset 结果：FAIL
  - sprite: FAIL (opaque=32 bbox=[5, 5, 11, 16] border=False palette=True)
- 观察与问题：
  - run_status: PIPELINE PASS
  - semantic drift: concept描述含有 "杖/晶体/蘑菇/斧头" 等自证/合成索引特征
