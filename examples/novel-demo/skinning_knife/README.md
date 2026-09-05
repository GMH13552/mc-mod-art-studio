# 剥皮小刀 (Skinning Knife)

- 形式：`item`
- 尺寸：`16x16`
- 输出：`sprite.png`
- novelty：`0.75`（部件级参考映射，禁逐像素复制）

## 说明
一把短柄剥皮/狩猎小刀：刀身短小、刀尖略微上翘，刀柄用皮革缠绕并露出木质芯；整体是新物品，不是原版 sword。

## 部件级参考来源表

| 部件 | 参考原版资产 | 原版参考 hash (md5) | borrowed_texture | borrowed_palette | borrowed_structure | 不借什么 |
|---|---|---|---|---|---|---|
| 刀刃 | iron_sword.png | iron_sword.png=d8489670a89dcd89008870e245f75d5f | 金属划痕、刃口高光、冷灰明暗体积 | base=#BEBEBE light=#FFFFFF dark=#444444 accent=#D8D8D8 outline=#181818 | 短小弯曲刀片（非长剑）、刃口高光沿刃线 | 不借 iron_sword 的斜向满画布剑形、不借整把剑的精确索引 |
| 护手/颈 | iron_sword.png / leather.png | iron_sword.png=d8489670a89dcd89008870e245f75d5f<br>leather.png=074eb989d8d88e20269414e654152236 | 深灰/深褐自然分隔 | base=#444444 light=#6B6B6B dark=#181818 accent=#3D1C10 outline=#181818 | 刀刃与刀柄之间的 1-2px 横向窄条 | 不借剑护手完整形状/原版剑柄 |
| 刀柄 | leather.png + stick.png / oak_planks.png | leather.png=074eb989d8d88e20269414e654152236<br>stick.png=ccd09839f4d1c71729bd222884e8f7dd<br>oak_planks.png=2b7c6bc281025a86308a0331623bb2d6 | 皮革缠绳 + 木芯颗粒 | base=#9E492A light=#C65C35 dark=#542716 accent=#896727 outline=#281E0B | 1-2px 宽短柄、缠绳横向、木纹纵向 | 不借 leather/stick 单独物品形状，不复制皮革/木棍像素 |

> 参考来源均为本机 1.18.2 Java 完整库（full-index.json），原版 PNG 未复制进本仓库。

## 部件配色卡（palette 按部件拆）

| 部件 | 配色卡 | 说明 |
|---|---|---|
| 刀刃 | base=#BEBEBE light=#FFFFFF dark=#444444 accent=#D8D8D8 outline=#181818 | 钢铁灰：清冷灰阶，白高光只沿刃口/棱线出现，暗部用深灰；不使用棕色。 |
| 护手/颈 | base=#444444 light=#6B6B6B dark=#181818 accent=#3D1C10 outline=#181818 | 护手用深灰为主，局部深褐过渡到柄；不参与刀刃高光。 |
| 刀柄 | base=#9E492A light=#C65C35 dark=#542716 accent=#896727 outline=#281E0B | 刀柄皮革棕：主色中棕，亮部橙棕，暗部深红棕；木芯用深褐/木纹黄棕点缀。 |

## 生成命令
```bash
# 从仓库根目录运行；LLM key 从 /tmp/mc_llm.env 读取，不写入仓库。
set -a; source /tmp/mc_llm.env; set +a
python3 examples/novel-demo/demo_generate.py
```

## Hash
- prompt sha256：`12062c8269ba8dcd6fd121cf233230ba1f966dafee3a0f637938479db69b9720`
- answer sha256：`389f3ecbb9941967edb660ed86376a8536aa1908ce63340ab78e1c3a7a367813`
- png sha256：`c14fe2b9b092c4b216549f9f6e334759ff75d1786aef65c86e0c7c869dbd6071`

