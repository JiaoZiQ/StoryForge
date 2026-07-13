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
