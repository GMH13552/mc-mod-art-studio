# entity_uv check: creeper

```
PASS: 符合标准实体 UV 布局 (entity=creeper, size=64x32, opaque=865, regions=3)
```

| 项 | 结果 | 说明 |
|---|---|---|
| 尺寸 | PASS | creeper 原版纹理是 64x32 实际=64x32，期望=64x32 |
| 非空 | PASS | opaque_pixels=865 |
| 区域 head | PASS | 期望 0,0 -> 32,16，opaque=384 |
| 区域 body | PASS | 期望 16,16 -> 40,32，opaque=352 |
| 区域 legs | PASS | 期望 0,16 -> 16,26，opaque=128 |

## 区域占位

| 区域 | 期望坐标 | opaque | 结果 |
|---|---|---|---|
| head | 0,0 -> 32,16 | 384 | PASS |
| body | 16,16 -> 40,32 | 352 | PASS |
| legs | 0,16 -> 16,26 | 128 | PASS |
