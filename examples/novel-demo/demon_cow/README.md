# 恶魔牛 (Demon Cow)

- 形式：`item`
- 尺寸：`16x16`
- 输出：`sprite.png`
- novelty：`0.75`（部件级参考映射，禁逐像素复制）

## 说明
一个恶魔化牛头/牛图标：正面牛头，红色恶魔皮肤，黑色角/眼窝，眼睛和角尖带青色魂火；保留牛/红魔菌牛的剪影语义，但整体是新物品图标。

## 部件级参考来源表

| 部件 | 参考原版资产 | 原版参考 hash (md5) | borrowed_texture | borrowed_palette | borrowed_structure | 不借什么 |
|---|---|---|---|---|---|---|
| 牛头 | cow.png / red_mooshroom.png | cow.png=64e4fcacfe84ee63b91898364c883d40<br>red_mooshroom.png=00fbc3ceee0959ddcabd3f43355ce6e4 | 红黑皮肤、鼻梁高光、脸颊暗部 | base=#A00F10 light=#E04A45 dark=#3A0708 accent=#940E0F outline=#171414 | 正面牛头剪影、鼻梁纵向、脸颊两侧暗面 | 不借整张 64x32 牛皮肤、不复制原版牛头像素 |
| 双角/耳朵 | cow.png / red_mooshroom.png | cow.png=64e4fcacfe84ee63b91898364c883d40<br>red_mooshroom.png=00fbc3ceee0959ddcabd3f43355ce6e4 | 黑色角/深红耳、角尖可发魂火 | base=#2B0505 light=#5A0A0B dark=#171414 accent=#A00F10 outline=#171414 | 顶部双角、两侧耳朵 | 不借原版角/耳具体像素 |
| 眼睛/鼻口 | red_mooshroom.png + soul_fire_0.png | red_mooshroom.png=00fbc3ceee0959ddcabd3f43355ce6e4<br>soul_fire_0.png=bf4e3e98bc177b997ce91bf6cc9d9ba2 | 黑色眼窝 + 青色魂火 + 暗红鼻口 | base=#01A7AC light=#FFFFFF dark=#018488 accent=#00D5DA outline=#171414 | 两眼左右对称、鼻口在下方 | 不复制整张 soul_fire 火焰贴图 |

> 参考来源均为本机 1.18.2 Java 完整库（full-index.json），原版 PNG 未复制进本仓库。

## 部件配色卡（palette 按部件拆）

| 部件 | 配色卡 | 说明 |
|---|---|---|
| 牛头 | base=#A00F10 light=#E04A45 dark=#3A0708 accent=#940E0F outline=#171414 | 恶魔牛红：主体暗红，亮部红棕高光，暗部黑红；不使用原版普通棕色牛配色。 |
| 双角/耳朵 | base=#2B0505 light=#5A0A0B dark=#171414 accent=#A00F10 outline=#171414 | 角/耳深黑红：比身体更暗，仅用暗红/黑红；不加入青色主色。 |
| 眼睛/鼻口 | base=#01A7AC light=#FFFFFF dark=#018488 accent=#00D5DA outline=#171414 | 魂火青：眼窝内青色发光，亮部白色核心，暗部青蓝；鼻口仍用暗红/黑红，不整体变青。 |

## 生成命令
```bash
# 从仓库根目录运行；LLM key 从 /tmp/mc_llm.env 读取，不写入仓库。
set -a; source /tmp/mc_llm.env; set +a
python3 examples/novel-demo/demo_generate.py
```

## Hash
- prompt sha256：`494e66dac45216c132a60fa1b6ef2619db41c48789ab100ad1b9c1a4e465fc47`
- answer sha256：`79bf3f68c81b057ba8748499e4286965a13f2b22c14a7f63030f2dfbd6efc685`
- png sha256：`cebfc6cdf51e043aba4821cf3f7b9e91097a834785ff327458ea1fc6159d184f`

