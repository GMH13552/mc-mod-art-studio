# Tiling Check: glowstone

- Tool: `check_tiling.py`
- Images: top=`tests/runs/v3/glowstone/assets/mcmod/textures/block/q_836777f3_top.png`, side=`tests/runs/v3/glowstone/assets/mcmod/textures/block/q_836777f3_side.png`, bottom=`tests/runs/v3/glowstone/assets/mcmod/textures/block/q_836777f3_bottom.png`
- Size: `16x16`
- Threshold: 32 (RGB max channel diff)
- Require opaque edges: yes
- Side order: `north,east,south,west`
- **Overall: `PASS`**

| Check | Edge | Status | MaxDiff | AvgDiff | TransparentPairs | Detail |
|---|---|---|---|---|---|---|
| side_wrap | - | PASS | 0 | 0.00 | 0/16 | - |
| top_side | top | PASS | 0 | 0.00 | 0/16 | forward |
| top_side | bottom | PASS | 0 | 0.00 | 0/16 | forward |
| top_side | left | PASS | 0 | 0.00 | 0/16 | forward |
| top_side | right | PASS | 0 | 0.00 | 0/16 | forward |
| bottom_side | top | PASS | 0 | 0.00 | 0/16 | forward |
| bottom_side | bottom | PASS | 0 | 0.00 | 0/16 | forward |
| bottom_side | left | PASS | 0 | 0.00 | 0/16 | forward |
| bottom_side | right | PASS | 0 | 0.00 | 0/16 | forward |

## 结论

边缘连续：通过。
