# mc-mod-art-studio

用**纯文本 LLM**（不需要多模态/看图）生成 Minecraft 自定义美术资源：16x16 item、方块多面、十字 cross、实体 UV 等。

工作原理：把贴图序列化成 `W/H + PALETTE + INDEX GRID` 文本，LLM 读文本、按格式输出像素答案，再转 PNG 并打包成资源包。

## 快速开始

```bash
# 1) 安装依赖（只需要 Pillow）
pip install pillow

# 2) 配置 LLM（用你自己的 API key；不配置也能用现成示例跑通）
cp .env.example .env
# 编辑 .env：设置 LLM_API_KEY=sk-xxx（可选 LLM_BASE_URL / LLM_MODEL）
set -a; source .env; set +a

# 3) 一键运行
#    方式 A：直接用示例 raw_answer（不调用 LLM，离线可跑）
python3 run_pipeline.py --query "异形水晶法杖" --form item \
    --raw examples/alien_crystal_wand/raw_answer.txt \
    --out out/alien_crystal_wand

#    方式 B：调用 LLM 生成新资源
python3 run_pipeline.py --query "异形水晶法杖" --form item --top 5 \
    --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' \
    --out out/alien_crystal_wand

#    方式 C：顺手打包成 Minecraft 资源包
python3 run_pipeline.py --query "异形水晶法杖" --form item \
    --llm-cmd 'python3 llm_client.py --prompt-file {prompt_file}' \
    --out out/alien_crystal_wand --package

# 4) 查看产物
ls out/alien_crystal_wand/                 # sprite.png / prompt_pack.json / raw_answer.txt
ls out/alien_crystal_wand/resourcepack/    # --package 时生成
```

## LLM 配置

`llm_client.py` 兼容任意 OpenAI `chat/completions` 接口，通过环境变量提供密钥与模型：

```bash
export LLM_API_KEY=sk-xxxx
export LLM_BASE_URL=https://opencode.ai/zen/go/v1
export LLM_MODEL=deepseek-v4-flash
```

（如果你的服务商不是 opencode-go，把 `LLM_BASE_URL` / `LLM_MODEL` 换成它的地址和模型名即可；`.env` 示意见 `.env.example`。）

## 常用参数

| 参数 | 作用 |
|---|---|
| `--query` | 你的想法，例如 “异形水晶法杖”“蘑菇幼苗” |
| `--form` | `item` / `block_multi` / `cross` / `entity_uv` / `auto` |
| `--top` | 检索参考节点数 `1..8`（默认 3） |
| `--mc-path` | 扫描你的 Minecraft/资源包目录，用你本机的素材做参考 |
| `--index` | 用之前 `scan_mc_assets.py` 生成的索引 |
| `--raw` | 用现成 raw_answer.txt，跳过 LLM |
| `--llm-cmd` | 调用外部 LLM 命令，支持 `{prompt}` / `{prompt_file}` |
| `--package` | 同时打包资源包 |
| `--out` | 输出目录 |

## 设计流程

`run_pipeline.py` 自动完成：

```
扫描/索引 → 检索参考节点(1..8) → 语义概念卡 → 提示包 → LLM 输出像素文本 → PNG → 资源包
```

生成时模型会先被要求“理解这个物体是什么”，再设计：

- 配色方案（主色/亮部/暗部/描边色/饱和度）
- 形状图样（每个部件的形状 → 纹样沿形状结构走向）
- 参考节点（多个，作为设计参考，不是硬性指标）

## 示例

![showcase](showcase.png)

- `examples/alien_crystal_wand/`：顶部水晶簇法杖（低饱和青绿 + 深色描边 + 纵向棱面高光）。
- `examples/mushroom_sprout/`：cross 形式的小蘑菇（内容=蘑菇本体，不是树苗）。

## 自检

```bash
python3 scan_mc_assets.py --self-test
python3 retrieve_assets.py --self-test
python3 concept_grounder.py --self-test
python3 build_style_prompt.py --self-test
python3 compose_asset.py --self-test
python3 package_asset.py --self-test
```