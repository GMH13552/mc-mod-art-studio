# Pixel Asset Check Evidence

- Tool: `check_pixel_asset.py` v1.0.0
- Input: `examples/alien_crystal_wand/sprite.png` (16x16)
- Verdict: **PASS**

## Checks

- **non_empty** [PASS]: 不透明像素数 >= 20  
  - opaque_pixels=57 threshold=20
- **size** [PASS]: 尺寸为 16x16  
  - size=16x16
- **bbox** [PASS]: 剪影 bbox 四周至少 1px 透明  
  - bbox=[1, 1, 15, 15] margins={'left': 1, 'top': 1, 'right': 1, 'bottom': 1}
- **border** [PASS]: 外轮廓存在足够暗色描边像素（暗色边界占比 >= 0.15）  
  - boundary_pixels=38 dark_boundary=27 ratio=0.7105
- **palette** [PASS]: 调色板同时含暗色/亮色/主色  
  - dark=26 mid=20 bright=11 dominant=[62, 143, 132, 255] count=11
- **part_separation** [INFO]: 部件分离为启发式报告（未用 --require-separation 纳入判定）  
  - components=1 sizes=[57]

## Metrics

| Metric | Value |
|---|---|
| opaque_count | 57 |
| opaque_min | 20 |
| size | 16x16 |
| bbox | [1, 1, 15, 15] |
| margins | {'left': 1, 'top': 1, 'right': 1, 'bottom': 1} |
| boundary_pixel_count | 38 |
| boundary_dark_count | 27 |
| boundary_dark_ratio | 0.7105 |
| boundary_vs_all_delta | -10.31 |
| palette | dark=26 mid=20 bright=11 |
| dominant_color | [62, 143, 132, 255] |
| component_count | 1 |
| component_sizes | [57] |
| separation_ok | None |

## Notes

- 本检查为通用像素启发式，不绑定具体物品名或形状。
- `part_separation` 默认仅报告；用 `--require-separation` 才会纳入 verdict。
- 阈值可通过 CLI 参数调整，产生可复现的证据文件。
