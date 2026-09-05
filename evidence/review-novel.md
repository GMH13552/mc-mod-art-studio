# n4 review：mc-novel-demo 独立终审

- 评审范围：整条 through-line：n1（第一版复盘 + 参考影响 A/B）、n2（4 个原版没有的新资产演示 + 部件级参考）、n3（README/推送）。
- 评审日期：2026-09-05
- 结论：**reject**

> 主体交付物（复盘、A/B 证据、4 个 PNG、README/推送）基本达标，但发现 1 处明确的文档/脚本行为不一致（overclaim），按评审规则判 reject。修复后重新复核可转 pass。

## 1. n1：第一版复盘与参考影响 A/B

**已核验：**

- `docs/first-version-analysis.md` 存在，内容与当前代码一致：
  - `run_pipeline._build_compact_prompt()` 确实没有读取/注入 `style_rules` 与 `features.summary`；
  - `build_style_prompt._build_v2_prompt_text()` 确实仍输出“检索特征摘要”和“风格规则”；
  - 因此“当前一命令管线真实 prompt 丢掉了风格卡和特征摘要”的结论成立。
- A/B 实验证据文件在 `/tmp/n1_with_ref`、`/tmp/n1_no_ref`，且 prompt/raw 哈希与 `docs/reference-influence.md` 记录完全一致：
  - `n1_with_ref` prompt.sha256 `98129c...`、raw.sha256 `c7d188...`
  - `n1_no_ref` prompt.sha256 `7e6950...`、raw.sha256 `0c6b93...`
- Prompt 差异可复现：
  - 默认 prompt：字符数 8651、行数 274（按字符数/wc -m 计），含 `## 原版参考（结构化语法 + 少量片段）`；
  - `--no-original-ref` prompt：字符数 3848、行数 86，原版参考块整块消失。
- 输出差异可复现：
  - 默认版 raw_answer 写“剑沿左上到右下对角线方向延伸”，检查器 `bbox=[0,0,16,16]`、opaque=84、overall FAIL；
  - 关参考版 raw_answer 写“剑沿垂直轴线…剑尖朝上”，`bbox=[5,2,11,15]`、opaque=46、overall PASS。
- Index grid 相似度复算：
  - `n1_with_ref` vs `iron_sword.png`：235/256 = **91.8%**，与文档一致；
  - `n1_no_ref` vs `iron_sword.png`：157/256 = **61.3%**，与文档一致；
  - 两版互相 61.3%，也与文档一致。
- 调色板复算：
  - `n1_with_ref` 7 色全部存在于原版 `iron_sword.png` 调色板（实际上是 **7/7**，文档写 6/7，属于轻微低估）；
  - `n1_no_ref` 7 色中 5 色与原版重合，缺 `#896727`，新增 `#2E2E2E`/`#7A7A7A`，与文档一致。

**结论：** n1 的复盘和 A/B 影响验证成立；仅发现一处非阻断的数值低估（6/7 实际为 7/7）。

## 2. n2：4 个原版没有的新资产演示

**已核验：**

- `examples/novel-demo/` 下 4 个资产目录齐全：`villager_hide/`、`skinning_knife/`、`skeleton_staff/`、`demon_cow/`。
- 4 张 `sprite.png` 均存在、非空、16×16 RGBA、可看：

| 资产 | 尺寸 | 非透明像素 | bbox | 视觉可辨认性 |
|---|---|---|---|---|
| 村民皮 Villager Hide | 16×16 | 124 | `[2,1,13,15]` | 橙棕皮革主体 + 灰色织物内衬，可辨认 |
| 剥皮小刀 Skinning Knife | 16×16 | 99 | `[4,1,12,15]` | 短刀刃 + 皮革/木柄，可辨认 |
| 骷髅法杖 Skeleton Staff | 16×16 | 74 | `[3,1,12,15]` | 骨白骷髅头 + 木杖，可辨认 |
| 恶魔牛 Demon Cow | 16×16 | 158 | `[1,1,15,15]` | 红牛头 + 黑色角/青色魂火，可辨认 |

- 4 个 prompt 均包含“部件级参考映射”表：`borrowed_texture` / `borrowed_palette` / `borrowed_structure` / `不借什么`，且配色按部件拆分。
- 4 个 prompt **未包含任何原版 compact 索引网格**；grep 只命中输出格式中的 `PALETTE + INDEX GRID` 和“禁止复制索引网格”的提示，没有把原版 compact 文本注入参考层。
- 所有 prompt/answer/png sha256 与各资产 `README.md`、`hashes.json` 一致。
- 所有原版参考 md5 与 `mc_asset_library_full/full-index.json` 核对一致（leather、soul_fire_0、skeleton、villager、bone_block_side、cow、red_mooshroom、stick、oak_planks、iron_sword）。
- 仓库内未发现把原版 PNG 复制进来；`git ls-files '*.png'` 只包含 examples 下的演示/示例图。

**发现的问题：**

1. **overclaim（阻断）**：`examples/novel-demo/README.md` 写“若模型输出与原版索引网格高度重合，重试并记录（脚本最多重试 2 次）”。但 `examples/novel-demo/demo_generate.py` 的重试逻辑只在空回答/解析失败/尺寸错误/0 不透明像素等异常时重试，并没有与原版索引网格做相似度比对，也没有记录“高度重合”事件。文档描述的防复制保护机制在脚本中不存在，属于明确的功能性 overclaim。
2. `villager_hide/sprite.png` 的 `check_pixel_asset.json` 记录 `overall: FAIL`，原因是 `bright_count=0`（调色板缺少亮色档）。图片仍可看，但这意味着 4 个演示中有一个未通过自身的像素质量检查。
3. `examples/novel-demo/README.md` 称“完整 `skeleton.png`/`villager.png` 等不在 115 小库内”，实际 `library-index.json`（115 小库）包含 `skeleton.png` 和 `villager.png`；这句来源说明不准确（真正不在小库的是 `leather.png`、`soul_fire_0/1.png`、`bone_block_side.png` 等）。

**结论：** 4 个新资产本身存在且可看、部件级参考卡完整、哈希可信；但 README 关于“高重合自动重试”的说明与脚本实际行为不符，构成 overclaim，因此本次不能判 pass。

## 3. n3：README / 推送

**已核验：**

- 本地 `HEAD` = `931be0c6ff80729058fc40c7ee74b7bd235f9c2a`。
- `git ls-remote origin refs/heads/main` = `931be0c...`。
- `gh api repos/GMH13552/mc-mod-art-studio/commits/931be0c` 返回 same sha，commit message 为 `n3: novel-demo showcase ...`，即远程 HEAD 确认为 931be0c。
- 工作树干净（`git status --short` 为空）。
- `README.md` 效果图 4 张均指向 `examples/novel-demo/*/sprite.png`，文件实际存在；不是 reset-demo 或其他示例。
- 仓库结构、新增文件均已被 `git` 跟踪，`git ls-files examples/novel-demo` 包含全部 4 个资产生成物与 README。
- 本次评审未 push、未修改代码。

**结论：** n3 的 README/推送状态本身核验通过；唯一残留的是 n2 中的 README 内容 overclaim。

## 4. 最终 verdict

**reject**。

- 核心成功标准（第一版复盘、参考影响 A/B、4 个新资产演示、README/仓库同步、远程 HEAD 推送）在事实层面基本已经满足。
- 但 `examples/novel-demo/README.md` 对 `demo_generate.py` 的“高重合自动重试并记录”描述不实，属于 overclaim。
- 建议修复：要么在脚本中实现原版索引网格相似度检测+重试+记录，要么把 README 该句改为“脚本仅在异常/解析失败时最多重试 2 次；未做原版索引网格相似度自动检测”。同时可顺手修正：
  - `docs/reference-influence.md` 中 with_ref 与原版调色板重合数（6/7 → 7/7）；
  - `examples/novel-demo/README.md` 的 115 小库范围说明（skeleton/villager 在小库内）；
  - `villager_hide` 的 check FAIL 状态说明或补足亮色档。
