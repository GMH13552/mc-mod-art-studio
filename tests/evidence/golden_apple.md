# golden_apple 运行证据

- 命令：`python3 run_pipeline.py --query "金苹果" --form item --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/golden_apple --package`
- 执行日期：2026-09-05 (UTC)
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- form：item
- 产物：
  - `tests/runs/golden_apple/sprite.png`
- raw_answer sha256：1be437a5174a60790055718a59d6a8d832b0ef6feec1f86454d3d9cbb640cf4a
- PNG 尺寸：
  - `sprite`: 16x16
- check_pixel_asset 命令：
  - `python3 check_pixel_asset.py tests/runs/golden_apple/sprite.png --expected-size 16x16 --out tests/reports/golden_apple.json`
- check_pixel_asset 结果：FAIL
  - sprite: FAIL (opaque=0 bbox=None border=False palette=False)
- 观察与问题：
  - run_status: PIPELINE PASS (first attempt exit 1: PALETTE parser error; retry exit 0)
  - semantic drift: concept描述含有 "杖/晶体/蘑菇/斧头" 等自证/合成索引特征
  - 输出为全透明/空纹理（bbox=None, opaque=0），属于“全 -1”退化基线。
