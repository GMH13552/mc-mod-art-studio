# entity_uv check: pig

```
FAIL: 不满足标准实体 UV 布局 (entity=pig, size=64x32, opaque=319, regions=3)
```

| 项 | 结果 | 说明 |
|---|---|---|
| 尺寸 | PASS | pig 原版纹理是 64x32 实际=64x32，期望=64x32 |
| 非空 | PASS | opaque_pixels=319 |
| 区域 head | PASS | 期望 0,0 -> 32,16，opaque=159 |
| 区域 body | PASS | 期望 28,8 -> 64,32，opaque=153 |
| 区域 legs | FAIL | 期望 0,16 -> 16,26，opaque=0 |

## 区域占位

| 区域 | 期望坐标 | opaque | 结果 |
|---|---|---|---|
| head | 0,0 -> 32,16 | 159 | PASS |
| body | 28,8 -> 64,32 | 153 | PASS |
| legs | 0,16 -> 16,26 | 0 | FAIL |
