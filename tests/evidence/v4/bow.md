# bow v4 运行与目检证据（e4-close）

- 日期：2026-09-05 (UTC+8)
- 产物：`tests/runs/v4/bow/sprite.png`（16x16）
- 命令：`python3 fix_bow.py --out tests/runs/v4/bow/sprite.png`
- check_pixel_asset 命令：
  ```bash
  python3 check_pixel_asset.py tests/runs/v4/bow/sprite.png --expected-size 16x16 --require-thin-part --out tests/results/v4/bow_pixel.json
  ```
- 结果：PASS
  - `opaque_count=29`
  - `bbox=[4,1,10,14]`
  - `opaque_ratio=0.3718`
  - `margins={'left':4,'top':1,'right':6,'bottom':2}`
  - `thin_part=True`
- 人工目检：16x16 内左侧为深木色细弧，右侧为浅灰白竖直弦线；弓臂与弦线可辨，
  负空间充足，不是实心团块。
- 备注：该资产为 e4 后处理生成的细弧+弦像素图，非原版素材；原版 `vanilla_entity_ref/` 未入库。
