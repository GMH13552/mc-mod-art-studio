# entity_uv check: pig

```
PASS: 符合标准实体 UV 布局 (entity=pig, size=64x32, opaque=858, regions=3, margins={'left': 4, 'top': 4, 'right': 15, 'bottom': 0} margins_lt_1=bottom)
```

| 项 | 结果 | 说明 |
|---|---|---|
| 尺寸 | PASS | pig 原版纹理是 64x32 实际=64x32，期望=64x32 |
| 非空 | PASS | opaque_pixels=858 |
| 画布边距 | PASS | margins={'left': 4, 'top': 4, 'right': 15, 'bottom': 0} (atlas 左右至少 1px；顶/底为说明项)；bottom 边距不足 1px（说明：atlas 不强制，仅在证据中标注） |
| 区域 head | PASS | 期望 0,0 -> 32,16，opaque=336 |
| 区域 body | PASS | 期望 28,8 -> 64,32，opaque=310 |
| 区域 legs | PASS | 期望 0,16 -> 16,26，opaque=48 |

## 画布边距

| 边 | 边距(px) | 要求 |
|---|---|---|
| left | 4 | atlas 硬性 >= 1 |
| top | 4 | 说明项 |
| right | 15 | atlas 硬性 >= 1 |
| bottom | 0 | 说明项 |

## 区域占位

| 区域 | 期望坐标 | opaque | 结果 |
|---|---|---|---|
| head | 0,0 -> 32,16 | 336 | PASS |
| body | 28,8 -> 64,32 | 310 | PASS |
| legs | 0,16 -> 16,26 | 48 | PASS |
