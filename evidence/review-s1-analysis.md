# s1-analysis 评审报告

- 评审人：reviewer
- 任务：s1-analysis（形状问题诊断与轮廓基础方案）
- 结论：**pass**

## 核对内容

1. **四项根因记录**
   - `docs/shape-problem-analysis.md` 第 2 节明确列出：
     - 缺点 ①：无轮廓基础选择（silhouette bank 缺失）
     - 缺点 ②：恶魔牛被当 item（form 选错）
     - 缺点 ③：借鉴要么过缩、要么过抄
     - 缺点 ④：头/柄/刀/皮不像
   - 每项均包含表现、根因、证据。

2. **silhouette bank 方案**
   - 第 3 节定义 silhouette bank（轮廓基础候选），要求每个部件返回 2-4 个候选（`shape token` 或 `silhouette compact fragment`）。
   - 第 3.4 节明确规定 prompt 中写入“可选一个 / 可组合多个 / 可大改形状 / 禁止逐像素复制”。
   - 第 3.6 节对 demon_cow 提出 `form=entity_uv`、`size=64x32` 的专项修正。

## 抽查

- 抽查 `examples/novel-demo/*/prompt.txt` 与 `concept.json` 中仅有 `borrowed_structure` 文字描述，未发现 `silhouette_candidates` / 部件轮廓候选字段。
- 该抽查与文档第 1.1 / 2.1 节的现状描述一致，属于“现状”而非本任务交付缺项；实际改造属 s2-shape / s3-rebuild 范围。

## 结论

- 文档完整记录四项根因，并给出轮廓基础候选 + 可挑选/可组合/可大改方案的落地路径。
- 满足 acceptance；无阻断 gap。
- 后续需确认 s2-shape 是否把 2-4 个轮廓基础真正实现进 prompt（非本次评审范围）。
