# bow 运行证据

- 命令：`python3 run_pipeline.py --query "弓" --form item --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/bow --package`
- 执行日期：2026-09-05 (UTC)
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- form：item
- 产物：
  - `tests/runs/bow/sprite.png`
- raw_answer sha256：3b0657377aac8ed7b3c3d311f39730de10816e455ddeebe1fd769ede3b6fb46e
- PNG 尺寸：
  - `sprite`: 16x16
- check_pixel_asset 命令：
  - `python3 check_pixel_asset.py tests/runs/bow/sprite.png --expected-size 16x16 --out tests/reports/bow.json`
- check_pixel_asset 结果：FAIL
  - sprite: FAIL (opaque=120 bbox=[2, 0, 13, 16] border=True palette=True)
- 观察与问题：
  - run_status: PIPELINE PASS
  - semantic drift: concept描述含有 "杖/晶体/蘑菇/斧头" 等自证/合成索引特征
