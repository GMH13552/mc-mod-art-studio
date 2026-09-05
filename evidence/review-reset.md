# q5 review：mc-quality-reset 独立终审

- 评审范围：通过全仓库交付物核验 reset/cleaning/README 这一条 through-line，不逐项核对任务清单。
- 评审日期：2026-09-05
- 结论：**pass**

## 1. 原版参考恢复

- `run_pipeline.py --query 弓 --form item --index .../library-index.json --prompt-only`
  实际输出包含：
  - `## 原版参考（结构化语法 + 少量片段）`
  - `> 借鉴但不照抄：形状/纹理/配色可按需要修改。`
  - `> 禁止逐像素复制；只学习以下配色家族/材质签名/结构hint/UV 区域等“参考语法”。`
  - `### 原版参考片段`，其中附有原版 compact 文本（Silhouette/Palette 区块），并非只有摘要。
- `--novelty 0.85` 时保留结构化参考语法但不再附 compact 片段；`--no-original-ref` 时整个参考块消失。参数行为与 README/docs 描述一致。
- `reference_analyzer.py` 提供 `analyze_compact` / `render_reference_block` / `decide_reference_include`，且自测可运行。

## 2. 4 张 reset-demo 演示图

`examples/reset-demo/` 下 4 张 PNG 均存在且非空：

| 文件 | 尺寸 | 非透明像素/总像素 | 可看性 |
|---|---|---|---|
| `bow.png` | 16×16 | 60/256 | 棕色弓形，可辨认 |
| `bricks.png` | 392×128 | 50176/50176 | 三面红砖合成预览，纹理清楚 |
| `creeper.png` | 64×32 | 784/2048 | 绿色苦力怕脸/身体，标准实体 UV |
| `pig.png` | 64×32 | 483/2048 | 粉色猪形，标准实体 UV |

与可用的原版 `bricks.png` / `creeper.png` / `pig.png` 做像素比较：bricks 是合成预览（尺寸不同），creeper/pig 尺寸相同但像素差异很大，未发现逐像素复制原版贴图。

## 3. 仓库清理

- `git status --short` 为空；工作树干净。
- `git ls-files` 共 76 个文件；无 evidence/、无 tests/results、无旧 showcase、无 audit_generation.py、无 fix_bow.py 等 q4 清理掉的产物。
- 跟踪的 PNG 仅 `examples/` 下 6 张演示/示例图，未包含原版 Minecraft 贴图。
- `.gitignore` 已覆盖 `__pycache__/`、`*.pyc`、`generated/` 等本地产物。

## 4. README

- README 共 184 行，中文，结构完整：定位 → 工作流概念 → 快速开始 → 常用参数 → 效果图 → 核心模块 → 自检 → 仓库结构。
- 4 个图片引用均指向 `examples/reset-demo/*.png`，文件实际存在，无缺失引用。
- 内容与代码基本一致：`--novelty` / `--no-original-ref` / `reference_block`、模块表、自检命令均真实存在。
- `python3 -m unittest discover -s tests -v` 10/10 通过；`python3 reference_analyzer.py` 自测通过。

## 5. 非阻塞 gap / 备注

- `examples/reset-demo/` 只保留最终 PNG 和 README，未附带对应 raw_answer/prompt_pack/validator 报告；因此“均由 `run_pipeline.py --novelty 0.5` 生成”在当前仓库树内不能独立复现，只能由历史提交/此前 evidence 佐证。这不是本次 acceptance 的阻断项（验收只要求 4 张 PNG 存在且非空），但若未来要长期审计生成 provenance，建议补一份轻量 manifest。
- 本次终审只读并做 prompt-only 验证，未 push、未修改代码；为验证临时产生的 `generated/` 已清除。

## Verdict

**pass**：原版参考已恢复，4 张演示图存在且可看，仓库已清理，README 通顺配图且无引用缺失。overclaim 检查未发现与代码/仓库状态冲突的实质夸大部分；仅有“演示图 provenance 不可在当前树复现”的轻微可审计性 gap。
