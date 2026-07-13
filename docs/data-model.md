# 数据模型

主键沿用 Milestone 1 的自增整数。SQLite 是默认开发数据库；PostgreSQL 使用同一 SQLAlchemy metadata。

## M4 变化

### `chapters`

M4 使用状态：

```text
generated → evaluating → evaluated_passed
                       ↘ evaluated_needs_revision
                       ↘ evaluation_failed
```

`score` 保存最新完整评估的 0–10 最终分。旧 Evaluation 不因章节状态变化或新尝试失败而删除。

### `evaluations`

在旧评分字段基础上增加：

- `(chapter_id, evaluation_version)` 唯一；版本从 1 递增。
- `status`：`completed` 或 `partial_failed`。
- `mechanical_score`、`critic_score`、`consistency_score`、`overall_score`。
- `pacing_score`、`dialogue_score`、`emotional_impact_score`、`outline_adherence_score`，并保留 prose/plot/character。
- `raw_scores`、`weighted_scores`，用于审计权重前后结果。
- `evaluator_versions`、`prompt_versions`、`config_version`。
- `blocking_reasons`、`recommended_action`、`passed`。
- `provider`、`model`。

旧 M1 评分列的 0–100 数据库约束为兼容已有数据保留；M4 入口和 service 对 M4 分数使用 Pydantic 0–10 约束。

### `evaluation_issues`

一行保存一个机械或 Critic 问题：来源、稳定 code、分类、severity、描述、短 evidence、建议、扣分和小型 metadata。它与 Evaluation 级联删除，但正常业务不会覆盖或删除历史 Evaluation。

### `consistency_conflicts`

保存：Evaluation、项目、章节、冲突类型、severity、subject、双方 evidence、可选历史 fact ID、建议解决方案、置信度、规则 code、状态和时间戳。

状态只有一套：

```text
open | ignored | resolved | false_positive
```

恢复为 `open` 会清空 `resolved_at`；其他状态记录处理时间。

### `characters.knowledge`

人物知识边界使用 JSON 字符串列表，和作者侧 `secrets` 分离。规则引擎只有在 secret 未 reveal、人物不在知识列表、历史中也无获得事件时才报告知识泄漏。这是保守的一版关系表示，不是完整知识图谱。

### `story_rules.structured_metadata`

新增向后兼容 JSON 字段，用于机械匹配，例如：

```json
{
  "location": "city",
  "forbidden_predicates": ["uses_fire"],
  "allows_resurrection": false
}
```

自由文本 `statement` 仍保留；没有结构化 metadata 的规则不会被伪装成确定性机器判断。

## 既有 M3 表

- `projects`：brief、规划结果、目标与状态。
- `characters`、`locations`、`story_rules`：计划世界与人物。
- `chapters`、`chapter_versions`：当前正文与不可变完整版本快照。
- `facts`：subject/predicate/object、来源章节、有效区间、置信度和原文引句。
- `foreshadowings`：setup、预期/实际 payoff 和状态。

## 迁移

- `3d5c121d94ea`：M1 初始领域表。
- `b550a962dc62`：M3 规划/生成字段、状态和 `chapter_versions`。
- `ad6fd0f94186`：M4 Evaluation 明细、EvaluationIssue、Conflict、章节评估状态、人物知识和 StoryRule metadata。

M4 migration 不修改旧 migration。它支持空库 upgrade head，也会为已有 M3 Evaluation 按章、按 ID 回填稳定 `evaluation_version`，并可降级到 base。
