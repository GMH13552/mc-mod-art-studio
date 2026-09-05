# 村民皮 (Villager Hide)

- 形式：`item`
- 尺寸：`16x16`
- 输出：`sprite.png`
- novelty：`0.75`（部件级参考映射，禁逐像素复制）

## 说明
一张被剥下并鞣制的村民皮/兽皮，作为自定义采集材料和掉落物；主体是一块折叠/铺开的皮革，带折痕、颗粒、接缝，边缘露出灰褐色村民长袍织物带与缝线。

## 部件级参考来源表

| 部件 | 参考原版资产 | 原版参考 hash (md5) | borrowed_texture | borrowed_palette | borrowed_structure | 不借什么 |
|---|---|---|---|---|---|---|
| 皮面主体 | leather.png | leather.png=074eb989d8d88e20269414e654152236 | 皮革颗粒、折痕高光、不规则剥制边缘 | base=#C65C35 light=#D76B43 dark=#542716 accent=#9E492A outline=#3D1C10 | 16x16 中央皮面主体、边缘包边、自然折痕 | 不借 leather.png 的物品外形/具体排布 |
| 织物内衬 | villager.png | villager.png=8da291f5374bae0356045285be0f1954 | 村民长袍布料层叠、缝线针脚质感 | base=#6F6D6A light=#817D79 dark=#545353 accent=#636260 outline=#3D2D29 | 皮面下缘/内侧的窄条织物与 1px 缝线 | 不借村民头部/脸/身体/手臂形状，不把整张图画成村民皮肤 |
| 挂环/标签 | stick.png / iron_sword.png | stick.png=ccd09839f4d1c71729bd222884e8f7dd<br>iron_sword.png=d8489670a89dcd89008870e245f75d5f | 深色小环/木质小节颗粒 | base=#493615 light=#896727 dark=#281E0B accent=#684E1E outline=#281E0B | 上缘 2-3px 小环或木牌 | 不借棍/剑形状 |

> 参考来源均为本机 1.18.2 Java 完整库（full-index.json），原版 PNG 未复制进本仓库。

## 部件配色卡（palette 按部件拆）

| 部件 | 配色卡 | 说明 |
|---|---|---|
| 皮面主体 | base=#C65C35 light=#D76B43 dark=#542716 accent=#9E492A outline=#3D1C10 | 皮革棕：主色暖橙棕，亮部偏橙，暗部深红棕，边缘用深褐描边。 |
| 织物内衬 | base=#6F6D6A light=#817D79 dark=#545353 accent=#636260 outline=#3D2D29 | 村民袍灰：低饱和暖灰，亮部稍浅，暗部深灰；缝线用更暗灰绿/深棕分隔。 |
| 挂环/标签 | base=#493615 light=#896727 dark=#281E0B accent=#684E1E outline=#281E0B | 挂环用暗棕木色：主色深棕，亮部木褐，暗部近黑；避免与皮面主色混同。 |

## 生成命令
```bash
# 从仓库根目录运行；LLM key 从 /tmp/mc_llm.env 读取，不写入仓库。
set -a; source /tmp/mc_llm.env; set +a
python3 examples/novel-demo/demo_generate.py
```

## Hash
- prompt sha256：`391e39c2dc1a0bbf58bbd8c2cbf5f5dc2a323c966f3a6ff38a004ce283503d18`
- answer sha256：`127c9ccb238bd8ddfa5b9e891999ddc41442405a78f07c8a5fc788028818e14d`
- png sha256：`d5a07da084a16fe3a2bf47ddfa7445a36fd78eac911c66f2ed2759ceb13456d7`

## 索引相似度检测
- 阈值：`0.8`
- 最高相似参考：`villager.png`（score `0.515625`）
- 因高相似度重试次数：`0`
- 检查记录：`[{"attempt": 1, "similarity": 0.515625, "reference": "villager", "note": "recorded from committed sprite (post-hoc re-check)"}]`

## 像素自检（check_pixel_asset.py）
- 结论：`FAIL`
- 未通过项：`0` 个亮色像素（`bright_count=0` 会判 FAIL），详见 `check_pixel_asset.json`。

