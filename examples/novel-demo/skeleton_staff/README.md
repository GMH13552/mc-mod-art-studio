# 骷髅法杖 (Skeleton Staff)

- 形式：`item`
- 尺寸：`16x16`
- 输出：`sprite.png`
- novelty：`0.75`（部件级参考映射，禁逐像素复制）

## 说明
一根顶端镶着骷髅头的新法杖/权杖：上方是骨白色、带深色眼窝的骷髅头，下方是木质杖身/握柄；整体是“法杖”而不是骷髅怪物。

## 部件级参考来源表

| 部件 | 参考原版资产 | 原版参考 hash (md5) | borrowed_texture | borrowed_palette | borrowed_structure | 不借什么 |
|---|---|---|---|---|---|---|
| 骷髅头/眼窝 | skeleton.png (head region) + bone_block_side.png | skeleton.png=88910a4a570d759c9cc22ea557936ba3<br>bone_block_side.png=da8f5260eee6417c6c9b62e4ef5de5e7 | 骨白底、深色眼窝、骨裂纹/凹槽质感 | base=#E9E6D4 light=#FFFFFD dark=#CBC6A5 accent=#DBD8C6 outline=#2E2E2E | 杖顶骨白头骨、眼窝位于中上部、左右对称 | 不借 skeleton 全身/动画/武器，不复制骨架纹理；只取头部语义 |
| 连接插座 | bone_block_side.png / stick.png | bone_block_side.png=da8f5260eee6417c6c9b62e4ef5de5e7<br>stick.png=ccd09839f4d1c71729bd222884e8f7dd | 暗色小口/环、骨质接缝 | base=#7B7E6B light=#CBC6A5 dark=#494949 accent=#493615 outline=#2E2E2E | 骷髅头下的 1-2px 暗色小口/环 | 不借方块/骨头物品外形 |
| 杖身/握柄 | stick.png / oak_planks.png | stick.png=ccd09839f4d1c71729bd222884e8f7dd<br>oak_planks.png=2b7c6bc281025a86308a0331623bb2d6 | 木纹纵向、少量磨损颗粒 | base=#493615 light=#896727 dark=#281E0B accent=#684E1E outline=#281E0B | 1-2px 宽木杖、底部可加粗握柄 | 不借木棍单独物品、不借剑/火炬形状 |

> 参考来源均为本机 1.18.2 Java 完整库（full-index.json），原版 PNG 未复制进本仓库。

## 部件配色卡（palette 按部件拆）

| 部件 | 配色卡 | 说明 |
|---|---|---|
| 骷髅头/眼窝 | base=#E9E6D4 light=#FFFFFD dark=#CBC6A5 accent=#DBD8C6 outline=#2E2E2E | 骨白/骨灰：米白底，亮部近纯白，暗部暖灰；眼窝用深灰/黑灰，不出现彩度。 |
| 连接插座 | base=#7B7E6B light=#CBC6A5 dark=#494949 accent=#493615 outline=#2E2E2E | 连接口用骨灰/深灰绿过渡，少量深褐木色，避免与骷髅头同色糊在一起。 |
| 杖身/握柄 | base=#493615 light=#896727 dark=#281E0B accent=#684E1E outline=#281E0B | 木柄棕：主色深棕，亮部木褐，暗部近黑；亮木纹沿纵向走，不与骨白混用。 |

## 生成命令
```bash
# 从仓库根目录运行；LLM key 从 /tmp/mc_llm.env 读取，不写入仓库。
set -a; source /tmp/mc_llm.env; set +a
python3 examples/novel-demo/demo_generate.py
```

## Hash
- prompt sha256：`0866cb630444c131f0c7798d5dd21d10e889f6f9a48cef2f144698909682cfd2`
- answer sha256：`dd6328fd8bed4407d4717eebe9d8ee2e132159d42ea9b08914c7357bccb06d7f`
- png sha256：`dafbdd8306890436544f887c54c3bbacd2c3e801d4a3c612ce62f3da49ab6950`

## 索引相似度检测
- 阈值：`0.8`
- 最高相似参考：`skeleton.png`（score `0.710938`）
- 因高相似度重试次数：`0`
- 检查记录：`[{"attempt": 1, "similarity": 0.710938, "reference": "skeleton", "note": "recorded from committed sprite (post-hoc re-check)"}]`

## 像素自检（check_pixel_asset.py）
- 结论：`PASS`

