# diamond_sword 运行证据

- 命令：`python3 run_pipeline.py --query "钻石剑" --form item --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/diamond_sword --package`
- 执行日期：2026-09-05 (UTC)
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- form：item
- 产物：
  - `tests/runs/diamond_sword/sprite.png`
- raw_answer sha256：6e0ac65ae7fe4c148ccaf22498743e41dcfba964dda8a4afb1cb2fb22664b427
- PNG 尺寸：
  - `sprite`: 16x16
- check_pixel_asset 命令：
  - `python3 check_pixel_asset.py tests/runs/diamond_sword/sprite.png --expected-size 16x16 --out tests/reports/diamond_sword.json`
- check_pixel_asset 结果：FAIL
  - sprite: FAIL (opaque=54 bbox=[4, 0, 11, 16] border=True palette=True)
- 观察与问题：
  - run_status: PIPELINE PASS
  - semantic drift: concept描述含有 "杖/晶体/蘑菇/斧头" 等自证/合成索引特征
