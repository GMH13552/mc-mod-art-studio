# creeper 运行证据

- 命令：`python3 run_pipeline.py --query "苦力怕" --form entity_uv --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/creeper --package`
- 执行日期：2026-09-05 (UTC)
- 仓库 commit：`02ec21bbf537558aadcee5025f93044a06f3b1e0`
- form：entity_uv
- 产物：
  - `tests/runs/creeper/raw_answer.txt`（7036 字节）
- raw_answer sha256：`tests/runs/creeper/raw_answer.txt` → `35f5dd0b669a7d767430f2f8b3e77126d931a51f3238869fa955361f79709e74`
- PNG 尺寸：无 PNG 生成
- check_pixel_asset 命令：
- check_pixel_asset 结果：N/A
- 观察与问题：
  - run_status: PIPELINE FAIL: unexpected extra data after index grid (LLM output 33 rows for 64x32; raw_answer all -1; no PNG)
  - raw_answer 校正：raw_answer.txt 存在且为全 -1（2112 个索引均为 -1），但因 33 行（期望 32）仍被 parser 判为 unexpected extra data，未生成 PNG。
  - semantic drift: concept描述含有 "杖/晶体/蘑菇/斧头" 等自证/合成索引特征
