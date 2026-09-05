# Tiling Check: bricks

- Tool: `check_tiling.py`
- Images: top=`tests/runs/v3/bricks/assets/mcmod/textures/block/q_7ea27816_top.png`, side=`tests/runs/v3/bricks/assets/mcmod/textures/block/q_7ea27816_side.png`, bottom=`tests/runs/v3/bricks/assets/mcmod/textures/block/q_7ea27816_bottom.png`
- Size: `16x16`
- Threshold: 32 (RGB max channel diff)
- Require opaque edges: yes
- Side order: `north,east,south,west`
- **Overall: `FAIL`**

| Check | Edge | Status | MaxDiff | AvgDiff | TransparentPairs | Detail |
|---|---|---|---|---|---|---|
| side_wrap | - | PASS | 0 | 0.00 | 0/16 | - |
| top_side | top | FAIL | 116 | 101.50 | 0/16 | forward |
| top_side | bottom | FAIL | 116 | 101.50 | 0/16 | forward |
| top_side | left | FAIL | 116 | 101.50 | 0/16 | forward |
| top_side | right | FAIL | 116 | 101.50 | 0/16 | forward |
| bottom_side | top | PASS | 0 | 0.00 | 0/16 | forward |
| bottom_side | bottom | PASS | 0 | 0.00 | 0/16 | forward |
| bottom_side | left | PASS | 0 | 0.00 | 0/16 | forward |
| bottom_side | right | PASS | 0 | 0.00 | 0/16 | forward |

## 失败原因 / 修复建议

- top_side.top: max_diff=116/32 transparent_pairs=0/16
- top_side.bottom: max_diff=116/32 transparent_pairs=0/16
- top_side.left: max_diff=116/32 transparent_pairs=0/16
- top_side.right: max_diff=116/32 transparent_pairs=0/16

修复建议：block_multi 的顶/侧/底贴图边缘必须完全不透明，且 side 的左右边一致；若颜色差超阈值，应让同一材质的跨面边缘使用相同的边缘像素（可用 1px 描边/接缝统一）。
