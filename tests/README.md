# 测试集运行协议（t1-testset）

> 本协议由 t1 编写；实际执行由 t4（或后续运行 worker）完成。原则：**不只测项目自己生成的样例，也不测用户点名的样例；测试集必须用项目自身 `run_pipeline.py` 执行。**

## 1. 职责边界

- 本目录只定义“测什么”“怎么跑”“记录什么”。
- `tests/test_set.md` 定义 12 个非自证测试条目。
- `tests/runs/`、`tests/reports/`、`tests/evidence/` 由执行时生成，**t1 不运行生成**。
- `check_pixel_asset.py` 为另一 worker 提供的通用 16x16 像素校验脚本；当前仓库根目录已有该脚本（版本 v1.0.0）。若执行时脚本缺失，则记 `PENDING` 并等待其提供。

## 2. 前置条件

- 工作目录：仓库根目录 `/tmp/mc-mod-art-studio-core`（以下命令均在此目录执行）。
- 依赖：`python3`、Pillow（`pip install pillow`）。
- LLM 在线模式：需 `llm_client.py` 可用的 API Key / Base URL / Model，见仓库 `.env.example`。
- 离线模式（仅复跑已有 `raw_answer.txt`）：不需要 LLM，但需要该条目已有 raw_answer。

## 3. 通用执行模板

### 3.1 在线生成（首选，真正跑通 pipeline）

```bash
python3 run_pipeline.py \
  --query "<中文查询>" \
  --form <item|block_multi|cross|entity_uv> \
  --top 5 \
  --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' \
  --out tests/runs/<slug> \
  --package
```

- `--top 5`：保留默认之外的检索宽度，避免只对着 1~3 个参考节点过拟合。
- `--package`：同时生成资源包，覆盖打包环节。
- 禁用“只测自己样例”：`--raw` 只能用于**已有且不是本项目 examples/ 的 raw_answer**，不能直接复用 `examples/alien_crystal_wand/raw_answer.txt` 等自证样本。

### 3.2 离线复跑（当该条目已有外部/中途生成的 raw_answer 时）

```bash
python3 run_pipeline.py \
  --query "<中文查询>" \
  --form <form> \
  --raw tests/runs/<slug>/raw_answer.txt \
  --out tests/runs/<slug> \
  --package
```

### 3.3 只生成 prompt（排查提示词问题，不消费 LLM 输出）

```bash
python3 run_pipeline.py \
  --query "<中文查询>" \
  --form <form> \
  --out tests/runs/<slug> \
  --prompt-only
```

## 4. 12 条测试命令

| ID | slug | query | form | 命令（可替换 `--llm-cmd` 为 `--raw tests/runs/<slug>/raw_answer.txt`） |
|---|---|---|---|---|
| t01 | `diamond_sword` | 钻石剑 | `item` | `python3 run_pipeline.py --query "钻石剑" --form item --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/diamond_sword --package` |
| t02 | `golden_apple` | 金苹果 | `item` | `python3 run_pipeline.py --query "金苹果" --form item --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/golden_apple --package` |
| t03 | `bow` | 弓 | `item` | `python3 run_pipeline.py --query "弓" --form item --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/bow --package` |
| t04 | `glowstone` | 荧石 | `block_multi` | `python3 run_pipeline.py --query "荧石" --form block_multi --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/glowstone --package` |
| t05 | `bricks` | 红砖 | `block_multi` | `python3 run_pipeline.py --query "红砖" --form block_multi --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/bricks --package` |
| t06 | `lapis_block` | 青金石块 | `block_multi` | `python3 run_pipeline.py --query "青金石块" --form block_multi --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/lapis_block --package` |
| t07 | `poppy` | 虞美人 | `cross` | `python3 run_pipeline.py --query "虞美人" --form cross --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/poppy --package` |
| t08 | `oak_sapling` | 橡树树苗 | `cross` | `python3 run_pipeline.py --query "橡树树苗" --form cross --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/oak_sapling --package` |
| t09 | `pig` | 猪 | `entity_uv` | `python3 run_pipeline.py --query "猪" --form entity_uv --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/pig --package` |
| t10 | `creeper` | 苦力怕 | `entity_uv` | `python3 run_pipeline.py --query "苦力怕" --form entity_uv --top 5 --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' --out tests/runs/creeper --package` |
| t11 | `chest` | 箱子 | `block_custom`（扩展） | 见 5.1 |
| t12 | `stone_brick_stairs` | 石砖楼梯 | `block_custom`（扩展） | 见 5.1 |

## 5. `block_custom` 特殊协议

当前 `run_pipeline.py --form` 的 choices 只有 `item/block_multi/cross/entity_uv/auto`，**未暴露 `block_custom`**。这是代码现状（证据：`python3 run_pipeline.py --help`、`build_style_prompt.py` 的 `_VALID_FORMS`）。

因此 t11/t12 不能作为普通测试条目直接交给 `run_pipeline` 一键跑；作为扩展覆盖，采用以下组合。

> **已实测的一键链路缺口（verified-gap，2026-09-05）**
> - `retrieve_assets.py --query "箱子" --top 5 --out tests/retrieval/chest.json` **不能**在本仓库无 `mc_asset_library/library-index.json` 时直接执行：实际报错 `no built-in index found`，exit 2。当前版本只有 `--self-test` 模式会临时生成合成索引，普通模式不会自动使用合成索引。
> - `concept_grounder.py --query "箱子" --form block_custom --template chest --out ...` 在不传 `--retrieval` 时会因缺失索引在内部调用 `retrieve_assets.retrieve()` 而失败（FileNotFoundError）。
> - 因此，**当前不把 t11/t12 的 LLM 生成链路（retrieval → concept → raw）作为可复现测试内容**；t11/t12 在本测试集中的可复现范围是 `package_asset.py --template` 的模板打包。

### 5.1 可复现命令：仅 package template 打包

`package_asset.py` 的内置模板可从 `builtin_models_fallback/` 回退读取，**不需要** `mc_asset_library_full/` 或外部原版素材；不传 `--raw` 时会生成占位纹理，用于验证模板/blockstate/model/texture 打包链路。

```bash
# chest（t11）
python3 package_asset.py \
  --template chest \
  --name chest \
  --out tests/runs/chest/resourcepack \
  --pack-mcmeta

# stairs（t12）
python3 package_asset.py \
  --template stairs \
  --name stone_brick_stairs \
  --out tests/runs/stone_brick_stairs/resourcepack \
  --pack-mcmeta
```

> 若要覆盖 LLM 生成的 raw_answer，需要先自行准备 `tests/runs/<slug>/raw_answer.txt`（multi-face raw），再加 `--raw <该文件>`；这不是当前可复现的一键链路。

### 5.2 未实现/未纳入通过标准的部分（供后续实现）

暂时记录目标命令（**当前不可直接复现**；其中 retrieval JSON 必须先由外部索引/scan_mc_assets 生成）：

```bash
# A. 先生成 retrieval JSON（需要已有索引；无索引时下述命令会 FAIL，已实测）
# 需要先: python3 scan_mc_assets.py --mc-path <你的Minecraft包路径> --out tests/retrieval/chest_index.json
# 再:     python3 retrieve_assets.py --query "箱子" --top 5 --index tests/retrieval/chest_index.json --out tests/retrieval/chest.json
# 或者:  直接提供/生成 `tests/retrieval/chest.json`（含 anchors/features 的 retrieval JSON）

# B. 生成 block_custom 概念卡（依赖 A 的 retrieval JSON）
# 实测：有合法 retrieval JSON 时，`concept_grounder.py --retrieval ...` 可生成概念卡（exit 0）。
python3 concept_grounder.py \
  --query "箱子" --form block_custom --template chest \
  --retrieval tests/retrieval/chest.json \
  --out tests/runs/chest/concept.json

# C. 生成 raw_answer（当前没有 run_pipeline 一键生成路径；
#        需要后续实现或由人工/外部 LLM 制作，格式为 block_custom 多面 raw）
# 占位：tests/runs/chest/raw_answer.txt

# D. 打包（当 raw_answer 已提供时，在 5.1 命令上加 --raw）
python3 package_asset.py \
  --template chest \
  --raw tests/runs/chest/raw_answer.txt \
  --name chest \
  --out tests/runs/chest/resourcepack \
  --pack-mcmeta
```

楼梯未实现部分的对应命令：

```bash
python3 concept_grounder.py \
  --query "石砖楼梯" --form block_custom --template stairs \
  --retrieval tests/retrieval/stone_brick_stairs.json \
  --out tests/runs/stone_brick_stairs/concept.json
```

> 若后续 `run_pipeline.py` 增加 `--form block_custom`，则统一改为：
> `python3 run_pipeline.py --query "箱子" --form block_custom --top 5 --llm-cmd ... --out tests/runs/chest --package`

## 6. 校验脚本调用

`check_pixel_asset.py` 已由另一 worker 提供（`python3 check_pixel_asset.py --help` 可查看参数；当前版本 v1.0.0）。实际调用采用**位置参数传 PNG**，并输出 JSON 或 Markdown evidence：

```bash
# 单面 16x16 资产（item/cross/block_multi 单面）
python3 check_pixel_asset.py \
  tests/runs/<slug>/sprite.png \
  --expected-size 16x16 \
  --out tests/reports/<slug>.json

# entity_uv（64x32 或 64x64）
python3 check_pixel_asset.py \
  tests/runs/pig/sprite.png \
  --expected-size 64x32 \
  --out tests/reports/pig.json
```

- `block_multi` 需要分别检查 `_top.png` / `_side.png` / `_bottom.png` 三个 16x16 贴图。
- `block_custom` 每个纹理 key 是一张 16x16 PNG，应逐 key 检查。
- 若输出为 `.md`，则 `--out tests/reports/<slug>.md` 会直接生成人类可读 evidence；若输出为 `.json`，保留结构化 metrics。
- 若脚本缺失（当前不存在此情况）：在 `tests/evidence/<slug>.md` 中记 `check_pixel_asset: PENDING`，不要伪造校验结果。

## 7. evidence 模板

每个条目运行后，在 `tests/evidence/<slug>.md` 记录：

```markdown
# <slug> 运行证据

- 命令：`python3 run_pipeline.py ...`（t11/t12 为 `python3 package_asset.py --template ...`）
- 执行日期：YYYY-MM-DD (UTC)
- 仓库 commit：`git rev-parse HEAD`
- form：<item|block_multi|cross|entity_uv|block_custom>
- 产物：
  - `tests/runs/<slug>/sprite.png` / `cross.png` / `*.png`
  - `tests/runs/<slug>/raw_answer.txt`（若为 block_custom 仅打包模板验证，可无）
  - `tests/runs/<slug>/hashes.json`
  - `tests/runs/<slug>/resourcepack/`（--package 时）
- raw_answer sha256：从 `tests/runs/<slug>/hashes.json` 读取
- PNG 尺寸：记录实际尺寸（item/cross 应为 16x16；entity_uv 应为 64x32 或 64x64）
- check_pixel_asset 命令：`python3 check_pixel_asset.py tests/runs/<slug>/sprite.png --expected-size <WxH> --out tests/reports/<slug>.json`
- check_pixel_asset 结果：PASS / FAIL（附 `tests/reports/<slug>.json` 或 `.md`；block_multi/block_custom 逐面记录）
- 观察与问题：...
```

## 8. 通过标准（供 t4/check worker 使用）

- 每条命令 exit code = 0。`run_pipeline` 条目还需 `PIPELINE: PASS`；`block_custom` t11/t12 按 §5.1 的 `package_asset` 命令只需 `OK: packaged ...` 且 `VALIDATE: PASS`。
- `raw_answer.txt` 存在且非空；`hashes.json` 的 `answer_sha256` 与文件一致（**仅适用于有 `raw_answer` 的条目**；t11/t12 按 §5.1 仅做 package template 打包时，不要求 raw_answer/concept）。
- 输出 PNG 尺寸与 form 契约一致：
  - `item` / `block_multi` / `cross`：16x16
  - `entity_uv`：64x32 或 64x64
  - `block_custom`：每个纹理 key 16x16（由 `package_asset` 校验，占位纹理同样满足）
- `--package` 时资源包 manifest/blockstate/model 存在且 `package_asset` 语义校验通过。
- 记录 `tests/evidence/<slug>.md`，不得用项目 `examples/` 产物代替。
