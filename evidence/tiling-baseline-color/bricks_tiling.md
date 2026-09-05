# Tiling Check: bricks

> **免责声明**：本文件为 `--allow-transparent` 的“仅颜色对照”结果，只比较 RGB 颜色、不检查边缘不透明度；**不代表严格可用性**。在严格模式（block_multi 的 top/side/bottom 必须是 16x16 全不透明且边缘连续）下，对应的 `tiling-baseline/` 结果为 FAIL。

- Tool: `check_tiling.py`
- Images: top=`tests/runs/v2/bricks/resourcepack/assets/demo/textures/block/q_7ea27816_top.png`, side=`tests/runs/v2/bricks/resourcepack/assets/demo/textures/block/q_7ea27816_side.png`, bottom=`tests/runs/v2/bricks/resourcepack/assets/demo/textures/block/q_7ea27816_bottom.png`
- Size: `16x16`
- Threshold: 32 (RGB max channel diff)
- Require opaque edges: no
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
