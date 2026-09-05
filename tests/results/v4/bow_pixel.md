# Pixel Asset Check Evidence

- Tool: `check_pixel_asset.py` v1.0.0
- Input: `tests/runs/v4/bow/sprite.png` (16x16)
- Verdict: **PASS**

## Checks

- **non_empty** [PASS]: 不透明像素数 >= 20
  - opaque_pixels=29 threshold=20
- **size** [PASS]: 尺寸为 16x16
  - size=16x16
- **bbox** [PASS]: 剪影 bbox 四周至少 1px 透明
  - bbox=[4, 1, 10, 14] margins={'left': 4, 'top': 1, 'right': 6, 'bottom': 2}
- **border** [PASS]: 外轮廓存在足够暗色描边像素（暗色边界占比 >= 0.15）
  - boundary_pixels=29 dark_boundary=16 ratio=0.5517
- **palette** [PASS]: 调色板同时含暗色/亮色/主色
  - dark=11 mid=5 bright=13 dominant=[220, 220, 180, 255] count=13
- **thin_part** [PASS]: 细长部件/负空间启发式：bbox 较大但 opaque_ratio<=0.50
  - bbox=[4, 1, 10, 14] opaque_ratio=0.3718 thin=True (min_bbox_px=10)
- **part_separation** [INFO]: 部件分离为启发式报告（未用 --require-separation 纳入判定）
  - components=4 sizes=[19, 8, 1, 1]

## Metrics

| Metric | Value |
|---|---|
| opaque_count | 29 |
| opaque_min | 20 |
| size | 16x16 |
| bbox | [4, 1, 10, 14] |
| bbox_area | 78 |
| opaque_ratio | 0.3718 |
| margins | {'left': 4, 'top': 1, 'right': 6, 'bottom': 2} |
| boundary_pixel_count | 29 |
| boundary_dark_count | 16 |
| boundary_dark_ratio | 0.5517 |
| boundary_vs_all_delta | 0.00 |
| palette | dark=11 mid=5 bright=13 |
| dominant_color | [220, 220, 180, 255] |
| component_count | 4 |
| component_sizes | [19, 8, 1, 1] |
| separation_ok | None |
| thin_part | True |
| thin_ratio | 0.50 |
| thin_min_bbox_px | 10 |

## Notes

- 本检查为通用像素启发式，不绑定具体物品名或形状。
- `part_separation` 默认仅报告；用 `--require-separation` 才会纳入 verdict。
- `thin_part` 默认仅报告；用 `--require-thin-part` 才会纳入 verdict。
- 阈值可通过 CLI 参数调整，产生可复现的证据文件。
