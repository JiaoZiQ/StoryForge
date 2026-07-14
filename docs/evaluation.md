# 章节评估

## MechanicalEvaluator

`MechanicalEvaluationConfig` 集中保存阈值、AI 套话、禁用表达和稳定 code 对应扣分。评分从 10 开始统一扣分并限制到 0–10，规则函数本身不分散计算最终分。

指标：

- `word_count`、`paragraph_count`、`sentence_count`
- `average_sentence_length`、`sentence_length_stddev`
- `dialogue_ratio`
- `repeated_paragraph_count`、`repeated_ngram_ratio`
- `banned_phrase_count`
- `short_paragraph_ratio`、`long_paragraph_ratio`

实现只使用标准库正则、Counter 和 statistics，不依赖分词服务。中文按 CJK 字符、英文按单词做基础计数。

## FactNormalizer

比较前会移除中英文空格和常见标点、大小写归一、规范小数尾零，并映射有限的明确 alias：

- alive/dead、true/false、yes/no、是/否、存活/死亡
- located_at/is_at/location
- owns/carries/possesses
- knows/learned/discovered

未知 predicate 保持保守形式；不会用编辑距离或向量相似度强行合并。原始 FactEvidence 始终保留。

## ConsistencyChecker

十组规则：直接事实冲突、死亡人物行动、地点冲突、知识泄漏、StoryRule、物品状态/持有、时间顺序、关键事件缺失、forbidden reveal、伏笔状态。

每个 Conflict 保存稳定 `rule_code`、severity、subject、新旧 evidence、置信度和建议。低于 `critical_confidence_min` 的匹配不会产生 critical。

## CriticAgent

八个维度均为 0–10：Prose、Plot、Character、Pacing、Dialogue、Emotional impact、Consistency、Outline adherence。

业务校验包括：

- overall 与维度均值不能明显背离。
- severity 只允许 low/medium/high/critical。
- revision priority 必须引用存在的 issue code。
- critical consistency issue 不能建议通过。
- evidence 必须是当前正文里的短片段。
- 空正文拒绝调用。

## EvaluationScorer

默认权重定义在 `EvaluationScoringConfig`，必须包含准确维度并合计为 1。输出同时保存 `raw_scores` 和 `weighted_scores`。

合并后依次应用 high conflict 扣分、critical 封顶、空正文归零和通过门禁。Blocking reasons 是稳定机器码；推荐动作只用于后续人工或 M5 消费。

## 版本与可追溯性

每次尝试新增 Evaluation 版本，记录 Mechanical/Consistency/Scoring 版本、Critic provider/model、Prompt system/user 版本、配置版本和时间戳。Conflict 和 Issue 关联到具体 Evaluation，因此后续规则调整不会改写历史判断。

M5 起，每条 Evaluation 和 Conflict 还关联具体 ChapterVersion；工作流重放使用 Evaluation.idempotency_key 返回已有结果，不能静默新增重复版本。

## RevisionBriefBuilder

RevisionBriefBuilder 以规则排序问题：critical consistency、high consistency、forbidden reveal、outline、character、plot、pacing、prose、mechanical。每轮只选择 3–5 个主要任务，并显式带入 must-preserve accepted facts、forbidden changes、目标字数范围和验收条件。

首轮策略为 `targeted_repair`；上一轮没有改善时切换 `structural_rewrite`，后续有改善但仍需修订时使用 `alternative_approach`。Builder 不调用 LLM，顺序和输出完全确定。

## RevisionAgent

RevisionAgent 通过 `revision.system`/`revision.user` v1 Prompt 接收当前来源版本与结构化 brief，只返回 `RevisedChapterDraft`。输出必须有完整正文、摘要和非空 `changes_made`。Agent 不访问数据库，不覆盖旧版本，也不接收未来章节或未接受事实。

## AcceptanceEvaluator

版本比较规则优先，不只看 overall score：

- 比较 Final、Consistency 和 Outline 三个维度。
- 比较 critical/high 数和 blocking reasons。
- 计算 resolved、unresolved 和 newly introduced issue codes。
- 新增 critical 时禁止接受；新版本满足全部门禁且没有未解决的 high/critical brief 任务时 `accept_new`。
- 提升达到最小阈值但仍阻断时 `keep_old_retry`；变差或无明显提升时保留旧最佳版本并调整策略。
- 达到最大轮次返回 `human_review`。

VersionComparison 保存完整维度、分差、问题变化、decision、confidence 和理由，便于复盘每次接受/拒绝。
