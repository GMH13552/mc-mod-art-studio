# entity_uv check: creeper

```
FAIL: 不满足标准实体 UV 布局 (entity=creeper, size=64x32, opaque=44, regions=3)
```

| 项 | 结果 | 说明 |
|---|---|---|
| 尺寸 | PASS | creeper 原版纹理是 64x32 实际=64x32，期望=64x32 |
| 非空 | PASS | opaque_pixels=44 |
| 区域 head | PASS | 期望 0,0 -> 32,16，opaque=44 |
| 区域 body | FAIL | 期望 16,16 -> 40,32，opaque=0 |
| 区域 legs | FAIL | 期望 0,16 -> 16,26，opaque=0 |

## 区域占位

| 区域 | 期望坐标 | opaque | 结果 |
|---|---|---|---|
| head | 0,0 -> 32,16 | 44 | PASS |
| body | 16,16 -> 40,32 | 0 | FAIL |
| legs | 0,16 -> 16,26 | 0 | FAIL |
