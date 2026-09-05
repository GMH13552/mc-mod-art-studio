# poppy 运行证据

- 命令：`python3 run_pipeline.py --query "虞美人" --form cross --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/poppy --package`
- 执行日期：2026-09-05 (UTC)
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- form：cross
- 产物：
  - `tests/runs/poppy/sprite.png`
- raw_answer sha256：d04cf46be0fc41c5e3c09cd9a17cfb5e741c567240f7c79b4650d099dd57542e
- PNG 尺寸：
  - `sprite`: 16x16
- check_pixel_asset 命令：
  - `python3 check_pixel_asset.py tests/runs/poppy/sprite.png --expected-size 16x16 --out tests/reports/poppy.json`
- check_pixel_asset 结果：FAIL
  - sprite: FAIL (opaque=70 bbox=[3, 4, 12, 16] border=False palette=False)
- 观察与问题：
  - run_status: PIPELINE PASS
  - semantic drift: concept描述含有 "杖/晶体/蘑菇/斧头" 等自证/合成索引特征
