# check_pixel_asset 使用说明

`check_pixel_asset.py` 是通用 16x16 像素资产检查器，用于在生成流程后输出可复现的
像素级 evidence：非空、bbox、描边/外轮廓暗色、亮度色阶、部件分离启发式。脚本不绑定
任何具体物品名或形状，只依赖 Pillow 与 Python 标准库。

## 快速开始

```bash
# 直接查看终端摘要
python3 check_pixel_asset.py examples/alien_crystal_wand/sprite.png

# 输出 JSON evidence
python3 check_pixel_asset.py examples/alien_crystal_wand/sprite.png \
    --out examples/check-evidence/alien_crystal_wand.json

# 输出 Markdown evidence
python3 check_pixel_asset.py examples/mushroom_sprout/cross.png \
    --out examples/check-evidence/mushroom_sprout_cross.md

# 合成图自测
python3 check_pixel_asset.py --self-test
```

## 检查项

| 检查项 | 默认判定 | 可调参数 |
|---|---|---|
| `non_empty` | 不透明像素数 >= 20 | `--opaque-min` |
| `size` | 尺寸为 16x16 | `--expected-size` |
| `bbox` | 剪影四周至少 1px 透明 | `--min-margin` |
| `border` | 外轮廓暗色像素占比 >= 0.15，且外轮廓像素 >= 2 | `--border-dark-lum`、`--min-border-dark-ratio`、`--min-border-px` |
| `palette` | 暗色桶 >= 2、亮色桶 >= 2、主色出现次数 >= 2 | `--dark-lum`、`--bright-lum`、`--min-bucket-px`、`--min-main-px` |
| `part_separation` | 默认仅报告；`--require-separation` 时要求连通块 >= 2 | `--min-components` |
| `thin_part` | 默认仅报告；`--require-thin-part` 时要求 bbox 长边 >= 10 且 opaque_ratio <= 0.5 | `--thin-min-bbox-px`、`--thin-ratio` |

所有检查均输出证据指标，不读取/依赖物品名称、概念卡或 LLM 私有模型。

## 输出的关键指标

- `opaque_count` / `opaque_min`：非空像素数与阈值。
- `bbox` / `bbox_area` / `opaque_ratio`：剪影包围盒、包围盒面积、bbox 内不透明覆盖率
  （`opaque_count / bbox_area`；用于负空间/镂空程度量化，例如弓类细长资产应显著低于 1.0）。
- `margins`：剪影四周透明边距。
- `boundary_pixel_count` / `boundary_dark_ratio`：外轮廓像素数、暗色边界占比。
- `boundary_vs_all_delta`：外轮廓平均亮度与全体平均亮度之差（负值表示边界偏暗）。
- `palette`：dark/mid/bright 分桶数量、主色 RGBA 与占比。
- `component_count` / `component_sizes`：4-连通非透明分量数量与大小。
- `thin_part` / `thin_ok`：细长部件/负空间启发式；当 bbox 较大但 `opaque_ratio` 较低时判定为细长/镂空，可用于弓类资产。
- `verdict.overall`：`PASS` / `FAIL`。CLI 会在 `FAIL` 时返回退出码 `1`，`PASS` 时返回 `0`。

## 可复现命令

```bash
cd /tmp/mc-mod-art-studio-core

# 冒烟检查两个示例并生成 evidence
python3 check_pixel_asset.py --help
python3 check_pixel_asset.py examples/alien_crystal_wand/sprite.png \
    --out examples/check-evidence/alien_crystal_wand.json
python3 check_pixel_asset.py examples/alien_crystal_wand/sprite.png \
    --out examples/check-evidence/alien_crystal_wand.md
python3 check_pixel_asset.py examples/mushroom_sprout/cross.png \
    --out examples/check-evidence/mushroom_sprout_cross.json
python3 check_pixel_asset.py examples/mushroom_sprout/cross.png \
    --out examples/check-evidence/mushroom_sprout_cross.md

# 单元测试
python3 -m unittest discover -s tests -v
```

## 设计假设

1. 不透明判定阈值为 alpha > 8，与 `text_to_texture.py` 的 `ALPHA_THRESHOLD` 一致。
2. 亮度采用 Rec.709 加权；暗色/亮色分桶默认 `<80` / `>=160`。
3. 描边启发式采用“外轮廓像素中暗色占比”，不是物体识别，因此对没有刻意描边的
   资产可能给出 FAIL，需要按资产风格调整阈值。
4. 部件分离默认不作为 PASS/FAIL 门槛，因为许多单件物品（法杖、单块蘑菇）本应只有
   一个连通块；需要“必须多部件”时可显式传入 `--require-separation`。
