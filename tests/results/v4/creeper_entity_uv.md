# entity_uv check: creeper

```
PASS: 符合标准实体 UV 布局 (entity=creeper, size=64x32, opaque=898, regions=3, margins={'left': 1, 'top': 1, 'right': 1, 'bottom': 1})
```

| 项 | 结果 | 说明 |
|---|---|---|
| 尺寸 | PASS | creeper 原版纹理是 64x32 实际=64x32，期望=64x32 |
| 非空 | PASS | opaque_pixels=898 |
| 画布边距 | PASS | margins={'left': 1, 'top': 1, 'right': 1, 'bottom': 1} (atlas 左右至少 1px；顶/底为说明项) |
| 区域 head | PASS | 期望 0,0 -> 32,16，opaque=132 |
| 区域 body | PASS | 期望 16,16 -> 40,32，opaque=300 |
| 区域 legs | PASS | 期望 0,16 -> 16,26，opaque=15 |

## 画布边距

| 边 | 边距(px) | 要求 |
|---|---|---|
| left | 1 | atlas 硬性 >= 1 |
| top | 1 | 说明项 |
| right | 1 | atlas 硬性 >= 1 |
| bottom | 1 | 说明项 |

## 区域占位

| 区域 | 期望坐标 | opaque | 结果 |
|---|---|---|---|
| head | 0,0 -> 32,16 | 132 | PASS |
| body | 16,16 -> 40,32 | 300 | PASS |
| legs | 0,16 -> 16,26 | 15 | PASS |
