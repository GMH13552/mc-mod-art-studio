# s5-review：rebuild-demo 重做演示独立复核

- 评审人：final_reviewer
- 评审范围：整条 through-line —— s1 诊断 / s2 silhouette bank 机制 / s3 重做 4 演示 / s4 README 与推送
- 评审日期：2026-09-05
- 检查目录：`/tmp/mc-mod-art-studio-core`
- 结论：**pass**（含非阻断 gaps）

## 1. 核验方法与动作

本次复核只读执行，未修改任何代码，未 push；仅在 `evidence/` 下新增本复核报告。

- 阅读 `docs/shape-problem-analysis.md`、`docs/silhouette-bank.md`、`docs/workflow-concept.md`、`README.md`。
- 抽查 `examples/rebuild-demo/` 4 张 PNG（非空/尺寸/像素统计/视觉读取）。
- 运行仓库内置自检：`reference_analyzer.py --self-test`、`build_style_prompt.py --self-test`、`check_entity_uv.py --self-test`、`python3 -m unittest discover -s tests -v`。
- 核对 `prompt_pack.json` 中每个部件的 `silhouette_bank` 候选数 2–4。
- 核对 `hashes.json` / `README.md` 中列出的 prompt/answer/png SHA-256。
- 确认本地 HEAD 与远程 HEAD 均为 commit `70d11b2d89c6b4dc14cb7702c74b53ba01cdde13`，工作树干净。

## 2. s1：诊断通过

- `docs/shape-problem-analysis.md` 完整记录四项缺点与根因：
  1. 无轮廓基础选择（silhouette bank 缺失）
  2. 恶魔牛被当 item（form 选错）
  3. 借鉴过缩 / 过抄
  4. 头/柄/刀/皮不像
- 文档同时给出 silhouette bank（2–4 个候选、shape token / X/. 剪影、可挑选/可组合/可大改/禁止当最终网格）与 demon_cow 专项修正（`entity_uv` 64x32）。
- `evidence/review-s1-analysis.md` 已由 reviewer 独立判 pass；本次复核确认该结论与当前仓库内容一致。

## 3. s2：机制实现通过

- `reference_analyzer.py` 存在 `build_silhouette_bank` / `render_silhouette_candidates`，`analyze_compact()` 返回 `silhouette` 与 `silhouette_candidates`。
- `build_style_prompt.py` 会把 `silhouette_bank` 写入 `concept_card.shape_pattern.silhouette_candidates`，并在 prompt 渲染“部件轮廓候选”。
- `run_pipeline.py` 渲染最终紧凑 prompt 时同样包含 `silhouette_candidates`；`--llm-image` 支持多次/逗号分隔多图。
- `llm_client.py --image` 支持多次/逗号分隔；多图进入 OpenAI 兼容 `image_url` 列表。
- `entity_uv_spec.py` 含 cow / red_mooshroom 64x32 标准区域；`check_entity_uv.py --entity cow|red_mooshroom` 可自检。

实测自检：

```text
reference_analyzer self-test: PASS
build_style_prompt self-test: PASS (2 packs, 44 checks passed)
check_entity_uv self-test: PASS
unittest: Ran 12 tests ... OK
```

4 个 `prompt_pack.json` 的 `silhouette_bank` 中，每个部件候选数均为 4（满足 2–4 要求），且每个候选都有 `token` / `source`；1 个或多个候选含 `X/.` compact fragment。

抽查 4 个 `prompt.txt`，均包含：

```text
### 部件轮廓候选 silhouette_candidates（2-4 个/部件）
> 形状候选 = 菜单，不是锁。
> - 可选其中一个；
> - 可组合多个；
> - 可大改形状（加长/加粗/弯曲/变形/换比例都允许）；
> - 禁止把候选当成最终网格/逐像素复制候选剪影。
```

## 4. s3：重做 4 个演示通过

### 4.1 PNG 抽查

| 资产 | 尺寸 | 非透明像素 | bbox（含端点） | 颜色数 | 视觉可辨认性 |
|---|---|---|---|---|---|
| 恶魔牛 `demon_cow/sprite.png` | 64×32 | 1616 | `[1,0,62,31]` | 5 | 红色恶魔牛实体 UV：可见头/角/耳/鼻口/身体/腿/尾，眼窝与角尖有青色魂火点缀 |
| 骷髅法杖 `skeleton_staff/sprite.png` | 16×16 | 52 | `[5,2,10,14]` | 7 | 骨白骷髅头（可辨眼窝/下颌暗示）+ 木色杖柄，整体可辨为法杖 |
| 剥皮小刀 `skinning_knife/sprite.png` | 16×16 | 68 | `[2,2,13,14]` | 8 | 短刀身微上翘 + 深色护手 + 皮革/木柄，明显是小刀而非长剑 |
| 村民皮 `villager_hide/sprite.png` | 16×16 | 107 | `[3,1,12,14]` | 7 | 不规则皮张轮廓，带毛边/折痕/缝线，下缘有灰褐织物内衬，不再是方形/圆形 |

4 张 PNG 均非空、在 16×16/64×32 正确画布内、视觉可读。

### 4.2 自检结果

- `demon_cow`：`check_entity_uv.py sprite.png --entity cow` → **PASS**（size=64x32, opaque=1616, regions=7；左右 1px 边距，顶/底 0 为说明项）。
- `skeleton_staff` / `skinning_knife` / `villager_hide`：`check_pixel_asset.py` → **PASS**（size / bbox / border / palette 均通过）。
- 与各资产 `check_results.json` 记录一致。

### 4.3 哈希与来源说明

- `skeleton_staff`、`skinning_knife` 的 `prompt.txt / raw_answer.txt / sprite.png` SHA-256 与 `hashes.json` 完全一致。
- `demon_cow`、`villager_hide` 的 `prompt_sha256 / png_sha256` 与 `hashes.json` 完全一致；`answer_sha256` 如实记录为 `programmatic-fallback`。
- 各 `README.md` 均记录 部件 → 原版参考 → 借用 texture/palette/structure → 轮廓基础来源 → 改了什么。
- `rebuild-demo/README.md` **诚实披露**：
  - `skeleton_staff` 与 `skinning_knife`：最终 PNG 由文本 LLM 根据带 silhouette bank 的 prompt 生成；
  - `demon_cow` 与 `villager_hide`：文本 LLM 输出不稳定，最终采用程序化模板换色/轮廓底（`cow.png` 64x32 实体轮廓、`rabbit_hide.png` 皮张轮廓），未把原版 PNG 复制进仓库。
  - 这与 s3 验收中“恶魔牛=cow 模板改、村民皮=皮/兔皮轮廓”的允许范围一致，未发现隐藏性 overclaim。

## 5. s4：README 与推送通过

- `README.md` 效果图已改为 `examples/rebuild-demo/*/sprite.png` 4 张，文件实际存在。
- `docs/silhouette-bank.md`、`docs/workflow-concept.md` 已更新 silhouette bank / 实体模板说明。
- 本地 `HEAD` = `70d11b2d89c6b4dc14cb7702c74b53ba01cdde13`。
- `git ls-remote origin refs/heads/main` = 同一 SHA，即远程 HEAD 确认为 `70d11b2`。
- `git status --short` 为空；工作树干净。
- `git show --stat HEAD` 显示本次提交包含 README/docs/机制代码/rebuild-demo 4 个资产/证据/测试，符合 s4 交付。

## 6. 非阻断 gaps / 建议

1. **2 个演示非 LLM 端到端生成**：`demon_cow`、`villager_hide` 最终 PNG 使用程序化模板轮廓 + 新调色板；因此“文本 LLM 看到 silhouette bank 后生成”的完整链路只由 `skeleton_staff`、`skinning_knife` 两张图直接展示。当前 README 已如实说明，且 s3 验收允许“cow 模板改 / 兔皮轮廓”，故不判为阻断。若后续要更完整地证明形状菜单有效性，建议再跑一次更稳定的视觉 LLM（或更强文本模型）生成这两个资产并保留其 prompt/raw/PNG。
2. **主 README 的“均带 silhouette bank”可更精确**：主 README 效果图段落称 4 张均带 silhouette bank；严格说 4 个资产都保存了含 bank 的 prompt，但其中 2 个最终图来自程序化 fallback。`examples/rebuild-demo/README.md` 已澄清；建议主 README 加一行脚注避免读者误以为 4 张都是 LLM 生成。
3. **复现依赖本机绝对路径**：`build_programmatic_demos.py` / `rebuild_generate.py` 通过 `FULL = /mnt/c/Users/.../mc_asset_library_full/textures` 引用本地原版库；仓库不包含原版 PNG，导致其他机器无法无修改复现。这与仓库“不含原版素材”的原则一致，但在审计/复现长线上是已知可审计性 gap。
4. **个别轮廓候选较泛化**：如 `skinning_knife` 的刀柄候选复用了 `iron-sword-blade` 等非柄部 token，`skeleton_staff` 的 socket/fringe 也用了整件 `-shape` 候选。候选数、来源、X/. 剪影均满足验收，但若要让菜单更精准，后续可把“部件 → 候选”的切分再细化。

## 7. Verdict

**pass**。

- s1 诊断、s2 silhouette bank 机制、s3 重做 4 演示、s4 README/推送四条链路环环相扣，均满足任务验收。
- 4 张演示 PNG 真实存在、尺寸正确、可看，且 demon_cow 已是 64×32 实体 UV 并通过 `check_entity_uv`。
- 机制代码、自测、哈希、README 与远程推送状态一致；未发现阻断性 overclaim。
- 上述 gaps 均为可审计性或可改进项，不改变本 through-line 的通过结论。
