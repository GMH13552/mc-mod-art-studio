# Tiling Check: lapis_block

- Tool: `check_tiling.py`
- Images: top=`tests/runs/v3/lapis_block/assets/mcmod/textures/block/q_975291d177f35757_top.png`, side=`tests/runs/v3/lapis_block/assets/mcmod/textures/block/q_975291d177f35757_side.png`, bottom=`tests/runs/v3/lapis_block/assets/mcmod/textures/block/q_975291d177f35757_bottom.png`
- Size: `16x16`
- Threshold: 32 (RGB max channel diff)
- Require opaque edges: yes
- Side order: `north,east,south,west`
- **Overall: `FAIL`**

| Check | Edge | Status | MaxDiff | AvgDiff | TransparentPairs | Detail |
|---|---|---|---|---|---|---|
| side_wrap | - | FAIL | 64 | 8.00 | 0/16 | - |
| top_side | top | PASS | 0 | 0.00 | 0/16 | forward |
| top_side | bottom | PASS | 0 | 0.00 | 0/16 | forward |
| top_side | left | PASS | 0 | 0.00 | 0/16 | forward |
| top_side | right | PASS | 0 | 0.00 | 0/16 | forward |
| bottom_side | top | PASS | 0 | 0.00 | 0/16 | forward |
| bottom_side | bottom | PASS | 0 | 0.00 | 0/16 | forward |
| bottom_side | left | PASS | 0 | 0.00 | 0/16 | forward |
| bottom_side | right | FAIL | 64 | 8.00 | 0/16 | forward |

## 失败原因 / 修复建议

- side_wrap: max_diff=64/32 transparent_pairs=0/16
- bottom_side.right: max_diff=64/32 transparent_pairs=0/16

修复建议：block_multi 的顶/侧/底贴图边缘必须完全不透明，且 side 的左右边一致；若颜色差超阈值，应让同一材质的跨面边缘使用相同的边缘像素（可用 1px 描边/接缝统一）。
